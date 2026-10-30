"""Files a run leaves behind for other tools and for auditors, all under <work dir>/evidence.

  junit.xml      every check and unit test, for any CI's test view
  results.sarif  findings with file and line, for code scanning
  evidence.json  what ran, on exactly which build and tools, with what result
  EVIDENCE.md    the same for a reader, with what each check does not show

This records what happened. It does not claim compliance with any standard.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from . import __version__
from .catalog import get_test
from .config import ProjectConfig

_TOOLS = {"compiler": ["arm-none-eabi-gcc", "--version"], "qemu": ["qemu-system-arm", "--version"],
          "renode": ["renode", "--version"], "host_cc": ["cc", "--version"], "gdb": ["arm-none-eabi-gdb", "--version"]}
_RULES = {
    "VL-UNIT": ("Unit test failed", "error"),
    "VL-FUZZ": ("Fuzzing found a crash", "error"),
    "VL-FAULT": ("A single skipped instruction breaks a security property", "error"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tool_versions() -> dict[str, str]:
    found = {}
    for name, cmd in _TOOLS.items():
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
            except (OSError, subprocess.TimeoutExpired):
                continue
            found[name] = next((l.strip() for l in out.splitlines() if l.strip()), "")
    return found


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(root), *args], capture_output=True, text=True)
    except OSError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def junit_xml(suite) -> str:
    cases: list[str] = []
    failures = 0
    for c in suite.checks:
        body = ""
        if c.status == "fail":
            failures += 1
            body = f"<failure message={quoteattr(c.summary)}>{escape(c.log[-4000:])}</failure>"
        elif c.status == "skip":
            body = f"<skipped message={quoteattr(c.summary)}/>"
        cases.append(f'<testcase classname="virtulab.checks" name={quoteattr(c.test)}>{body}</testcase>')
    if suite.outcome:
        for t in suite.outcome.tests.cases:
            body = ""
            if t.result == "FAIL":
                failures += 1
                body = f"<failure message={quoteattr(t.message or 'failed')}>{escape(t.file)}:{t.line}</failure>"
            elif t.result == "IGNORE":
                body = "<skipped/>"
            cases.append(f'<testcase classname={quoteattr(t.file)} name={quoteattr(t.name)}>{body}</testcase>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<testsuite name="virtulab" tests="{len(cases)}" failures="{failures}">\n  '
            + "\n  ".join(cases) + "\n</testsuite>\n")


def _result(rule: str, message: str, file: str | None, line: int | None) -> dict:
    result: dict = {"ruleId": rule, "level": _RULES[rule][1], "message": {"text": message}}
    if file:
        region = {"region": {"startLine": line}} if line else {}
        result["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": file}, **region}}]
    return result


def sarif(suite) -> dict:
    results = []
    if suite.outcome:
        for t in suite.outcome.tests.failures:
            results.append(_result("VL-UNIT", f"{t.name}: {t.message or 'failed'}", t.file, t.line))
    for c in suite.checks:
        if c.test == "fault":
            for f in c.data.get("findings", []):
                results.append(_result("VL-FAULT", f"Skipping `{f['instruction']}` in {f['function']} breaks "
                                                    f"the property of {f['probe']}", f.get("file"), f.get("line")))
        elif c.test == "fuzz" and c.failed:
            found = c.data.get("finding") or {}
            results.append(_result("VL-FUZZ", c.summary, found.get("file") or c.data.get("harness"), found.get("line")))
    rules = [{"id": k, "shortDescription": {"text": v[0]}} for k, v in _RULES.items()]
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "VirtuLab CI", "version": __version__, "rules": rules}},
                      "results": results}]}


def manifest(cfg: ProjectConfig, suite, root: Path) -> dict:
    data: dict = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "virtulab": __version__,
        "commit": os.environ.get("GITHUB_SHA") or _git(root, "rev-parse", "HEAD"),
        "tree_clean": not _git(root, "status", "--porcelain"),
        "board": cfg.board,
        "tools": _tool_versions(),
        "overall": "fail" if any(c.failed for c in suite.checks) else "pass",
        "checks": [{"test": c.test, "status": c.status, "summary": c.summary,
                    "limits": get_test(c.test).limits,
                    "data": {k: v for k, v in c.data.items() if k != "findings"}} for c in suite.checks],
    }
    build = suite.outcome.build if suite.outcome else None
    if build and build.elf and build.elf.is_file():
        data["image"] = {"sha256": sha256(build.elf), "flash": build.sizes.flash, "ram": build.sizes.ram}
    return data


def evidence_markdown(m: dict) -> str:
    lines = ["# VirtuLab evidence record", "",
             "What ran, on which build, and with what result. This is an input to a safety or security "
             "case, not a statement of compliance with any standard.", "",
             f"- **Result:** {m['overall']}", f"- **Commit:** `{m['commit'] or 'not a git repository'}`"
             + ("" if m["tree_clean"] else " (with uncommitted changes)"),
             f"- **Board:** `{m['board']}`", f"- **Generated:** {m['generated']} by VirtuLab {m['virtulab']}"]
    if "image" in m:
        lines.append(f"- **Unit-test image SHA-256:** `{m['image']['sha256']}`")
    lines += ["", "| Check | Result | Details | What it does not show |", "| :-- | :-- | :-- | :-- |"]
    clean = lambda t: re.sub(r"\s+", " ", t).replace("|", "\\|")
    for c in m["checks"]:
        lines.append(f"| {c['test']} | {c['status']} | {clean(c['summary'])} | {clean(c['limits']) or '—'} |")
    lines += ["", "## Tools", ""] + [f"- **{k}:** {v}" for k, v in m["tools"].items()] + [""]
    return "\n".join(lines)


def write(cfg: ProjectConfig, suite, root: Path, work: Path) -> Path:
    out = work / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    (out / "junit.xml").write_text(junit_xml(suite))
    (out / "results.sarif").write_text(json.dumps(sarif(suite), indent=2))
    m = manifest(cfg, suite, root)
    (out / "evidence.json").write_text(json.dumps(m, indent=2))
    (out / "EVIDENCE.md").write_text(evidence_markdown(m))
    return out
