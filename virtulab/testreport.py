"""The verification report: one page per run, for people, with what was expected and what came out.

Written by `virtulab run` as .virtulab/report.html next to the evidence files. It is built only from
what the run produced: the evidence manifest, each test's checks as the on-target runtime printed
them, and each scenario's inputs and output. Print it from the browser for a PDF.
"""

import json
from pathlib import Path

from .boards import BOARDS
from .catalog import TESTS


def build(cfg, suite, root: Path, manifest: dict, command: str = "") -> dict:
    outcome = suite.outcome
    unit = []
    if outcome and outcome.tests:
        for case in outcome.tests.cases:
            unit.append({"file": case.file, "line": case.line, "name": case.name, "result": case.result,
                         "message": case.message, "checks": case.checks})
    from .scaffold import origins
    files = sorted({u["file"] for u in unit})
    who = origins(cfg, root, files)
    checks = []
    for c in suite.checks:
        test = TESTS.get(c.test)
        checks.append({"test": c.test, "title": c.title, "status": c.status, "summary": c.summary,
                       "limits": test.limits if test else "", "data": c.data})
    return {
        "project": root.name,
        "command": command,
        "board": {"name": cfg.board, "description": BOARDS[cfg.board].description, "cpu": BOARDS[cfg.board].cpu,
                  "emulator": BOARDS[cfg.board].emulator},
        "manifest": manifest,
        "unit": unit,
        "origins": who,
        "checks": checks,
        "modules": {n: {"model": m.model, "bus": m.bus, "address": m.address} for n, m in cfg.modules.items()},
    }


def write(cfg, suite, root: Path, work: Path, manifest: dict, command: str = "") -> Path:
    data = build(cfg, suite, root, manifest, command)
    page = (Path(__file__).with_name("ui") / "report.html").read_text()
    (work / "report.json").write_text(json.dumps(data))
    out = work / "report.html"
    out.write_text(page.replace("/*REPORT_DATA*/null", json.dumps(data).replace("</", "<\\/"), 1))
    return out
