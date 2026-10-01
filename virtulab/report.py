"""Run outcome model and the Markdown report posted to PRs and job summaries."""

from dataclasses import dataclass, field

from .baseline import Baseline, diff_symbols
from .boards import Board
from .build import BuildResult
from .emulator import RunResult
from .parse import Fault, TestSummary

PASSED = "passed"
FAILED = "failed"
CRASHED = "crashed"
TIMEOUT = "timeout"
BUILD_FAILED = "build_failed"
BUDGET_EXCEEDED = "budget_exceeded"

STATUS_LABELS = {
    PASSED: "✅ PASSED",
    FAILED: "❌ FAILED",
    CRASHED: "💥 CRASHED",
    TIMEOUT: "⏱️ TIMED OUT",
    BUILD_FAILED: "🔨 BUILD FAILED",
    BUDGET_EXCEEDED: "⚠️ MEMORY BUDGET EXCEEDED",
}

MAX_LOG_CHARS = 30_000  # PR comments are capped at 65,536 characters


@dataclass
class Outcome:
    board: Board
    build: BuildResult
    run: RunResult | None = None
    tests: TestSummary = field(default_factory=TestSummary)
    fault: Fault | None = None
    baseline: Baseline | None = None
    baseline_note: str | None = None
    budget_violations: list[str] = field(default_factory=list)
    timeout: float = 0.0

    @property
    def status(self) -> str:
        if not self.build.ok or self.run is None:
            return BUILD_FAILED
        if self.fault:
            return CRASHED
        if self.run.timed_out:
            return TIMEOUT
        if self.run.exit_code != 0 or self.tests.failed:
            return FAILED
        if self.budget_violations:
            return BUDGET_EXCEEDED
        return PASSED

    @property
    def flash_delta(self) -> int | None:
        if self.baseline and self.build.sizes:
            return self.build.sizes.flash - self.baseline.sizes.flash
        return None

    @property
    def ram_delta(self) -> int | None:
        if self.baseline and self.build.sizes:
            return self.build.sizes.ram - self.baseline.sizes.ram
        return None


def marker(report_id: str) -> str:
    return f"<!-- virtulab-ci-report:{report_id} -->"


def fmt_bytes(n: int) -> str:
    return f"{n:,} B"


def fmt_capacity(n: int) -> str:
    if n >= 1024 * 1024 and n % (1024 * 1024) == 0:
        return f"{n // (1024 * 1024)} MiB"
    return f"{n // 1024} KiB"


def fmt_delta(delta: int | None) -> str:
    if delta is None:
        return "—"
    if delta > 0:
        return f"+{delta:,} B 📈"
    if delta < 0:
        return f"{delta:,} B 📉"
    return "±0 B"


def _usage(used: int, capacity: int) -> str:
    return f"{used / capacity:.1%} of {fmt_capacity(capacity)}"


def _fence(text: str) -> str:
    """Wrap text in a code fence that cannot be closed by the text itself."""
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}text\n{text}\n{fence}"


def _truncate(text: str, limit: int = MAX_LOG_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"… ({len(text) - limit:,} earlier characters truncated)\n" + text[-limit:]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(outcome: Outcome, report_id: str = "default") -> str:
    board = outcome.board
    lines = [
        marker(report_id),
        f"### 🤖 VirtuLab CI Report — `{board.name}` ({board.cpu}, "
        f"{'Renode' if board.emulator == 'renode' else 'QEMU'})",
        "",
    ]

    status = f"**Status:** {STATUS_LABELS[outcome.status]}"
    if outcome.run:
        status += f" · Emulation `{outcome.run.duration:.2f}s`"
    lines += [status, ""]

    sizes = outcome.build.sizes
    if sizes:
        base_label = (
            f"Δ vs `{outcome.baseline.sha[:7]}`" if outcome.baseline else "Δ vs baseline"
        )
        lines += [
            f"| Metric | Current | {base_label} | Usage |",
            "| :--- | ---: | ---: | :--- |",
            f"| **Flash** | `{fmt_bytes(sizes.flash)}` | {fmt_delta(outcome.flash_delta)} "
            f"| {_usage(sizes.flash, board.flash_size)} |",
            f"| **RAM** | `{fmt_bytes(sizes.ram)}` | {fmt_delta(outcome.ram_delta)} "
            f"| {_usage(sizes.ram, board.ram_size)} (static) |",
        ]
        tests = outcome.tests
        if tests.total:
            icon = "✅" if not tests.failed else "❌"
            ignored = f", {tests.ignored} ignored" if tests.ignored else ""
            lines.append(
                f"| **Unit tests** | `{tests.passed} / {tests.total}` | — "
                f"| {icon} {tests.failed} failed{ignored} |"
            )
        lines.append("")

    if outcome.baseline_note and not outcome.baseline:
        lines += [f"<sub>No footprint delta: {outcome.baseline_note}.</sub>", ""]

    for violation in outcome.budget_violations:
        lines.append(f"> [!WARNING]\n> {violation}")
    if outcome.budget_violations:
        lines.append("")

    if not outcome.build.ok:
        errors = [d for d in outcome.build.diagnostics if d.severity == "error"]
        if errors:
            lines += ["#### 🔨 Compiler errors", "", "| Location | Error |", "| :--- | :--- |"]
            lines += [f"| `{d.file}:{d.line}` | {_cell(d.message)} |" for d in errors[:20]]
            lines.append("")
        lines += [
            "<details open>",
            "<summary>Build log</summary>",
            "",
            _fence(_truncate(outcome.build.log.strip())),
            "</details>",
        ]
        return "\n".join(lines) + "\n"

    failures = outcome.tests.failures
    if failures:
        lines += ["#### ❌ Failing tests", "", "| Test | Location | Message |",
                  "| :--- | :--- | :--- |"]
        lines += [
            f"| `{c.name}` | `{c.file}:{c.line}` | {_cell(c.message) or '—'} |"
            for c in failures
        ]
        lines.append("")

    if outcome.fault:
        f = outcome.fault
        where = f" in `{f.function}`" if f.function else ""
        at = f" at `{f.location}`" if f.location else ""
        lines += [
            f"#### 💥 {f.kind}{where}{at}",
            "",
            f"`pc={f.pc:#010x} lr={f.lr:#010x}` {f.registers}".rstrip(),
            "",
        ]

    if outcome.run and outcome.run.timed_out:
        lines += [
            f"#### ⏱️ Firmware did not exit within {outcome.timeout:g}s",
            "",
            "Return from `main()` or call `vl_exit(code)` to end the run.",
            "",
        ]

    if outcome.baseline:
        changes = diff_symbols(outcome.baseline.symbols, outcome.build.symbols)
        if changes:
            lines += [
                "<details>",
                "<summary>📊 Largest symbol size changes</summary>",
                "",
                "| Symbol | Before | After | Δ |",
                "| :--- | ---: | ---: | ---: |",
            ]
            lines += [
                f"| `{_cell(c.name)}` | {c.before:,} | {c.after:,} | {c.delta:+,} |"
                for c in changes
            ]
            lines += ["", "</details>", ""]

    if outcome.run and outcome.run.sim_commands:
        lines += [
            "<details>",
            "<summary>🎛️ Emulator commands (vl_sim)</summary>",
            "",
            _fence("\n".join(outcome.run.sim_commands)),
            "</details>",
            "",
        ]

    if outcome.run:
        lines += [
            "<details>",
            "<summary>🔍 Emulator output</summary>",
            "",
            _fence(_truncate(outcome.run.output.strip() or "(no output)")),
            "</details>",
        ]
    return "\n".join(lines) + "\n"
