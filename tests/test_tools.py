"""`virtulab setup`: a download is installed only when its checksum matches, and then put on PATH.

These tests use a small archive made on the spot and a local file URL. They never download or run
a real toolchain."""

import hashlib
import io
import os
import shutil
import stat
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from virtulab import VirtulabError, tools


def make_archive(folder: Path) -> Path:
    """A .tar.gz shaped like an xPack release: one top folder, a bin folder, an executable."""
    data = b"#!/bin/sh\necho fake\n"
    archive = folder / "fake-tool.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("fake-tool-1.0/bin/fake-gcc")
        info.size, info.mode = len(data), 0o755
        tar.addfile(info, io.BytesIO(data))
    return archive


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        patcher = mock.patch.dict(os.environ, {"VIRTULAB_HOME": str(self.tmp / "home")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.archive = make_archive(self.tmp)
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def tool(self, digest: str) -> tools.Tool:
        asset = tools.Asset(self.archive.as_uri(), digest)
        return tools.Tool("fake", "1.0", "fake-gcc", "fake toolchain", {tools.platform_key(): asset})

    def test_a_matching_download_is_installed_and_executable(self):
        found = tools.install(self.tool(self.digest))
        self.assertEqual(found.name, "fake-gcc")
        self.assertTrue(found.stat().st_mode & stat.S_IXUSR, "the executable bit must survive unpacking")
        self.assertEqual(tools.installed(self.tool(self.digest)), found)

    def test_a_download_with_the_wrong_checksum_is_refused_and_removed(self):
        with self.assertRaises(VirtulabError):
            tools.install(self.tool("0" * 64))
        self.assertIsNone(tools.installed(self.tool("0" * 64)))
        self.assertFalse(any(tools.install_dir(self.tool("0" * 64)).glob("**/fake-gcc")))

    def test_an_installed_tool_goes_first_on_path(self):
        fake = self.tool(self.digest)
        found = tools.install(fake)
        with mock.patch.dict(tools.TOOLS, {"fake": fake}, clear=True), mock.patch.dict(os.environ, {"PATH": "/usr/bin"}):
            tools.activate()
            self.assertEqual(os.environ["PATH"].split(os.pathsep)[0], str(found.parent))

    def test_a_platform_without_a_build_is_a_clear_error(self):
        lonely = tools.Tool("fake", "1.0", "fake-gcc", "fake toolchain", {"plan9-mips": tools.Asset("x", "0" * 64)})
        with self.assertRaises(VirtulabError):
            tools.install(lonely)

    def test_every_pinned_download_has_a_full_checksum(self):
        for tool in tools.TOOLS.values():
            for key, asset in tool.assets.items():
                self.assertRegex(asset.sha256, r"^[0-9a-f]{64}$", f"{tool.name} {key}")
                self.assertTrue(asset.url.startswith("https://"), f"{tool.name} {key}")


if __name__ == "__main__":
    unittest.main()
