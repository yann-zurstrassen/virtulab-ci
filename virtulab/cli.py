"""Command line entry point: `python3 -m virtulab run|boards|action`."""

import argparse
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import VirtulabError, __version__, github
from .baseline import build_baseline
from .boards import BOARDS, get_board
from .build import BuildConfig, addr2line, build
from .emulator import run as run_emulator
from .parse import parse_fault, parse_tests
from .report import (
    BUILD_FAILED, PASSED, STATUS_LABELS, Outcome, fmt_bytes, fmt_capacity, fmt_delta, marker,
    render_markdown,
)

EXIT_FAILED = 1
EXIT_ERROR = 2


@dataclass
class Options:
    board: str = "lm3s6965evb"
    sources: list[str] = field(default_factory=lambda: ["**/*.c"])
    include_dirs: list[str] = field(default_factory=list)
    cflags: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)
    linker_script: str | None = None
    runtime: bool = True
    peripherals: str | None = None  # Renode .repl file or inline description
    timeout: float = 30.0
    baseline_ref: str | None = None
    max_flash_increase: int | None = None
    max_ram_increase: int | None = None
    root: Path = Path(".")
    work_dir: str = ".virtulab"
    comment: bool = False
    github_token: str = ""
    report_id: str = "default"


def parse_timeout(value: str) -> float:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|m)?\s*", value)
    if not m:
        raise VirtulabError(f"Invalid timeout '{value}' (use e.g. 30s, 2m or 500ms)")
    number, unit = float(m[1]), m[2] or "s"
    return number * {"ms": 0.001, "s": 1, "m": 60}[unit]


