"""VirtuLab CI — build, emulate and analyse bare-metal Cortex-M firmware."""

from pathlib import Path

__version__ = "0.1.0"

RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
DEVICES_DIR = Path(__file__).resolve().parent / "devices"  # Renode peripheral models


class VirtulabError(Exception):
    """A configuration problem the user has to fix (bad board, no sources, ...)."""
