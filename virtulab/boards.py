"""Emulated target boards. Every entry here is exercised by tests/test_e2e.py.

QEMU boards are fast and CPU-accurate but model few peripherals. Renode boards
model the SoC peripherals (GPIO, I2C, SPI, USART, ...) and accept extra
devices such as sensors, so drivers can be tested before hardware exists.
"""

from dataclasses import dataclass

from . import VirtulabError

KIB = 1024
MIB = 1024 * KIB

M0 = ("-mcpu=cortex-m0", "-mthumb")
M3 = ("-mcpu=cortex-m3", "-mthumb")
M4F = ("-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard")
M7F = ("-mcpu=cortex-m7", "-mthumb", "-mfpu=fpv5-d16", "-mfloat-abi=hard")


@dataclass(frozen=True)
class Board:
    name: str  # also the QEMU machine name for QEMU boards
    cpu: str
    description: str
    cflags: tuple[str, ...]
    flash_origin: int
    flash_size: int
    ram_origin: int
    ram_size: int
    emulator: str = "qemu"  # "qemu" | "renode"
    platform: str | None = None  # Renode platform description (.repl)
    console: str | None = None  # Renode UART used as the firmware console
    runtime_defines: tuple[str, ...] = ()  # how the runtime reaches the console


BOARDS = {
    board.name: board
    for board in [
        Board("lm3s6965evb", "Cortex-M3", "TI Stellaris LM3S6965", M3,
              0x0000_0000, 256 * KIB, 0x2000_0000, 64 * KIB),
        Board("lm3s811evb", "Cortex-M3", "TI Stellaris LM3S811", M3,
              0x0000_0000, 64 * KIB, 0x2000_0000, 8 * KIB),
        Board("stm32vldiscovery", "Cortex-M3", "ST STM32F100RB", M3,
              0x0800_0000, 128 * KIB, 0x2000_0000, 8 * KIB),
        Board("netduinoplus2", "Cortex-M4F", "ST STM32F405RG", M4F,
              0x0800_0000, 1 * MIB, 0x2000_0000, 128 * KIB),
        Board("microbit", "Cortex-M0", "Nordic nRF51822", M0,
              0x0000_0000, 256 * KIB, 0x2000_0000, 16 * KIB),
        Board("mps2-an385", "Cortex-M3", "Arm MPS2 AN385", M3,
              0x0000_0000, 4 * MIB, 0x2000_0000, 4 * MIB),
        Board("mps2-an386", "Cortex-M4F", "Arm MPS2 AN386", M4F,
              0x0000_0000, 4 * MIB, 0x2000_0000, 4 * MIB),
        Board("mps2-an500", "Cortex-M7F", "Arm MPS2 AN500", M7F,
              0x0000_0000, 4 * MIB, 0x2000_0000, 128 * KIB),
        # Real STM32F407VG limits (1 MiB flash, 128 KiB SRAM), not Renode's larger map.
        Board("stm32f4_discovery", "Cortex-M4F", "ST STM32F407VG Discovery", M4F,
              0x0800_0000, 1 * MIB, 0x2000_0000, 128 * KIB,
              emulator="renode",
              platform="platforms/boards/stm32f4_discovery-kit.repl",
              console="sysbus.usart2",
              runtime_defines=("-DVL_CONSOLE_STM32_USART=0x40004400",)),
    ]
}


def get_board(name: str) -> Board:
    try:
        return BOARDS[name]
    except KeyError:
        raise VirtulabError(
            f"Unknown board '{name}'. Supported boards: {', '.join(BOARDS)}"
        ) from None
