"""A check that could not do its job must fail. Green has to mean the check really ran."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from virtulab import RUNTIME_DIR, VirtulabError, cigen, config, yamlite
from virtulab.baseline import NO_REF, NOTHING_TO_COMPARE, build_baseline
from virtulab.boards import BOARDS
from virtulab.build import BuildConfig, BuildResult, Sizes
from virtulab.cli import Options, _check_budgets, main
from virtulab.config import ProjectConfig
from virtulab.parse import TestSummary
from virtulab.report import Outcome, PASSED, render_markdown
from virtulab.suite import FAIL, unit_checks
from virtulab.emulator import RunResult
from tests.test_e2e import HAVE_TOOLS

BOARD = BOARDS["lm3s6965evb"]


def outcome(total: int = 4, note: str | None = None) -> Outcome:
    build = BuildResult(True, "", [], sizes=Sizes(100, 10, 10))
    return Outcome(BOARD, build, run=RunResult(0, False, "", 0.1), tests=TestSummary(total=total),
                   baseline_note=note)


def budgeted() -> Options:
    return Options(max_flash_increase=1024)


class VerdictTest(unittest.TestCase):
    def test_zero_tests_is_a_failure(self):
        checks = unit_checks(outcome(total=0), ProjectConfig(tests={"unit": {}}))
        self.assertEqual(checks[0].status, FAIL)

    def test_unavailable_baseline_fails_a_budget(self):
        o = outcome(note="baseline ref 'x' not found")
        _check_budgets(budgeted(), o)
        checks = unit_checks(o, ProjectConfig(tests={"footprint": {}}))
        self.assertEqual(checks[0].status, FAIL)
        self.assertIn("could not be checked", checks[0].summary)

    def test_a_baseline_with_nothing_to_compare_is_not_a_failure(self):
        for note in (NO_REF, NOTHING_TO_COMPARE):
            o = outcome(note=note)
            _check_budgets(budgeted(), o)
            self.assertEqual(o.budget_violations, [])

    def test_the_headline_covers_every_check(self):
        o = outcome()
        self.assertEqual(o.status, PASSED)
        self.assertIn("✅ PASSED", render_markdown(o))
        md = render_markdown(o, checks_ok=False)
        self.assertIn("❌ FAILED", md)
        self.assertNotIn("✅ PASSED", md)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_bad_input_is_an_error_not_a_traceback(self):
        self.assertEqual(main(["init", "-C", str(self.tmp / "a"), "-m", "t=tmp108@i2c1:zz", "-y"]), 2)
        self.assertEqual(main(["init", "-C", str(self.tmp / "b"), "-m", "t=nope@i2c1", "--template", "starter", "-y"]), 2)

    def test_a_rejected_init_writes_nothing(self):
        root = self.tmp / "c"
        self.assertEqual(main(["init", "-C", str(root), "-t", "unit,bogus", "--template", "starter", "-y"]), 2)
        self.assertEqual(list(root.rglob("*.c")), [])

    def test_flags_the_file_would_ignore_are_refused(self):
        (self.tmp / "virtulab.yml").write_text("version: 1\nboard: lm3s6965evb\ntests:\n  unit: {}\n")
        self.assertEqual(main(["run", "-C", str(self.tmp), "--ldflags=-lm"]), 2)

    def test_option_types_are_checked(self):
        with self.assertRaises(VirtulabError):
            config.from_dict({"tests": {"fuzz": {"seconds": "abc"}}})

    def test_yaml_unescapes_left_to_right(self):
        self.assertEqual(yamlite.loads(r'a: "C:\\new"')["a"], "C:\\new")


class WorkflowTest(unittest.TestCase):
    def test_pull_request_code_and_the_write_token_are_kept_apart(self):
        text = cigen.github_workflow(ProjectConfig())
        scan, report = text.split("  report:\n")
        self.assertNotIn("pull-requests: write", scan)
        self.assertIn("persist-credentials: false", scan)
        self.assertIn("include-hidden-files: true", scan)
        self.assertIn("pull-requests: write", report)
        self.assertNotIn("actions/checkout", report)


class BaselineFetchTest(unittest.TestCase):
    def test_a_full_clone_keeps_its_history(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)

        def git(cwd, *args):
            return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t.invalid", *args],
                                  check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "init", "-q", "--bare", str(tmp / "origin.git")], check=True)
        subprocess.run(["git", "clone", "-q", str(tmp / "origin.git"), str(tmp / "w")], check=True, capture_output=True)
        for i in range(3):
            (tmp / "w" / "f").write_text(str(i))
            git(tmp / "w", "add", "f")
            git(tmp / "w", "commit", "-qm", str(i))
        git(tmp / "w", "push", "-q", "origin", "HEAD:refs/heads/remote-only")
        git(tmp / "w", "branch", "-q", "local-ref")
        cfg = BuildConfig(board=BOARD, sources=["*.c"])
        for ref in ("local-ref", "remote-only"):
            build_baseline(ref, tmp / "w", cfg, tmp / "work")
            self.assertEqual(git(tmp / "w", "rev-parse", "--is-shallow-repository"), "false")
            self.assertEqual(git(tmp / "w", "rev-list", "--count", "HEAD"), "3")


@unittest.skipUnless(HAVE_TOOLS and (shutil.which("arm-none-eabi-gdb") or shutil.which("gdb-multiarch")),
                     "the toolchain, QEMU and an Arm gdb are required")
class FaultSweepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = self.tmp / "p"
        self.assertEqual(main(["init", "-C", str(self.root), "-b", "lm3s6965evb", "-t", "unit,fault",
                               "--template", "starter", "--ci", "none", "-y"]), 0)

    def test_a_target_that_matches_nothing_fails(self):
        path = self.root / "virtulab.yml"
        path.write_text(path.read_text().replace("target: src/auth.c", "target: src/auht.c"))
        self.assertEqual(main(["run", "-C", str(self.root), "--only", "fault"]), 1)
        self.assertIn("inconclusive", (self.root / ".virtulab" / "report.md").read_text())

    def test_a_broken_debugger_fails(self):
        result = subprocess.run(
            [str(RUNTIME_DIR / "fault_inject.sh"), "--elf", str(self._elf()), "--board", "lm3s6965evb",
             "--source", "src/auth.c"], cwd=self.root, capture_output=True, text=True,
            env={"GDB": "/usr/bin/false", "PATH": subprocess.os.environ["PATH"]})
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("FAULT status=inconclusive", result.stdout)

    def _elf(self) -> Path:
        self.assertEqual(main(["run", "-C", str(self.root), "--only", "fault"]), 0)
        return next((self.root / ".virtulab" / "fault").rglob("firmware.elf"))


if __name__ == "__main__":
    unittest.main()
