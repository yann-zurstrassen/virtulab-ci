"""examples/sensirion-sht3x: Sensirion's own driver, unchanged, against our SHT31 model."""

import hashlib
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from .test_project import HAVE_RENODE, HAVE_TOOLS, run_cli

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sensirion-sht3x"
VENDOR = EXAMPLE / "vendor" / "sensirion"


class VendoredDriverTest(unittest.TestCase):
    def test_the_vendor_files_are_exactly_what_was_published(self):
        for line in (VENDOR / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split(None, 1)
            self.assertEqual(hashlib.sha256((VENDOR / name.strip()).read_bytes()).hexdigest(), digest,
                             f"{name}: the vendored driver was edited; fix the glue instead")

    def test_the_example_declares_everything_virtulab_needs(self):
        code, out = run_cli("check", "-C", str(EXAMPLE))
        self.assertIn("air", out)
        self.assertNotIn("❌ air", out)


@unittest.skipUnless(HAVE_TOOLS and HAVE_RENODE, "the toolchain and Renode are required")
class VendoredDriverRunTest(unittest.TestCase):
    def copy(self) -> Path:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "example"
        shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns(".virtulab"))
        return root

    def test_sensirions_driver_passes_on_the_virtual_board(self):
        code, out = run_cli("run", "-C", str(self.copy()), "--only", "unit")
        self.assertEqual(code, 0, out)
        self.assertIn("8 Tests 0 Failures", out)

    def test_a_glue_layer_that_does_not_wait_is_caught(self):
        root = self.copy()
        hal = root / "hal" / "sensirion_i2c_hal.c"
        text = hal.read_text()
        self.assertIn("delay_ms((useconds + 999u) / 1000u);", text)
        hal.write_text(text.replace("delay_ms((useconds + 999u) / 1000u);", "(void)useconds;"))
        code, out = run_cli("run", "-C", str(root), "--only", "unit")
        self.assertEqual(code, 1, out)
        self.assertIn("test_vendor_single_shot_in_every_mode:FAIL", out)


if __name__ == "__main__":
    unittest.main()
