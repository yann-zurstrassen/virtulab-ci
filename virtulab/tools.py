"""Tools VirtuLab can install for you, so it runs without Docker.

`virtulab setup` downloads pinned builds into ~/.virtulab/tools (or $VIRTULAB_HOME/tools), checks
each file against the SHA-256 written below, and refuses one that does not match. Installed tools
are put first on PATH whenever VirtuLab runs; tools you installed yourself keep working.
A host C compiler for fuzzing and coverage is not downloaded: use the system's.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import VirtulabError


@dataclass(frozen=True)
class Asset:
    url: str
    sha256: str


@dataclass(frozen=True)
class Tool:
    name: str
    version: str
    executable: str  # a file that marks where the tool's programs are
    summary: str
    assets: dict[str, Asset]  # platform key -> download


_GCC = "https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/download/v15.2.1-1.1/"
_QEMU = "https://github.com/xpack-dev-tools/qemu-arm-xpack/releases/download/v9.2.4-1/"
_RENODE = "https://github.com/renode/renode/releases/download/v1.17.0/"

TOOLS = {t.name: t for t in [
    Tool("gcc", "15.2.1-1.1", "arm-none-eabi-gcc", "Arm GNU toolchain and GDB (xPack)", {
        "darwin-arm64": Asset(_GCC + "xpack-arm-none-eabi-gcc-15.2.1-1.1-darwin-arm64.tar.gz",
                              "574082d35e49a2bcbdc355836b2a3ae5e5bb3b9456c9f5e37177db2ab4aad870"),
        "darwin-x64": Asset(_GCC + "xpack-arm-none-eabi-gcc-15.2.1-1.1-darwin-x64.tar.gz",
                            "5be906a5194c3173e145a58048e5607ffff947773237802b93e55e23c415f1b6"),
        "linux-arm64": Asset(_GCC + "xpack-arm-none-eabi-gcc-15.2.1-1.1-linux-arm64.tar.gz",
                             "67980c7990eba7bb7ffdf39699102effd70889f5ac427be19a8c8a6c5fab2972"),
        "linux-x64": Asset(_GCC + "xpack-arm-none-eabi-gcc-15.2.1-1.1-linux-x64.tar.gz",
                           "da6a49ad4003944b823c6c93702a8787c922ab34bd7e918ec0eaf6933a9b1ff6"),
    }),
    Tool("qemu", "9.2.4-1", "qemu-system-arm", "QEMU for Arm (xPack)", {
        "darwin-arm64": Asset(_QEMU + "xpack-qemu-arm-9.2.4-1-darwin-arm64.tar.gz",
                              "2752ae3bdff112a8574373157ef1e0eb51fd50b1ee8554275f2ff20ba1ff1b6d"),
        "darwin-x64": Asset(_QEMU + "xpack-qemu-arm-9.2.4-1-darwin-x64.tar.gz",
                            "c8be02219b4328624f696942aff8d6d5b98dbf07c6f2eb61adca12b7a120a140"),
        "linux-arm64": Asset(_QEMU + "xpack-qemu-arm-9.2.4-1-linux-arm64.tar.gz",
                             "50fc7ccace24982bcf964a1b5286a05b63f185421f5e1018fb6cbaf78b42277b"),
        "linux-x64": Asset(_QEMU + "xpack-qemu-arm-9.2.4-1-linux-x64.tar.gz",
                           "203dc2c71e25fcf97b95181328e9b888cc8092ff404bffd4d267b9defabcb698"),
    }),
    # Renode publishes no build for Intel Macs; there, sensor boards run in the Docker image.
    Tool("renode", "1.17.0", "renode", "Renode, for boards with sensors", {
        "darwin-arm64": Asset(_RENODE + "renode-1.17.0.osx-arm64-portable.dmg",
                              "63b1fb691207f503cea937e4ec8fad3e068a517d0abac3c24c0206c62f6c4d12"),
        "linux-arm64": Asset(_RENODE + "renode-1.17.0.linux-arm64-portable.tar.gz",
                             "e9051578411441bfb47b77de0381cfba3badce03663367fab561472fd7807f1f"),
        "linux-x64": Asset(_RENODE + "renode-1.17.0.linux-portable.tar.gz",
                           "4ba7c68b59e2447f188ef4b4b112fcccd2802582c460beedceb63b84e5605a5f"),
    }),
    # The STM32F40x register file Renode's platform uses, for register names in `virtulab trace`.
    Tool("svd", "STM32F40x", "STM32F40x.svd.gz", "STM32F40x register file", {
        key: Asset("https://dl.antmicro.com/projects/renode/svd/STM32F40x.svd.gz", "d71b3e11c870ec83346eb994e98a57c5eacdf0082d2949ed495d7a3828bf41ec")
        for key in ("darwin-arm64", "darwin-x64", "linux-arm64", "linux-x64")
    }),
]}


def platform_key() -> str:
    system = {"darwin": "darwin", "linux": "linux"}.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64" if machine in ("x86_64", "amd64") else machine
    return f"{system}-{arch}"


def home() -> Path:
    return Path(os.environ.get("VIRTULAB_HOME", Path.home() / ".virtulab")) / "tools"


def install_dir(tool: Tool) -> Path:
    return home() / f"{tool.name}-{tool.version}"


def installed(tool: Tool) -> Path | None:
    """Where the tool's marker file is, if this version is installed completely."""
    root = install_dir(tool)
    if not (root / ".complete").is_file():
        return None
    found = next((p for p in root.rglob(tool.executable) if p.is_file()), None)
    return found


