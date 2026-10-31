"""`virtulab.yml`: one file describing board, modules and tests.

The CLI, the GitHub Action, the Docker image and the web UI all read this
file, so no CI system duplicates settings. Unknown keys are errors (with a
"did you mean"), so typos never fail silently.
"""

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import MONITOR_MARK, VirtulabError, peripherals as custom, yamlite
from .boards import BOARDS
from .catalog import DEFAULT_TESTS, MODULES, PROTOCOLS, TESTS, get_module, get_test
from .yamlite import Hex

CONFIG_NAMES = ("virtulab.yml", "virtulab.yaml")
SCHEMA_VERSION = 1

_TOP_KEYS = ("version", "board", "build", "timeout", "modules", "peripherals", "analog", "stimulus", "stimulus_file",
             "tests", "ci")
_BUILD_KEYS = ("sources", "include", "cflags", "ldflags", "linker_script", "runtime", "command", "elf")
_MODULE_KEYS = ("model", "bus", "address", "cs")
_CI_KEYS = ("provider", "branches")
_PROVIDERS = ("github", "gitlab")
_NAME = re.compile(r"[a-z][a-z0-9_]*")


@dataclass
class ModuleSpec:
    name: str
    model: str
    bus: str
    address: int | None = None
    cs: str | None = None  # SPI chip-select pin, e.g. "PA4"; None = the module's default


@dataclass
class ProjectConfig:
    board: str = "lm3s6965evb"
    sources: list[str] = field(default_factory=lambda: ["**/*.c"])
    include: list[str] = field(default_factory=list)
    cflags: str = ""
    ldflags: str = ""
    linker_script: str | None = None
    runtime: bool = True
    build_command: str | None = None  # the project's own build, e.g. cmake --build build
    build_elf: str | None = None  # the ELF that command produces
    timeout: str = "30s"
    modules: dict[str, ModuleSpec] = field(default_factory=dict)
    peripherals: dict[str, custom.Peripheral] = field(default_factory=dict)
    analog: dict[str, custom.AnalogBlock] = field(default_factory=dict)
    raw_analog: dict = field(default_factory=dict)
    stimulus: list[custom.Stimulus] = field(default_factory=list)
    stimulus_file: str | None = None
    raw_peripherals: dict = field(default_factory=dict)
    raw_stimulus: list = field(default_factory=list)
    tests: dict[str, dict] = field(default_factory=lambda: {t: {} for t in DEFAULT_TESTS})
    ci_provider: str = "github"
    ci_branches: list[str] = field(default_factory=lambda: ["main"])

    def to_dict(self) -> dict:
        build: dict = {"sources": list(self.sources)}
        if self.build_command:
            build = {"command": self.build_command, "elf": self.build_elf}
        if self.include:
            build["include"] = list(self.include)
        if self.cflags:
            build["cflags"] = self.cflags
        if self.ldflags:
            build["ldflags"] = self.ldflags
        if self.linker_script:
            build["linker_script"] = self.linker_script
        if not self.runtime:
            build["runtime"] = False
        data: dict = {"version": SCHEMA_VERSION, "board": self.board, "build": build,
                      "timeout": self.timeout}
        if self.modules:
            data["modules"] = {}
            for name, m in self.modules.items():
                entry: dict = {"model": m.model, "bus": m.bus}
                if m.address is not None:
                    entry["address"] = Hex(m.address)
                if m.cs is not None:
                    entry["cs"] = m.cs
                data["modules"][name] = entry
        if self.raw_peripherals:
            data["peripherals"] = self.raw_peripherals
        if self.raw_analog:
            data["analog"] = self.raw_analog
        if self.raw_stimulus:
            data["stimulus"] = self.raw_stimulus
        if self.stimulus_file:
            data["stimulus_file"] = self.stimulus_file
        data["tests"] = {t: dict(opts) for t, opts in self.tests.items()}
        data["ci"] = {"provider": self.ci_provider, "branches": list(self.ci_branches)}
        return data

    def dumps(self) -> str:
        header = ("# VirtuLab CI configuration. Edit by hand or with `virtulab ui`.\n"
                  "# Docs: https://github.com/yann-zurstrassen/virtulab-ci\n")
        return header + yamlite.dumps(self.to_dict()) + "\n"


