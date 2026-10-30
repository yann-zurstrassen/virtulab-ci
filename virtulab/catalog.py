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
class Sample:
    """The starter firmware `init --template starter` writes for a sensor (templates/starter/<id>)."""
    suite: str  # test suite function that test_main.c calls
    hardware: tuple[str, ...]  # files that only build for the target (excluded from native coverage)
    extras: tuple[str, ...] = ()  # pure-logic template folders the driver builds on


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
    default_cs: str | None = None  # SPI chip-select pin the emulator model is wired to
    sample: Sample | None = None  # starter firmware, None = the sensor has none


MODULES = {m.id: m for m in [
    Module("tmp108", "TI TMP108 temperature sensor", "temperature", "i2c", "accurate",
           "VirtuLab.TMP108",
           "Digital temperature sensor with 0.0625 °C resolution and alert output.",
           default_address=0x48, addresses=(0x48, 0x49, 0x4A, 0x4B),
           sim=("Temperature",),
           gaps="Alert pin and one-shot conversion timing are not modelled.",
           needs_device_file=True,
           sample=Sample("test_thermostat_run", ("src/thermostat.c", "src/tmp108.c", "test/test_thermostat.c"))),
    Module("bmp180", "Bosch BMP180 pressure and temperature sensor", "pressure", "i2c", "builtin",
           "Sensors.BMP180",
           "Barometric pressure and temperature sensor with factory calibration data.",
           default_address=0x77, addresses=(0x77,),
           sim=("Temperature", "Pressure"),
           gaps="Renode's model. VirtuLab's sample tests check the chip ID and the raw temperature path only.",
           sample=Sample("test_bmp180_run", ("src/bmp180.c", "test/test_bmp180.c"))),
    Module("ina219", "TI INA219 current and power monitor", "power", "i2c", "accurate",
           "VirtuLab.INA219",
           "Measures bus voltage, shunt voltage, current and power of a supply rail, 0 to 32 V.",
           default_address=0x40, addresses=tuple(range(0x40, 0x50)),
           sim=("BusVoltage", "Current", "ShuntResistance"),
           gaps="Conversion time, averaging, operating modes, the bus-voltage range bit and "
                "the overflow flag are not modelled.",
           needs_device_file=True,
           sample=Sample("test_ina219_run", ("src/ina219.c", "test/test_ina219.c"))),
    Module("adxl345", "Analog Devices ADXL345 accelerometer", "accelerometer", "spi", "accurate",
           "VirtuLab.ADXL345",
           "3-axis accelerometer, +-2 to +-16 g, read as 16-bit values.",
           default_cs="PA4",
           sim=("AccelerationX", "AccelerationY", "AccelerationZ", "Responding"),
           gaps="SPI mode, interrupts, FIFO, tap detection, offset registers and output data "
                "rate are not modelled. Output reads zero until the Measure bit is set.",
           needs_device_file=True,
           sample=Sample("test_adxl345_run", ("src/adxl345.c", "test/test_adxl345.c"))),
    Module("mpu6050", "InvenSense MPU-6050 6-axis motion sensor", "imu", "i2c", "accurate",
           "VirtuLab.MPU6050",
           "3-axis accelerometer and 3-axis gyroscope with a temperature sensor.",
           default_address=0x68, addresses=(0x68, 0x69),
           sim=("AccelerationX", "AccelerationY", "AccelerationZ", "AngularRateX", "AngularRateY",
                "AngularRateZ", "Temperature"),
           gaps="Sample-rate divider, filter, FIFO, interrupts, the auxiliary I2C master and "
                "self-test are not modelled. Sensor values read zero while the chip sleeps.",
           needs_device_file=True,
           sample=Sample("test_mpu6050_run", ("src/mpu6050.c", "test/test_mpu6050.c"))),
    Module("sht31", "Sensirion SHT31 temperature and humidity sensor", "humidity", "i2c", "accurate",
           "VirtuLab.SHT31",
           "Digital humidity and temperature sensor with CRC-protected 16-bit results.",
           default_address=0x44, addresses=(0x44, 0x45),
           sim=("Temperature", "Humidity", "CorruptCrc", "ConversionTime"),
           gaps="Alert thresholds and ART mode are not modelled, and clock stretching is not charged "
                "any time. An early read returns 0xFF bytes, where a real chip would not acknowledge it.",
           needs_device_file=True,
           sample=Sample("test_sht31_run", ("src/sht31.c", "test/test_sht31.c"), extras=("clock",))),
    Module("max31855", "Maxim MAX31855 thermocouple converter", "thermocouple", "spi", "accurate",
           "VirtuLab.MAX31855",
           "Reads a K-type thermocouple as a 32-bit frame with cold-junction and fault bits.",
           default_cs="PB0",
           sim=("ThermocoupleTemperature", "InternalTemperature", "OpenCircuit", "ShortToGround",
                "ShortToVcc", "Responding"),
           gaps="Conversion time and thermocouple type limits are not modelled; the value is current.",
           needs_device_file=True,
           sample=Sample("test_max31855_run", ("src/max31855.c", "test/test_max31855.c"))),
    Module("w25q128", "Winbond W25Q128 SPI flash (16 MiB)", "flash", "spi", "accurate",
           "VirtuLab.W25Q128",
           "NOR flash: read, page program and erase, with the write-enable and busy rules.",
           default_cs="PB1",
           sim=("BusyPolls", "Responding"),
           gaps="Real program and erase times (use BusyPolls), fast-read, dual and quad modes, "
                "suspend and the security registers are not modelled.",
           needs_device_file=True,
           sample=Sample("test_w25q128_run", ("src/w25q128.c", "test/test_w25q128.c"))),
    Module("at_modem", "Generic AT-command cellular modem", "modem", "uart", "accurate",
           "VirtuLab.ATModem",
           "Cellular modem speaking V.250 and 3GPP TS 27.007 AT commands at 115200 baud.",
           sim=("Signal", "Registration", "SimReady", "Silent", "Failing"),
           gaps="Only AT, ATE0/1, +CSQ, +CREG?, +CPIN? and +CGMI. No data connections or SMS, "
                "and replies come at once.",
           needs_device_file=True,
           sample=Sample("test_modem_run", ("src/modem.c", "test/test_modem.c"))),
    Module("modbus_rtu", "Generic Modbus RTU temperature and humidity transmitter", "modbus", "uart",
           "accurate", "VirtuLab.ModbusRtuSlave",
           "RS-485 style sensor answering Modbus functions 3, 4 and 6 at 9600 baud.",
           sim=("Temperature", "Humidity", "SlaveAddress", "Silent", "CorruptCrc"),
           gaps="Frames are taken as eight bytes, not by the 3.5-character silence. Functions "
                "other than 3, 4 and 6 answer an exception.",
           needs_device_file=True,
           sample=Sample("test_modbus_rtu_run", ("src/modbus_rtu.c", "test/test_modbus_rtu.c"),
                         extras=("modbus",))),
    Module("nmea_gps", "Generic NMEA GPS receiver", "gps", "uart", "accurate",
           "VirtuLab.NMEAGps",
           "GPS module sending NMEA 0183 position sentences at 9600 baud (u-blox, MediaTek and others).",
           sim=("Latitude", "Longitude", "Altitude", "Satellites", "HasFix", "CorruptChecksum",
                "Silent", "EmitFix"),
           gaps="Only GGA sentences, sent when the test asks. No baud-rate pacing, no host "
                "commands, no timing of fix acquisition.",
           needs_device_file=True,
           sample=Sample("test_gps_run", ("src/gps.c", "test/test_gps.c"), extras=("nmea",))),
]}


