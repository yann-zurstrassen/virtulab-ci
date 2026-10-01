"""Run a firmware image in QEMU (semihosting) or Renode (UART console)."""

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import DEVICES_DIR, VirtulabError
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


@dataclass
class RunResult:
    exit_code: int | None  # None when the run timed out
    timed_out: bool
    output: str
    duration: float
    sim_commands: list[str] | None = None  # vl_sim() calls, "ok  cmd" / "FAIL cmd"


def run(board: Board, elf: Path, timeout: float, work_dir: Path,
        peripherals: str | None = None) -> RunResult:
    if board.emulator == "renode":
        return _run_renode(board, elf, timeout, work_dir, peripherals)
    if peripherals:
        raise VirtulabError(
            f"'{board.name}' runs on QEMU, which cannot add peripherals. "
            "Use a Renode board such as stm32f4_discovery."
        )
    return _run_qemu(board, elf, timeout)


def _start(cmd: list[str], **kwargs) -> subprocess.Popen:
    try:
        return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, **kwargs)
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
                   uart_log: Path, sim_log: Path) -> Path:
    lines = ["using sysbus"]
    if peripherals and "VirtuLab." in peripherals:
        # Compile the VirtuLab device library (datasheet-accurate models) into Renode.
        lines += [f"include @{model}" for model in sorted(DEVICES_DIR.glob("*.cs"))]
    lines += [
        'mach create "virtulab"',
        f"machine LoadPlatformDescription @{board.platform}",
    ]
    if peripherals:
        repl = work_dir / "peripherals.repl"
        repl.write_text(peripherals.rstrip() + "\n")
        lines.append(f"machine LoadPlatformDescription @{repl}")
    lines += [
        f"sysbus LoadELF @{elf}",
        f"{board.console} CreateFileBackend @{uart_log} true",
    ]
    symbols = symbol_addresses(elf)
    if "vl_sim_hook" in symbols and "vl_sim_ack" in symbols:
        hook = work_dir / "vl_sim_hook.py"
        hook.write_text(_SIM_HOOK.format(log=str(sim_log), ack=symbols["vl_sim_ack"]))
        lines.append(f"cpu AddHook {symbols['vl_sim_hook']:#x} \"execfile('{hook}')\"")
    lines.append("start")
    script = work_dir / "run.resc"
    script.write_text("\n".join(lines) + "\n")
    return script


def _run_renode(board: Board, elf: Path, timeout: float, work_dir: Path,
                peripherals: str | None) -> RunResult:
    work_dir.mkdir(parents=True, exist_ok=True)
    uart_log, sim_log, renode_log = (work_dir / n for n in ("uart.log", "sim.log", "renode.log"))
    for f in (uart_log, sim_log):
        f.unlink(missing_ok=True)
    script = _renode_script(board, elf.resolve(), work_dir, peripherals, uart_log, sim_log)

    start = time.monotonic()
    with open(renode_log, "wb") as log:
        proc = _start([RENODE, "--disable-xwt", "--plain", "--port", "-1", str(script)],
                      cwd=work_dir, stdout=log, stderr=subprocess.STDOUT)
        exit_match, timed_out = None, False
        try:
            while True:
                text = uart_log.read_text(errors="replace") if uart_log.exists() else ""
                exit_match = _EXIT_SENTINEL.search(text)
                if exit_match or proc.poll() is not None:
                    break
                if time.monotonic() - start > timeout:
                    timed_out = True
                    break
                time.sleep(0.05)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    duration = time.monotonic() - start

    text = uart_log.read_text(errors="replace") if uart_log.exists() else ""
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
                     duration=duration, sim_commands=sim_commands)
