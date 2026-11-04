import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from virtulab import VirtulabError, github
from virtulab.cli import options_from_env, parse_byte_limit, parse_timeout, split_list


class OptionParsingTest(unittest.TestCase):
    def test_parse_timeout(self):
        self.assertEqual(parse_timeout("30s"), 30)
        self.assertEqual(parse_timeout("2m"), 120)
        self.assertEqual(parse_timeout("500ms"), 0.5)
        self.assertEqual(parse_timeout("15"), 15)
        with self.assertRaises(VirtulabError):
            parse_timeout("soon")

    def test_parse_byte_limit(self):
        self.assertIsNone(parse_byte_limit(""))
        self.assertEqual(parse_byte_limit("512"), 512)
        self.assertEqual(parse_byte_limit("4K"), 4096)
        self.assertEqual(parse_byte_limit("2KiB"), 2048)
        with self.assertRaises(VirtulabError):
            parse_byte_limit("lots")

    def test_split_list(self):
        self.assertEqual(split_list("src/*.c\n  test/*.c, lib/x.c"),
                         ["src/*.c", "test/*.c", "lib/x.c"])

    def test_options_from_action_inputs(self):
        opts = options_from_env({
            "INPUT_BOARD": "mps2-an386",
            "INPUT_SOURCES": "src/**/*.c\ntest/*.c",
            "INPUT_INCLUDE_DIRS": "include",
            "INPUT_CFLAGS": '-O2 -DNAME="a b"',
            "INPUT_RUNTIME": "false",
            "INPUT_TIMEOUT": "10s",
            "INPUT_BASELINE_REF": "",
            "INPUT_MAX_FLASH_INCREASE": "1K",
            "INPUT_COMMENT": "false",
            "INPUT_WORKING_DIRECTORY": "firmware",
        })
        self.assertEqual(opts.board, "mps2-an386")
        self.assertEqual(opts.sources, ["src/**/*.c", "test/*.c"])
        self.assertEqual(opts.include_dirs, ["include"])
        self.assertEqual(opts.cflags, ["-O2", "-DNAME=a b"])
        self.assertFalse(opts.runtime)
        self.assertEqual(opts.timeout, 10)
        self.assertIsNone(opts.baseline_ref)
        self.assertEqual(opts.max_flash_increase, 1024)
        self.assertIsNone(opts.max_ram_increase)
        self.assertFalse(opts.comment)
        self.assertEqual(opts.root, Path("firmware"))

    def test_action_defaults(self):
        opts = options_from_env({})
        self.assertEqual(opts.board, "lm3s6965evb")
        self.assertEqual(opts.sources, ["**/*.c"])
        self.assertTrue(opts.runtime)
        self.assertTrue(opts.comment)


class WorkflowCommandsTest(unittest.TestCase):
    def test_annotation_escaping(self):
        out = io.StringIO()
        with redirect_stdout(out):
            github.annotate("error", "50% bad\nline 2", "src/a,b.c", 7, title="Test: x")
        self.assertEqual(out.getvalue(),
                         "::error file=src/a%2Cb.c,line=7,title=Test%3A x::50%25 bad%0Aline 2\n")

    def test_outputs_use_heredoc_delimiters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out"
            with mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(path)}):
                github.set_outputs({"a": 1, "b": None, "c": "x\ny"})
            lines = path.read_text().splitlines()
        self.assertEqual(lines[0].split("<<")[0], "a")
        self.assertEqual(lines[1], "1")
        self.assertEqual(lines[4], "")  # None -> empty value
        self.assertEqual(lines[7:9], ["x", "y"])

    def test_repo_path_relative_to_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp).resolve()
            with mock.patch.dict(os.environ, {"GITHUB_WORKSPACE": str(ws)}):
                self.assertEqual(github.repo_path(ws / "fw", "src/a.c"), "fw/src/a.c")


class FakeAPI(github.GitHubAPI):
    def __init__(self, pages):
        super().__init__("token", "owner/repo")
        self.pages = pages
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET":
            page = int(path.rsplit("page=", 1)[1])
            return self.pages[page - 1] if page <= len(self.pages) else []
        return {"html_url": f"https://github.com/x#{method}"}


class StickyCommentTest(unittest.TestCase):
    def test_updates_existing_comment_on_later_page(self):
        filler = [{"id": i, "body": "unrelated"} for i in range(100)]
        api = FakeAPI([filler, [{"id": 555, "body": "<!-- marker -->\nold"}]])
        url = api.upsert_comment(7, "<!-- marker -->", "new body")
        self.assertEqual(url, "https://github.com/x#PATCH")
        self.assertEqual(api.calls[-1],
                         ("PATCH", "/repos/owner/repo/issues/comments/555", {"body": "new body"}))

    def test_creates_comment_when_missing(self):
        api = FakeAPI([[{"id": 1, "body": "hi"}]])
        api.upsert_comment(7, "<!-- marker -->", "body")
        self.assertEqual(api.calls[-1],
                         ("POST", "/repos/owner/repo/issues/7/comments", {"body": "body"}))

    def test_pull_request_number_from_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"pull_request": {"number": 42}}))
            with mock.patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event)}):
                self.assertEqual(github.pull_request_number(), 42)
            event.write_text(json.dumps({"ref": "refs/heads/main"}))
            with mock.patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event)}):
                self.assertIsNone(github.pull_request_number())


if __name__ == "__main__":
    unittest.main()
