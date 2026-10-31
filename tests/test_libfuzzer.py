"""A standard LLVMFuzzerTestOneInput harness works, with and without libFuzzer installed."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from virtulab import suite
from virtulab.cli import main

REPO = Path(__file__).resolve().parent.parent
HARNESS = """\
#include <stdint.h>
#include <stddef.h>
#include "parser.h"
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    parser_frame_t frame;
    (void)parser_parse(data, size, &frame);
    return 0;
}
"""
CONFIG = """\
version: 1
board: lm3s6965evb
build:
  sources: [src/parser.c]
tests:
  fuzz:
    harness: fuzz/fuzz.c
    sources: [src/parser.c, src/crc.c]
    include: [include]
    seconds: 3
"""


class DetectionTest(unittest.TestCase):
    def test_a_mention_in_a_comment_is_not_a_harness(self):
        self.assertIsNone(suite._STANDARD_HARNESS.search("/* wrapped as LLVMFuzzerTestOneInput() later */\nint main(void)"))
        self.assertTrue(suite._STANDARD_HARNESS.search(HARNESS))


class StandardHarnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "p"
        for sub in ("src", "include", "fuzz/corpus"):
            (self.root / sub).mkdir(parents=True)
        shutil.copy(REPO / "src/parser.c", self.root / "src")
        shutil.copy(REPO / "examples/crc/src/crc.c", self.root / "src")
        shutil.copy(REPO / "include/parser.h", self.root / "include")
        shutil.copy(REPO / "examples/crc/include/crc.h", self.root / "include")
        (self.root / "fuzz/fuzz.c").write_text(HARNESS)
        (self.root / "fuzz/corpus/frame").write_bytes(bytes([0xA5, 1, 0x10, 0, 0]))
        (self.root / "virtulab.yml").write_text(CONFIG)

    def report(self) -> str:
        return (self.root / ".virtulab" / "report.md").read_text()

    def seed_bug(self) -> None:
        path = self.root / "src/parser.c"
        text = path.read_text().replace("payload_len > PARSER_MAX_PAYLOAD) {\n        return PARSER_ERR_TOO_LONG;\n    }\n    if (len <",
                                        "payload_len > PARSER_MAX_PAYLOAD + 1u) {\n        return PARSER_ERR_TOO_LONG;\n    }\n    if (len <", 1)
        self.assertNotEqual(text, path.read_text())
        path.write_text(text)

    def test_clean_parser_passes(self):
        self.assertEqual(main(["run", "-C", str(self.root)]), 0)
        self.assertIn("0 crashes", self.report())

    def test_the_seeded_overflow_is_found(self):
        self.seed_bug()
        self.assertEqual(main(["run", "-C", str(self.root)]), 1)
        self.assertTrue(list((self.root / "fuzz/crashes").iterdir()), "the crash input must be kept")

    def test_the_defect_is_reported_where_it_is(self):
        text = "src/parser.c:12:5: runtime error: signed integer overflow: 1 * 2\n"
        self.assertEqual(suite._sanitizer_finding(text, self.root)["line"], 12)
        text = f"SUMMARY: AddressSanitizer: heap-buffer-overflow {self.root}/src/parser.c:9:3 in f\n"
        found = suite._sanitizer_finding(text, self.root)
        self.assertEqual((found["file"], found["line"]), ("src/parser.c", 9))

    def test_a_saved_crash_fails_the_next_run_first(self):
        self.seed_bug()
        main(["run", "-C", str(self.root)])
        self.assertEqual(main(["run", "-C", str(self.root)]), 1)
        self.assertIn("reproduces", self.report())

    def test_without_libfuzzer_the_report_says_blind_mutation(self):
        with mock.patch.object(suite, "_libfuzzer_compiler", return_value=None):
            self.assertEqual(main(["run", "-C", str(self.root)]), 0)
        self.assertIn("blind mutation", self.report())


if __name__ == "__main__":
    unittest.main()
