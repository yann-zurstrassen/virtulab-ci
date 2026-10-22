"""What a user can pick: boards, communication protocols, sensors and tests.

This is the single source of truth for `virtulab catalog`, `virtulab check`,
the setup wizard and the web UI. Every entry here is either backed by a real
emulator feature or marked as not available, never listed as a promise.

Fidelity tiers (see docs/FIDELITY.md):
  accurate     written from the datasheet, behaviour is checked by tests
  builtin      Renode's own model, correct for the documented subset only
  cpu-only     the CPU runs, but no peripherals can be attached
"""

from dataclasses import dataclass, field

from . import VirtulabError
from .boards import BOARDS

# ---------------------------------------------------------------------------
# Protocols

@dataclass(frozen=True)
class Protocol:
    id: str
    title: str
    summary: str
    uses_address: bool  # I2C devices are addressed, SPI devices use a chip select


PROTOCOLS = {p.id: p for p in [
    Protocol("i2c", "I²C", "Two-wire bus, devices are selected by a 7-bit address.", True),
    Protocol("spi", "SPI", "Four-wire bus, one device per chip-select line.", False),
    Protocol("uart", "UART", "Serial link between two devices.", False),
]}


# ---------------------------------------------------------------------------
# Boards: the Board dataclass in boards.py describes memory and emulator.
# What can be attached to it (which buses exist) lives here.

# Renode STM32F4: console uses USART2, so it is not offered as a user bus.
_STM32F4_BUSES = {
    "i2c1": "i2c", "i2c2": "i2c", "i2c3": "i2c",
    "spi1": "spi", "spi2": "spi", "spi3": "spi",
    "usart1": "uart", "usart3": "uart", "uart4": "uart", "uart5": "uart",
}

BOARD_BUSES: dict[str, dict[str, str]] = {"stm32f4_discovery": _STM32F4_BUSES}

BOARD_NOTES = {
    "stm32f4_discovery": "Renode: models I²C, SPI and UART, so sensors can be attached.",
}


def board_buses(board: str) -> dict[str, str]:
    return BOARD_BUSES.get(board, {})


def board_info(name: str) -> dict:
    b = BOARDS[name]
    buses = board_buses(name)
    return {
        "id": b.name,
        "title": b.description,
        "cpu": b.cpu,
        "flash": b.flash_size,
        "ram": b.ram_size,
        "emulator": b.emulator,
        "buses": buses,
        "protocols": sorted(set(buses.values())),
        "tier": "peripherals" if buses else "cpu-only",
        "note": BOARD_NOTES.get(name, "QEMU: CPU, memory and console. No peripherals can be attached."),
    }


# ---------------------------------------------------------------------------
# Modules: external parts on the board.

@dataclass(frozen=True)
class Module:
    id: str
    title: str
    kind: str  # "temperature", "flash", ...
    protocol: str
    tier: str  # "accurate" | "builtin"
    renode_type: str  # peripheral type used in the generated .repl
    summary: str
    default_address: int | None = None
    addresses: tuple[int, ...] = ()  # allowed addresses (empty = any 7-bit)
    sim: tuple[str, ...] = ()  # properties a test can change with vl_sim()
    gaps: str = ""  # what is not modelled
    needs_device_file: bool = False  # ships as C# in virtulab/devices


MODULES = {m.id: m for m in [
    Module("tmp108", "TI TMP108 temperature sensor", "temperature", "i2c", "accurate",
           "VirtuLab.TMP108",
           "Digital temperature sensor with 0.0625 °C resolution and alert output.",
           default_address=0x48, addresses=(0x48, 0x49, 0x4A, 0x4B),
           sim=("Temperature",),
           gaps="Alert pin and one-shot conversion timing are not modelled.",
           needs_device_file=True),
    Module("bmp180", "Bosch BMP180 pressure and temperature sensor", "pressure", "i2c", "builtin",
           "Sensors.BMP180",
           "Barometric pressure and temperature sensor with factory calibration data.",
           default_address=0x77, addresses=(0x77,),
           sim=("Temperature", "Pressure"),
           gaps="Renode's model. VirtuLab's sample tests check the chip ID and the raw temperature path only."),
]}


def module_info(m: Module) -> dict:
    return {
        "id": m.id, "title": m.title, "kind": m.kind, "protocol": m.protocol, "tier": m.tier,
        "summary": m.summary, "default_address": m.default_address,
        "addresses": list(m.addresses), "sim": list(m.sim), "gaps": m.gaps,
    }


def get_module(name: str) -> Module:
    try:
        return MODULES[name]
    except KeyError:
        raise VirtulabError(
            f"Unknown module '{name}'. Available: {', '.join(MODULES)}"
        ) from None


