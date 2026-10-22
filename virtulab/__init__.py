"""VirtuLab CI — build, emulate and analyse bare-metal Cortex-M firmware."""

import os
from pathlib import Path

__version__ = "0.1.0"

RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
DEVICES_DIR = Path(__file__).resolve().parent / "devices"  # Renode peripheral models


class VirtulabError(Exception):
    """A configuration problem the user has to fix (bad board, no sources, ...)."""


def subprocess_env() -> dict[str, str]:
    """Environment for `python -m virtulab` children: finds this package from any directory."""
    env = dict(os.environ)
    parent = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = parent + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env
