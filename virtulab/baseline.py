"""Build the same firmware at a baseline git ref to compute footprint deltas."""

import io
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

from . import VirtulabError
from .build import BuildConfig, Sizes, build

NULL_SHA = "0" * 40


@dataclass
class Baseline:
    ref: str
    sha: str
    sizes: Sizes
    symbols: dict[str, int]


@dataclass
class SymbolDelta:
    name: str
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    # safe.directory: the workspace is owned by another uid inside the action container.
    return subprocess.run(
        ["git", "-c", "safe.directory=*", "-C", str(root), *args], capture_output=True
    )


def build_baseline(
    ref: str, root: Path, cfg: BuildConfig, work_dir: Path
) -> tuple[Baseline | None, str | None]:
    """Return (baseline, None) on success or (None, reason) when it is unavailable."""
    if not ref or ref == NULL_SHA:
        return None, "no baseline ref"

    toplevel = _git(root, "rev-parse", "--show-toplevel")
    if toplevel.returncode != 0:
        return None, "not a git repository"
    repo_root = Path(toplevel.stdout.decode().strip())
    project_subdir = root.resolve().relative_to(repo_root.resolve())

    # Shallow CI checkouts usually lack the baseline commit. If the fetch fails
    # (no remote, offline) fall back to the ref as it exists locally.
    fetched = _git(root, "fetch", "--no-tags", "--quiet", "--depth=1", "origin", ref)
    target = "FETCH_HEAD" if fetched.returncode == 0 else ref
    resolved = _git(root, "rev-parse", "--verify", "--quiet", f"{target}^{{commit}}")
    if resolved.returncode != 0:
        return None, f"baseline ref '{ref}' not found"
    sha = resolved.stdout.decode().strip()

    # Run from the top level: inside a subdirectory, git archive exports only that subtree.
    archive = _git(repo_root, "archive", "--format=tar", sha)
    if archive.returncode != 0:
        return None, f"could not export {sha[:7]}"
    src_dir = work_dir / "baseline-src"
    if src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(src_dir, filter="data")

    try:
        result = build(src_dir / project_subdir, cfg, work_dir / "baseline-build")
    except VirtulabError as exc:
        return None, f"baseline did not build ({exc})"
    if not result.ok or result.sizes is None:
        return None, f"baseline {sha[:7]} failed to build"
    return Baseline(ref=ref, sha=sha, sizes=result.sizes, symbols=result.symbols), None


def diff_symbols(
    before: dict[str, int], after: dict[str, int], limit: int = 10
) -> list[SymbolDelta]:
    deltas = [
        SymbolDelta(name, before.get(name, 0), after.get(name, 0))
        for name in before.keys() | after.keys()
        if before.get(name, 0) != after.get(name, 0)
    ]
    deltas.sort(key=lambda d: (-abs(d.delta), d.name))
    return deltas[:limit]
