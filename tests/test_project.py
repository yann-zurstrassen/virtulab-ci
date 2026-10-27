"""Project mode end to end: init -> check -> run with the selected tests (QEMU, host cc)."""

import io
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path

from virtulab import config
from virtulab.cli import main
from virtulab.emulator import RENODE
from virtulab.ui.server import make_handler

HAVE_TOOLS = all(shutil.which(t) for t in ("arm-none-eabi-gcc", "qemu-system-arm", "cc", "gcov"))
HAVE_RENODE = bool(shutil.which(RENODE))


def run_cli(*args: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(args))
    return code, out.getvalue()


SENSORS = ["-m", "temp=tmp108@i2c1", "-m", "baro=bmp180@i2c1", "-m", "power=ina219@i2c1",
           "-m", "imu=mpu6050@i2c1", "-m", "air=sht31@i2c1",
           "-m", "accel=adxl345@spi1", "-m", "couple=max31855@spi1", "-m", "storage=w25q128@spi1",
           "-m", "gps=nmea_gps@usart1", "-m", "modem=at_modem@usart3", "-m", "rs485=modbus_rtu@uart4"]

# (file, correct code, broken code, a sample test that must fail because of it)
SEEDED_BUGS = [
    ("src/adxl345.c", "#define COUNTS_PER_G 256", "#define COUNTS_PER_G 128",
     "test_adxl345_measures_gravity_on_the_z_axis"),
    ("src/nmea.c", "if (sum != (uint8_t)((high << 4) | low)) {", "if (0) {",
     "test_gps_rejects_a_corrupted_sentence"),
    ("src/ina219.c", "*milliwatts = (int32_t)raw * 2;", "*milliwatts = (int32_t)raw * 3;",
     "test_ina219_measures_bus_voltage_current_and_power"),
    ("src/mpu6050.c", "MPU6050_REG_POWER_MANAGEMENT_1, 0x00)", "MPU6050_REG_POWER_MANAGEMENT_1, 0x40)",
     "test_mpu6050_measures_gravity"),
    ("src/sht31.c", "if (sht31_crc8(raw[0], raw[1]) != raw[2] || sht31_crc8(raw[3], raw[4]) != raw[5]) {",
     "if (0) {", "test_sht31_rejects_a_result_with_a_bad_checksum"),
    ("src/sht31.c", "    delay_ms(SHT31_CONVERSION_MS);\n", "",
     "test_sht31_measures_temperature_and_humidity"),
    ("src/max31855.c", "if (frame & (1u << 16)) {", "if (0) {", "test_max31855_reports_each_fault"),
    ("src/w25q128.c", "if ((status = w25q128_wait_ready()) != W25Q128_OK) {", "if (0) {",
     "test_w25q128_waits_while_the_chip_is_busy"),
    ("src/w25q128.c", "size_t chunk = len < room ? len : room;",
     "size_t chunk = len < W25Q128_PAGE_SIZE ? len : W25Q128_PAGE_SIZE;",
     "test_w25q128_write_across_a_page_boundary"),
    ("src/modem.c", "*dbm = -113 + 2 * rssi;", "*dbm = -113 + rssi;", "test_modem_signal_strength_in_dbm"),
    ("src/modem.c", "if (rssi == 99) {", "if (0) {", "test_modem_unknown_signal_is_not_a_number"),
    ("src/modbus.c", "if (frame[len - 2u] != (uint8_t)crc || frame[len - 1u] != (uint8_t)(crc >> 8)) {",
     "if (0) {", "test_modbus_rtu_refuses_an_answer_with_a_wrong_crc"),
    ("src/modbus_rtu.c", "(int32_t)(int16_t)registers[1] * 100", "(int32_t)registers[1] * 100",
     "test_modbus_rtu_reads_negative_temperature"),
]


