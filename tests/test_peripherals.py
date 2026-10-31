"""Peripherals defined in virtulab.yml, analog inputs, and sensor input on a timeline."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from virtulab import VirtulabError, config, peripherals
from virtulab.check import check
from virtulab.cli import main
from virtulab.scenarios import Case, _fault_verdict, _verdict, parse_cases
from tests.test_project import HAVE_RENODE, HAVE_TOOLS

REPO = Path(__file__).resolve().parent.parent
BASE = {"board": "stm32f4_discovery", "tests": {"unit": {}}}
TANK = {"bus": "i2c1", "address": 0x55, "registers": [{"name": "LEVEL", "at": 1, "size": 2, "access": "ro"}]}


TANK_FULL = {"bus": "i2c1", "address": 0x55, "registers": [
    {"name": "ID", "at": 0, "reset": 0xA5, "access": "ro"}, {"name": "LEVEL", "at": 1, "size": 2, "access": "ro"},
    {"name": "LIMIT", "at": 3, "size": 2, "reset": 800}]}


def cfg(**extra):
    return config.from_dict({**BASE, **extra})


class ConfigTest(unittest.TestCase):
    def test_bad_rules_are_explained(self):
        for bad in ({"when": "PA1", "set": "PA2"}, {"when": "PA1", "is": "maybe", "set": "PA2", "to": 1},
                    {"when": "PA1", "set": "PA2", "to": "yes"}, {"when": "PA1", "for": "soon", "set": "PA2", "to": 1},
                    {"when": "PA1", "set": "PA2", "to": 1, "colour": "red"}):
            with self.assertRaises(VirtulabError, msg=str(bad)):
                cfg(rules=[bad])

    def test_the_board_check_catches_bad_rule_targets(self):
        def errors(rule):
            return " ".join(f.message for f in check(cfg(rules=[rule]), None, tools=False).errors)
        self.assertIn("pin name", errors({"when": "Z9", "set": "PA2", "to": 1}))
        self.assertIn("not a module", errors({"when": "PA1", "set": "ghost.X", "to": 1}))

    def test_scenario_verdicts_keep_a_crash_apart_from_a_failure(self):
        case = Case("c", [], None, ["HEATER=OFF"], ["HEATER=ON"])
        self.assertEqual(_fault_verdict(case, "HEATER=OFF", 0), "held")
        self.assertEqual(_fault_verdict(case, "HEATER=ON", 0), "broken")
        self.assertEqual(_fault_verdict(case, "", 0), "no_result")
        self.assertEqual(_fault_verdict(case, "", 250), "no_result")
        self.assertEqual(_verdict(case, "", None), "no_result")

    def test_a_case_with_faults_must_name_what_must_not_happen(self):
        c = cfg(tests={"scenarios": {"sources": ["a.c"], "cases": {"x": {"expect": "OK", "faults": ["1ms"]}}}})
        with self.assertRaises(VirtulabError):
            parse_cases(c)

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

    def test_a_fault_during_a_sensor_scenario_is_caught_at_its_source(self):
        root = self.project("oven-controller")
        path = root / "virtulab.yml"
        path.write_text(path.read_text().replace('cflags: "-std=c99 -Wall -Wextra"',
                                                 'cflags: "-std=c99 -Wall -Wextra -DOVEN_HARDENED=0"'))
        self.assertEqual(main(["run", "-C", str(root), "--only", "fault"]), 1)
        sarif = json.loads((root / ".virtulab" / "evidence" / "results.sarif").read_text())
        files = {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
                 for r in sarif["runs"][0]["results"] if r["ruleId"] == "VL-FAULT"}
        self.assertEqual(files, {"src/oven.c"})

    def test_the_hardened_oven_survives_the_sweep(self):
        self.assertEqual(main(["run", "-C", str(self.project("oven-controller")), "--only", "fault"]), 0)

    def test_a_renode_sweep_that_finds_nothing_to_attack_fails(self):
        root = self.project("oven-controller")
        path = root / "virtulab.yml"
        path.write_text(path.read_text().replace("target: src/oven.c", "target: src/ovne.c"))
        self.assertEqual(main(["run", "-C", str(root), "--only", "fault"]), 1)
        self.assertIn("inconclusive", (root / ".virtulab" / "report.md").read_text())

    def run_scenarios(self, root: Path) -> tuple[int, dict]:
        code = main(["run", "-C", str(root), "--only", "scenarios"])
        return code, json.loads((root / ".virtulab" / "evidence" / "evidence.json").read_text())

    def plain_controller(self) -> Path:
        root = self.project("oven-controller")
        path = root / "virtulab.yml"
        path.write_text(path.read_text().replace('cflags: "-std=c99 -Wall -Wextra"',
                                                 'cflags: "-std=c99 -Wall -Wextra -DCONTROLLER_HARDENED=0"'))
        return root

    def test_the_hardened_controller_never_leaves_the_heater_on(self):
        code, record = self.run_scenarios(self.project("oven-controller"))
        self.assertEqual(code, 0)
        self.assertEqual(record["checks"][0]["data"]["bypass"], 0)
        self.assertGreater(record["checks"][0]["data"]["swept"], 0)

    def test_a_moment_only_bug_needs_a_timed_fault(self):
        root = self.plain_controller()
        code, _ = self.run_scenarios(root)
        self.assertEqual(code, 1)
        sarif = json.loads((root / ".virtulab" / "evidence" / "results.sarif").read_text())
        texts = [r["message"]["text"] for r in sarif["runs"][0]["results"] if r["ruleId"] == "VL-FAULT"]
        timed = {t.split("`")[1] for t in texts if "after 0 ms" not in t}
        untimed = {t.split("`")[1] for t in texts if "after 0 ms" in t}
        self.assertTrue(timed - untimed, "timed faults must reach what an untimed sweep cannot")

    def test_a_scenario_that_goes_wrong_without_any_fault_fails(self):
        root = self.project("oven-controller")
        path = root / "virtulab.yml"
        path.write_text(path.read_text().replace("stimulus_file: inputs/normal_warmup.csv\n        expect: HEATER=ON",
                                                 "stimulus_file: inputs/normal_warmup.csv\n        expect: HEATER=OFF"))
        self.assertEqual(self.run_scenarios(root)[0], 1)

    def test_a_rule_lets_the_world_react_to_a_pin(self):
        code, record = self.run_scenarios(self.project("motor-limit-switch"))
        self.assertEqual(code, 0)
        self.assertGreater(record["checks"][0]["data"]["swept"], 0)

    def test_a_motor_left_running_by_one_skip_is_caught(self):
        root = self.project("motor-limit-switch")
        path = root / "virtulab.yml"
        path.write_text(path.read_text().replace('cflags: "-std=c99 -Wall -Wextra"',
                                                 'cflags: "-std=c99 -Wall -Wextra -DGATE_HARDENED=0"'))
        self.assertEqual(self.run_scenarios(root)[0], 1)

    def test_a_users_own_renode_model_is_loaded_as_it_is(self):
        root = self.project("custom-sensor")
        source = peripherals.model_source(peripherals.parse_peripheral("tank", TANK_FULL)).replace("Custom_tank", "MyTank")
        (root / "models").mkdir()
        (root / "models/MyTank.cs").write_text(source)
        (root / "models/tank.repl").write_text("tank: VirtuLab.MyTank @ i2c1 0x55\n")
        path = root / "virtulab.yml"
        text = path.read_text()
        head, _, tail = text.partition("peripherals:\n")
        path.write_text(head + "models: [models/MyTank.cs]\nrepl: models/tank.repl\n" + tail[tail.index("tests:"):])
        (root / "test/test_tank.c").write_text((root / "test/test_tank.c").read_text()
                                               .replace("    RUN_TEST(test_the_alarm_follows_the_filling_trace);\n", ""))
        self.assertEqual(self.run_only_unit(root), 0)

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
