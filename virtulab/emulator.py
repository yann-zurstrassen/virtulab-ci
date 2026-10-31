"""Run a firmware image in QEMU (semihosting) or Renode (UART console)."""

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import DEVICES_DIR, MONITOR_MARK, VirtulabError
from .boards import Board
from .build import symbol_addresses

QEMU = os.environ.get("VIRTULAB_QEMU", "qemu-system-arm")
RENODE = os.environ.get("VIRTULAB_RENODE", "renode")

# Harmless QEMU noise on the Stellaris boards.
_NOISE = ("Timer with period zero",)

# Printed by the runtime's vl_exit() on emulators without semihosting.
_EXIT_SENTINEL = re.compile(r"^VIRTULAB_EXIT: (-?\d+)\r?$", re.MULTILINE)

# Runs inside Renode when the CPU reaches vl_sim_hook(command): execute the
# monitor command, log it, and acknowledge before the firmware continues.
_SIM_HOOK = """\
bus = machine.SystemBus
status, command = 2, '?'
try:
    address = int(self.GetRegister(0).RawValue)
    chars = []
    while len(chars) < 512:
        byte = bus.ReadByte(address + len(chars))
        if byte == 0:
            break
        chars.append(chr(byte))
    command = ''.join(chars)
    status = 1 if monitor.Parse(command) else 2
    error = ''
except Exception as e:
    error = ' (%s)' % e
log = open({log!r}, 'a')
log.write('%s %s%s\\n' % ('ok  ' if status == 1 else 'FAIL', command, error))
log.close()
bus.WriteDoubleWord({ack:#x}, status)
"""


# Runs each time the CPU reaches the attacked instruction: resume past it, once.
_SKIP_HOOK = """\
import os
if not os.path.exists({marker!r}) and machine.LocalTimeSource.ElapsedVirtualTime.TotalMilliseconds >= {after_ms!r}:
    open({marker!r}, 'w').close()
    self.PC = type(self.PC).Create({resume:#x}, 32)
"""


@dataclass
class FaultSkip:
    """Skip one instruction: at `at`, resume at `resume`, and leave `marker` as proof it happened."""
    at: int
    resume: int
    marker: Path
    after_ms: float = 0.0  # first execution at or after this virtual time


@dataclass
class RunResult:
    exit_code: int | None  # None when the run timed out
    timed_out: bool
    output: str
    duration: float
    sim_commands: list[str] | None = None  # vl_sim() calls, "ok  cmd" / "FAIL cmd"
    model_warnings: list[str] | None = None  # what the sensor models complained about, "air: message"
    timeout_pc: int | None = None  # where the CPU was when the run timed out (Renode only)


def run(board: Board, elf: Path, timeout: float, work_dir: Path,
        peripherals: str | None = None, skip: FaultSkip | None = None) -> RunResult:
    if board.emulator == "renode":
        return _run_renode(board, elf, timeout, work_dir, peripherals, skip)
    if peripherals:
        raise VirtulabError(
            f"'{board.name}' runs on QEMU, which cannot add peripherals. "
            "Use a Renode board such as stm32f4_discovery."
        )
    return _run_qemu(board, elf, timeout)


def _start(cmd: list[str], stdin=subprocess.DEVNULL, **kwargs) -> subprocess.Popen:
    try:
        return subprocess.Popen(cmd, stdin=stdin, **kwargs)
    except FileNotFoundError:
        raise VirtulabError(f"'{cmd[0]}' not found. Is the emulator installed?") from None


