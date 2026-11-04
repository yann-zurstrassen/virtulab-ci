"""`virtulab trace`: the recording is read correctly, and each access is named and placed."""

import shutil
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from virtulab import trace
from virtulab.config import load
from virtulab.peripherals import analog_source, parse_analog
from tests.test_project import HAVE_RENODE, HAVE_TOOLS

REPO = Path(__file__).resolve().parent.parent
LOG = """\
[09:00:00.0001] [INFO] adc1: [cpu: 0x8000094] WriteUInt32 to 0x8 (unknown), value 0x40000001
[09:00:00.0002] [INFO] VL_MS 12
[09:00:00.0003] [INFO] \x1b[32madc1: [cpu: 0x800009C] ReadUInt32 from 0x4C (unknown), returned 0xC1E\x1b[0m
[09:00:00.0004] [WARNING] something unrelated
"""
SVD = """<device><peripherals>
<peripheral><name>ADC1</name><description>Analog to digital</description><baseAddress>0x40012000</baseAddress>
<registers>
 <register><name>CR2</name><description>control 2</description><addressOffset>0x8</addressOffset>
  <fields><field><name>ADON</name><bitOffset>0</bitOffset><bitWidth>1</bitWidth></field>
          <field><name>SWSTART</name><bitOffset>30</bitOffset><bitWidth>1</bitWidth></field></fields></register>
</registers></peripheral>
<peripheral derivedFrom="ADC1"><name>ADC2</name><baseAddress>0x40012100</baseAddress></peripheral>
</peripherals></device>"""


