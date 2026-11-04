"""The studio: what it shows, what it runs, and what it refuses."""

import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from virtulab import VirtulabError
from virtulab.ui.server import make_handler
from virtulab.ui.studio import Studio, parse_variants

REPO = Path(__file__).resolve().parent.parent


class StudioTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, tmp)
        self.root = tmp / "patch"
        shutil.copytree(REPO / "examples/wearable-patch", self.root, ignore=shutil.ignore_patterns(".virtulab"))
        (self.root / ".virtulab").mkdir()
        (self.root / ".virtulab" / "secret.txt").write_text("not a project file")
        self.studio = Studio(self.root, parse_variants(["plain=-DPATCH_HARDENED=0"]))

    def test_it_lists_project_files_and_refuses_others(self):
        files = self.studio.files()
        self.assertIn("virtulab.yml", files)
        self.assertIn("src/patch.c", files)
        self.assertFalse(any(f.startswith(".virtulab") for f in files))
        self.assertIn("fall = true;", self.studio.file("src/patch.c")["text"])
        for bad in ("../patch/virtulab.yml", ".virtulab/secret.txt", "/etc/passwd"):
            with self.assertRaises(VirtulabError, msg=bad):
                self.studio.file(bad)

    def test_it_tells_your_code_from_what_virtulab_provides(self):
        origins = self.studio.origins()
        self.assertEqual(origins["src/patch.c"], "yours")
        self.assertEqual(origins["virtulab.yml"], "project")
        self.assertEqual(origins["src/mpu6050.c"], "starter")
        self.assertEqual(origins["test/test_patch.c"], "yours")
        self.assertEqual(origins["test/test_sht31.c"], "starter")       # untouched: the build writes the runner
        self.assertNotIn("test/test_main.c", origins)
        self.assertEqual(origins["virtulab/models/SHT31.cs"], "virtulab")
        self.assertEqual(self.studio.file("virtulab/runtime/startup.c")["origin"], "virtulab")
        (self.root / "src" / "mpu6050.c").write_text("/* changed */\n")
        self.assertEqual(self.studio.origins()["src/mpu6050.c"], "extended")

    def test_the_project_names_its_scenarios_and_variants(self):
        project = self.studio.project()
        self.assertEqual([c["name"] for c in project["cases"]],
                         ["daily_life", "patient_falls", "fever", "damaged_sensor_cable"])
        self.assertEqual(list(project["variants"]), ["as written", "plain"])

    def test_a_variant_adds_its_flags_to_the_project_flags(self):
        cmd, key, page = self.studio.plan("trace", "patient_falls", "plain", "0x80002a8@1300ms")
        self.assertIn("--cflags=-std=c99 -Wall -Wextra -DPATCH_HARDENED=0", cmd)
        self.assertIn("--skip", cmd)
        self.assertEqual(key, "runs/patient-falls--plain--glitch-0x80002a8-1300ms")
        cmd, key, _ = self.studio.plan("sweep", None, "as written", None)
        self.assertFalse(any(c.startswith("--cflags") for c in cmd))
        with self.assertRaises(VirtulabError):
            self.studio.plan("trace", "patient_falls", "plain", "0x80; rm -rf /")
        with self.assertRaises(VirtulabError):
            self.studio.plan("trace", "patient_falls", "nope", None)

    def test_the_server_serves_the_studio_and_never_saves(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.root, "tok", self.studio))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        self.assertIn("VirtuLab Studio", urllib.request.urlopen(base + "/").read().decode())
        self.assertIn("set up your virtual board", urllib.request.urlopen(base + "/setup").read().decode())
        req = urllib.request.Request(base + "/api/save", data=json.dumps({"config": {}}).encode(),
                                     headers={"X-VirtuLab-Token": "tok", "Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        self.assertIn("without rewriting", json.loads(err.exception.read())["error"])
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/view/../../virtulab.yml")


class AppWindowTest(unittest.TestCase):
    def test_an_app_window_uses_the_first_browser_found(self):
        from virtulab.ui.server import app_window_command
        cmd = app_window_command("http://127.0.0.1:1/#token=x", ["/no/such/browser", "sh"])
        self.assertEqual(cmd[1], "--app=http://127.0.0.1:1/#token=x")
        self.assertTrue(cmd[0].endswith("sh"))
        self.assertIsNone(app_window_command("http://x", ["/no/such/browser"]))


if __name__ == "__main__":
    unittest.main()
