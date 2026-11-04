"""The datasheet maps stay true: every reference points at real code, and the catalog agrees with the models."""

import json
import re
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from virtulab import VirtulabError, catalog, datasheets
from virtulab.ui.server import make_handler

ROOT = Path(__file__).resolve().parent.parent


class MapTest(unittest.TestCase):
    def test_every_sensor_has_a_map(self):
        self.assertEqual(sorted(catalog.MODULES), datasheets.available())

    def test_every_reference_points_at_real_code(self):
        for module in datasheets.available():
            data = datasheets.load(module)
            self.assertTrue(data["rows"], module)
            for row in data["rows"]:
                where = f"{module}: {row['topic']}"
                self.assertIn(row["status"], datasheets.STATUS, where)
                self.assertTrue(row.get("datasheet"), where)
                for place in datasheets.PLACES:
                    if place in row:
                        self.assertIsNotNone(row[place]["line"],
                                             f"{where}: '{row[place]['anchor']}' not found in {row[place]['path']}")
                if row["status"] in ("modelled", "simplified"):
                    self.assertTrue("model" in row or "driver" in row or "test" in row,
                                    f"{where}: says it is modelled but names no code")

    def test_a_modelled_row_has_a_test_unless_it_is_a_simple_constant(self):
        # Not every row needs a test, but the maps should not drift towards having none.
        for module in datasheets.available():
            rows = [r for r in datasheets.load(module)["rows"] if r["status"] == "modelled"]
            tested = [r for r in rows if "test" in r]
            self.assertGreaterEqual(len(tested) * 2, len(rows), f"{module}: fewer than half the rows are tested")

    def test_sample_tests_named_in_the_maps_are_run_by_their_suite(self):
        for module in datasheets.available():
            for row in datasheets.load(module)["rows"]:
                if "test" in row:
                    path = datasheets.PACKAGE / row["test"]["path"]
                    name = row["test"]["anchor"]
                    self.assertRegex(path.read_text(), rf"RUN_TEST\({name}\)", f"{module}: {name} is never run")

    def test_catalog_simulation_properties_exist_in_the_emulator_models(self):
        for module in catalog.MODULES.values():
            if module.tier != "accurate":
                continue
            source = (datasheets.PACKAGE / "devices" / module.renode_type.split(".")[-1]).with_suffix(".cs").read_text()
            for prop in module.sim:
                self.assertRegex(source, rf"public\s+\S+\s+{prop}\b", f"{module.id}: {prop} is not in the model")

    def test_generated_markdown_is_current(self):
        committed = (ROOT / "docs" / "DATASHEETS.md").read_text()
        self.assertEqual(committed, datasheets.all_markdown() + "\n",
                         "docs/DATASHEETS.md is out of date: run `python3 -m virtulab datasheet --markdown > docs/DATASHEETS.md`")

    def test_documents_are_fully_described_and_citations_name_one(self):
        for module in datasheets.available():
            data = datasheets.load(module)
            ids = set()
            for doc in data["documents"]:
                for key in ("id", "title", "revision", "retrieved", "sha256", "kind"):
                    self.assertTrue(doc.get(key), f"{module}: document {doc.get('id')} has no {key}")
                self.assertRegex(str(doc["sha256"]), r"^[0-9a-f]{64}$", f"{module}: {doc['id']} sha256")
                ids.add(doc["id"])
            for row in data["rows"]:
                source = str(row.get("source") or "")
                if source:
                    self.assertIn(source.split(None, 1)[0], ids | {datasheets.NOT_IN_DATASHEET},
                                  f"{module}: '{row['topic']}' cites a document that is not listed")
                for other in row.get("corroborated_by") or []:
                    self.assertIn(other, ids, f"{module}: '{row['topic']}' is corroborated by an unlisted document")

    def test_rows_that_claim_a_datasheet_fact_are_cited(self):
        """The rule of the project: nothing is written from memory. Rows with no citation are listed."""
        missing = {m: sum(r["unverified"] for r in datasheets.load(m)["rows"]) for m in datasheets.available()}
        missing = {m: n for m, n in missing.items() if n}
        self.assertEqual(missing, {}, "rows without a citation (unverified): fetch the document and cite it")

    def test_generated_issue_ledger_is_current(self):
        committed = (ROOT / "docs" / "DATASHEET_ISSUES.md").read_text()
        self.assertEqual(committed, datasheets.issues_markdown() + "\n",
                         "docs/DATASHEET_ISSUES.md is out of date: run `python3 -m virtulab datasheet --issues > docs/DATASHEET_ISSUES.md`")

    def test_unknown_module_is_a_clear_error(self):
        with self.assertRaises(VirtulabError):
            datasheets.load("nope")


class PageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Path(self.tmp.name), "tok"))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = f"http://127.0.0.1:{server.server_port}"

    def get(self, path):
        req = urllib.request.Request(self.base + path, headers={"X-VirtuLab-Token": "tok"})
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as err:
            with err:
                return err.code, json.loads(err.read())

    def test_page_serves_the_map_and_code_windows(self):
        status, data = self.get("/api/datasheet?module=adxl345")
        self.assertEqual(status, 200)
        row = next(r for r in data["rows"] if r["topic"] == "Device ID")
        status, window = self.get(f"/api/source?module=adxl345&path={row['model']['path']}&line={row['model']['line']}")
        self.assertEqual(status, 200)
        self.assertIn("0xE5", window["text"])
        self.assertEqual(window["highlight"], row["model"]["line"])

    def test_page_only_serves_files_the_map_names(self):
        for path in ("../config.py", "config.py", "/etc/passwd", "devices/../config.py"):
            status, data = self.get(f"/api/source?module=adxl345&path={path}&line=1")
            self.assertEqual(status, 400, path)
        self.assertEqual(self.get("/api/source?module=adxl345&line=1")[0], 400)
        self.assertEqual(self.get("/api/datasheet?module=../x")[0], 400)

    def test_catalog_reports_the_status_counts(self):
        modules = {m["id"]: m for m in self.get("/api/catalog")[1]["modules"]}
        self.assertGreater(modules["adxl345"]["datasheet"]["statuses"]["modelled"], 0)
        self.assertIn("unverified", modules["adxl345"]["datasheet"])


if __name__ == "__main__":
    unittest.main()
