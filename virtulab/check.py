"""`virtulab check`: validate the board, wiring and test selection before anything runs.

It answers "will this configuration work, and how much can I trust it" in
one screen. Errors stop a run; warnings are shown in the report.
"""

import glob
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import emulator
from .boards import BOARDS
from .catalog import board_buses, get_module, get_test, PROTOCOLS
from . import VirtulabError
from .config import ProjectConfig, all_stimulus, option, parse_pin

OK, WARN, ERROR = "ok", "warn", "error"
_ICON = {OK: "✅", WARN: "⚠️ ", ERROR: "❌"}


@dataclass
class Finding:
    level: str
    subject: str
    message: str
    missing_tool: bool = False  # the config is fine, this machine just lacks a tool


@dataclass
class CheckResult:
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, subject: str, message: str, missing_tool: bool = False) -> None:
        self.findings.append(Finding(level, subject, message, missing_tool))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARN]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def only_missing_tools(self) -> bool:
        """Errors exist, but all of them are tools this machine lacks (Docker can supply them)."""
        return bool(self.errors) and all(f.missing_tool for f in self.errors)

    def to_json(self) -> dict:
        return {"ok": self.ok, "findings": [vars(f) for f in self.findings]}

    def to_text(self) -> str:
        width = max((len(f.subject) for f in self.findings), default=0)
        lines = [f"{_ICON[f.level]} {f.subject:<{width}}  {f.message}" for f in self.findings]
        lines.append("")
        lines.append("Board check passed" if self.ok else
                     f"Board check failed: {len(self.errors)} error(s)")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        rows = "\n".join(f"| {_ICON[f.level]} | `{f.subject}` | {f.message} |" for f in self.findings)
        return f"| | Item | Result |\n| :-- | :-- | :-- |\n{rows}\n"


def _tool(name: str, board: str) -> str | None:
    """The executable that satisfies a host-tool requirement, or None."""
    if name == "emulator":
        exe = emulator.RENODE if BOARDS[board].emulator == "renode" else emulator.QEMU
        return shutil.which(exe)
    if name == "qemu":
        return shutil.which(emulator.QEMU)
    if name == "cc":
        return next(filter(None, (shutil.which(c) for c in (os.environ.get("CC", "cc"), "gcc", "clang"))), None)
    if name == "arm-gdb":
        return next(filter(None, (shutil.which(c) for c in ("arm-none-eabi-gdb", "gdb-multiarch"))), None)
    return shutil.which(name)


def tool_status(test: str, board: str) -> list[str]:
    """Names of the host tools a test needs that are not installed."""
    needs = get_test(test).needs
    if test == "fault" and BOARDS[board].emulator == "renode":
        needs = ("arm-none-eabi-gcc", "emulator")  # the sweep drives Renode itself, no gdb
    return [n for n in needs if _tool(n, board) is None]


def _matches(root: Path, patterns: list[str]) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        found += glob.glob(str(root / pattern), recursive=True)
    return found


def _check_inputs(res: CheckResult, cfg: ProjectConfig, root: Path | None, label: str) -> None:
    """Every input step must name a real input of this project."""
    try:
        steps = all_stimulus(cfg, root)
    except VirtulabError as exc:
        res.add(ERROR, label, str(exc))
        steps = []
    for s in steps:
        if s.module in cfg.analog:
            if s.prop not in cfg.analog[s.module].inputs:
                res.add(ERROR, label, f"{s.module} has no input '{s.prop}'")
                break
            continue
        if s.module not in cfg.modules and s.module not in cfg.peripherals:
            res.add(ERROR, label, f"'{s.module}' is not a module or peripheral of this project")
            break
        if s.module in cfg.peripherals and s.prop not in {r.name for r in cfg.peripherals[s.module].registers}:
            res.add(ERROR, label, f"{s.module} has no register '{s.prop}'")
            break
        if s.module in cfg.modules and s.prop not in get_module(cfg.modules[s.module].model).sim:
            res.add(ERROR, label, f"{cfg.modules[s.module].model} has no input '{s.prop}'. "
                                       f"Available: {', '.join(get_module(cfg.modules[s.module].model).sim)}")
            break
    else:
        if steps:
            res.add(OK, label, f"{len(steps)} sensor input step(s) on the virtual clock")