def _unknown(where: str, keys, allowed) -> None:
    for key in keys:
        if key not in allowed:
            hint = difflib.get_close_matches(str(key), allowed, n=1)
            suffix = f" Did you mean '{hint[0]}'?" if hint else f" Allowed: {', '.join(allowed)}."
            raise VirtulabError(f"virtulab.yml: unknown key '{key}' in {where}.{suffix}")


def _str_list(where: str, value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p for p in re.split(r"[\s,]+", value) if p]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise VirtulabError(f"virtulab.yml: '{where}' must be a list of strings")


def _expect(where: str, value, kind):
    if value is not None and not isinstance(value, kind):
        raise VirtulabError(f"virtulab.yml: '{where}' must be a {kind.__name__}")
    return value


def from_dict(data: dict) -> ProjectConfig:
    if not isinstance(data, dict):
        raise VirtulabError("virtulab.yml must contain a mapping at the top level")
    _unknown("the top level", data, _TOP_KEYS)
    version = data.get("version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise VirtulabError(f"virtulab.yml: unsupported version {version} (this is VirtuLab "
                            f"schema version {SCHEMA_VERSION})")
    cfg = ProjectConfig()

    if "board" in data:
        cfg.board = str(data["board"])
    if cfg.board not in BOARDS:
        hint = difflib.get_close_matches(cfg.board, BOARDS, n=1)
        suffix = f" Did you mean '{hint[0]}'?" if hint else ""
        raise VirtulabError(f"virtulab.yml: unknown board '{cfg.board}'.{suffix} "
                            f"Run `virtulab catalog` to list boards.")

    build = _expect("build", data.get("build"), dict) or {}
    _unknown("build", build, _BUILD_KEYS)
    if "sources" in build:
        cfg.sources = _str_list("build.sources", build["sources"])
    cfg.include = _str_list("build.include", build.get("include"))
    cfg.cflags = str(build.get("cflags") or "")
    cfg.ldflags = str(build.get("ldflags") or "")
    cfg.linker_script = build.get("linker_script") or None
    cfg.runtime = bool(build.get("runtime", True))
    if "command" in build and not isinstance(build["command"], str):
        raise VirtulabError("virtulab.yml: build.command must be text. Put it in quotes")
    cfg.build_command = build.get("command") or None
    cfg.build_elf = build.get("elf") or None
    if bool(cfg.build_command) != bool(cfg.build_elf):
        raise VirtulabError("virtulab.yml: build.command and build.elf go together")
    if "timeout" in data:
        cfg.timeout = str(data["timeout"])

    modules = _expect("modules", data.get("modules"), dict) or {}
    for name, spec in modules.items():
        if not _NAME.fullmatch(str(name)):
            raise VirtulabError(f"virtulab.yml: module name '{name}' must be lowercase letters, "
                                "digits and underscores, starting with a letter")
        spec = spec or {}
        if not isinstance(spec, dict):
            raise VirtulabError(f"virtulab.yml: module '{name}' must be a mapping")
        _unknown(f"module '{name}'", spec, _MODULE_KEYS)
        for required in ("model", "bus"):
            if required not in spec:
                raise VirtulabError(f"virtulab.yml: module '{name}' needs '{required}'")
        address = spec.get("address")
        if address is not None and not isinstance(address, int):
            raise VirtulabError(f"virtulab.yml: module '{name}' address must be a number, e.g. 0x48")
        cs = spec.get("cs")
        if cs is not None and not isinstance(cs, str):
            raise VirtulabError(f"virtulab.yml: module '{name}' cs must be a pin name, e.g. PA4")
        cfg.modules[str(name)] = ModuleSpec(str(name), str(spec["model"]), str(spec["bus"]), address, cs)

    declared = _expect("peripherals", data.get("peripherals"), dict) or {}
    for name, spec in declared.items():
        if not _NAME.fullmatch(str(name)):
            raise VirtulabError(f"virtulab.yml: peripheral name '{name}' must be lowercase letters, "
                                "digits and underscores, starting with a letter")
        if str(name) in cfg.modules:
            raise VirtulabError(f"virtulab.yml: '{name}' is both a module and a peripheral")
        cfg.peripherals[str(name)] = custom.parse_peripheral(str(name), _expect(f"peripheral '{name}'", spec, dict) or {})
    cfg.raw_peripherals = declared
    cfg.raw_analog = _expect("analog", data.get("analog"), dict) or {}
    for name, spec in cfg.raw_analog.items():
        cfg.analog[str(name)] = custom.parse_analog(str(name), _expect(f"analog '{name}'", spec, dict) or {})
    cfg.raw_stimulus = _expect("stimulus", data.get("stimulus"), list) or []
    cfg.stimulus = custom.parse_stimulus(cfg.raw_stimulus)
    cfg.stimulus_file = data.get("stimulus_file") or None

    tests = data.get("tests")
    if tests is None:
        cfg.tests = {t: {} for t in DEFAULT_TESTS}
    else:
        cfg.tests = {}
        entries = tests if isinstance(tests, list) else [{k: v} for k, v in tests.items()]
        for entry in entries:
            if isinstance(entry, str):
                entry = {entry: {}}
            if not isinstance(entry, dict):
                raise VirtulabError("virtulab.yml: 'tests' must be a mapping or a list of names")
            for tid, opts in entry.items():
                if tid not in TESTS:
                    hint = difflib.get_close_matches(str(tid), TESTS, n=1)
                    suffix = f" Did you mean '{hint[0]}'?" if hint else ""
                    raise VirtulabError(f"virtulab.yml: unknown test '{tid}'.{suffix} "
                                        f"Available: {', '.join(TESTS)}")
                opts = {} if opts in (None, True) else opts
                if opts is False:
                    continue
                if not isinstance(opts, dict):
                    raise VirtulabError(f"virtulab.yml: options of test '{tid}' must be a mapping")
                _unknown(f"tests.{tid}", opts, [o.name for o in get_test(tid).options])
                for o in get_test(tid).options:
                    if o.kind == "int" and o.name in opts and not isinstance(opts[o.name], int):
                        raise VirtulabError(f"virtulab.yml: tests.{tid}.{o.name} must be a whole number")
                cfg.tests[str(tid)] = dict(opts)

    ci = _expect("ci", data.get("ci"), dict) or {}
    _unknown("ci", ci, _CI_KEYS)
    cfg.ci_provider = str(ci.get("provider", "github"))
    if cfg.ci_provider not in _PROVIDERS:
        raise VirtulabError(f"virtulab.yml: ci.provider must be one of {', '.join(_PROVIDERS)}")
    cfg.ci_branches = _str_list("ci.branches", ci.get("branches")) or ["main"]
    return cfg


def find(root: Path) -> Path | None:
    for name in CONFIG_NAMES:
        if (root / name).is_file():
            return root / name
    return None


def load(root: Path) -> ProjectConfig | None:
    path = find(root)
    if path is None:
        return None
    return from_dict(yamlite.load(path))


def option(cfg: ProjectConfig, test: str, name: str):
    """A test option: the project's value, or the catalog default."""
    opts = cfg.tests.get(test, {})
    if name in opts:
        return opts[name]
    for o in get_test(test).options:
        if o.name == name:
            return o.default
    raise KeyError(name)


CORE_CLOCK_HZ = 16_000_000  # the STM32F4 reset clock (HSI)

_PIN = re.compile(r"P([A-I])(\d|1[0-5])")


def parse_pin(text: str) -> tuple[str, int]:
    """'PA4' -> ('A', 4). Raises VirtulabError for anything that is not a GPIO pin name."""
    m = _PIN.fullmatch(text.strip().upper())
    if not m:
        raise VirtulabError(f"'{text}' is not a pin name. Use a port letter A-I and a pin 0-15, e.g. PA4")
    return m[1], int(m[2])


def sim_path(cfg: ProjectConfig, name: str) -> str:
    """The emulator monitor path of a module, as used in `vl_sim("<path> Property value")`."""
    if name in cfg.analog:
        return f"sysbus.{name}"
    if name in cfg.peripherals:
        return f"sysbus.{cfg.peripherals[name].bus}.{name}"
    m = cfg.modules[name]
    module = get_module(m.model)
    if module.protocol == "uart":
        return f"sysbus.{m.name}"
    if module.protocol == "spi":
        return f"sysbus.{m.bus}.{m.bus}_mux.{m.name}"
    return f"sysbus.{m.bus}.{m.name}"


def all_stimulus(cfg: ProjectConfig, root: Path | None) -> list[custom.Stimulus]:
    """The timeline and the recorded trace together, in time order."""
    steps = list(cfg.stimulus)
    if cfg.stimulus_file and root is not None:
        steps += custom.read_trace(root / cfg.stimulus_file)
    return sorted(steps, key=lambda s: s.at_ms)


def generated_models(cfg: ProjectConfig, root: Path | None) -> dict[str, str]:
    """Renode model sources this project needs, by file name."""
    files = {f"{p.class_name}.cs": custom.model_source(p) for p in cfg.peripherals.values()}
    files.update({f"{a.class_name}.cs": custom.analog_source(a) for a in cfg.analog.values()})
    timed = [(s.at_ms, sim_path(cfg, s.module), s.prop, s.value) for s in all_stimulus(cfg, root) if s.at_ms > 0]
    if timed:
        files["Stimulus.cs"] = custom.stimulus_source(timed)
    return files


def renode_repl(cfg: ProjectConfig, root: Path | None = None) -> str | None:
    """The generated Renode lines for the declared modules. Users never write these.

    SPI devices sit behind a multiplexer on their bus, which turns the chip-select GPIO
    lines into transaction boundaries (the emulator's SPI block does not see them) and
    routes each transaction to the one device whose line is low.
    UART devices are not registered on a bus: they sit on the other end of a UART hub, so
    their connection is a monitor command, added after MONITOR_MARK.
    """
    lines, monitor = [], []
    chip_selects: dict[str, list[str]] = {}  # GPIO port -> "pin -> mux@index"
    spi_index: dict[str, int] = {}  # bus -> devices attached so far
    for m in cfg.modules.values():
        module = get_module(m.model)
        if module.protocol == "uart":
            hub = f"vl_{m.name}_link"
            lines.append(f"{m.name}: {module.renode_type} @ sysbus")
            monitor += [f'emulation CreateUARTHub "{hub}"',
                        f"connector Connect sysbus.{m.bus} {hub}",
                        f"connector Connect sysbus.{m.name} {hub}"]
        elif module.protocol == "spi":
            mux = f"{m.bus}_mux"
            index = spi_index.get(m.bus, 0)
            if index == 0:
                lines.append(f"{mux}: SPI.SPIMultiplexer @ {m.bus}")
            spi_index[m.bus] = index + 1
            lines.append(f"{m.name}: {module.renode_type} @ {mux} {index}")
            port, pin = parse_pin(m.cs or module.default_cs or "PA4")
            chip_selects.setdefault(port, []).append(f"    {pin} -> {mux}@{index}")
            # Chip-select lines idle high on a real board (pull-ups). Without this the emulator
            # sees every unused line as low, i.e. every device as selected.
            monitor += [f"sysbus.{m.bus}.{mux} SetActiveLow {index}",
                        f"sysbus.{m.bus}.{mux} OnGPIO {index} true"]
        else:
            address = m.address if m.address is not None else module.default_address
            target = f"{m.bus} {address:#04x}" if address is not None else m.bus
            lines.append(f"{m.name}: {module.renode_type} @ {target}")
    for p in cfg.peripherals.values():
        lines.append(f"{p.name}: VirtuLab.{p.class_name} @ {p.bus} {p.address:#04x}")
    for a in cfg.analog.values():
        lines.append(f"{a.name}: VirtuLab.{a.class_name} @ sysbus {a.base:#x}")
    steps = all_stimulus(cfg, root)
    if any(s.at_ms > 0 for s in steps):
        lines.append("vl_stimulus: VirtuLab.Stimulus")
    monitor += [f"{sim_path(cfg, s.module)} {s.prop} {s.value!r}" for s in steps if s.at_ms == 0]
    if not lines:
        return None
    # Time: the core runs from the 16 MHz reset clock, so SysTick counts at that rate and a
    # firmware delay of 1 ms is 1 ms on the emulator's virtual clock, the clock device models
    # use for their own latencies. The emulated CPU's speed is left at Renode's default (about
    # 100 MIPS, six times a real 16 MHz core): the emulated I2C block needs a fast CPU to
    # sequence its transfers (see docs/FIDELITY.md, "Time").
    monitor.insert(0, f"sysbus.nvic Frequency {CORE_CLOCK_HZ}")
    for port, wires in chip_selects.items():
        lines.append(f"gpioPort{port}:")
        lines += wires
    text = "\n".join(lines) + "\n"
    if monitor:
        text += MONITOR_MARK + "\n" + "\n".join(monitor) + "\n"
    return text


__all__ = ["ProjectConfig", "ModuleSpec", "from_dict", "load", "find", "option",
           "renode_repl", "sim_path", "parse_pin", "MODULES", "PROTOCOLS"]
