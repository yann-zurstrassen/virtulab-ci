"""A team keeps its own build: VirtuLab runs the command and tests the ELF it produces."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from virtulab import VirtulabError, config
from virtulab.cli import main
from tests.test_e2e import CRC_EXAMPLE, HAVE_TOOLS

CONFIG = """\
version: 1
board: lm3s6965evb
build:
  command: {command}
  elf: out/firmware.elf
tests:
  unit: {{}}
  footprint: {{ flash_increase: 16 }}
"""


class ConfigTest(unittest.TestCase):
    def test_command_needs_an_elf(self):
        with self.assertRaises(VirtulabError):
            config.from_dict({"build": {"command": "make"}})

    def test_a_command_yaml_reads_as_a_boolean_is_refused(self):
        with self.assertRaises(VirtulabError):
            config.from_dict({"build": {"command": True, "elf": "a.elf"}})

    def test_round_trip(self):
        cfg = config.from_dict({"build": {"command": "make", "elf": "a.elf"}})
        again = config.from_dict(cfg.to_dict())
        self.assertEqual((again.build_command, again.build_elf), ("make", "a.elf"))


@unittest.skipUnless(HAVE_TOOLS, "arm-none-eabi-gcc and qemu-system-arm are required")
class OwnBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        crc = self.tmp / "crc"
        shutil.copytree(CRC_EXAMPLE, crc)
        code = main(["run", "-C", str(crc), "-s", "src/*.c", "test/*.c", "-I", "include"])
        self.assertEqual(code, 0)
        self.root = self.tmp / "project"
        (self.root / "prebuilt").mkdir(parents=True)
        shutil.copy(crc / ".virtulab" / "build" / "firmware.elf", self.root / "prebuilt" / "firmware.elf")

    def write(self, command: str) -> None:
        (self.root / "virtulab.yml").write_text(CONFIG.format(command=command))

    def test_the_elf_of_the_command_is_tested(self):
        self.write("mkdir -p out && cp prebuilt/firmware.elf out/firmware.elf")
        self.assertEqual(main(["run", "-C", str(self.root)]), 0)
        report = (self.root / ".virtulab" / "report.md").read_text()
        self.assertIn("4 / 4", report)

    def test_a_failing_command_fails(self):
        self.write("exit 3")
        self.assertEqual(main(["run", "-C", str(self.root), "--only", "unit"]), 2)

    def test_a_missing_elf_is_explained(self):
        self.write("echo built")
        self.assertEqual(main(["run", "-C", str(self.root), "--only", "unit"]), 2)
        self.assertIn("does not exist", (self.root / ".virtulab" / "report.md").read_text())

    def test_the_baseline_runs_the_same_command(self):
        self.write("mkdir -p out && cp prebuilt/firmware.elf out/firmware.elf")
        (self.root / ".gitignore").write_text("out/\n.virtulab/\n")
        git = ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t.invalid"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-qm", "base"], check=True)
        self.assertEqual(main(["run", "-C", str(self.root), "--baseline", "HEAD"]), 0)
        self.assertIn("±0 B", (self.root / ".virtulab" / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