@unittest.skipUnless(HAVE_TOOLS and HAVE_RENODE, "the toolchain and Renode are required")
class SensorRunTest(unittest.TestCase):
    """Sample firmware for every sensor runs green on Renode, and its tests catch seeded driver bugs."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        code, out = run_cli("init", "-C", str(cls.tmp), "-b", "stm32f4_discovery", "-t", "unit",
                            *SENSORS, "--template", "starter", "--ci", "none", "-y")
        assert code == 0, out

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def setUp(self):
        self.snapshot = {p: p.read_text() for p in self.tmp.rglob("*.[ch]")}
        self.addCleanup(lambda: [p.write_text(t) for p, t in self.snapshot.items()])

    def run_unit(self):
        return run_cli("run", "-C", str(self.tmp), "--only", "unit")

    def test_all_eleven_sensors_pass_together(self):
        code, out = self.run_unit()
        self.assertEqual(code, 0, out)
        self.assertNotIn(":FAIL", out)
        for name in ("test_adxl345_disconnected_sensor_is_detected", "test_gps_rejects_a_corrupted_sentence",
                     "test_bmp180_reports_its_chip_id", "test_fan_turns_on_when_hot",
                     "test_ina219_saturates_at_the_end_of_its_shunt_range",
                     "test_mpu6050_must_be_woken_from_sleep", "test_sht31_crc_matches_the_datasheet_example",
                     "test_max31855_detects_a_disconnected_chip", "test_w25q128_write_across_a_page_boundary",
                     "test_modem_starts_and_turns_echo_off", "test_modbus_rtu_reads_temperature_and_humidity"):
            self.assertIn(f"{name}:PASS", out)

    def test_seeded_driver_bugs_are_caught(self):
        for rel, good, bad, _ in SEEDED_BUGS:
            path = self.tmp / rel
            text = path.read_text()
            self.assertIn(good, text, f"{rel}: the sample changed, update the seeded bug")
            path.write_text(text.replace(good, bad))
        code, out = self.run_unit()
        self.assertEqual(code, 1, out)
        for _, _, _, caught_by in SEEDED_BUGS:
            self.assertIn(f"{caught_by}:FAIL", out)


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_init_writes_config_ci_and_sample_firmware(self):
        code, out = run_cli("init", "-C", str(self.tmp), "-b", "stm32f4_discovery",
                            "-m", "temp=tmp108@i2c1:0x48", "-m", "baro=bmp180@i2c1",
                            "-t", "unit,coverage", "--template", "starter", "-y")
        self.assertEqual(code, 0, out)
        cfg = config.load(self.tmp)
        self.assertEqual(cfg.board, "stm32f4_discovery")
        self.assertEqual(set(cfg.modules), {"temp", "baro"})
        self.assertEqual(list(cfg.tests), ["unit", "coverage"])
        for path in ("src/tmp108.c", "src/bmp180.c", "src/i2c.c", "test/test_main.c",
                     ".github/workflows/virtulab.yml"):
            self.assertTrue((self.tmp / path).is_file(), path)
        main_c = (self.tmp / "test/test_main.c").read_text()
        self.assertIn("test_thermostat_run", main_c)
        self.assertIn("test_bmp180_run", main_c)
        self.assertIn("sysbus.i2c1.baro", (self.tmp / "test/test_bmp180.c").read_text())
        self.assertIn("#define BMP180_ADDR 0x77", (self.tmp / "include/bmp180.h").read_text())
        self.assertIn("src/bmp180.c", cfg.tests["coverage"]["exclude"])

    def test_init_writes_sample_firmware_for_spi_and_uart_sensors(self):
        code, out = run_cli("init", "-C", str(self.tmp), "-b", "stm32f4_discovery",
                            "-m", "accel=adxl345@spi1", "-m", "gps=nmea_gps@usart1",
                            "-t", "unit,coverage", "--template", "starter", "-y")
        self.assertEqual(code, 0, out)
        for path in ("src/spi.c", "src/adxl345.c", "src/uart.c", "src/gps.c", "src/nmea.c",
                     "include/stm32f4_regs.h", "test/test_adxl345.c", "test/test_gps.c", "test/test_nmea.c"):
            self.assertTrue((self.tmp / path).is_file(), path)
        self.assertFalse((self.tmp / "src/i2c.c").exists())  # only drivers for the protocols in use
        main_c = (self.tmp / "test/test_main.c").read_text()
        self.assertIn("test_adxl345_run", main_c)
        self.assertIn("test_gps_run", main_c)
        self.assertIn("test_nmea_run", main_c)
        self.assertIn('"sysbus.spi1.spi1_mux.accel"', (self.tmp / "test/test_adxl345.c").read_text())
        self.assertIn('"sysbus.gps"', (self.tmp / "test/test_gps.c").read_text())
        exclude = config.load(self.tmp).tests["coverage"]["exclude"]
        self.assertIn("src/gps.c", exclude)
        self.assertNotIn("src/nmea.c", exclude)  # pure logic is measured on the host

    def test_every_sensor_with_sample_firmware_generates_a_complete_project_alone(self):
        from virtulab import catalog
        board_buses = catalog.board_buses("stm32f4_discovery")
        for module in catalog.MODULES.values():
            if not module.sample:
                continue
            with self.subTest(module.id):
                root = self.tmp / module.id
                bus = next(b for b, kind in board_buses.items() if kind == module.protocol)
                code, out = run_cli("init", "-C", str(root), "-b", "stm32f4_discovery", "-m", f"s={module.id}@{bus}",
                                    "--template", "starter", "--ci", "none", "-y")
                self.assertEqual(code, 0, out)
                suite = module.sample.suite
                self.assertIn(f"{suite}();", (root / "test/test_main.c").read_text())
                tests = "".join(p.read_text() for p in (root / "test").glob("test_*.c"))
                self.assertRegex(tests, rf"int {suite}\(void\)")
                for file in module.sample.hardware:
                    self.assertTrue((root / file).is_file(), file)
                self.assertNotIn("@", "".join(p.read_text() for p in (root / "src").glob("*.c")
                                              if "@" in p.read_text()), "an unreplaced placeholder")

    def test_sample_drivers_refuse_other_buses(self):
        for module in ("a=adxl345@spi2", "a=nmea_gps@uart5"):
            code, _ = run_cli("init", "-C", str(self.tmp), "-b", "stm32f4_discovery",
                              "-m", module, "--template", "starter", "-y")
            self.assertEqual(code, 2, module)
            self.assertFalse((self.tmp / "virtulab.yml").exists())

    def test_sample_drivers_follow_the_configured_chip_select(self):
        code, out = run_cli("init", "-C", str(self.tmp), "-b", "stm32f4_discovery",
                            "-m", "accel=adxl345@spi1", "--template", "starter", "-y")
        self.assertEqual(code, 0, out)
        self.assertIn("#define ADXL345_CS {0x40020000u, 4, 3}", (self.tmp / "include/adxl345.h").read_text())

    def test_init_refuses_bad_combinations_and_overwrites(self):
        code, _ = run_cli("init", "-C", str(self.tmp), "-b", "lm3s6965evb",
                          "-m", "temp=tmp108@i2c1", "-y")
        self.assertEqual(code, 2)  # QEMU boards cannot host sensors
        self.assertFalse((self.tmp / "virtulab.yml").exists())
        self.assertEqual(run_cli("init", "-C", str(self.tmp), "-b", "lm3s6965evb", "-y")[0], 0)
        self.assertEqual(run_cli("init", "-C", str(self.tmp), "-b", "lm3s6965evb", "-y")[0], 2)

    def test_sample_firmware_does_not_clobber_existing_files(self):
        (self.tmp / "src").mkdir()
        (self.tmp / "src/crc.c").write_text("// mine\n")
        code, _ = run_cli("init", "-C", str(self.tmp), "-b", "lm3s6965evb", "--template", "starter", "-y")
        self.assertEqual(code, 2)
        self.assertEqual((self.tmp / "src/crc.c").read_text(), "// mine\n")

    def test_catalog_json_and_text(self):
        code, out = run_cli("catalog", "--json")
        self.assertEqual(code, 0)
        self.assertIn("tmp108", [m["id"] for m in json.loads(out)["modules"]])
        self.assertIn("SENSORS AND MODULES", run_cli("catalog")[1])

    def test_ci_command_prints_and_writes(self):
        run_cli("init", "-C", str(self.tmp), "-b", "lm3s6965evb", "--ci", "gitlab", "-y")
        self.assertTrue((self.tmp / ".gitlab-ci.yml").is_file())
        self.assertIn("uses: yann-zurstrassen/virtulab-ci@v1", run_cli("ci", "-C", str(self.tmp), "--provider", "github")[1])


@unittest.skipUnless(HAVE_TOOLS, "arm-none-eabi-gcc, qemu-system-arm, cc and gcov are required")
class ProjectRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        code, out = run_cli("init", "-C", str(cls.tmp), "-b", "lm3s6965evb", "-t", "unit,coverage,fuzz",
                            "--template", "starter", "--ci", "none", "-y")
        assert code == 0, out
        cfg = config.load(cls.tmp)
        cfg.tests["fuzz"]["seconds"] = 1
        (cls.tmp / "virtulab.yml").write_text(cfg.dumps())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def setUp(self):  # every test starts from the pristine sample
        self.snapshot = {p: p.read_text() for p in self.tmp.rglob("*.[ch]")}
        self.addCleanup(lambda: [p.write_text(t) for p, t in self.snapshot.items()])

    def test_selected_tests_pass_and_report_lists_them(self):
        code, out = run_cli("run", "-C", str(self.tmp))
        self.assertEqual(code, 0, out)
        report = (self.tmp / ".virtulab/report.md").read_text()
        for title in ("Unit tests on the virtual board", "Line and branch coverage", "Fuzzing"):
            self.assertIn(f"| {title} | ✅ PASS |", report)
        self.assertIn("All 3 selected checks passed", out)

    def test_only_and_skip_select_tests(self):
        code, out = run_cli("run", "-C", str(self.tmp), "--only", "unit")
        self.assertEqual(code, 0)
        self.assertNotIn("Fuzzing", (self.tmp / ".virtulab/report.md").read_text())
        code, out = run_cli("run", "-C", str(self.tmp), "--skip", "unit,coverage")
        self.assertEqual(code, 0, out)
        report = (self.tmp / ".virtulab/report.md").read_text()
        self.assertIn("Fuzzing", report)
        self.assertNotIn("Unit tests", report)

    def test_fuzz_catches_what_unit_tests_miss(self):
        parser = self.tmp / "src/parser.c"
        text = parser.read_text()
        parser.write_text(text.replace("if (payload_len > PARSER_MAX_PAYLOAD) {\n        return PARSER_ERR_TOO_LONG;\n    }\n    if (len <",
                                       "if (payload_len > PARSER_MAX_PAYLOAD + 1u) {\n        return PARSER_ERR_TOO_LONG;\n    }\n    if (len <"))
        code, out = run_cli("run", "-C", str(self.tmp), "--only", "unit,fuzz")
        self.assertEqual(code, 1, out)
        report = (self.tmp / ".virtulab/report.md").read_text()
        self.assertIn("| Unit tests on the virtual board | ✅ PASS |", report)
        self.assertIn("| Fuzzing | ❌ FAIL |", report)
        shutil.rmtree(self.tmp / "fuzz/crashes", ignore_errors=True)

    def test_failing_unit_test_is_reported_and_fails_the_run(self):
        (self.tmp / "src/crc.c").write_text((self.tmp / "src/crc.c").read_text().replace("0x1021", "0x1020"))
        code, out = run_cli("run", "-C", str(self.tmp), "--only", "unit")
        self.assertEqual(code, 1)
        self.assertIn("❌ Unit tests on the virtual board", out)

    def test_coverage_threshold_fails_below_minimum(self):
        cfg = config.load(self.tmp)
        cfg.tests["coverage"]["min_lines"] = 100
        (self.tmp / "virtulab.yml").write_text(cfg.dumps())
        self.addCleanup(lambda: (self.tmp / "virtulab.yml").write_text(
            config.from_dict({**cfg.to_dict(), "tests": {**cfg.tests, "coverage": {}}}).dumps()))
        code, out = run_cli("run", "-C", str(self.tmp), "--only", "coverage")
        self.assertEqual(code, 1, out)
        self.assertIn("below the required 100%", out)

    def test_invalid_config_is_a_clear_error(self):
        (self.tmp / "virtulab.yml").write_text("boadr: x\n")
        self.addCleanup(lambda: (self.tmp / "virtulab.yml").write_text(self.good))
        self.good = config.from_dict({"board": "lm3s6965evb", "tests": {"unit": {}, "coverage": {}, "fuzz": {"seconds": 1}},
                                      "build": {"sources": ["src/*.c", "test/*.c"], "include": ["include", "test"],
                                                "cflags": "-std=c99 -Wall -Wextra"}}).dumps()
        code, _ = run_cli("run", "-C", str(self.tmp))
        self.assertEqual(code, 2)


class UiServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.token = "testtoken"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.tmp, self.token))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def call(self, path, body=None, token=None, host=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                    headers={"X-VirtuLab-Token": self.token if token is None else token})
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as err:
            with err:
                return err.code, json.loads(err.read())

    def test_api_needs_the_token_and_a_local_host_header(self):
        self.assertEqual(self.call("/api/catalog", token="wrong")[0], 403)
        self.assertEqual(self.call("/api/catalog", host="evil.example")[0], 403)
        self.assertEqual(self.call("/api/save", {}, token="")[0], 403)
        status, data = self.call("/api/catalog")
        self.assertEqual(status, 200)
        self.assertIn("stm32f4_discovery", [b["id"] for b in data["boards"]])
        page = urllib.request.urlopen(self.base + "/").read().decode()
        self.assertIn("VirtuLab setup", page)

    def test_check_preview_and_save_round_trip(self):
        cfg = {"board": "stm32f4_discovery", "modules": {"temp": {"model": "tmp108", "bus": "i2c1", "address": 72}},
               "tests": {"unit": {}, "coverage": {}}, "ci": {"provider": "github", "branches": ["main"]}}
        status, data = self.call("/api/check", {"config": cfg, "sample": True})
        self.assertEqual(status, 200, data)
        self.assertNotIn("error", [f["level"] for f in data["findings"] if f["subject"] != "unit"
                                   and "not installed" not in f["message"]])
        status, data = self.call("/api/preview", {"config": cfg, "sample": True})
        self.assertIn("temp: { model: tmp108, bus: i2c1, address: 0x48 }", data["yaml"])
        self.assertIn("test/*.c", data["yaml"])
        status, data = self.call("/api/save", {"config": cfg, "sample": True})
        self.assertEqual(status, 200, data)
        self.assertIn("virtulab.yml", data["written"])
        self.assertTrue((self.tmp / "src/tmp108.c").is_file())
        self.assertEqual(config.load(self.tmp).board, "stm32f4_discovery")
        # a second save needs an explicit overwrite
        self.assertEqual(self.call("/api/save", {"config": cfg})[0], 400)

    @unittest.skipUnless(HAVE_TOOLS, "toolchain and emulator required")
    def test_run_from_the_page_streams_output_and_returns_the_report(self):
        cfg = {"board": "lm3s6965evb", "tests": {"unit": {}, "coverage": {}}}
        self.assertEqual(self.call("/api/save", {"config": cfg, "sample": True, "write_ci": False})[0], 200)
        self.assertEqual(self.call("/api/run", {"only": ["unit"]})[0], 200)
        for _ in range(200):
            status, data = self.call("/api/run")
            if data["state"] == "done":
                break
            threading.Event().wait(0.2)
        self.assertEqual(data["exit_code"], 0, data["output"])
        self.assertIn("4/4 tests passed", data["output"])
        self.assertIn("Unit tests on the virtual board", data["report"])

    def test_the_page_offers_and_saves_spi_and_uart_sensors(self):
        catalog = self.call("/api/catalog")[1]
        by_protocol = {m["id"]: m["protocol"] for m in catalog["modules"]}
        self.assertEqual({"adxl345": "spi", "nmea_gps": "uart"}, {k: by_protocol[k] for k in ("adxl345", "nmea_gps")})
        cfg = {"board": "stm32f4_discovery", "tests": {"unit": {}}, "modules": {
            "accel": {"model": "adxl345", "bus": "spi1"}, "gps": {"model": "nmea_gps", "bus": "usart1"}}}
        status, data = self.call("/api/save", {"config": cfg, "sample": True, "write_ci": False})
        self.assertEqual(status, 200, data)
        status, data = self.call("/api/check", {"config": cfg})
        self.assertEqual(status, 200, data)
        self.assertTrue(data["ok"], data)
        self.assertTrue((self.tmp / "src/adxl345.c").is_file())
        self.assertIn("accel: { model: adxl345, bus: spi1 }", (self.tmp / "virtulab.yml").read_text())

    def test_invalid_input_is_a_400_with_a_message(self):
        status, data = self.call("/api/check", {"config": {"board": "nope"}})
        self.assertEqual(status, 400)
        self.assertIn("unknown board", data["error"])
        status, data = self.call("/api/save", {"config": {"board": "lm3s6965evb", "modules": {
            "t": {"model": "tmp108", "bus": "i2c1"}}}})
        self.assertEqual(status, 400)
        self.assertFalse((self.tmp / "virtulab.yml").exists())


if __name__ == "__main__":
    unittest.main()
