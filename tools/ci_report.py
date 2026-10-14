#!/usr/bin/env python3
"""Assemble the sticky PR comment from the fragments the CI jobs leave in .ci/.

Reads .ci/footprint.md (the engine report: tests, Flash/RAM, delta vs baseline)
and the one-line RESULT files of the coverage, fuzz and fault-injection jobs.
Prints Markdown to --out, and with --post upserts it as the PR comment.
"""
import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI_DIR = Path(".ci")
MARKER = "<!-- virtulab-ci-report:default -->"


def read(path: Path) -> str | None:
    return path.read_text() if path.is_file() else None


def key_values(line: str) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S+)", line))


def result_line(text: str | None, tag: str) -> str | None:
    if text is None:
        return None
    lines = [ln for ln in text.splitlines() if ln.startswith(tag + " ")]
    return lines[-1] if lines else None


def coverage_row(text: str | None) -> tuple[str, str]:
    line = result_line(text, "COVERAGE")
    if line is None:
        return "⏭️ not run", ""
    lines = re.search(r"lines=(\S+) \((\S+)\)", line)
    branches = re.search(r"branches=(\S+) \((\S+)\)", line)
    if not (lines and branches):
        return "⚠️ unreadable", line
    return (f"`{lines[1]}` lines · `{branches[1]}` branches",
            f"{lines[2]} lines, {branches[2]} branches taken at least once (gcov, native build)")


def fuzz_row(text: str | None) -> tuple[str, str]:
    line = result_line(text, "FUZZ")
    if line is None:
        return "⏭️ not run", ""
    kv = key_values(line)
    found = int(kv["crashes"]) + int(kv["regressions"])
    status = "✅ 0 crashes" if found == 0 else f"❌ {found} crash found"
    detail = (f"{int(kv['execs']):,} execs in {kv['seconds']}s, seed {kv['seed']}; "
              f"{kv['regressions']} known crash input(s) reproduced. Host-side parser fuzzing.")
    return status, detail


def fault_row(text: str | None) -> tuple[str, str]:
    line = result_line(text, "FAULT")
    if line is None:
        return "⏭️ not run", ""
    kv = key_values(line)
    if kv["status"] == "bypass":
        return ("❌ auth bypass reachable by single instruction skip",
                f"{kv['bypass']} of {kv['swept']} skipped instructions grant a wrong PIN")
    return ("✅ no bypass found",
            f"{kv['swept']} single-instruction skips tried, first execution only")


def build_report() -> str:
    footprint = read(CI_DIR / "footprint.md") or read(Path(".virtulab/report.md"))
    base = (footprint or f"{MARKER}\n### 🤖 VirtuLab CI Report\n\n_No engine report found._\n").rstrip()
    if MARKER not in base:
        base = f"{MARKER}\n{base}"
    rows = [
        ("Coverage (unit tests)", *coverage_row(read(CI_DIR / "coverage.txt"))),
        ("Fuzzing (`parser`)", *fuzz_row(read(CI_DIR / "fuzz.txt"))),
        ("Fault injection (`auth`)", *fault_row(read(CI_DIR / "fault.txt"))),
    ]
    table = "\n".join(f"| {name} | {status} | {detail} |" for name, status, detail in rows)
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    sha = os.environ.get("GITHUB_SHA", "")
    fidelity = (f"{server}/{repo}/blob/{sha}/docs/FIDELITY.md" if server and repo and sha
                else "docs/FIDELITY.md")
    return (f"{base}\n\n### 🛡️ Security & safety checks\n\n"
            f"| Check | Result | Details |\n| :--- | :--- | :--- |\n{table}\n\n"
            f"Fidelity: see [docs/FIDELITY.md]({fidelity}). Emulation is the fast layer; "
            f"hardware-in-the-loop stays the final gate.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=".ci/report.md")
    parser.add_argument("--post", action="store_true", help="upsert the PR comment (GitHub Actions)")
    args = parser.parse_args()

    report = build_report()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(f"report written to {out}")
    if args.post:
        sys.path.insert(0, str(ROOT))
        from virtulab import github
        github.post_pr_comment(report, MARKER, os.environ.get("GITHUB_TOKEN", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
