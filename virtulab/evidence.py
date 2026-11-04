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
        if c.test in ("fault", "scenarios"):
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
    data["inputs"] = _inputs(cfg, root)
    data["models"] = _models(cfg, root)
    return data


def _inputs(cfg: ProjectConfig, root: Path) -> dict[str, str]:
    """SHA-256 of every file that decides what was tested: the project file, the scenario inputs,
    and the user's own models, so a result names exactly what produced it."""
    names = ["virtulab.yml", cfg.stimulus_file, *cfg.models, cfg.repl]
    cases = (cfg.tests.get("scenarios") or {}).get("cases") or {}
    names += [c.get("stimulus_file") for c in cases.values() if isinstance(c, dict)]
    found = {}
    for name in names:
        if name and (root / name).is_file():
            found[name] = sha256(root / name)
    return dict(sorted(found.items()))


def _models(cfg: ProjectConfig, root: Path) -> dict[str, dict]:
    """Each emulated peripheral: which model answered for it, its file's SHA-256, and how far that
    model has been checked (catalog.model_trust)."""
    from . import DEVICES_DIR
    from .catalog import MODULES, model_trust
    found = {}
    for name, m in cfg.modules.items():
        module = MODULES.get(m.model)
        if not module:
            continue
        entry = {"model": m.model, "title": module.title, "trust": model_trust(m.model)}
        if module.renode_type.startswith("VirtuLab."):
            source = DEVICES_DIR / f"{module.renode_type.split('.', 1)[1]}.cs"
            if source.is_file():
                entry["file"] = f"virtulab/devices/{source.name}"
                entry["sha256"] = sha256(source)
        found[name] = entry
    for name, p in cfg.peripherals.items():
        found[name] = {"model": "register list", "title": f"{name}: described in virtulab.yml",
                       "trust": {"level": "register-list", "label": "Your register list",
                                 "detail": "Stores the registers you listed; it has no behaviour beyond that."}}
    for name, a in cfg.analog.items():
        found[name] = {"model": "ADC", "title": f"{name}: the chip's ADC",
                       "trust": {"level": "ideal", "label": "Ideal ADC",
                                 "detail": "Exact voltages, no noise, sampling or conversion time."}}
    return found


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
    if m.get("models"):
        lines += ["", "## Emulated peripherals", "", "| Peripheral | Model | Evidence behind the model | SHA-256 |",
                  "| :-- | :-- | :-- | :-- |"]
        lines += [f"| {n} | {e['title']} | {e['trust']['label']} | `{e.get('sha256', '—')}` |" for n, e in m["models"].items()]
    if m.get("inputs"):
        lines += ["", "## Inputs", ""] + [f"- `{n}`: `{h}`" for n, h in m["inputs"].items()]
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
