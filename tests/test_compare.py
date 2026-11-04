"""Comparing the twin with real hardware: the parts that must agree do, and the rest is reported."""

import shutil
import tempfile
import unittest
from pathlib import Path

from virtulab import VirtulabError
from virtulab.compare import Message, compare, read_messages, write_messages


def msg(t, write, read, address=0x55):
    return Message(t, "i2c1", address, tuple(write), tuple(read))


TWIN = [msg(0, [0], [0xA5]), msg(1, [1], [0x00, 0x64]), msg(70, [1], [0x03, 0x16]), msg(116, [1], [0x03, 0xB6])]


class CompareTest(unittest.TestCase):
    def test_the_same_conversation_matches_whatever_the_timing(self):
        real = [Message(m.time_ms * 1.37 + 5, m.bus, m.address, m.write, m.read) for m in TWIN]
        result = compare(TWIN, real)
        self.assertTrue(result.ok)
        self.assertEqual(result.matched, 4)

    def test_a_reading_that_differs_is_reported(self):
        real = list(TWIN)
        real[2] = msg(70, [1], [0x03, 0x20])
        result = compare(TWIN, real)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.different), 1)

    def test_a_tolerance_accepts_sensor_noise_but_not_more(self):
        real = list(TWIN)
        real[2] = msg(70, [1], [0x03, 0x18])  # 2 counts away
        self.assertTrue(compare(TWIN, real, tolerance=3).ok)
        self.assertFalse(compare(TWIN, real, tolerance=1).ok)

    def test_a_checksummed_reply_compares_values_and_ignores_the_checksum(self):
        twin = [msg(0, [0x24, 0x00], [0x66, 0x66, 0x93, 0x73, 0x33, 0x1A])]
        real = [msg(0, [0x24, 0x00], [0x66, 0x6A, 0x5C, 0x73, 0x30, 0x77])]  # 4 and 3 counts away, other checksums
        self.assertTrue(compare(twin, real, tolerance=5, frame=(2, 1)).ok)
        self.assertFalse(compare(twin, real, tolerance=3, frame=(2, 1)).ok)
        self.assertFalse(compare(twin, real, tolerance=5).ok, "without the layout, checksums break the values")

    def test_each_value_of_a_reply_can_have_its_own_tolerance(self):
        twin = [msg(0, [0x24, 0x00], [0x62, 0x03, 0x00, 0x73, 0x33, 0x00])]
        real = [msg(0, [0x24, 0x00], [0x62, 0x40, 0x00, 0x76, 0x00, 0x00])]  # +61 and +717 counts
        self.assertTrue(compare(twin, real, tolerance=[75, 1311], frame=(2, 1)).ok)
        self.assertFalse(compare(twin, real, tolerance=[75, 700], frame=(2, 1)).ok)

    def test_missing_and_extra_messages_are_reported(self):
        real = TWIN[:2] + [msg(50, [0x10], [0x01])] + TWIN[3:]
        result = compare(TWIN, real)
        self.assertEqual([m.write for m in result.only_twin], [(1,)])
        self.assertEqual([m.write for m in result.only_real], [(0x10,)])

    def test_a_different_question_is_never_matched_by_tolerance(self):
        real = list(TWIN)
        real[1] = msg(1, [3], [0x00, 0x64])  # asked another register
        self.assertFalse(compare(TWIN, real, tolerance=1000).ok)

    def test_the_file_format_round_trips_and_rejects_junk(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        write_messages(TWIN, tmp / "m.csv")
        self.assertEqual(read_messages(tmp / "m.csv"), TWIN)
        (tmp / "bad.csv").write_text("time_ms,bus,address,write,read\n1,i2c1,0x55,zz,\n")
        with self.assertRaises(VirtulabError):
            read_messages(tmp / "bad.csv")
        (tmp / "cols.csv").write_text("t,addr\n1,2\n")
        with self.assertRaises(VirtulabError):
            read_messages(tmp / "cols.csv")


if __name__ == "__main__":
    unittest.main()