class ReadingTest(unittest.TestCase):
    def test_accesses_carry_virtual_time_and_their_instruction(self):
        events = trace.parse_log(LOG)
        self.assertEqual([(e["t"], e["op"], e["offset"], e["value"], e["pc"]) for e in events if e["kind"] == "access"],
                         [(0, "write", 0x8, 0x40000001, 0x8000094), (12, "read", 0x4C, 0xC1E, 0x800009C)])

    def test_bus_messages_and_ignored_bits_are_read(self):
        log = ("[x] [DEBUG] i2c1: Starting transmission\n[x] [DEBUG] i2c1: Writing to 0x55: [0x3]\n"
               "[x] [DEBUG] i2c1: Performed read from 0x55: [0x3]\n[x] [DEBUG] i2c1: Performed read from 0x55: [0x20]\n"
               "[x] [DEBUG] i2c1: Stopping transmission\n[x] [INFO] VL_MS 4\n"
               "[x] [INFO] i2c1: [cpu: 0x800010] WriteUInt32 to 0x0 (unknown), value 0x8000\n"
               "[x] [WARNING] i2c1: Unhandled write to offset 0x0. Unhandled bits: [15] when writing value 0x8000. Tags: SWRST (0x1).\n")
        events = trace.parse_log(log)
        bus = [e for e in events if e["kind"] == "bus"]
        self.assertEqual((bus[0]["address"], bus[0]["write"], bus[0]["read"]), (0x55, [3], [3, 0x20]))
        trace._note_unmodelled(events)
        access = next(e for e in events if e["kind"] == "access")
        self.assertEqual(access["unmodelled"]["bits"], "15")
        self.assertIn("SWRST", access["unmodelled"]["tags"])

    def test_spi_and_uart_messages_are_rebuilt_from_data_register_accesses(self):
        from virtulab import config
        cfg = config.from_dict({"board": "stm32f4_discovery", "modules": {
            "accel": {"model": "adxl345", "bus": "spi1"}, "gps": {"model": "nmea_gps", "bus": "usart1"}}})
        dr = lambda p, op, v: {"kind": "access", "t": 1, "peripheral": p, "op": op, "register": "DR", "value": v}
        events = [{"kind": "select", "t": 1, "bus": "spi1", "index": 0, "selected": True},
                  dr("spi1", "write", 0x80), dr("spi1", "read", 0x00), dr("spi1", "write", 0x00), dr("spi1", "read", 0xE5),
                  {"kind": "select", "t": 1, "bus": "spi1", "index": 0, "selected": False},
                  dr("spi1", "write", 0x55),
                  dr("usart1", "read", ord("$")), dr("usart1", "read", ord("G")), dr("usart1", "write", ord("x"))]
        messages = [e for e in trace._serial_messages(cfg, events) if e["kind"] == "bus"]
        spi = [m for m in messages if m["protocol"] == "spi"]
        uart = [m for m in messages if m["protocol"] == "uart"]
        self.assertEqual([(m["device"], m["write"], m["read"]) for m in spi], [("accel", [0x80, 0x00], [0x00, 0xE5])],
                         "only traffic while the chip select is low belongs to the device")
        self.assertEqual([(m["write"], m["read"]) for m in uart], [([], [ord("$"), ord("G")]), ([ord("x")], [])],
                         "a change of direction starts a new message")

    def test_catalog_messages_are_named_by_the_model_and_its_datasheet(self):
        from virtulab import config
        cfg = config.from_dict({"board": "stm32f4_discovery", "modules": {
            "accel": {"model": "adxl345", "bus": "spi1"}, "temp": {"model": "tmp108", "bus": "i2c1"},
            "air": {"model": "sht31", "bus": "i2c1"}}})
        bus = lambda device, w, r: {"kind": "bus", "device": device, "write": w, "read": r}
        events = [bus("accel", [0x80, 0x00], [0x00, 0xE5]), bus("accel", [0x1E, 0x05], []),
                  bus("temp", [0x01], []), bus("temp", [], [0x60, 0xA0]), bus("air", [0x30, 0xA2], [])]
        trace._decode_catalog(cfg, events)
        accel_id, unknown, select, read, reset = (e["catalog"] for e in events)
        self.assertEqual((accel_id["name"], accel_id["op"], accel_id["data"]), ("DevId", "read", [0xE5]))
        self.assertIn("Device ID", [r["topic"] for r in accel_id["datasheet"]])
        self.assertIsNotNone(accel_id["model"]["line"])
        self.assertIsNone(unknown["name"], "a register the model does not name stays unnamed, never guessed")
        self.assertEqual((read["name"], read["op"], read["data"]), ("ConfigurationRegister", "read", [0x60, 0xA0]),
                         "a read after a pointer write is about that register")
        self.assertEqual(reset["name"], "Soft reset")

    def test_a_project_defined_device_message_is_decoded_into_registers(self):
        from virtulab.peripherals import parse_peripheral
        p = parse_peripheral("tank", {"bus": "i2c1", "address": 0x55, "registers": [
            {"name": "LEVEL", "at": 1, "size": 2}, {"name": "LIMIT", "at": 3, "size": 2}]})
        self.assertEqual(trace._decode_registers(p.registers, False, [3], [0x03, 0x20]),
                         [{"register": "LIMIT", "op": "read", "value": 800, "size": 2}])
        self.assertEqual(trace._decode_registers(p.registers, False, [3, 0x02, 0xEE], []),
                         [{"register": "LIMIT", "op": "write", "value": 750, "size": 2}])

    def test_registers_and_fields_come_from_the_svd_file(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "chip.svd").write_text(SVD)
        chip = trace.load_svd(tmp / "chip.svd")
        self.assertEqual(chip["ADC2"]["registers"][0x8]["name"], "CR2", "a derived peripheral shares its registers")
        fields = {f["name"]: f["value"] for f in trace.decode(chip["ADC1"]["registers"][0x8]["fields"], 0x40000001)}
        self.assertEqual(fields, {"ADON": 1, "SWSTART": 1})

    def test_memories_and_the_core_are_not_named_after_a_peripheral(self):
        self.assertIsNone(trace.svd_name("flash"))
        self.assertIsNone(trace.svd_name("nvic"))
        self.assertEqual(trace.svd_name("gpioPortA"), "GPIOA")
        self.assertEqual(trace.svd_name("adc1"), "ADC1")

    def test_a_generated_model_access_points_at_its_read_or_write_handler(self):
        source = analog_source(parse_analog("adc1", {"inputs": {"t": 1}}))
        lines = source.splitlines()
        read, write = trace._model_line(source, 0x8, "read"), trace._model_line(source, 0x8, "write")
        self.assertIn("case Control2Register:", lines[read - 1])
        self.assertIn("case Control2Register:", lines[write - 1])
        self.assertLess(read, write)