# ---------------------------------------------------------------------------
# Tests

@dataclass(frozen=True)
class Option:
    name: str
    kind: str  # "str" | "int" | "list" | "bytes" | "percent"
    default: object
    help: str
    required: bool = False


@dataclass(frozen=True)
class TestKind:
    id: str
    title: str
    summary: str
    stage: str  # shown as a badge: "functional" | "footprint" | "security"
    needs: tuple[str, ...]  # host tools
    options: tuple[Option, ...] = ()
    on_by_default: bool = False
    limits: str = ""  # what this test does not prove
    emulated_boards_only: bool = False  # fault injection drives QEMU


TESTS = {t.id: t for t in [
    TestKind(
        "unit", "Unit tests on the virtual board",
        "Builds the firmware with the Arm toolchain and runs its tests on the emulated CPU.",
        "functional", ("arm-none-eabi-gcc", "emulator"),
        on_by_default=True,
    ),
    TestKind(
        "footprint", "Flash and RAM budget",
        "Compares memory use with the base branch and fails the build above a budget.",
        "footprint", ("arm-none-eabi-gcc", "git"),
        options=(
            Option("flash_increase", "bytes", "4K", "Fail when flash grows more than this"),
            Option("ram_increase", "bytes", "2K", "Fail when RAM grows more than this"),
        ),
        on_by_default=True,
        limits="Needs a git history to compare with; skipped on the first commit.",
    ),
    TestKind(
        "coverage", "Line and branch coverage",
        "Runs the same tests natively with gcov and reports how much of the code they execute.",
        "security", ("cc", "gcov"),
        options=(
            Option("sources", "list", ["src/*.c"], "Source files to measure (not the tests)"),
            Option("exclude", "list", [], "Files left out of the native build (hardware-only code)"),
            Option("min_lines", "percent", 0, "Fail below this line coverage (0 = report only)"),
        ),
        limits="Line and branch only, no MC/DC. Measured on a host build, not on the target.",
    ),
    TestKind(
        "fuzz", "Fuzzing",
        "Throws mutated inputs at a parser with AddressSanitizer and UBSan and reports crashes.",
        "security", ("cc",),
        options=(
            Option("harness", "str", "fuzz/fuzz.c", "Fuzz harness file", required=True),
            Option("sources", "list", ["src/*.c"], "Code under test"),
            Option("include", "list", ["include"], "Include directories"),
            Option("seconds", "int", 20, "Time budget"),
            Option("seed", "int", 1, "Seed, so a crash reproduces on a laptop"),
            Option("crash_dir", "str", "fuzz/crashes", "Crash inputs are saved and replayed here"),
        ),
        limits="Host-side fuzzing of the logic, not full-system fuzzing of the firmware image.",
    ),
    TestKind(
        "fault", "Fault injection (instruction skip)",
        "Skips one instruction at a time inside a function and reports any wrong-PIN style bypass.",
        "security", ("arm-none-eabi-gcc", "qemu", "arm-gdb"),
        options=(
            Option("probe", "str", "fault/probe.c", "Probe: fails only if the bypass happens",
                   required=True),
            Option("sources", "list", ["src/auth.c"], "Code under attack (also built into the probe)"),
            Option("target", "str", "src/auth.c", "Source file whose instructions are skipped",
                   required=True),
            Option("include", "list", ["include"], "Include directories"),
        ),
        limits="Single skip, first execution only. Not a model of physical glitches.",
        emulated_boards_only=True,
    ),
]}

DEFAULT_TESTS = [t.id for t in TESTS.values() if t.on_by_default]


def get_test(name: str) -> TestKind:
    try:
        return TESTS[name]
    except KeyError:
        raise VirtulabError(f"Unknown test '{name}'. Available: {', '.join(TESTS)}") from None


def test_info(t: TestKind) -> dict:
    return {
        "id": t.id, "title": t.title, "summary": t.summary, "stage": t.stage,
        "needs": list(t.needs), "default": t.on_by_default, "limits": t.limits,
        "qemu_only": t.emulated_boards_only,
        "options": [
            {"name": o.name, "kind": o.kind, "default": o.default, "help": o.help,
             "required": o.required}
            for o in t.options
        ],
    }


def as_json() -> dict:
    """Everything the UI and `virtulab catalog --json` show."""
    return {
        "boards": [board_info(n) for n in BOARDS],
        "protocols": [{"id": p.id, "title": p.title, "summary": p.summary} for p in PROTOCOLS.values()],
        "modules": [module_info(m) for m in MODULES.values()],
        "tests": [test_info(t) for t in TESTS.values()],
    }
