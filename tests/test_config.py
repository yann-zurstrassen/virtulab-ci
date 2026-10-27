"""virtulab.yml parsing, validation, catalog and board check. No toolchain needed."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from virtulab import MONITOR_MARK, VirtulabError, catalog, cigen, config, yamlite
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
        repl, _, monitor = config.renode_repl(cfg).partition(MONITOR_MARK)
        self.assertEqual(repl.splitlines(),
                         ["temp: VirtuLab.TMP108 @ i2c1 0x49", "baro: Sensors.BMP180 @ i2c2 0x77"])
        self.assertEqual(monitor.split(), ["sysbus.nvic", "Frequency", "16000000"])  # the clock all models share
        self.assertIsNone(config.renode_repl(ProjectConfig()))

    def test_spi_and_uart_modules_become_renode_lines(self):
        cfg = config.from_dict({"board": "stm32f4_discovery", "modules": {
            "accel": {"model": "adxl345", "bus": "spi2", "cs": "pb12"},
            "other": {"model": "adxl345", "bus": "spi2", "cs": "PC3"},
            "gps": {"model": "nmea_gps", "bus": "usart3"}}})
        repl, _, monitor = config.renode_repl(cfg).partition(MONITOR_MARK)
        self.assertEqual(repl.splitlines(), [
            "spi2_mux: SPI.SPIMultiplexer @ spi2", "accel: VirtuLab.ADXL345 @ spi2_mux 0",
            "other: VirtuLab.ADXL345 @ spi2_mux 1", "gps: VirtuLab.NMEAGps @ sysbus",
            "gpioPortB:", "    12 -> spi2_mux@0", "gpioPortC:", "    3 -> spi2_mux@1"])
        self.assertEqual([c for c in monitor.splitlines() if c], [
            "sysbus.nvic Frequency 16000000",
            "sysbus.spi2.spi2_mux SetActiveLow 0", "sysbus.spi2.spi2_mux OnGPIO 0 true",
            "sysbus.spi2.spi2_mux SetActiveLow 1", "sysbus.spi2.spi2_mux OnGPIO 1 true",
            'emulation CreateUARTHub "vl_gps_link"', "connector Connect sysbus.usart3 vl_gps_link",
            "connector Connect sysbus.gps vl_gps_link"])
        self.assertEqual(config.sim_path(cfg, "accel"), "sysbus.spi2.spi2_mux.accel")
        self.assertEqual(config.sim_path(cfg, "gps"), "sysbus.gps")

    def test_chip_select_is_kept_in_the_file(self):
        cfg = config.from_dict({"modules": {"a": {"model": "adxl345", "bus": "spi1", "cs": "PA4"}}})
        self.assertIn("a: { model: adxl345, bus: spi1, cs: PA4 }", cfg.dumps())
        self.assertEqual(config.from_dict(yamlite.loads(cfg.dumps())).modules["a"].cs, "PA4")


class DumpIsStandardYamlTest(unittest.TestCase):
    def test_values_that_standard_yaml_would_read_as_aliases_are_quoted(self):
        text = yamlite.dumps(config.ProjectConfig().to_dict())
        self.assertIn('sources: ["**/*.c"]', text)
        self.assertEqual(yamlite.loads(text)["build"]["sources"], ["**/*.c"])
        for value in ("*.c", "@x", "**/a"):
            self.assertEqual(yamlite.loads("v: " + yamlite.dumps({"k": value}).split(": ", 1)[1])["v"], value)
            self.assertTrue(yamlite.dumps({"k": value}).split(": ", 1)[1].startswith('"'), value)


class CheckTest(unittest.TestCase):
    def check(self, **data):
        return check(config.from_dict(data), tools=False)

    def test_valid_wiring_passes(self):
        res = self.check(board="stm32f4_discovery", modules={
            "t": {"model": "tmp108", "bus": "i2c1", "address": 0x48},
            "b": {"model": "bmp180", "bus": "i2c1"}})
        self.assertTrue(res.ok, res.to_text())

    def test_a_module_cannot_take_a_name_the_board_already_uses(self):
        for name in ("flash", "sram", "crc", "rcc", "i2c1", "timer3"):
            res = self.check(board="stm32f4_discovery", modules={name: {"model": "w25q128", "bus": "spi1"}})
            self.assertFalse(res.ok, name)
            self.assertIn("already a peripheral", res.to_text())
        res = self.check(board="stm32f4_discovery", modules={"storage": {"model": "w25q128", "bus": "spi1"}})
        self.assertTrue(res.ok, res.to_text())

    def test_the_readme_example_is_a_valid_configuration(self):
        import re
        from pathlib import Path
        from virtulab import yamlite
        readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
        block = re.search(r"```yaml\n(version: 1\n.*?)```", readme, re.S).group(1)
        res = check(config.from_dict(yamlite.loads(block)), tools=False)
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

    def test_spi_and_uart_modules_pass_on_the_right_buses(self):
        res = self.check(board="stm32f4_discovery", modules={
            "accel": {"model": "adxl345", "bus": "spi1"}, "gps": {"model": "nmea_gps", "bus": "usart1"}})
        self.assertTrue(res.ok, res.to_text())
        res = self.check(board="stm32f4_discovery", modules={"a": {"model": "adxl345", "bus": "i2c1"}})
        self.assertIn("speaks SPI", res.to_text())
        res = self.check(board="stm32f4_discovery", modules={"g": {"model": "nmea_gps", "bus": "spi1"}})
        self.assertIn("speaks UART", res.to_text())

    def test_uart_carries_one_device_but_spi_can_share_with_distinct_chip_selects(self):
        res = self.check(board="stm32f4_discovery", modules={
            "a": {"model": "nmea_gps", "bus": "usart1"}, "b": {"model": "nmea_gps", "bus": "usart1"}})
        self.assertIn("usart1 already has 'a'", res.to_text())
        res = self.check(board="stm32f4_discovery", modules={
            "a": {"model": "adxl345", "bus": "spi1"}, "b": {"model": "adxl345", "bus": "spi1", "cs": "PB0"}})
        self.assertTrue(res.ok, res.to_text())
        res = self.check(board="stm32f4_discovery", modules={
            "a": {"model": "adxl345", "bus": "spi1"}, "b": {"model": "adxl345", "bus": "spi2"}})
        self.assertIn("chip-select pin PA4 is already used by 'a'", res.to_text())
        res = self.check(board="stm32f4_discovery", modules={"a": {"model": "adxl345", "bus": "spi1", "cs": "PA5"}})
        self.assertIn("carries the SPI1 clock", res.to_text())

    def test_chip_select_must_be_a_pin_name(self):
        res = self.check(board="stm32f4_discovery", modules={
            "a": {"model": "adxl345", "bus": "spi1", "cs": "A4"}})
        self.assertIn("not a pin name", res.to_text())

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
