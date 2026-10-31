"""The first-day mistakes of someone bringing their own driver, and what the tool tells them.

A project with one SHT31 on I2C1 and a hand-written driver. Each test breaks it in a way a real user
would, and checks that the output points at the cause and not just at the symptom.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from virtulab import emulator
from .test_project import HAVE_RENODE, HAVE_TOOLS, run_cli

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sensirion-sht3x"

DRIVER = """\
#include "mysht.h"
{include}
#include "i2c.h"

#define ADDR {address}

int mysht_read(int32_t *mdegc, int32_t *mpct)
{{
    uint8_t cmd[2] = {{0x24, 0x00}};
    uint8_t raw[6];
    if (i2c1_write(ADDR, cmd, 2) != I2C_OK) return -1;
    {wait}
    if (i2c1_read(ADDR, raw, 6) != I2C_OK) return -2;
    uint16_t t = (uint16_t)((raw[0] << 8) | raw[1]);
    uint16_t h = (uint16_t)((raw[3] << 8) | raw[4]);
    *mdegc = -45000 + (int32_t)(175000LL * t / 65535);
    *mpct = (int32_t)(100000LL * h / 65535);
    return 0;
}}
"""

TEST = """\
#include "clock.h"
#include "i2c.h"
#include "mysht.h"
#include "virtulab.h"
#include "virtulab_test.h"

static void test_reads_room_temperature(void)
{{
    int32_t t = 0, h = 0;
    {clock}
    i2c1_init();
    vl_sim("sysbus.i2c1.air Temperature 23.5");
    vl_sim("sysbus.i2c1.air Humidity 40");
    TEST_ASSERT_EQUAL_INT(0, mysht_read(&t, &h));
    TEST_ASSERT_INT_WITHIN(100, 23500, t);
    TEST_ASSERT_INT_WITHIN(100, 40000, h);
}}

int main(void)
{{
    UNITY_BEGIN();
    RUN_TEST(test_reads_room_temperature);
    return UNITY_END();
}}
"""

CONFIG = """\
version: 1
board: stm32f4_discovery
build:
  sources: ["src/*.c", "test/*.c"]
  include: [include]
timeout: 10s
modules:
  {name}: {{ model: sht31, bus: i2c1 }}
tests:
  unit: {{}}
"""


class FakeLogTest(unittest.TestCase):
    """What is read out of Renode's log, with no emulator involved."""

    PERIPHERALS = ("air: VirtuLab.SHT31 @ i2c1 0x44\nbaro: Sensors.BMP180 @ i2c1 0x77\n"
                   f"{emulator.MONITOR_MARK}\nsysbus.nvic Frequency 1\n")

    def warnings(self, log: str, peripherals=PERIPHERALS):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "renode.log"
            path.write_text(log)
            return emulator.model_warnings(path, peripherals)

    def test_only_the_declared_models_speak_and_each_line_once(self):
        log = (
            "[12:00:00.1] [WARNING] gpioPortB: Unhandled write to offset 0x4\n"
            "[12:00:00.2] [WARNING] i2c1.air: Read before the measurement is done: the chip would not acknowledge\n"
            "\x1b[33m(virtulab) \x1b[0m[12:00:00.2] [WARNING] i2c1.air: Read before the measurement is done: "
            "the chip would not acknowledge (5)\n"
            "[12:00:00.3] [WARNING] i2c1.other: not one of ours\n"
        )
        self.assertEqual(self.warnings(log),
                         ["air: Read before the measurement is done: the chip would not acknowledge"])

    def test_a_wrong_address_names_the_address_the_project_declares(self):
        log = "[12:00:00.1] [WARNING] i2c1: Child address changed to 0x45, but target is not registered\n"
        self.assertEqual(self.warnings(log),
                         ["i2c1: nothing answers at 0x45 (the project declares air at 0x44, baro at 0x77)"])
        self.assertEqual(self.warnings(log.replace("i2c1:", "i2c2:")),
                         ["i2c2: nothing answers at 0x45 (no module is declared on this bus)"])

    def test_nothing_without_peripherals_or_a_log(self):
        self.assertEqual(self.warnings("[1] [WARNING] i2c1.air: x\n", peripherals=None), [])
        self.assertEqual(emulator.model_warnings(Path("/nonexistent/renode.log"), self.PERIPHERALS), [])


@unittest.skipUnless(HAVE_TOOLS and HAVE_RENODE, "the toolchain and Renode are required")
class MistakesRunTest(unittest.TestCase):
    def project(self, *, name="air", address="0x44", wait="delay_ms(16);", clock="clock_init();") -> Path:
        root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, root)
        for folder in ("src", "include"):
            shutil.copytree(EXAMPLE / folder, root / folder)
        (root / "test").mkdir()
        (root / "include" / "mysht.h").write_text(
            "#include <stdint.h>\nint mysht_read(int32_t *mdegc, int32_t *mpct);\n")
        include = '#include "clock.h"' if "delay_ms" in wait else ""
        (root / "src" / "mysht.c").write_text(DRIVER.format(include=include, address=address, wait=wait))
        (root / "test" / "test_main.c").write_text(TEST.format(clock=clock))
        (root / "virtulab.yml").write_text(CONFIG.format(name=name))
        return root

    def run_unit(self, root: Path):
        return run_cli("run", "-C", str(root), "--only", "unit")

    def test_the_correct_driver_passes_and_the_run_is_quiet(self):
        code, out = self.run_unit(self.project())
        self.assertEqual(code, 0, out)
        self.assertNotIn("sensor models reported", out)

    def test_a_module_named_like_a_board_peripheral_is_refused_before_the_emulator_starts(self):
        code, out = self.run_unit(self.project(name="flash"))
        self.assertNotEqual(code, 0)
        self.assertIn("'flash' is already a peripheral of stm32f4_discovery", out)
        self.assertNotIn("Emulating", out)

    def test_a_driver_that_does_not_wait_is_told_the_result_was_not_ready(self):
        root = self.project(wait="")
        code, out = self.run_unit(root)
        self.assertEqual(code, 1, out)
        self.assertIn("air: Read before the measurement is done", out)
        self.assertIn("What the sensor models reported", (root / ".virtulab" / "report.md").read_text())

    def test_a_driver_at_the_wrong_address_is_told_which_address_the_project_declares(self):
        root = self.project(address="0x45")
        code, out = self.run_unit(root)
        self.assertEqual(code, 1, out)
        self.assertIn("i2c1: nothing answers at 0x45 (the project declares air at 0x44)", out)

    def test_a_hang_is_reported_with_the_place_it_is_stuck(self):
        root = self.project(clock="")  # delay_ms() spins forever when SysTick was never started
        code, out = self.run_unit(root)
        self.assertEqual(code, 1, out)
        self.assertIn("The CPU was still in delay_ms (src/clock.c:", out)
        self.assertIn("The CPU was still running in `delay_ms", (root / ".virtulab" / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
