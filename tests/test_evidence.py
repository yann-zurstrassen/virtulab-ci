"""What a run hands to other tools must be valid and must say what really happened."""

import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from virtulab import evidence
from virtulab.boards import BOARDS
from virtulab.build import BuildResult, Sizes
from virtulab.config import ProjectConfig
from virtulab.emulator import RunResult
from virtulab.parse import TestCase, TestSummary
from virtulab.report import Outcome
from virtulab.suite import FAIL, PASS, CheckOutcome, SuiteResult


def suite() -> SuiteResult:
    cases = [TestCase("test/a.c", 3, "test_ok", "PASS"), TestCase("test/a.c", 9, "test_bad", "FAIL", 'x <"&')]
    tests = TestSummary(cases=cases, total=2, failed=1)
    outcome = Outcome(BOARDS["lm3s6965evb"], BuildResult(True, "", [], sizes=Sizes(1, 1, 1)),
                      run=RunResult(1, False, "", 0.1), tests=tests)
    finding = {"probe": "fault/p.c", "address": "0x10", "function": "verify", "instruction": "bne.n",
               "file": "src/auth.c", "line": 42}
    checks = [CheckOutcome("unit", FAIL, "tests failed"), CheckOutcome("coverage", PASS, "90% lines"),
              CheckOutcome("fault", FAIL, "bypass", data={"findings": [finding], "bypass": 1})]
    return SuiteResult(outcome=outcome, checks=checks)


class EvidenceTest(unittest.TestCase):
    def test_junit_parses_and_counts_failures(self):
        root = ET.fromstring(evidence.junit_xml(suite()))
        self.assertEqual(root.get("tests"), "5")
        self.assertEqual(root.get("failures"), "3")

    def test_sarif_points_at_the_source_line(self):
        results = evidence.sarif(suite())["runs"][0]["results"]
        fault = next(r for r in results if r["ruleId"] == "VL-FAULT")
        location = fault["locations"][0]["physicalLocation"]
        self.assertEqual(location["artifactLocation"]["uri"], "src/auth.c")
        self.assertEqual(location["region"]["startLine"], 42)

    def test_the_record_states_limits_and_makes_no_compliance_claim(self):
        m = evidence.manifest(ProjectConfig(), suite(), Path("."))
        self.assertEqual(m["overall"], "fail")
        coverage = next(c for c in m["checks"] if c["test"] == "coverage")
        self.assertIn("no MC/DC", coverage["limits"])
        text = evidence.evidence_markdown(m)
        self.assertIn("not a statement of compliance", text)
        json.dumps(m)


if __name__ == "__main__":
    unittest.main()
