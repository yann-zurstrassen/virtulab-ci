"""`virtulab demo`: set up a project from scratch, run it, then break it three ways.

The three "pull requests" are the ones the README shows: each keeps every unit
test green and is caught only by the check built for it.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from . import VirtulabError, subprocess_env
from .catalog import get_test
from .config import load as load_config

def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=VirtuLab Demo",
                    "-c", "user.email=demo@virtulab.invalid", *args],
                   check=True, capture_output=True)


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise VirtulabError(f"Demo patch does not apply to {path.name}; the template changed.")
    path.write_text(text.replace(old, new, 1))


def _virtulab(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-m", "virtulab", *args, "-C", str(root)],
                          capture_output=True, text=True, env=subprocess_env())
    return proc.returncode, proc.stdout + proc.stderr


def _summary(output: str) -> str:
    marker = "── Summary"
    return output[output.index(marker):].strip() if marker in output else output[-1500:]


def _step(title: str) -> None:
    print(f"\n{'═' * 70}\n  {title}\n{'═' * 70}", flush=True)


def run_demo(root: Path, fuzz_seconds: int = 5) -> int:
    root = root.resolve()
    if root.exists() and any(root.iterdir()):
        raise VirtulabError(f"{root} is not empty. Pick another folder with -C.")
    for tool in ("git", "arm-none-eabi-gcc", "qemu-system-arm", "cc"):
        if not shutil.which(tool):
            raise VirtulabError(f"The demo needs '{tool}' on this machine. "
                                "Or run it in the image: docker run --rm -it ghcr.io/yann-zurstrassen/"
                                "virtulab-ci:1 demo")

    _step("1. Create a project: board, tests and CI in one command")
    cmd = ["init", "-C", str(root), "-b", "lm3s6965evb", "-t", "unit,footprint,coverage,fuzz,fault",
           "--template", "starter", "--ci", "github", "-y"]
    print("$ virtulab " + " ".join(cmd), flush=True)
    code, out = _virtulab_args(cmd)
    print(out)
    if code:
        return code
    config = root / "virtulab.yml"
    cfg = load_config(root)
    cfg.tests["fuzz"]["seconds"] = fuzz_seconds  # keep the demo short
    config.write_text(cfg.dumps())

    _step("2. Check the setup before running anything")
    print("$ virtulab check", flush=True)
    code, out = _virtulab(root, "check")
    print(out)
    if code:
        return code

    _step("3. First push: every selected test runs")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "Initial firmware")
    print("$ virtulab run", flush=True)
    code, out = _virtulab(root, "run", "--baseline", "HEAD")
    print(_summary(out))
    if code:
        print("\nThe untouched sample should pass. Something is wrong with this machine's setup.")
        return 1

    scenarios = [
        ("4. A teammate adds an 8 KiB history buffer",
         "Unit tests stay green. The footprint budget (2 KiB RAM) does not.",
         "unit,footprint",
         lambda: (_edit(root / "src/parser.c", "parser_status_t parser_parse(",
                        "uint8_t parser_history[8192]; /* new: keep the last frames */\n\n"
                        "parser_status_t parser_parse("),
                  _edit(root / "src/parser.c", "memset(frame, 0, sizeof(*frame));\n    if (len < PARSER_OVERHEAD)",
                        "memset(frame, 0, sizeof(*frame));\n    parser_history[len % 8192u] = 1u;\n"
                        "    if (len < PARSER_OVERHEAD)")),
         "footprint"),
        ("5. A teammate relaxes the parser length check by one",
         "All unit tests pass. Fuzzing finds the overflow.",
         "unit,fuzz",
         lambda: _edit(root / "src/parser.c", "if (payload_len > PARSER_MAX_PAYLOAD) {\n        return PARSER_ERR_TOO_LONG;\n    }\n    if (len <",
                       "if (payload_len > PARSER_MAX_PAYLOAD + 1u) {\n        return PARSER_ERR_TOO_LONG;\n    }\n    if (len <"),
         "fuzz"),
        ("6. A teammate drops the redundant PIN comparison 'to save flash'",
         "All unit tests pass. A single skipped instruction now grants a wrong PIN.",
         "unit,fault",
         lambda: _edit(root / "include/auth.h", "#define AUTH_HARDENED 1", "#define AUTH_HARDENED 0"),
         "fault"),
    ]
    caught = []
    for title, story, only, patch, expected in scenarios:
        _step(title)
        print(story, flush=True)
        patch()
        print(f"$ virtulab run --only {only}", flush=True)
        extra = ["--baseline", "HEAD"] if "footprint" in only else []
        code, out = _virtulab(root, "run", "--only", only, *extra)
        summary = _summary(out)
        print(summary)
        title_of_expected = get_test(expected).title
        caught.append(code != 0 and any(line.startswith("❌") and title_of_expected in line
                                        for line in summary.splitlines()))
        _git(root, "checkout", "-q", "--", ".")

    _step("What you get")
    print(f"""Everything above is driven by one file: {config}
Run `virtulab ui -C {root}` to change the board, sensors and tests in a browser,
`virtulab ci -C {root}` to see the CI workflow, and push to run it for real.""")
    ok = all(caught)
    print("\nDemo result:", "✅ every broken change was caught" if ok else "❌ a broken change slipped through")
    return 0 if ok else 1


def _virtulab_args(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-m", "virtulab", *args], capture_output=True, text=True,
                          env=subprocess_env())
    return proc.returncode, proc.stdout + proc.stderr
