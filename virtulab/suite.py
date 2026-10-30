"""Run the tests a project selected in virtulab.yml and combine them into one report.

Each test kind returns a `CheckResult`; the unit run provides the board table
and logs, and the others add rows to the "checks" table of the sticky comment.
"""

import glob
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import RUNTIME_DIR, VirtulabError, github
from .boards import BOARDS
from .build import resolve_sources
from .catalog import TESTS, get_test
from .check import _tool, check
from .config import ProjectConfig, option, renode_repl
from .report import BUDGET_EXCEEDED, PASSED, Outcome, fmt_delta

PASS, FAIL, SKIP = "pass", "fail", "skip"
_ICON = {PASS: "✅", FAIL: "❌", SKIP: "⏭️"}
FAULT_SCRIPT = RUNTIME_DIR / "fault_inject.sh"
HOST_SHIM = RUNTIME_DIR / "host" / "vl_host.c"

# Flags that only make sense for the Arm target and would break a host build.
_TARGET_FLAG = re.compile(r"-m(cpu|thumb|fpu|float-abi|arch|tune)\b|-Os$|-O[0-3sg]$|-ffreestanding$")


@dataclass
class CheckOutcome:
    test: str
    status: str
    summary: str
    log: str = ""
    data: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return get_test(self.test).title

    @property
    def failed(self) -> bool:
        return self.status == FAIL


def _run(cmd: list[str], cwd: Path, timeout: float) -> tuple[int | None, str]:
    """Run a command, returning (exit code or None on timeout, combined output)."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"") + (exc.stderr or b"")
        return None, out.decode(errors="replace")
    except FileNotFoundError:
        raise VirtulabError(f"'{cmd[0]}' not found") from None
    return proc.returncode, (proc.stdout + proc.stderr).decode(errors="replace")


def _host_flags(cflags: str) -> list[str]:
    return [f for f in shlex.split(cflags) if not _TARGET_FLAG.match(f)]


def _globs(root: Path, patterns: list[str]) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        found += sorted(m for m in glob.glob(pattern, root_dir=root, recursive=True)
                        if (root / m).is_file())
    return list(dict.fromkeys(found))


def _includes(cfg: ProjectConfig, root: Path, extra: list[str] | None = None) -> list[str]:
    dirs = list(cfg.include) + (extra or [])
    return [f"-I{(root / d).resolve()}" for d in dirs]


# ---------------------------------------------------------------------------
# coverage

_GCOV_FILE = re.compile(r"^File '(.+)'$")
_GCOV_LINES = re.compile(r"^Lines executed:([\d.]+)% of (\d+)")
_GCOV_BRANCH = re.compile(r"^Taken at least once:([\d.]+)% of (\d+)")


def parse_gcov(output: str, root: Path) -> dict:
    """Sum gcov -b summaries over the project's own files."""
    totals = {"lines": 0.0, "lines_total": 0, "branches": 0.0, "branches_total": 0}
    mine = False
    for line in output.splitlines():
        if m := _GCOV_FILE.match(line):
            path = Path(m[1])
            mine = path.is_absolute() and path.is_relative_to(root) or not path.is_absolute()
        elif mine and (m := _GCOV_LINES.match(line)):
            totals["lines"] += float(m[1]) * int(m[2]) / 100
            totals["lines_total"] += int(m[2])
        elif mine and (m := _GCOV_BRANCH.match(line)):
            totals["branches"] += float(m[1]) * int(m[2]) / 100
            totals["branches_total"] += int(m[2])
    return totals