def _run_qemu(board: Board, elf: Path, timeout: float) -> RunResult:
    cmd = [
        QEMU,
        "-M", board.name,
        "-nographic",
        "-monitor", "none",
        "-semihosting-config", "enable=on,target=native",
        "-kernel", str(elf),
    ]
    start = time.monotonic()
    proc = _start(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        raw, _ = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        raw, _ = proc.communicate()
        timed_out = True
    duration = time.monotonic() - start

    output = "\n".join(
        line for line in raw.decode("utf-8", errors="replace").splitlines()
        if not any(noise in line for noise in _NOISE)
    )
    return RunResult(
        exit_code=None if timed_out else proc.returncode,
        timed_out=timed_out,
        output=output,
        duration=duration,
    )


def _renode_script(board: Board, elf: Path, work_dir: Path, peripherals: str | None,
                   uart_log: Path, sim_log: Path, skip: FaultSkip | None = None) -> Path:
    lines = ["using sysbus"]
    if peripherals and ("VirtuLab." in peripherals or (work_dir / "models").is_dir()):
        # Compile the VirtuLab device library (datasheet-accurate models) into Renode.
        lines += [f"include @{model}" for model in sorted(DEVICES_DIR.glob("*.cs"))]
        lines += [f"include @{model}" for model in sorted((work_dir / "models").glob("*.cs"))]
    lines += [
        'mach create "virtulab"',
        f"machine LoadPlatformDescription @{board.platform}",
    ]
    if peripherals:
        description, _, monitor = peripherals.partition(MONITOR_MARK)
        repl = work_dir / "peripherals.repl"
        repl.write_text(description.rstrip() + "\n")
        lines.append(f"machine LoadPlatformDescription @{repl}")
        lines += [cmd for cmd in monitor.splitlines() if cmd.strip()]
    lines += [
        f"sysbus LoadELF @{elf}",
        f"{board.console} CreateFileBackend @{uart_log} true",
    ]
    symbols = symbol_addresses(elf)
    if "vl_sim_hook" in symbols and "vl_sim_ack" in symbols:
        hook = work_dir / "vl_sim_hook.py"
        hook.write_text(_SIM_HOOK.format(log=str(sim_log), ack=symbols["vl_sim_ack"]))
        lines.append(f"cpu AddHook {symbols['vl_sim_hook']:#x} \"execfile('{hook}')\"")
    if skip:
        hook = work_dir / "vl_skip_hook.py"
        hook.write_text(_SKIP_HOOK.format(resume=skip.resume, marker=str(skip.marker), after_ms=skip.after_ms))
        lines.append(f"cpu AddHook {skip.at:#x} \"execfile('{hook}')\"")
    lines.append("start")
    script = work_dir / "run.resc"
    script.write_text("\n".join(lines) + "\n")
    return script


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _renode_error(log: Path) -> str | None:
    """The text of a failed Renode command ("There was an error executing command ..."), if any."""
    if not log.exists():
        return None
    text = _ANSI.sub("", log.read_text(errors="replace"))
    start = text.find("There was an error executing command")
    if start < 0:
        start = text.find("Errors during compilation or loading")  # a model that does not compile
    if start < 0:
        return None
    block = text[start:].split("\n\n")[0].split("[INFO]")[0]
    return block.strip()


_WARNING = re.compile(r"\[WARNING\] ([\w.]+): (.*?)(?: \(\d+\))?\s*$")
_MODEL_NAME = re.compile(r"^(\w+): (?:VirtuLab|Sensors)\.", re.MULTILINE)
_MAX_WARNINGS = 10
_NO_TARGET = re.compile(r"\[WARNING\] (\w+): Child address changed to (0x[0-9a-fA-F]+), but target is not registered")
_DECLARED = re.compile(r"^(\w+): (?:VirtuLab|Sensors)\.\w+ @ (\w+) (0x[0-9a-fA-F]+)", re.MULTILINE)


def model_warnings(log: Path, peripherals: str | None) -> list[str]:
    """Warnings the declared sensor models logged ("air: Read before the measurement is done ..."), once each.

    A model says why it answered the way it did (an early read, an unknown command, a write to a
    read-only register). Those lines sit in Renode's log among platform noise; only lines from a
    module the project declared are kept.
    """
    if not peripherals or not log.exists():
        return []
    description = peripherals.partition(MONITOR_MARK)[0]
    names = set(_MODEL_NAME.findall(description))
    declared = _DECLARED.findall(description)
    found: list[str] = []
    for line in _ANSI.sub("", log.read_text(errors="replace")).splitlines():
        miss = _NO_TARGET.search(line)
        if miss:
            bus, address = miss[1], miss[2]
            here = ", ".join(f"{n} at {a}" for n, b, a in declared if b == bus)
            entry = (f"{bus}: nothing answers at {address}"
                     + (f" (the project declares {here})" if here else " (no module is declared on this bus)"))
            if entry not in found:
                found.append(entry)
            continue
        match = _WARNING.search(line)
        if match and match[1].rsplit(".", 1)[-1] in names:
            entry = f"{match[1].rsplit('.', 1)[-1]}: {match[2]}"
            if entry not in found:
                found.append(entry)
    return found[:_MAX_WARNINGS]


def _read_pc(proc: subprocess.Popen, log: Path) -> int | None:
    """Ask Renode where the CPU is (its console is open on stdin) and read the answer from the log."""
    try:
        size = log.stat().st_size
        proc.stdin.write(b"sysbus.cpu PC\n")
        proc.stdin.flush()
    except (OSError, ValueError):
        return None
    for _ in range(40):
        time.sleep(0.05)
        text = _ANSI.sub("", log.read_bytes()[size:].decode(errors="replace")).replace("\r", "\n")  # Renode ends lines with \r
        match = re.search(r"^0x([0-9a-fA-F]+)\s*$", text, re.MULTILINE)
        if match:
            return int(match[1], 16)
    return None


def _read_log(path: Path) -> str:
    """The text so far. Renode replaces this file as it starts, so it can vanish between two checks."""
    try:
        return path.read_text(errors="replace")
    except FileNotFoundError:
        return ""


def _run_renode(board: Board, elf: Path, timeout: float, work_dir: Path,
                peripherals: str | None, skip: FaultSkip | None = None) -> RunResult:
    work_dir.mkdir(parents=True, exist_ok=True)
    uart_log, sim_log, renode_log = (work_dir / n for n in ("uart.log", "sim.log", "renode.log"))
    for f in (uart_log, sim_log):
        f.unlink(missing_ok=True)
    script = _renode_script(board, elf.resolve(), work_dir, peripherals, uart_log, sim_log, skip)

    start = time.monotonic()
    with open(renode_log, "wb") as log:
        # --console, with stdin kept open, prints the error of a command that fails (a bad platform
        # description, say). --plain hides it and the run just waits for the timeout.
        proc = _start([RENODE, "--disable-xwt", "--console", "--port", "-1", str(script)],
                      stdin=subprocess.PIPE, cwd=work_dir, stdout=log, stderr=subprocess.STDOUT)
        exit_match, timed_out, timeout_pc = None, False, None
        try:
            while True:
                text = _read_log(uart_log)
                exit_match = _EXIT_SENTINEL.search(text)
                if exit_match or proc.poll() is not None:
                    break
                failure = _renode_error(renode_log)
                if failure:
                    raise VirtulabError(f"Renode could not set up the virtual board:\n{failure}")
                if time.monotonic() - start > timeout:
                    timed_out = True
                    timeout_pc = _read_pc(proc, renode_log)
                    break
                time.sleep(0.05)
        finally:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    duration = time.monotonic() - start

    text = _read_log(uart_log)
    sim_commands = sim_log.read_text().splitlines() if sim_log.exists() else []
    if exit_match:
        output = text[:exit_match.start()].rstrip("\n")
        exit_code = int(exit_match[1])
    else:
        output = text.rstrip("\n")
        exit_code = None if timed_out else (proc.returncode or 1)
        if not timed_out:
            # Renode stopped without the firmware exiting: surface why.
            tail = renode_log.read_text(errors="replace").strip().splitlines()[-20:]
            output += "\n[renode exited unexpectedly]\n" + "\n".join(tail)
    return RunResult(exit_code=exit_code, timed_out=timed_out, output=output,
                     duration=duration, sim_commands=sim_commands,
                     model_warnings=model_warnings(renode_log, peripherals), timeout_pc=timeout_pc)