def check(cfg: ProjectConfig, root: Path | None = None, tools: bool | str = True) -> CheckResult:
    """Validate `cfg`. With `root`, also check that referenced files exist.

    `tools`: True reports missing host tools as errors, "warn" as warnings (the setup page,
    where CI or Docker provides them), False skips the lookup.
    """
    res = CheckResult()
    board = BOARDS[cfg.board]
    buses = board_buses(cfg.board)
    if buses:
        res.add(OK, cfg.board, f"{board.cpu}, {board.description} (Renode, buses: {', '.join(buses)})")
    else:
        res.add(OK, cfg.board, f"{board.cpu}, {board.description} (QEMU, CPU only)")

    # Wiring
    used: dict[tuple[str, object], str] = {}
    for m in cfg.modules.values():
        label = f"{m.name}"
        try:
            module = get_module(m.model)
        except Exception as exc:
            res.add(ERROR, label, str(exc))
            continue
        if m.name in board.reserved_names:
            res.add(ERROR, label, f"'{m.name}' is already a peripheral of {cfg.board} (the emulator would stop "
                                  f"with \"already declared\"). Rename the module, e.g. '{m.name}_chip'.")
            continue
        if not buses:
            res.add(ERROR, label, f"{cfg.board} runs on QEMU and cannot host modules. "
                                  "Pick stm32f4_discovery, or remove the module.")
            continue
        if m.bus not in buses:
            res.add(ERROR, label, f"{cfg.board} has no bus '{m.bus}'. Available: "
                                  f"{', '.join(b for b, k in buses.items() if k == module.protocol)}")
            continue
        if buses[m.bus] != module.protocol:
            res.add(ERROR, label, f"{module.title} speaks {PROTOCOLS[module.protocol].title} but "
                                  f"{m.bus} is a {PROTOCOLS[buses[m.bus]].title} bus")
            continue
        address = m.address if m.address is not None else module.default_address
        if module.addresses and address not in module.addresses:
            allowed = ", ".join(f"{a:#04x}" for a in module.addresses)
            res.add(ERROR, label, f"{module.title} can only be at {allowed}, not {address:#04x}")
            continue
        if PROTOCOLS[module.protocol].uses_address:
            clash = used.get((m.bus, address))
            if clash:
                res.add(ERROR, label, f"address {address:#04x} on {m.bus} is already used by '{clash}'")
                continue
            used[(m.bus, address)] = m.name
        elif module.protocol == "uart":
            # The emulator connects one device to a UART (a hub joins two ends).
            clash = used.get((m.bus, None))
            if clash:
                res.add(ERROR, label, f"{m.bus} already has '{clash}'. In the emulator a UART "
                                      "carries one device; use another UART.")
                continue
            used[(m.bus, None)] = m.name
        if module.default_cs:
            try:
                port, pin = parse_pin(m.cs or module.default_cs)
            except Exception as exc:
                res.add(ERROR, label, str(exc))
                continue
            if (port, pin) in {("A", 5), ("A", 6), ("A", 7)}:
                res.add(ERROR, label, f"P{port}{pin} carries the SPI1 clock or data lines. Pick another "
                                      "chip-select pin, e.g. PA4")
                continue
            clash = used.get(("cs", f"{port}{pin}"))
            if clash:
                res.add(ERROR, label, f"chip-select pin P{port}{pin} is already used by '{clash}'")
                continue
            used[("cs", f"{port}{pin}")] = m.name
        where = f"{m.bus} @ {address:#04x}" if address is not None else m.bus
        if module.tier == "accurate":
            res.add(OK, label, f"{module.title} on {where}: datasheet model")
        else:
            res.add(WARN, label, f"{module.title} on {where}: built-in Renode model. {module.gaps or 'Partial model.'}")

    for p in cfg.peripherals.values():
        if p.name in board.reserved_names:
            res.add(ERROR, p.name, f"'{p.name}' is already a peripheral of {cfg.board}. Rename it.")
        elif not buses:
            res.add(ERROR, p.name, f"{cfg.board} runs on QEMU and cannot host peripherals. Pick stm32f4_discovery.")
        elif buses.get(p.bus) != "i2c":
            res.add(ERROR, p.name, f"Custom peripherals work on I²C buses for now. Available: "
                                   f"{', '.join(b for b, k in buses.items() if k == 'i2c')}")
        elif used.get((p.bus, p.address)):
            res.add(ERROR, p.name, f"address {p.address:#04x} on {p.bus} is already used by '{used[(p.bus, p.address)]}'")
        else:
            used[(p.bus, p.address)] = p.name
            res.add(WARN, p.name, f"custom peripheral on {p.bus} @ {p.address:#04x}: your register list, "
                                  "not checked against a datasheet")
    for a in cfg.analog.values():
        if cfg.board != "stm32f4_discovery":
            res.add(ERROR, a.name, f"Analog inputs work on stm32f4_discovery for now, not {cfg.board}.")
        else:
            res.add(WARN, a.name, f"ADC with {len(a.inputs)} input(s), {a.vref:g} V reference. Voltages are ideal: "
                                  "no noise, sampling or conversion time")
    _check_inputs(res, cfg, root, "stimulus")
    for rule in cfg.rules:
        try:
            parse_pin(rule.pin)
            if "." in rule.target:
                module = rule.target.partition(".")[0]
                if module not in cfg.modules and module not in cfg.peripherals and module not in cfg.analog:
                    raise VirtulabError(f"'{module}' is not a module or peripheral of this project")
            else:
                parse_pin(rule.target)
        except VirtulabError as exc:
            res.add(ERROR, "rules", str(exc))
    if cfg.rules and not buses:
        res.add(ERROR, "rules", f"Rules need a board that models pins, not {cfg.board}.")
    for path in [*cfg.models, *([cfg.repl] if cfg.repl else [])]:
        if root is not None and not (root / path).is_file():
            res.add(ERROR, "models", f"'{path}' not found")
    if cfg.models or cfg.repl:
        res.add(WARN, "models", "your own Renode models: VirtuLab loads them as they are")

    # Tests
    for tid in cfg.tests:
        t = get_test(tid)
        for opt in t.options:
            if opt.required and not cfg.tests[tid].get(opt.name) and not opt.default:
                res.add(ERROR, tid, f"option '{opt.name}' is required")
        if tid == "scenarios":
            from .scenarios import parse_cases, with_case
            if board.emulator != "renode":
                res.add(ERROR, tid, f"{t.title} need a board that can carry inputs, not {cfg.board}")
                continue
            try:
                for case in parse_cases(cfg):
                    _check_inputs(res, with_case(cfg, case), root, f"{tid}.{case.name}")
            except VirtulabError as exc:
                res.add(ERROR, tid, str(exc))
                continue
        prebuilt = tid == "fault" and cfg.tests[tid].get("elf")
        if root is not None and tid in ("fuzz", "fault") and not prebuilt:
            key = "harness" if tid == "fuzz" else "probe"
            value = option(cfg, tid, key)
            absent = [p for p in ([value] if isinstance(value, str) else value) if not (root / p).is_file()]
            if absent:
                res.add(ERROR, tid, f"{key} file '{absent[0]}' not found")
                continue
        missing = tool_status(tid, cfg.board) if tools else []
        if missing and tools == "warn":
            res.add(WARN, tid, f"{t.title}: {', '.join(missing)} not installed on this machine. "
                               "CI and the Docker image have it")
        elif missing:
            res.add(ERROR, tid, f"{t.title}: missing host tool(s): {', '.join(missing)}",
                    missing_tool=True)
        else:
            note = f"{t.title}" + (f" — {t.limits}" if t.limits and t.stage == "security" else "")
            res.add(OK, tid, note)

    if root is not None and "unit" in cfg.tests and not cfg.build_command:
        if not _matches(root, cfg.sources):
            res.add(ERROR, "build", f"no source files match {', '.join(cfg.sources)}")
    return res
