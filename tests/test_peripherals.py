"""Peripherals defined in virtulab.yml, analog inputs, and sensor input on a timeline."""

import shutil
import tempfile
import unittest
from pathlib import Path

from virtulab import VirtulabError, config, peripherals
from virtulab.check import check
from virtulab.cli import main
from tests.test_project import HAVE_RENODE, HAVE_TOOLS

REPO = Path(__file__).resolve().parent.parent
BASE = {"board": "stm32f4_discovery", "tests": {"unit": {}}}
TANK = {"bus": "i2c1", "address": 0x55, "registers": [{"name": "LEVEL", "at": 1, "size": 2, "access": "ro"}]}


def cfg(**extra):
    return config.from_dict({**BASE, **extra})


class ConfigTest(unittest.TestCase):
    def test_bad_definitions_are_explained(self):
        for bad in ({"bus": "i2c1"},
                    {**TANK, "registers": []},
                    {**TANK, "registers": [{"name": "A", "at": 0, "size": 3}]},
                    {**TANK, "registers": [{"name": "A", "at": 0, "reset": 256}]},
                    {**TANK, "registers": [{"name": "A", "at": 0, "size": 2}, {"name": "B", "at": 1}]},
                    {**TANK, "registers": [{"name": "A", "at": 0}, {"name": "A", "at": 1}]},
                    {**TANK, "registers": [{"name": "A", "at": 255, "size": 2}]},
                    {**TANK, "colour": "red"}):
            with self.assertRaises(VirtulabError, msg=str(bad)):
                cfg(peripherals={"tank": bad})

    def test_bad_analog_is_explained(self):
        for name, spec in (("adc9", {"inputs": {"a": 1}}), ("adc1", {"inputs": {}}), ("adc1", {"inputs": {"a": 19}}),
                           ("adc1", {"inputs": {"a": 1, "b": 1}}), ("adc1", {"vref": 0, "inputs": {"a": 1}})):
            with self.assertRaises(VirtulabError, msg=str(spec)):
                cfg(analog={name: spec})

    def test_bad_stimulus_is_explained(self):
        for bad in ({"at": "soon", "set": "tank.LEVEL", "value": 1}, {"at": "1ms", "set": "tank", "value": 1},
                    {"at": "1ms", "set": "tank.LEVEL", "value": "hot"}, {"at": "1ms", "set": "tank.LEVEL"}):
            with self.assertRaises(VirtulabError, msg=str(bad)):
                cfg(peripherals={"tank": TANK}, stimulus=[bad])

    def test_the_board_check_catches_wiring_and_targets(self):
        def errors(**extra):
            return " ".join(f.message for f in check(cfg(**extra), None, tools=False).errors)
        self.assertIn("has no register", errors(peripherals={"tank": TANK},
                                                stimulus=[{"at": "1ms", "set": "tank.NOPE", "value": 1}]))
        self.assertIn("not a module", errors(stimulus=[{"at": "1ms", "set": "ghost.X", "value": 1}]))
        self.assertIn("I²C", errors(peripherals={"tank": {**TANK, "bus": "spi1"}}))
        self.assertIn("already used", errors(peripherals={"a": TANK, "b": TANK}))
        self.assertIn("has no input", errors(modules={"t": {"model": "tmp108", "bus": "i2c1"}},
                                             stimulus=[{"at": "1ms", "set": "t.Humidity", "value": 1}]))
        self.assertIn("has no input", errors(analog={"adc1": {"inputs": {"a": 1}}},
                                             stimulus=[{"at": "1ms", "set": "adc1.b", "value": 1}]))

    def test_a_project_can_be_written_back(self):
        first = cfg(peripherals={"tank": TANK}, analog={"adc1": {"inputs": {"a": 1}}},
                    stimulus=[{"at": "1ms", "set": "tank.LEVEL", "value": 1}])
        again = config.from_dict(first.to_dict())
        self.assertEqual(again.peripherals, first.peripherals)
        self.assertEqual(again.analog, first.analog)
        self.assertEqual(again.stimulus, first.stimulus)

    def test_a_trace_is_read_and_merged_in_time_order(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "t.csv").write_text("time_ms,tank.LEVEL\n20,2\n5,1\n")
        c = cfg(peripherals={"tank": TANK}, stimulus=[{"at": "10ms", "set": "tank.LEVEL", "value": 9}],
                stimulus_file="t.csv")
        self.assertEqual([s.value for s in config.all_stimulus(c, tmp)], [1.0, 9.0, 2.0])

    def test_a_trace_with_junk_is_refused(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "t.csv").write_text("time_ms,tank.LEVEL\n20,hot\n")
        with self.assertRaises(VirtulabError):
            peripherals.read_trace(tmp / "t.csv")


@unittest.skipUnless(HAVE_TOOLS and HAVE_RENODE, "the toolchain and Renode are required")
class EmulationTest(unittest.TestCase):
    def project(self, name: str) -> Path:
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        root = tmp / name
        shutil.copytree(REPO / "examples" / name, root, ignore=shutil.ignore_patterns(".virtulab"))
        return root

    def run_only_unit(self, root: Path) -> int:
        return main(["run", "-C", str(root), "--only", "unit"])

    def test_the_custom_sensor_follows_its_trace(self):
        self.assertEqual(self.run_only_unit(self.project("custom-sensor")), 0)

    def test_a_driver_with_the_wrong_byte_order_is_caught(self):
        root = self.project("custom-sensor")
        path = root / "src/tank.c"
        path.write_text(path.read_text().replace("(raw[0] << 8) | raw[1]", "(raw[1] << 8) | raw[0]"))
        self.assertEqual(self.run_only_unit(root), 1)

    def test_the_oven_controller_follows_the_temperature_profile(self):
        self.assertEqual(self.run_only_unit(self.project("oven-controller")), 0)

    def test_an_oven_that_ignores_the_broken_wire_is_caught(self):
        root = self.project("oven-controller")
        path = root / "src/oven.c"
        path.write_text(path.read_text().replace("if (counts >= OVEN_OPEN_COUNTS) {", "if (0) {"))
        self.assertEqual(self.run_only_unit(root), 1)

    def test_a_late_alarm_is_caught_by_the_profile(self):
        root = self.project("oven-controller")
        path = root / "include/oven.h"
        path.write_text(path.read_text().replace("#define OVEN_LIMIT_DEC 1800", "#define OVEN_LIMIT_DEC 2000"))
        self.assertEqual(self.run_only_unit(root), 1)

    def test_runs_give_the_same_test_results(self):
        root = self.project("oven-controller")
        results = []
        for _ in range(2):
            self.assertEqual(self.run_only_unit(root), 0)
            text = (root / ".virtulab" / "evidence" / "junit.xml").read_text()
            results.append(text)
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