def parse_byte_limit(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    m = re.fullmatch(r"\s*(\d+)\s*(B|K|KB|KiB)?\s*", value, re.IGNORECASE)
    if not m:
        raise VirtulabError(f"Invalid byte limit '{value}' (use e.g. 512 or 4K)")
    return int(m[1]) * (1024 if m[2] and m[2].upper().startswith("K") else 1)


def split_list(value: str) -> list[str]:
    """Split a whitespace/comma/newline separated action input."""
    return [item for item in re.split(r"[\s,]+", value) if item]


def options_from_env(env: dict[str, str]) -> Options:
    """Build Options from the INPUT_* variables GitHub passes to docker actions."""
    def get(name: str, default: str = "") -> str:
        return env.get(f"INPUT_{name.upper()}", default).strip()

    return Options(
        board=get("board") or "lm3s6965evb",
        sources=split_list(get("sources")) or ["**/*.c"],
        include_dirs=split_list(get("include_dirs")),
        cflags=shlex.split(get("cflags")),
        ldflags=shlex.split(get("ldflags")),
        linker_script=get("linker_script") or None,
        runtime=get("runtime", "true").lower() != "false",
        peripherals=get("peripherals") or None,
        timeout=parse_timeout(get("timeout") or "30s"),
        baseline_ref=get("baseline_ref") or None,
        max_flash_increase=parse_byte_limit(get("max_flash_increase")),
        max_ram_increase=parse_byte_limit(get("max_ram_increase")),
        root=Path(get("working_directory") or "."),
        comment=get("comment", "true").lower() == "true",
        github_token=get("github_token"),
        report_id=get("report_id") or "default",
    )


def options_from_args(ns: argparse.Namespace) -> Options:
    return Options(
        board=ns.board,
        sources=ns.sources,
        include_dirs=ns.include,
        cflags=shlex.split(ns.cflags),
        ldflags=shlex.split(ns.ldflags),
        linker_script=ns.linker_script,
        runtime=not ns.no_runtime,
        peripherals=ns.peripherals,
        timeout=parse_timeout(ns.timeout),
        baseline_ref=ns.baseline,
        max_flash_increase=parse_byte_limit(ns.max_flash_increase),
        max_ram_increase=parse_byte_limit(ns.max_ram_increase),
        root=Path(ns.directory),
        work_dir=ns.work_dir,
        comment=ns.comment,
        github_token=os.environ.get("GITHUB_TOKEN", ""),
    )


def load_peripherals(value: str | None, root: Path) -> str | None:
    """A peripherals value is either a .repl file in the project or inline text."""
    if not value:
        return None
    if "\n" not in value and ":" not in value:
        path = root / value
        if not path.is_file():
            raise VirtulabError(f"Peripherals file '{value}' not found")
        return path.read_text()
    return value


def _report_diagnostics(root: Path, outcome: Outcome) -> None:
    """Turn compiler errors, failing tests and crashes into PR annotations."""
    if not github.in_actions():
        return
    for d in outcome.build.diagnostics:
        github.annotate(d.severity, d.message, github.repo_path(root, d.file), d.line,
                        title=f"Compiler {d.severity}")
    for case in outcome.tests.failures:
        github.annotate("error", case.message or "Test failed",
                        github.repo_path(root, case.file), case.line,
                        title=f"Test failed: {case.name}")
    if outcome.fault:
        f = outcome.fault
        file, line = None, None
        if f.location:
            path, _, line_text = f.location.rpartition(":")
            file, line = github.repo_path(root, path), int(line_text)
        github.annotate("error", f"Firmware crashed with {f.kind} (pc={f.pc:#010x}) {f.registers}",
                        file, line, title=f"{f.kind} on {outcome.board.name}")
    if outcome.run and outcome.run.timed_out:
        github.annotate("error", f"Firmware did not exit within {outcome.timeout:g}s",
                        title="Emulation timed out")
    for violation in outcome.budget_violations:
        github.annotate("error", violation, title="Memory budget exceeded")


def _check_budgets(opts: Options, outcome: Outcome) -> None:
    for label, delta, limit in (
        ("Flash", outcome.flash_delta, opts.max_flash_increase),
        ("RAM", outcome.ram_delta, opts.max_ram_increase),
    ):
        if delta is not None and limit is not None and delta > limit:
            outcome.budget_violations.append(
                f"{label} grew by {delta:,} B, above the allowed {limit:,} B increase."
            )


def execute(opts: Options) -> int:
    board = get_board(opts.board)
    root = opts.root.resolve()
    if not root.is_dir():
        raise VirtulabError(f"Working directory '{opts.root}' does not exist")
    work_dir = (root / opts.work_dir).resolve()
    if work_dir == root or root.is_relative_to(work_dir):
        raise VirtulabError("The work directory must be a subdirectory of the project")

    cfg = BuildConfig(
        board=board,
        sources=opts.sources,
        include_dirs=opts.include_dirs,
        cflags=opts.cflags,
        ldflags=opts.ldflags,
        linker_script=opts.linker_script,
        runtime=opts.runtime,
    )

    peripherals = load_peripherals(opts.peripherals, root)
    emulator_name = "Renode" if board.emulator == "renode" else "QEMU"
    print(f"🚀 VirtuLab CI {__version__} — {board.name} ({board.cpu}, {board.description})")

    github.group("🔨 Build")
    result = build(root, cfg, work_dir / "build", exclude=work_dir)
    for src in result.sources:
        print(f"  {src}")
    if result.log.strip():
        print(result.log.rstrip())
    github.end_group()
    outcome = Outcome(board=board, build=result, timeout=opts.timeout)

    if result.ok and result.sizes:
        sizes = result.sizes
        print(f"📊 Flash {fmt_bytes(sizes.flash)} / {fmt_capacity(board.flash_size)} · "
              f"RAM {fmt_bytes(sizes.ram)} / {fmt_capacity(board.ram_size)} "
              f"(text {sizes.text:,}, data {sizes.data:,}, bss {sizes.bss:,})")

        if opts.baseline_ref:
            github.group(f"📐 Baseline build ({opts.baseline_ref})")
            outcome.baseline, outcome.baseline_note = build_baseline(
                opts.baseline_ref, root, cfg, work_dir
            )
            if outcome.baseline:
                print(f"Baseline {outcome.baseline.sha[:7]}: "
                      f"Flash {fmt_delta(outcome.flash_delta)}, RAM {fmt_delta(outcome.ram_delta)}")
            else:
                print(f"No baseline: {outcome.baseline_note}")
            github.end_group()
            _check_budgets(opts, outcome)

        print(f"⚡ Emulating on {emulator_name} {board.name} (timeout {opts.timeout:g}s)")
        github.group("Emulator output")
        outcome.run = run_emulator(board, result.elf, opts.timeout, work_dir / "emulator",
                                   peripherals)
        print(outcome.run.output)
        github.end_group()
        if outcome.run.sim_commands:
            print("🎛️  Emulator commands from vl_sim():")
            for line in outcome.run.sim_commands:
                print(f"  {line}")

        outcome.tests = parse_tests(outcome.run.output)
        outcome.fault = parse_fault(outcome.run.output)
        if outcome.fault:
            function, location = addr2line(result.elf, outcome.fault.pc)
            if location and Path(location).is_absolute():
                path, _, line = location.rpartition(":")
                if Path(path).resolve().is_relative_to(root):
                    location = f"{Path(path).resolve().relative_to(root).as_posix()}:{line}"
            outcome.fault.function, outcome.fault.location = function, location

    status = outcome.status
    summary = STATUS_LABELS[status]
    if outcome.run:
        summary += f" in {outcome.run.duration:.2f}s"
        if outcome.run.exit_code not in (None, 0):
            summary += f" (exit code {outcome.run.exit_code})"
    if outcome.tests.total:
        summary += f" — {outcome.tests.passed}/{outcome.tests.total} tests passed"
    print(summary)
    if outcome.fault:
        where = outcome.fault.location or f"pc={outcome.fault.pc:#010x}"
        print(f"💥 {outcome.fault.kind} in {outcome.fault.function or '?'} at {where}")

    markdown = render_markdown(outcome, opts.report_id)
    report_path = work_dir / "report.md"
    report_path.write_text(markdown)
    _report_diagnostics(root, outcome)

    if github.in_actions():
        sizes = result.sizes
        try:
            report_output = report_path.relative_to(github.workspace()).as_posix()
        except ValueError:
            report_output = str(report_path)
        github.set_outputs({
            "status": status,
            "flash_bytes": sizes.flash if sizes else "",
            "ram_bytes": sizes.ram if sizes else "",
            "flash_delta": outcome.flash_delta,
            "ram_delta": outcome.ram_delta,
            "tests_total": outcome.tests.total,
            "tests_passed": outcome.tests.passed,
            "tests_failed": outcome.tests.failed,
            "emulation_seconds": f"{outcome.run.duration:.2f}" if outcome.run else "",
            "report_path": report_output,
        })
        github.append_summary(markdown)
        if opts.comment:
            github.post_pr_comment(markdown, marker(opts.report_id), opts.github_token)
    else:
        print(f"📝 Report written to {os.path.relpath(report_path)}")

    if status == PASSED:
        return 0
    return EXIT_ERROR if status == BUILD_FAILED else EXIT_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="virtulab",
        description="Build bare-metal Cortex-M firmware, run it in QEMU and report the results.",
    )
    parser.add_argument("--version", action="version", version=f"virtulab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="build, measure and emulate firmware")
    run.add_argument("-b", "--board", default="lm3s6965evb", help="target board (see `boards`)")
    run.add_argument("-s", "--sources", nargs="+", default=["**/*.c"], metavar="GLOB",
                     help="source files or glob patterns (default: **/*.c)")
    run.add_argument("-I", "--include", action="append", default=[], metavar="DIR",
                     help="include directory (repeatable)")
    run.add_argument("--cflags", default="", help='extra compiler flags, e.g. "-O2 -DDEBUG"')
    run.add_argument("--ldflags", default="", help='extra linker flags, e.g. "-lm"')
    run.add_argument("--linker-script", help="custom linker script (default: generated)")
    run.add_argument("--no-runtime", action="store_true",
                     help="don't link the VirtuLab startup code (bring your own vector table)")
    run.add_argument("-p", "--peripherals", metavar="REPL",
                     help="extra Renode devices: a .repl file, or inline text such as "
                          "'tmp108: Sensors.TMP108 @ i2c1 0x48' (Renode boards only)")
    run.add_argument("-t", "--timeout", default="30s", help="emulation timeout (default: 30s)")
    run.add_argument("--baseline", metavar="REF",
                     help="git ref to compare the memory footprint against, e.g. main")
    run.add_argument("--max-flash-increase", metavar="BYTES",
                     help="fail if flash grows more than this vs the baseline")
    run.add_argument("--max-ram-increase", metavar="BYTES",
                     help="fail if RAM grows more than this vs the baseline")
    run.add_argument("-C", "--directory", default=".", help="project directory (default: .)")
    run.add_argument("--work-dir", default=".virtulab",
                     help="build/report directory inside the project (default: .virtulab)")
    run.add_argument("--comment", action="store_true",
                     help="post the report as a PR comment (GitHub Actions only)")

    sub.add_parser("boards", help="list supported boards")
    sub.add_parser("action", help="run with GitHub Action inputs (INPUT_* variables)")
    return parser


def main(argv: list[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    try:
        if ns.command == "boards":
            print(f"{'Board':<18} {'CPU':<11} {'Flash':>8} {'RAM':>8}  {'Emulator':<8}  Device")
            for b in BOARDS.values():
                print(f"{b.name:<18} {b.cpu:<11} {fmt_capacity(b.flash_size):>8} "
                      f"{fmt_capacity(b.ram_size):>8}  {b.emulator:<8}  {b.description}")
            return 0
        opts = options_from_env(dict(os.environ)) if ns.command == "action" else options_from_args(ns)
        return execute(opts)
    except VirtulabError as exc:
        if github.in_actions():
            github.annotate("error", str(exc), title="VirtuLab CI configuration error")
        else:
            print(f"❌ {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
