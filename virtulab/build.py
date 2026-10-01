"""Compile and link firmware with arm-none-eabi-gcc, then measure the image."""

import glob
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from . import RUNTIME_DIR, VirtulabError
from .boards import Board
from .parse import Diagnostic, parse_diagnostics

TOOLCHAIN_PREFIX = os.environ.get("VIRTULAB_TOOLCHAIN_PREFIX", "arm-none-eabi-")

CXX_SUFFIXES = {".cpp", ".cc", ".cxx", ".C"}
SOURCE_SUFFIXES = {".c", ".s", ".S"} | CXX_SUFFIXES

COMMON_FLAGS = ["-g", "-ffunction-sections", "-fdata-sections"]
DEFAULT_USER_FLAGS = ["-Os", "-Wall", "-Wextra"]
CXX_FLAGS = ["-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics"]
# GCC 14 makes this an error by default; older toolchains only warn, and the
# mistake then surfaces as a confusing undefined reference at link time.
C_FLAGS = ["-Werror=implicit-function-declaration"]
RUNTIME_SOURCES = ["startup.c", "virtulab_test.c"]
MIN_STACK_BYTES = 1024


@dataclass
class BuildConfig:
    board: Board
    sources: list[str]  # glob patterns, relative to the project root
    include_dirs: list[str] = field(default_factory=list)
    cflags: list[str] = field(default_factory=list)
    ldflags: list[str] = field(default_factory=list)
    linker_script: str | None = None
    runtime: bool = True


@dataclass
class Sizes:
    text: int
    data: int
    bss: int

    @property
    def flash(self) -> int:
        return self.text + self.data  # .data's initial values live in flash

    @property
    def ram(self) -> int:
        return self.data + self.bss


@dataclass
class BuildResult:
    ok: bool
    log: str
    diagnostics: list[Diagnostic]
    elf: Path | None = None
    sizes: Sizes | None = None
    symbols: dict[str, int] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)


def tool(name: str) -> str:
    return TOOLCHAIN_PREFIX + name


def resolve_sources(patterns: list[str], root: Path, exclude: Path | None = None) -> list[str]:
    """Expand glob patterns into source paths relative to root, skipping `exclude`."""
    excluded = exclude.resolve() if exclude else None
    found: list[str] = []
    for pattern in patterns:
        matches = sorted(
            m for m in glob.glob(pattern, root_dir=root, recursive=True)
            if Path(m).suffix in SOURCE_SUFFIXES and (root / m).is_file()
            and not (excluded and (root / m).resolve().is_relative_to(excluded))
        )
        if not matches:
            raise VirtulabError(f"Source pattern '{pattern}' matched no C/C++/assembly files")
        found.extend(m for m in matches if m not in found)
    return found


def render_linker_script(board: Board, dest: Path) -> Path:
    template = (RUNTIME_DIR / "cortex-m.ld.in").read_text()
    for key, value in {
        "FLASH_ORIGIN": hex(board.flash_origin),
        "FLASH_SIZE": hex(board.flash_size),
        "RAM_ORIGIN": hex(board.ram_origin),
        "RAM_SIZE": hex(board.ram_size),
        "MIN_STACK": hex(MIN_STACK_BYTES),
    }.items():
        template = template.replace(f"@{key}@", value)
    dest.write_text(template)
    return dest


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        raise VirtulabError(f"'{cmd[0]}' not found. Is the Arm GNU toolchain installed?") from None
    return proc.returncode, proc.stdout + proc.stderr