def run_coverage(cfg: ProjectConfig, root: Path, work: Path) -> CheckOutcome:
    cc = _tool("cc", cfg.board)
    measured = set(_globs(root, option(cfg, "coverage", "sources")))
    skipped = set(_globs(root, option(cfg, "coverage", "exclude")))
    sources = [s for s in resolve_sources(cfg.sources, root, exclude=work)
               if s.endswith(".c") and s not in skipped]
    if not measured:
        return CheckOutcome("coverage", FAIL, "no source files match coverage.sources")
    out = work / "coverage"
    out.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    flags = (_host_flags(cfg.cflags) + _includes(cfg, root, []) + [f"-I{RUNTIME_DIR}", "-DVIRTULAB_HOST=1"])
    objects, log = [], []
    all_sources = sources + [str(RUNTIME_DIR / "virtulab_test.c"), str(HOST_SHIM)]
    for i, src in enumerate(all_sources):
        path = src if Path(src).is_absolute() else str(root / src)
        (out / f"{i:03d}").mkdir(exist_ok=True)
        obj = out / f"{i:03d}" / f"{Path(src).stem}.o"
        instrument = src in measured
        cmd = [cc, *flags, "-O0", "-g", *(["--coverage"] if instrument else []), "-c", path, "-o", str(obj)]
        code, text = _run(cmd, root, 120)
        if code != 0:
            return CheckOutcome("coverage", FAIL, f"host build of {src} failed", text)
        objects.append(str(obj))
    binary = out / "unit_tests"
    code, text = _run([cc, "--coverage", *objects, "-o", str(binary)], root, 120)
    if code != 0:
        return CheckOutcome("coverage", FAIL, "host link failed", text)
    code, run_log = _run([str(binary)], root, 60)
    log.append(run_log)
    gcov_text = []
    for src in sorted(measured):
        obj = next((o for o in objects if o.endswith(f"/{Path(src).stem}.o")), None)
        if obj is None:
            continue
        _, text = _run(["gcov", "-b", "-o", str(Path(obj).parent), str(root / src)], out, 60)
        gcov_text.append(text)
    data = parse_gcov("\n".join(gcov_text), root)
    if not data["lines_total"]:
        return CheckOutcome("coverage", FAIL, "gcov produced no data", "\n".join(log + gcov_text))
    lp = 100 * data["lines"] / data["lines_total"]
    bp = 100 * data["branches"] / data["branches_total"] if data["branches_total"] else 0.0
    minimum = option(cfg, "coverage", "min_lines")
    summary = (f"{lp:.1f}% lines · {bp:.1f}% branches "
               f"({round(data['lines'])}/{data['lines_total']} lines, "
               f"{round(data['branches'])}/{data['branches_total']} branches)")
    if skipped:
        summary += f". {len(skipped)} hardware-only file(s) not measured"
    status, reason = PASS, ""
    if code != 0:
        status, reason = FAIL, "the unit tests failed on the host build"
    elif minimum and lp < minimum:
        status, reason = FAIL, f"line coverage {lp:.1f}% is below the required {minimum}%"
    return CheckOutcome("coverage", status, summary + (f" — {reason}" if reason else ""),
                        "\n".join(log), {"lines": round(lp, 1), "branches": round(bp, 1)})


# ---------------------------------------------------------------------------
# fuzz

_FUZZ_LINE = re.compile(r"FUZZ execs=(\d+) crashes=(\d+) regressions=(\d+) seed=(\d+) seconds=([\d.]+)")


