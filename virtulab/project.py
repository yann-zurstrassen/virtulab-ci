"""Run a project described by virtulab.yml: check it, run the selected tests, report."""

import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from . import VirtulabError, evidence, github
from .check import check
from .cigen import IMAGE
from .cli import EXIT_ERROR, EXIT_FAILED, Options, finish, parse_byte_limit, parse_timeout, run_unit
from .config import ProjectConfig, option, renode_repl
from .report import marker
from .suite import _ICON, FAIL, SuiteResult, run_extra, unit_checks


def select_tests(cfg: ProjectConfig, only: list[str] | None, skip: list[str] | None) -> ProjectConfig:
    """Narrow the configured tests for one run (`--only`, `--skip`, the action's `tests` input)."""
    tests = dict(cfg.tests)
    if only:
        unknown = [t for t in only if t not in tests]
        if unknown:
            raise VirtulabError(f"Test(s) {', '.join(unknown)} are not enabled in virtulab.yml. "
                                f"Enabled: {', '.join(tests) or 'none'}")
        tests = {t: tests[t] for t in only}
    for t in skip or []:
        tests.pop(t, None)
    return replace(cfg, tests=tests)


def to_options(cfg: ProjectConfig, root: Path, base: Options) -> Options:
    """Map the project configuration onto the engine options (flags in `base` win)."""
    footprint = cfg.tests.get("footprint")
    return replace(
        base,
        board=cfg.board,
        sources=cfg.sources,
        include_dirs=cfg.include,
        cflags=cfg.cflags.split(),
        ldflags=cfg.ldflags.split(),
        linker_script=cfg.linker_script,
        runtime=cfg.runtime,
        build_command=cfg.build_command,
        build_elf=cfg.build_elf,
        peripherals=renode_repl(cfg),
        timeout=parse_timeout(cfg.timeout),
        baseline_ref=base.baseline_ref if footprint is not None else None,
        max_flash_increase=(base.max_flash_increase if base.max_flash_increase is not None else
                            parse_byte_limit(str(option(cfg, "footprint", "flash_increase")))
                            if footprint is not None else None),
        max_ram_increase=(base.max_ram_increase if base.max_ram_increase is not None else
                          parse_byte_limit(str(option(cfg, "footprint", "ram_increase")))
                          if footprint is not None else None),
        root=root,
    )


def run_project(cfg: ProjectConfig, root: Path, base: Options) -> int:
    root = root.resolve()
    if not cfg.tests:
        raise VirtulabError("No tests selected. Enable some in virtulab.yml or run `virtulab init`.")

    result = check(cfg, root)
    github.group("🔎 Board check")
    print(result.to_text())
    github.end_group()
    if result.only_missing_tools and not os.environ.get("VIRTULAB_IN_DOCKER"):
        code = _run_in_docker(cfg, root, base)
        if code is not None:
            return code
        print("\nInstall the missing tools, or install Docker and VirtuLab will use its image.")
    if not result.ok:
        if github.in_actions():
            for f in result.errors:
                github.annotate("error", f"{f.subject}: {f.message}", title="VirtuLab configuration error")
        return EXIT_ERROR

    opts = to_options(cfg, root, base)
    work = (root / opts.work_dir).resolve()
    suite = SuiteResult()

    if "unit" in cfg.tests or "footprint" in cfg.tests:
        outcome, root, work = run_unit(opts)
        suite.outcome = outcome
        suite.checks += unit_checks(outcome, cfg)
    suite.checks += run_extra(cfg, root, work)
    # keep the order of the project file
    order = list(cfg.tests)
    suite.checks.sort(key=lambda c: order.index(c.test) if c.test in order else len(order))

    failed = [c for c in suite.checks if c.status == FAIL]
    print()
    print("── Summary ─────────────────────────────────────────────")
    for c in suite.checks:
        print(f"{_ICON[c.status]} {c.title:<38} {c.summary}")
    if github.in_actions():
        for c in failed:
            github.annotate("error", c.summary, title=f"{c.title} failed")

    extra = {
        "checks_total": len(suite.checks),
        "checks_failed": len(failed),
        "checks": ",".join(f"{c.test}={c.status}" for c in suite.checks),
    }
    written = evidence.write(cfg, suite, root, work)
    print(f"🧾 Evidence written to {os.path.relpath(written)}")
    if suite.outcome is None:
        code = _finish_without_unit(opts, cfg, suite, work, extra)
    else:
        code = finish(opts, suite.outcome, root, work, checks_md=suite.checks_markdown(),
                      extra_outputs=extra, extra_ok=not failed)
    total = len(suite.checks)
    if failed:
        print(f"❌ {len(failed)} of {total} selected check{'s' if total != 1 else ''} failed")
    else:
        print(f"✅ All {total} selected checks passed" if total != 1 else "✅ The selected check passed")
    return code


def _run_in_docker(cfg: ProjectConfig, root: Path, base: Options) -> int | None:
    """Re-run inside the VirtuLab image when this machine lacks the toolchain or emulator."""
    docker = shutil.which("docker")
    if not docker:
        return None
    image = os.environ.get("VIRTULAB_IMAGE", IMAGE)
    cmd = [docker, "run", "--rm", "-v", f"{root}:/workspace", "-w", "/workspace", image,
           "run", "--only", ",".join(cfg.tests)]
    if base.baseline_ref:
        cmd += ["--baseline", base.baseline_ref]
    print(f"🐳 Some tools are not installed here, so the tests run in {image}\n")
    sys.stdout.flush()
    return subprocess.run(cmd).returncode


def _finish_without_unit(opts: Options, cfg: ProjectConfig, suite: SuiteResult, work: Path,
                         extra: dict) -> int:
    """Report for projects that only selected security checks (no firmware build)."""
    ok = suite.ok
    lines = [marker(opts.report_id),
             f"### 🛡️ VirtuLab CI Report — `{cfg.board}`", "",
             f"**Status:** {'✅ PASSED' if ok else '❌ FAILED'}", "", suite.checks_markdown(), ""]
    for c in suite.checks:
        if c.log and c.status == FAIL:
            lines += [f"<details><summary>{c.title} log</summary>", "", "```text", c.log[-6000:], "```",
                      "</details>", ""]
    markdown = "\n".join(lines)
    work.mkdir(parents=True, exist_ok=True)
    (work / "report.md").write_text(markdown)
    if github.in_actions():
        github.set_outputs({"status": "passed" if ok else "failed", **extra})
        github.append_summary(markdown)
        if opts.comment:
            github.post_pr_comment(markdown, marker(opts.report_id), opts.github_token)
    else:
        print(f"📝 Report written to {os.path.relpath(work / 'report.md')}")
    return 0 if ok else EXIT_FAILED