def build(root: Path, cfg: BuildConfig, build_dir: Path, exclude: Path | None = None) -> BuildResult:
    """Build into build_dir, which is wiped first and must be owned by VirtuLab."""
    sources = resolve_sources(cfg.sources, root, exclude)
    if build_dir.exists():
        shutil.rmtree(build_dir)
    obj_dir = build_dir / "obj"
    obj_dir.mkdir(parents=True)

    if cfg.linker_script:
        linker_script = (root / cfg.linker_script).resolve()
        if not linker_script.is_file():
            raise VirtulabError(f"Linker script '{cfg.linker_script}' not found")
    else:
        linker_script = render_linker_script(cfg.board, build_dir / f"{cfg.board.name}.ld")

    includes = [f"-I{d}" for d in cfg.include_dirs]
    if cfg.runtime:
        includes.append(f"-I{RUNTIME_DIR}")

    jobs: list[list[str]] = []
    objects: list[Path] = []
    uses_cxx = False
    for index, src in enumerate(sources):
        is_cxx = Path(src).suffix in CXX_SUFFIXES
        uses_cxx |= is_cxx
        obj = obj_dir / f"{index:03d}_{Path(src).name}.o"
        jobs.append([
            tool("g++" if is_cxx else "gcc"), *cfg.board.cflags, *COMMON_FLAGS,
            *(CXX_FLAGS if is_cxx else C_FLAGS if src.endswith(".c") else []),
            *DEFAULT_USER_FLAGS, *includes, *cfg.cflags,
            "-c", src, "-o", str(obj),
        ])
        objects.append(obj)
    if cfg.runtime:
        for name in RUNTIME_SOURCES:
            obj = obj_dir / f"virtulab_{name}.o"
            jobs.append([
                tool("gcc"), *cfg.board.cflags, *cfg.board.runtime_defines, *COMMON_FLAGS,
                "-Os", "-Wall", "-Wextra", f"-I{RUNTIME_DIR}", "-c", str(RUNTIME_DIR / name),
                "-o", str(obj),
            ])
            objects.append(obj)

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
        results = list(pool.map(lambda cmd: _run(cmd, root), jobs))
    log = "".join(out for _, out in results)
    if any(code != 0 for code, _ in results):
        return BuildResult(False, log, parse_diagnostics(log), sources=sources)

    elf = build_dir / "firmware.elf"
    code, out = _run([
        tool("g++" if uses_cxx else "gcc"), *cfg.board.cflags, *map(str, objects),
        "-nostartfiles", "-T", str(linker_script), "--specs=nano.specs", "--specs=nosys.specs",
        "-Wl,--gc-sections", f"-Wl,-Map={build_dir / 'firmware.map'}",
        "-Wl,--no-warn-rwx-segments", *cfg.ldflags, "-o", str(elf),
    ], root)
    log += out
    if code != 0:
        return BuildResult(False, log, parse_diagnostics(log), sources=sources)

    return BuildResult(
        ok=True,
        log=log,
        diagnostics=parse_diagnostics(log),
        elf=elf,
        sizes=measure(elf),
        symbols=symbol_sizes(elf),
        sources=sources,
    )


def measure(elf: Path) -> Sizes:
    code, out = _run([tool("size"), "-B", str(elf)], elf.parent)
    if code != 0:
        raise VirtulabError(f"arm-none-eabi-size failed:\n{out}")
    text, data, bss = out.strip().splitlines()[-1].split()[:3]
    return Sizes(int(text), int(data), int(bss))


def symbol_sizes(elf: Path) -> dict[str, int]:
    """Size in bytes of every sized symbol in the image (functions and objects)."""
    code, out = _run([tool("nm"), "--print-size", "--size-sort", "-C", str(elf)], elf.parent)
    if code != 0:
        return {}
    sizes: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) == 4 and parts[2].lower() in "tdbr":
            sizes[parts[3]] = sizes.get(parts[3], 0) + int(parts[1], 16)
    return sizes


def symbol_addresses(elf: Path) -> dict[str, int]:
    """Address of every defined symbol (Thumb bit cleared for functions)."""
    code, out = _run([tool("nm"), str(elf)], elf.parent)
    addresses: dict[str, int] = {}
    if code == 0:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 3:
                addresses[parts[2]] = int(parts[0], 16) & ~1
    return addresses


def addr2line(elf: Path, address: int) -> tuple[str | None, str | None]:
    """Map an address to (function, "file:line"); either may be None if unknown."""
    code, out = _run([tool("addr2line"), "-f", "-C", "-e", str(elf), hex(address)], elf.parent)
    lines = out.strip().splitlines()
    if code != 0 or len(lines) < 2:
        return None, None
    function = None if lines[0] == "??" else lines[0]
    location = lines[1].split(" ")[0]
    if location.startswith("??") or location.endswith(":0"):
        location = None
    return function, location