def run_fuzz(cfg: ProjectConfig, root: Path, work: Path) -> CheckOutcome:
    cc = _tool("cc", cfg.board)
    harness = option(cfg, "fuzz", "harness")
    sources = _globs(root, option(cfg, "fuzz", "sources"))
    seconds, seed = int(option(cfg, "fuzz", "seconds")), int(option(cfg, "fuzz", "seed"))
    crash_dir = option(cfg, "fuzz", "crash_dir")
    include = [f"-I{(root / d).resolve()}" for d in option(cfg, "fuzz", "include")]
    out = work / "fuzz"
    out.mkdir(parents=True, exist_ok=True)
    binary = out / "fuzz_target"
    cmd = [cc, "-O1", "-g", "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
           *include, str(root / harness), *[str(root / s) for s in sources], "-o", str(binary)]
    code, text = _run(cmd, root, 180)
    if code != 0:
        return CheckOutcome("fuzz", FAIL, "the fuzz harness did not build", text)
    (root / crash_dir).mkdir(parents=True, exist_ok=True)
    code, text = _run([str(binary), "--seconds", str(seconds), "--seed", str(seed),
                       "--crash-dir", crash_dir], root, seconds + 60)
    m = _FUZZ_LINE.search(text)
    if not m:
        return CheckOutcome("fuzz", FAIL, "the fuzz run did not finish", text)
    execs, crashes, regressions = int(m[1]), int(m[2]), int(m[3])
    data = {"execs": execs, "crashes": crashes, "regressions": regressions, "seed": seed}
    detail = f"{execs:,} execs in {float(m[5]):.1f}s, seed {seed}"
    if crashes or regressions or code != 0:
        what = "known crash input reproduces" if regressions else "crash found"
        return CheckOutcome("fuzz", FAIL, f"{what}: {crashes} crash(es), {regressions} regression(s). {detail}",
                            text, data)
    return CheckOutcome("fuzz", PASS, f"0 crashes. {detail}. Host-side fuzzing of the logic.", text, data)


# ---------------------------------------------------------------------------
# fault injection

_FAULT_LINE = re.compile(r"FAULT status=(\w+) swept=(\d+) bypass=(\d+) crashed=(\d+)")


def _probes(cfg: ProjectConfig) -> list[str]:
    probe = option(cfg, "fault", "probe")
    return [probe] if isinstance(probe, str) else list(probe)


def _sweep(cfg: ProjectConfig, root: Path, work: Path, probe: str, name: str) -> CheckOutcome:
    from .build import BuildConfig, build  # local: build pulls in the Arm toolchain

    board = BOARDS[cfg.board]
    bcfg = BuildConfig(board=board, sources=[probe, *option(cfg, "fault", "sources")],
                       include_dirs=list(option(cfg, "fault", "include")),
                       cflags=shlex.split(cfg.cflags), runtime=cfg.runtime)
    result = build(root, bcfg, work / "fault" / name / "build", exclude=work)
    if not result.ok or result.elf is None:
        return CheckOutcome("fault", FAIL, f"the fault probe {probe} did not build", result.log)
    cmd = [str(FAULT_SCRIPT), "--elf", str(result.elf), "--board", board.name,
           "--source", option(cfg, "fault", "target")]
    code, text = _run(cmd, root, 1800)
    m = _FAULT_LINE.search(text)
    verdict = next((l for l in text.splitlines() if l.startswith("VERDICT")), "")
    if not m or m[1] == "inconclusive" or code not in (0, 1):
        return CheckOutcome("fault", FAIL, f"{probe}: {verdict or 'the sweep did not finish'}", text)
    swept, bypass, crashed = int(m[2]), int(m[3]), int(m[4])
    data = {"swept": swept, "bypass": bypass, "crashed": crashed}
    if bypass:
        return CheckOutcome("fault", FAIL, f"{probe}: bypass reachable: {bypass} of {swept} "
                                           "single-instruction skips grant access", text, data)
    return CheckOutcome("fault", PASS, f"{probe}: no bypass in {swept} skips", text, data)


def run_fault(cfg: ProjectConfig, root: Path, work: Path) -> CheckOutcome:
    """Sweep once per probe. Each probe states one security property; all of them must hold."""
    runs = [_sweep(cfg, root, work, p, Path(p).stem) for p in _probes(cfg)]
    bad = [r for r in runs if r.failed]
    data = {k: sum(r.data.get(k, 0) for r in runs) for k in ("swept", "bypass", "crashed")}
    log = "\n".join(r.log for r in (bad or runs))
    if bad:
        return CheckOutcome("fault", FAIL, "; ".join(r.summary for r in bad), log, data)
    return CheckOutcome("fault", PASS, f"no bypass in {data['swept']} single-instruction skips across "
                                       f"{len(runs)} propert{'y' if len(runs) == 1 else 'ies'} "
                                       "(first execution only)", log, data)


