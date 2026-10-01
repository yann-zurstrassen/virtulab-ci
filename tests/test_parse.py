import unittest

from virtulab.parse import parse_diagnostics, parse_fault, parse_tests

UNITY_OUTPUT = """\
Booting...
test/test_crc.c:33:test_empty:PASS
test/test_crc.c:12:test_check_value:FAIL: Expected 0xCBF43926 Was 0x00001234
test/test_crc.c:35:test_skipped:IGNORE: not on this board
test/test_crc.c:36:test_update:PASS

-----------------------
4 Tests 1 Failures 1 Ignored
FAIL
"""


class ParseTestsTest(unittest.TestCase):
    def test_unity_output(self):
        summary = parse_tests(UNITY_OUTPUT)
        self.assertEqual((summary.total, summary.failed, summary.ignored, summary.passed),
                         (4, 1, 1, 2))
        [failure] = summary.failures
        self.assertEqual(failure.file, "test/test_crc.c")
        self.assertEqual(failure.line, 12)
        self.assertEqual(failure.name, "test_check_value")
        self.assertEqual(failure.message, "Expected 0xCBF43926 Was 0x00001234")

    def test_counts_cases_without_summary_line(self):
        # e.g. the firmware crashed before UNITY_END()
        summary = parse_tests("a.c:1:t1:PASS\na.c:2:t2:FAIL\n")
        self.assertEqual((summary.total, summary.failed), (2, 1))
        self.assertEqual(summary.failures[0].message, "")

    def test_adds_up_multiple_unity_groups(self):
        out = "1 Tests 0 Failures 0 Ignored\n3 Tests 2 Failures 0 Ignored\n"
        summary = parse_tests(out)
        self.assertEqual((summary.total, summary.failed), (4, 2))

    def test_crlf_line_endings(self):
        summary = parse_tests("a.c:1:t1:FAIL: boom\r\n")
        self.assertEqual(summary.failures[0].message, "boom")

    def test_no_tests(self):
        summary = parse_tests("Hello from VirtuLab Virtual MCU!\n")
        self.assertEqual(summary.total, 0)


class ParseDiagnosticsTest(unittest.TestCase):
    def test_gcc_errors_and_warnings(self):
        log = (
            "src/crc.c: In function 'crc32':\n"
            "src/crc.c:7:5: error: 'foo' undeclared (first use in this function)\n"
            "src/crc.c:9:12: warning: unused variable 'x' [-Wunused-variable]\n"
            "src/crc.c:7:5: note: each undeclared identifier is reported only once\n"
            "include/crc.h:3: fatal error: missing.h: No such file or directory\n"
        )
        diags = parse_diagnostics(log)
        self.assertEqual([(d.file, d.line, d.severity) for d in diags], [
            ("src/crc.c", 7, "error"),
            ("src/crc.c", 9, "warning"),
            ("include/crc.h", 3, "error"),
        ])
        self.assertEqual(diags[0].column, 5)
        self.assertIsNone(diags[2].column)


class ParseFaultTest(unittest.TestCase):
    def test_fault_line(self):
        fault = parse_fault("ok\nVIRTULAB_FAULT: HardFault pc=0x0000016E lr=0x0000050D "
                            "cfsr=0x00008200 hfsr=0x40000000\n")
        self.assertEqual(fault.kind, "HardFault")
        self.assertEqual(fault.pc, 0x16E)
        self.assertEqual(fault.lr, 0x50D)
        self.assertEqual(fault.registers, "cfsr=0x00008200 hfsr=0x40000000")

    def test_cortex_m0_fault_has_no_status_registers(self):
        fault = parse_fault("VIRTULAB_FAULT: HardFault pc=0x00000100 lr=0xFFFFFFF9\n")
        self.assertEqual(fault.registers, "")

    def test_no_fault(self):
        self.assertIsNone(parse_fault("all good\n"))


if __name__ == "__main__":
    unittest.main()
