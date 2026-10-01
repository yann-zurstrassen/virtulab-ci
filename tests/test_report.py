import unittest
from pathlib import Path

from virtulab.baseline import Baseline, diff_symbols
from virtulab.boards import get_board
from virtulab.build import BuildResult, Sizes
from virtulab.emulator import RunResult
from virtulab.parse import Diagnostic, Fault, parse_tests
from virtulab.report import (
    BUDGET_EXCEEDED, BUILD_FAILED, CRASHED, FAILED, PASSED, TIMEOUT, Outcome, fmt_delta,
    render_markdown,
)

BOARD = get_board("lm3s6965evb")


def ok_build(**kw):
    return BuildResult(ok=True, log="", diagnostics=[], elf=Path("fw.elf"),
                       sizes=Sizes(text=6000, data=100, bss=500),
                       symbols={"main": 100, "crc32": 60}, **kw)


def run_result(output="", exit_code=0, timed_out=False):
    return RunResult(exit_code=None if timed_out else exit_code, timed_out=timed_out,
                     output=output, duration=0.42)


class StatusTest(unittest.TestCase):
    def test_statuses(self):
        failed_build = BuildResult(ok=False, log="", diagnostics=[])
        self.assertEqual(Outcome(BOARD, failed_build).status, BUILD_FAILED)
        self.assertEqual(Outcome(BOARD, ok_build(), run_result()).status, PASSED)
        self.assertEqual(Outcome(BOARD, ok_build(), run_result(exit_code=3)).status, FAILED)
        self.assertEqual(Outcome(BOARD, ok_build(), run_result(timed_out=True)).status, TIMEOUT)
        crashed = Outcome(BOARD, ok_build(), run_result(exit_code=0xFA),
                          fault=Fault("HardFault", 0x100, 0x200, ""))
        self.assertEqual(crashed.status, CRASHED)
        over = Outcome(BOARD, ok_build(), run_result(), budget_violations=["too big"])
        self.assertEqual(over.status, BUDGET_EXCEEDED)

    def test_failed_tests_fail_even_with_zero_exit_code(self):
        tests = parse_tests("a.c:1:t:FAIL: x\n")
        self.assertEqual(Outcome(BOARD, ok_build(), run_result(), tests=tests).status, FAILED)


class MarkdownTest(unittest.TestCase):
    def test_passing_report_with_baseline(self):
        baseline = Baseline("main", "abcdef1234567890", Sizes(5900, 100, 500),
                            {"main": 100, "crc32": 40})
        tests = parse_tests("a.c:1:t1:PASS\na.c:2:t2:PASS\n")
        md = render_markdown(Outcome(BOARD, ok_build(), run_result("hello"), tests=tests,
                                     baseline=baseline), report_id="lm3s")
        self.assertTrue(md.startswith("<!-- virtulab-ci-report:lm3s -->"))
        self.assertIn("✅ PASSED", md)
        self.assertIn("Δ vs `abcdef1`", md)
        self.assertIn("| **Flash** | `6,100 B` | +100 B 📈 | 2.3% of 256 KiB |", md)
        self.assertIn("| **RAM** | `600 B` | ±0 B |", md)
        self.assertIn("`2 / 2`", md)
        self.assertIn("| `crc32` | 40 | 60 | +20 |", md)

    def test_failing_tests_and_fault(self):
        tests = parse_tests("t.c:9:test_x:FAIL: Expected 1 Was 2 | pipe\n")
        fault = Fault("HardFault", 0x1234, 0x99, "cfsr=0x1", function="crash_me",
                      location="src/a.c:42")
        md = render_markdown(Outcome(BOARD, ok_build(), run_result("x", 0xFA), tests=tests,
                                     fault=fault))
        self.assertIn("| `test_x` | `t.c:9` | Expected 1 Was 2 \\| pipe |", md)
        self.assertIn("#### 💥 HardFault in `crash_me` at `src/a.c:42`", md)

    def test_build_failure_lists_errors(self):
        build = BuildResult(ok=False, log="src/a.c:3:1: error: boom", diagnostics=[
            Diagnostic("src/a.c", 3, 1, "error", "boom")])
        md = render_markdown(Outcome(BOARD, build))
        self.assertIn("🔨 BUILD FAILED", md)
        self.assertIn("| `src/a.c:3` | boom |", md)

    def test_log_cannot_break_out_of_code_fence(self):
        md = render_markdown(Outcome(BOARD, ok_build(), run_result("```\n# injected")))
        self.assertIn("````text\n```\n# injected\n````", md)

    def test_baseline_note_when_unavailable(self):
        md = render_markdown(Outcome(BOARD, ok_build(), run_result(),
                                     baseline_note="baseline ref 'main' not found"))
        self.assertIn("No footprint delta: baseline ref 'main' not found.", md)


class HelpersTest(unittest.TestCase):
    def test_fmt_delta(self):
        self.assertEqual(fmt_delta(None), "—")
        self.assertEqual(fmt_delta(0), "±0 B")
        self.assertEqual(fmt_delta(8192), "+8,192 B 📈")
        self.assertEqual(fmt_delta(-12), "-12 B 📉")

    def test_diff_symbols_orders_by_magnitude(self):
        deltas = diff_symbols({"a": 10, "b": 100, "gone": 5}, {"a": 12, "b": 40, "new": 30})
        self.assertEqual([(d.name, d.delta) for d in deltas],
                         [("b", -60), ("new", 30), ("gone", -5), ("a", 2)])


if __name__ == "__main__":
    unittest.main()