RUNNERS = {"coverage": run_coverage, "fuzz": run_fuzz, "fault": run_fault}


# ---------------------------------------------------------------------------
# orchestration

@dataclass
class SuiteResult:
    outcome: Outcome | None = None
    checks: list[CheckOutcome] = field(default_factory=list)
    unit_status: str = ""

    @property
    def ok(self) -> bool:
        return not any(c.failed for c in self.checks)

    def checks_markdown(self) -> str:
        if not self.checks:
            return ""
        rows = "\n".join(
            f"| {c.title} | {_ICON[c.status]} {c.status.upper() if c.status != PASS else 'PASS'} | {c.summary} |"
            for c in self.checks)
        return ("#### 🛡️ Selected checks\n\n| Check | Result | Details |\n| :--- | :--- | :--- |\n" + rows +
                "\n\n<sub>Emulation is the fast layer. Hardware-in-the-loop stays the final gate. "
                "See docs/FIDELITY.md.</sub>")


def unit_checks(outcome: Outcome, cfg: ProjectConfig) -> list[CheckOutcome]:
    """Turn the unit run into the `unit` and `footprint` rows."""
    checks = []
    if "unit" in cfg.tests:
        t = outcome.tests
        if not outcome.build.ok:
            checks.append(CheckOutcome("unit", FAIL, "the firmware did not build"))
        elif outcome.status in (PASSED, BUDGET_EXCEEDED) and t.total - t.ignored == 0:
            checks.append(CheckOutcome("unit", FAIL, "the firmware exited cleanly but ran no tests"))
        elif outcome.status in (PASSED, BUDGET_EXCEEDED):
            checks.append(CheckOutcome("unit", PASS, f"{t.passed}/{t.total} tests passed on {cfg.board}"))
        else:
            reason = {"timeout": "timed out", "crashed": "firmware crashed"}.get(outcome.status, "tests failed")
            checks.append(CheckOutcome("unit", FAIL, f"{reason}: {t.passed}/{t.total} tests passed"))
    if "footprint" in cfg.tests:
        sizes = outcome.build.sizes
        if outcome.budget_violations and not outcome.baseline:
            checks.append(CheckOutcome("footprint", FAIL, outcome.budget_violations[0]))
        elif outcome.baseline and sizes:
            summary = (f"Flash {sizes.flash:,} B ({fmt_delta(outcome.flash_delta)}), "
                       f"RAM {sizes.ram:,} B ({fmt_delta(outcome.ram_delta)})")
            if outcome.budget_violations:
                checks.append(CheckOutcome("footprint", FAIL, summary + " — " + outcome.budget_violations[0]))
            else:
                checks.append(CheckOutcome("footprint", PASS, summary))
        elif sizes:
            checks.append(CheckOutcome("footprint", SKIP,
                                       f"Flash {sizes.flash:,} B, RAM {sizes.ram:,} B. "
                                       f"No baseline: {outcome.baseline_note or 'none given'}"))
        else:
            checks.append(CheckOutcome("footprint", FAIL, "the firmware did not build"))
    return checks


def run_extra(cfg: ProjectConfig, root: Path, work: Path) -> list[CheckOutcome]:
    results = []
    for tid in cfg.tests:
        runner = RUNNERS.get(tid)
        if runner is None:
            continue
        print(f"▶ {get_test(tid).title}")
        github.group(f"🛡️ {get_test(tid).title}")
        started = time.monotonic()
        try:
            result = runner(cfg, root, work)
        except VirtulabError as exc:
            result = CheckOutcome(tid, FAIL, str(exc))
        print(f"  {_ICON[result.status]} {result.summary} ({time.monotonic() - started:.1f}s)")
        if result.status == FAIL and result.log:
            print(result.log[-3000:])
        github.end_group()
        results.append(result)
    return results