def activate() -> None:
    """Put installed tools first on PATH for this process and everything it starts."""
    dirs = [str(p.parent) for t in TOOLS.values() if t.name != "svd" and (p := installed(t))]
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])


def svd_file() -> Path | None:
    return installed(TOOLS["svd"])


def _download(url: str, dest: Path, label: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "virtulab-setup"})
    with urllib.request.urlopen(request, timeout=60) as response, dest.open("wb") as out:
        total, done, step = int(response.headers.get("Content-Length") or 0), 0, 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total and done * 10 // total > step:
                step = done * 10 // total
                print(f"  {label}: {step * 10}% of {total >> 20} MB", flush=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _unpack(archive: Path, dest: Path) -> None:
    name = archive.name
    if name.endswith(".tar.gz"):
        with tarfile.open(archive) as tar:
            tar.extractall(dest, filter="tar")  # keeps the executable bits and the links these tools ship
    elif name.endswith(".dmg"):
        mount = Path(tempfile.mkdtemp(prefix="virtulab-dmg-"))
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(archive)],
                       check=True, capture_output=True)
        try:
            for item in mount.iterdir():
                if not item.name.startswith("."):
                    target = dest / item.name
                    if item.is_dir():
                        shutil.copytree(item, target, symlinks=True)
                    else:
                        shutil.copy2(item, target)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True)
    else:
        shutil.copy2(archive, dest / name)


def install(tool: Tool, force: bool = False) -> Path:
    key = platform_key()
    asset = tool.assets.get(key)
    if asset is None:
        raise VirtulabError(f"No {tool.summary} build for {key}. Use the Docker image for what needs it.")
    if installed(tool) and not force:
        return installed(tool)
    root = install_dir(tool)
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset.url.rsplit("/", 1)[-1]
        print(f"⬇️  {tool.summary} {tool.version}", flush=True)
        _download(asset.url, archive, tool.name)
        actual = _sha256(archive)
        if actual != asset.sha256:
            shutil.rmtree(root, ignore_errors=True)
            raise VirtulabError(f"{archive.name}: SHA-256 is {actual}, expected {asset.sha256}. "
                                "The download was not installed.")
        _unpack(archive, root)
    (root / ".complete").write_text(f"{tool.version}\n{asset.url}\n{asset.sha256}\n")
    found = installed(tool)
    if found is None:
        raise VirtulabError(f"{tool.summary} unpacked, but {tool.executable} is not in it")
    print(f"✅ {tool.name} {tool.version} in {root}", flush=True)
    return found
