"""Parsers for compiler diagnostics, Unity test output and runtime fault reports."""

import re
from dataclasses import dataclass, field


@dataclass
class Diagnostic:
    file: str
    line: int
    column: int | None
    severity: str  # "error" | "warning"
    message: str


@dataclass
class TestCase:
    file: str
    line: int
    name: str
    result: str  # "PASS" | "FAIL" | "IGNORE"
    message: str = ""


@dataclass
class TestSummary:
    cases: list[TestCase] = field(default_factory=list)
    total: int = 0
    failed: int = 0
    ignored: int = 0

    @property
    def passed(self) -> int:
        return self.total - self.failed - self.ignored

    @property
    def failures(self) -> list[TestCase]:
        return [c for c in self.cases if c.result == "FAIL"]


@dataclass
class Fault:
    kind: str  # e.g. "HardFault"
    pc: int
    lr: int
    registers: str  # remaining "cfsr=... hfsr=..." text, may be empty
    location: str | None = None  # "file:line", resolved via addr2line
    function: str | None = None


_GCC_DIAGNOSTIC = re.compile(
    r"^(?P<file>[^:\s][^:\n]*):(?P<line>\d+):(?:(?P<col>\d+):)? "
    r"(?P<severity>fatal error|error|warning): (?P<message>.*)$",
    re.MULTILINE,
)

# Unity: file:line:test_name:PASS | file:line:test_name:FAIL: message | ...:IGNORE
_TEST_LINE = re.compile(
    r"^(?P<file>[^:\r\n]+):(?P<line>\d+):(?P<name>[^:\r\n]+):"
    r"(?P<result>PASS|FAIL|IGNORE)(?::\s?(?P<message>[^\r\n]*))?\r?$",
    re.MULTILINE,
)
_TEST_SUMMARY = re.compile(
    r"^(?P<total>\d+) Tests (?P<failed>\d+) Failures (?P<ignored>\d+) Ignored", re.MULTILINE
)

_FAULT = re.compile(
    r"^VIRTULAB_FAULT: (?P<kind>\S+) pc=(?P<pc>0x[0-9A-Fa-f]+) lr=(?P<lr>0x[0-9A-Fa-f]+)"
    r"(?P<rest>[^\r\n]*)",
    re.MULTILINE,
)


def parse_diagnostics(log: str) -> list[Diagnostic]:
    diagnostics = []
    for m in _GCC_DIAGNOSTIC.finditer(log):
        severity = "warning" if m["severity"] == "warning" else "error"
        diagnostics.append(
            Diagnostic(
                file=m["file"],
                line=int(m["line"]),
                column=int(m["col"]) if m["col"] else None,
                severity=severity,
                message=m["message"].strip(),
            )
        )
    return diagnostics


def parse_tests(output: str) -> TestSummary:
    summary = TestSummary()
    for m in _TEST_LINE.finditer(output):
        summary.cases.append(
            TestCase(
                file=m["file"],
                line=int(m["line"]),
                name=m["name"],
                result=m["result"],
                message=(m["message"] or "").strip(),
            )
        )
    totals = list(_TEST_SUMMARY.finditer(output))
    if totals:
        # A runner may call UNITY_BEGIN/END more than once; add the groups up.
        summary.total = sum(int(t["total"]) for t in totals)
        summary.failed = sum(int(t["failed"]) for t in totals)
        summary.ignored = sum(int(t["ignored"]) for t in totals)
    else:
        summary.total = len(summary.cases)
        summary.failed = sum(c.result == "FAIL" for c in summary.cases)
        summary.ignored = sum(c.result == "IGNORE" for c in summary.cases)
    return summary


def parse_fault(output: str) -> Fault | None:
    m = _FAULT.search(output)
    if not m:
        return None
    return Fault(
        kind=m["kind"], pc=int(m["pc"], 16), lr=int(m["lr"], 16), registers=m["rest"].strip()
    )