def _datasheet_summary(module_id: str) -> dict | None:
    from . import datasheets
    return datasheets.summary(module_id)


def module_info(m: Module) -> dict:
    return {
        "id": m.id, "title": m.title, "kind": m.kind, "protocol": m.protocol, "tier": m.tier,
        "summary": m.summary, "default_address": m.default_address,
        "addresses": list(m.addresses), "sim": list(m.sim), "gaps": m.gaps,
        "default_cs": m.default_cs, "datasheet": _datasheet_summary(m.id),
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
            Option("corpus", "str", "fuzz/corpus", "Example inputs to start from (libFuzzer harnesses)"),
        ),
        limits="Host-side fuzzing of the logic, not full-system fuzzing of the firmware image.",
    ),
    TestKind(
        "fault", "Fault injection (instruction skip)",
        "Skips one instruction at a time inside a function and reports any wrong-PIN style bypass.",
        "security", ("arm-none-eabi-gcc", "qemu", "arm-gdb"),
        options=(
            Option("probe", "list", ["fault/probe.c"],
                   "Probes, one security property each: a probe fails only if that property breaks",
                   required=True),
            Option("sources", "list", ["src/auth.c"], "Code under attack (also built into the probe)"),
            Option("target", "str", "src/auth.c", "Source file whose instructions are skipped",
                   required=True),
            Option("functions", "list", [], "Sweep only these functions (default: all in the target)"),
            Option("elf", "list", [], "Probe images your own build already produced, instead of `probe`"),
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
