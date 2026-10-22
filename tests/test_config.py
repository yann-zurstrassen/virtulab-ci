"""virtulab.yml parsing, validation, catalog and board check. No toolchain needed."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from virtulab import VirtulabError, catalog, cigen, config, yamlite
from virtulab.check import check
from virtulab.config import ModuleSpec, ProjectConfig


class YamlTest(unittest.TestCase):
    def test_round_trip_keeps_structure_and_hex(self):
        data = {"version": 1, "modules": {"t": {"model": "tmp108", "address": yamlite.Hex(0x48)}},
                "tests": {"unit": {}, "fuzz": {"sources": ["a.c", "b c.c"], "seconds": 5}},
                "text": "a: b", "flag": False, "none": None}
        text = yamlite.dumps(data)
        self.assertIn("address: 0x48", text)
        back = yamlite.loads(text)
        self.assertEqual(back["modules"]["t"]["address"], 0x48)
        self.assertEqual({**back, "modules": None}, {**data, "modules": None})

    def test_lists_of_mappings_and_comments(self):
        parsed = yamlite.loads("a: 1 # note\nitems:\n  - x\n  - k: v\n    z: [1, 2]\n  - { q: '#1' }\n")
        self.assertEqual(parsed, {"a": 1, "items": ["x", {"k": "v", "z": [1, 2]}, {"q": "#1"}]})

    def test_errors_name_the_line(self):
        for bad in ("a: [1, 2\n", "a: 1\na: 2\n", "a:\n\tb: 1\n", "just text\n"):
            with self.assertRaises(yamlite.YamlError, msg=bad):
                yamlite.loads(bad)


class ConfigTest(unittest.TestCase):
    def test_defaults_are_unit_and_footprint(self):
        cfg = config.from_dict({"board": "lm3s6965evb"})
        self.assertEqual(list(cfg.tests), ["unit", "footprint"])

    def test_typo_gets_a_suggestion(self):
        with self.assertRaisesRegex(VirtulabError, "Did you mean 'board'"):
            config.from_dict({"boadr": "lm3s6965evb"})
        with self.assertRaisesRegex(VirtulabError, "Did you mean 'fuzz'"):
            config.from_dict({"tests": {"fuz": {}}})
        with self.assertRaisesRegex(VirtulabError, "Did you mean 'seconds'"):
            config.from_dict({"tests": {"fuzz": {"secs": 3}}})
        with self.assertRaisesRegex(VirtulabError, "Did you mean 'stm32f4_discovery'"):
            config.from_dict({"board": "stm32f4_discovry"})

    def test_tests_can_be_a_list(self):
        cfg = config.from_dict({"tests": ["unit", {"fuzz": {"seconds": 3}}]})
        self.assertEqual(cfg.tests, {"unit": {}, "fuzz": {"seconds": 3}})

    def test_dump_and_load_are_inverse(self):
        cfg = ProjectConfig(board="stm32f4_discovery",
                            modules={"temp": ModuleSpec("temp", "tmp108", "i2c1", 0x48)},
                            tests={"unit": {}, "coverage": {"min_lines": 80}})
        back = config.from_dict(yamlite.loads(cfg.dumps()))
        self.assertEqual(back.to_dict(), cfg.to_dict())

    def test_modules_become_renode_lines(self):
        cfg = config.from_dict({"board": "stm32f4_discovery", "modules": {
            "temp": {"model": "tmp108", "bus": "i2c1", "address": 0x49},
            "baro": {"model": "bmp180", "bus": "i2c2"}}})
        self.assertEqual(config.renode_repl(cfg).splitlines(),
                         ["temp: VirtuLab.TMP108 @ i2c1 0x49", "baro: Sensors.BMP180 @ i2c2 0x77"])
        self.assertIsNone(config.renode_repl(ProjectConfig()))


class CheckTest(unittest.TestCase):
    def check(self, **data):
        return check(config.from_dict(data), tools=False)

    def test_valid_wiring_passes(self):
        res = self.check(board="stm32f4_discovery", modules={
            "t": {"model": "tmp108", "bus": "i2c1", "address": 0x48},
            "b": {"model": "bmp180", "bus": "i2c1"}})
        self.assertTrue(res.ok, res.to_text())

    def test_sensor_on_qemu_board_is_an_error(self):
        res = self.check(board="lm3s6965evb", modules={"t": {"model": "tmp108", "bus": "i2c1"}})
        self.assertIn("cannot host modules", res.to_text())
        self.assertFalse(res.ok)

    def test_wrong_bus_protocol_and_unknown_bus(self):
        res = self.check(board="stm32f4_discovery", modules={"t": {"model": "tmp108", "bus": "spi1"}})
        self.assertIn("speaks I²C", res.to_text())
        res = self.check(board="stm32f4_discovery", modules={"t": {"model": "tmp108", "bus": "i2c9"}})
        self.assertIn("no bus 'i2c9'", res.to_text())

    def test_address_conflict_and_invalid_address(self):
        res = self.check(board="stm32f4_discovery", modules={
            "a": {"model": "tmp108", "bus": "i2c1", "address": 0x48},
            "b": {"model": "tmp108", "bus": "i2c1", "address": 0x48}})
        self.assertIn("already used by 'a'", res.to_text())
        res = self.check(board="stm32f4_discovery", modules={"a": {"model": "tmp108", "bus": "i2c1", "address": 0x10}})
        self.assertIn("can only be at", res.to_text())
        # the same address on another bus is fine
        res = self.check(board="stm32f4_discovery", modules={
            "a": {"model": "tmp108", "bus": "i2c1"}, "b": {"model": "tmp108", "bus": "i2c2"}})
        self.assertTrue(res.ok, res.to_text())

    def test_fault_injection_needs_a_qemu_board(self):
        res = self.check(board="stm32f4_discovery", tests={"unit": {}, "fault": {}})
        self.assertIn("needs a QEMU board", res.to_text())

    def test_missing_files_are_reported_with_a_root(self):
        cfg = config.from_dict({"board": "lm3s6965evb", "tests": {"fuzz": {}}})
        with TemporaryDirectory() as tmp:
            res = check(cfg, Path(tmp), tools=False)
        self.assertIn("harness file 'fuzz/fuzz.c' not found", res.to_text())

    def test_missing_tools_are_flagged_so_docker_can_take_over(self):
        cfg = config.from_dict({"board": "lm3s6965evb"})
        from unittest import mock
        with mock.patch("virtulab.check._tool", return_value=None):
            res = check(cfg)
            warned = check(cfg, tools="warn")
        self.assertTrue(res.only_missing_tools)
        self.assertTrue(warned.ok)
        self.assertTrue(warned.warnings)


class CatalogTest(unittest.TestCase):
    def test_every_board_and_module_is_consistent(self):
        info = catalog.as_json()
        self.assertGreaterEqual(len(info["boards"]), 9)
        for module in catalog.MODULES.values():
            self.assertIn(module.protocol, catalog.PROTOCOLS)
            if module.addresses:
                self.assertIn(module.default_address, module.addresses)
        for board in info["boards"]:
            for protocol in board["protocols"]:
                self.assertIn(protocol, catalog.PROTOCOLS)
        self.assertEqual({t["id"] for t in info["tests"]}, {"unit", "footprint", "coverage", "fuzz", "fault"})

    def test_ci_files_reference_the_one_line_action(self):
        cfg = config.from_dict({"tests": {"unit": {}, "fuzz": {}}})
        path, text = cigen.render(cfg, "github")
        self.assertEqual(path, ".github/workflows/virtulab.yml")
        self.assertIn(f"uses: {cigen.ACTION}", text)
        self.assertIn("fetch-depth: 0", text)
        self.assertIn("fuzz/crashes", text)
        workflow = yamlite.loads(text)
        steps = workflow["jobs"]["virtulab"]["steps"]
        self.assertEqual([s.get("uses") for s in steps],
                         ["actions/checkout@v4", cigen.ACTION, "actions/upload-artifact@v4"])
        self.assertEqual(workflow["permissions"]["pull-requests"], "write")
        self.assertIn("fuzz/crashes", steps[2]["with"]["path"])
        self.assertEqual(steps[2]["with"]["if-no-files-found"], "ignore")
        path, text = cigen.render(cfg, "gitlab")
        self.assertEqual(path, ".gitlab-ci.yml")
        self.assertIn("virtulab run --baseline", text)
        self.assertIn("virtulab", yamlite.loads(text))


if __name__ == "__main__":
    unittest.main()