@unittest.skipUnless(HAVE_TOOLS and HAVE_RENODE, "the toolchain and Renode are required")
class RecordingTest(unittest.TestCase):
    def test_a_scenario_is_recorded_and_mapped_to_code(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        root = tmp / "oven"
        shutil.copytree(REPO / "examples/oven-controller", root, ignore=shutil.ignore_patterns(".virtulab"))
        data = trace.record(load(root), root, root / ".virtulab")
        reads = [e for e in data["events"] if e.get("peripheral") == "adc1" and e.get("register") == "DR"]
        self.assertTrue(reads)
        self.assertEqual(reads[0]["file"], "src/oven.c")
        self.assertIn("models/Analog_adc1.cs", data["files"])
        page = trace.write(data, root / ".virtulab" / "trace")
        self.assertIn("oven_read_counts", page.read_text())
        board = page.with_name("board.html").read_text()
        self.assertNotIn("/*TRACE_DATA*/null", board)
        self.assertIn('"duration_ms"', board)

    def test_a_custom_sensor_conversation_is_decoded(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        root = tmp / "tank"
        shutil.copytree(REPO / "examples/custom-sensor", root, ignore=shutil.ignore_patterns(".virtulab"))
        data = trace.record(load(root), root, root / ".virtulab")
        decoded = [d for e in data["events"] if e["kind"] == "bus" for d in e.get("decoded", [])]
        self.assertIn({"register": "LIMIT", "op": "read", "value": 800, "size": 2}, decoded)
        self.assertTrue(any(d["register"] == "LEVEL" and d["value"] == 950 for d in decoded))


if __name__ == "__main__":
    unittest.main()


class StartupTest(unittest.TestCase):
    def test_only_the_models_a_board_uses_are_compiled(self):
        import tempfile as tf
        from virtulab import emulator
        from virtulab.boards import BOARDS
        tmp = Path(tf.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "models").mkdir()
        with unittest.mock.patch.object(emulator, "symbol_addresses", return_value={}):
            script = emulator._renode_script(BOARDS["stm32f4_discovery"], tmp / "f.elf", tmp,
                                             "air: VirtuLab.SHT31 @ i2c1 0x44\n", tmp / "u", tmp / "s")
        includes = [l for l in script.read_text().splitlines() if l.startswith("include")]
        self.assertEqual([Path(l.split("@", 1)[1]).name for l in includes], ["SHT31.cs"])


@unittest.skipUnless(HAVE_TOOLS and HAVE_RENODE, "needs arm-none-eabi-gcc and Renode")
class FaultReplayTest(unittest.TestCase):
    def test_a_replayed_fault_is_on_the_page_and_breaks_the_fall(self):
        import contextlib
        import io
        import json

        from virtulab.cli import main
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        root = tmp / "patch"
        shutil.copytree(REPO / "examples/wearable-patch", root, ignore=shutil.ignore_patterns(".virtulab"))
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["trace", "-C", str(root), "--case", "patient_falls",
                         "--fault", "imu.AccelerationZ.stuck@1300ms"])
        self.assertEqual(code, 0)
        data = json.loads((root / ".virtulab/trace/trace.json").read_text())
        self.assertEqual(data["fault"]["kind"], "stuck")
        self.assertEqual(data["fault"]["until"], 1900)
        self.assertEqual(data["scenario"]["verdict"], "broken")       # the impact is never seen
        self.assertIn('"fault": {', (root / ".virtulab/trace/board.html").read_text())
        # the page lists what the scenario scripts, not the injected steps
        self.assertEqual(len(data["scenario"]["inputs"]), 5)
        # and shows how to reproduce it, and everything generated for it
        self.assertEqual(data["command"], "virtulab trace --case patient_falls --fault imu.AccelerationZ.stuck@1300ms")
        hood = data["under_the_hood"]
        self.assertIn("run.resc", hood["files"])
        self.assertIn('1300.0d, "sysbus.i2c1.imu", "AccelerationZ", 0.1m', hood["files"]["models/Stimulus.cs"])
        self.assertTrue(any("firmware.elf" in c for c in hood["commands"]))
        self.assertNotIn(str(root), json.dumps(hood))                   # paths are shown as <project>
        self.assertIn("FALL=NO", hood["uart"])
