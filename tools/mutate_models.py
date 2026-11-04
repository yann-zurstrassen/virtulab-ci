#!/usr/bin/env python3
"""Mutation-test the Renode device models in virtulab/devices/*.cs.

Each mutant is one small change to one line of a model (flip a comparison, change a constant,
delete a statement ...). The 11-sensor sample project runs against the mutated model. A mutant
the sample tests do not notice ("survived") is a modelled behaviour nothing checks: either add a
test, or, if the change cannot be observed, record it as equivalent.

Needs the toolchain and Renode (run it in the Docker image):
  docker run --rm --entrypoint python3 -v "$PWD:/workspace" -w /workspace virtulab-ci \
      tools/mutate_models.py --workers 6 --per-file 15 --out mutants.json
"""

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SENSORS = ["-m", "temp=tmp108@i2c1", "-m", "baro=bmp180@i2c1", "-m", "power=ina219@i2c1",
           "-m", "imu=mpu6050@i2c1", "-m", "air=sht31@i2c1",
           "-m", "accel=adxl345@spi1", "-m", "couple=max31855@spi1", "-m", "storage=w25q128@spi1",
           "-m", "gps=nmea_gps@usart1", "-m", "modem=at_modem@usart3", "-m", "rs485=modbus_rtu@uart4"]

# (name, regex, replacement), applied to code only (not comments, strings or log calls).
OPERATORS = [
    ("== to !=", re.compile(r"(?<![=!<>])==(?!=)"), "!="),
    ("!= to ==", re.compile(r"!="), "=="),
    ("< to <=", re.compile(r"(?<![<-])<(?![<=])"), "<="),
    ("> to >=", re.compile(r"(?<![>-])>(?![>=])"), ">="),
    ("<= to <", re.compile(r"<="), "<"),
    (">= to >", re.compile(r">="), ">"),
    ("&& to ||", re.compile(r"&&"), "||"),
    ("|| to &&", re.compile(r"\|\|"), "&&"),
    ("+ to -", re.compile(r"(?<=[\w)\]] )\+(?= [\w(])"), "-"),
    ("- to +", re.compile(r"(?<=[\w)\]] )-(?= [\w(])"), "+"),
    ("| to &", re.compile(r"(?<=[\w)\]] )\|(?= [\w(])"), "&"),
    ("& to |", re.compile(r"(?<=[\w)\]] )&(?= [\w(])"), "|"),
    ("<< to >>", re.compile(r"<<"), ">>"),
    (">> to <<", re.compile(r">>"), "<<"),
    ("^ to |", re.compile(r"(?<=[\w)\]] )\^(?= [\w(])"), "|"),
    ("true to false", re.compile(r"\btrue\b"), "false"),
    ("false to true", re.compile(r"\bfalse\b"), "true"),
    ("hex constant + 1", re.compile(r"\b0x[0-9A-Fa-f]+\b"), lambda m: hex(int(m.group(), 16) + 1)),
    ("constant + 1", re.compile(r"(?<![\w.x])\d+(?![\w.])"), lambda m: str(int(m.group()) + 1)),
    ("delete statement", re.compile(r"^(\s*)(?!return|var |int |byte |bool |case |break|default)[\w.\[\]]+ (?:[|&^+-]?=) [^;]+;\s*$"),
     lambda m: m.group(1) + ";"),
]
SKIP_LINE = re.compile(r'^\s*(//|using |namespace |\{|\}|\[|this\.Log|public (decimal|int|bool|double|byte) \w+ \{ get)'
                       r'|^\s*;?\s*$')
UNMUTATABLE = re.compile(r'=>|\bevent\b|\w<\w[\w<>, \[\]]*>')  # expression bodies and generics


def code_part(line: str) -> int:
    """Index where a trailing // comment starts, or len(line)."""
    in_string = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_string = not in_string
        if not in_string and line.startswith("//", i):
            return i
    return len(line)


def mutants(path: Path):
    lines = path.read_text().splitlines(keepends=True)
    for number, line in enumerate(lines):
        if SKIP_LINE.match(line) or UNMUTATABLE.search(line) or '"' in line.split("//")[0] and "Log(" in line:
            continue
        end = code_part(line)
        code, comment = line[:end], line[end:]
        for name, pattern, replacement in OPERATORS:
            for match in pattern.finditer(code):
                if '"' in code[:match.start()] and code[:match.start()].count('"') % 2:
                    continue
                if name == "delete statement":
                    new = pattern.sub(replacement, code.rstrip("\r\n")) + "\n" + comment.rstrip("\n")
                else:
                    repl = replacement(match) if callable(replacement) else replacement
                    new = code[:match.start()] + repl + code[match.end():] + comment
                if new.rstrip() == line.rstrip():
                    continue
                yield {"file": path.name, "line": number + 1, "operator": name,
                       "before": line.strip(), "after": new.strip(), "text": "".join(lines[:number] + [new] + lines[number + 1:])}


def run(args: list[str], cwd: Path, package_root: Path, timeout: int) -> tuple[int | None, str]:
    env = dict(os.environ, PYTHONPATH=str(package_root))
    try:
        done = subprocess.run([sys.executable, "-m", "virtulab", *args], cwd=cwd, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return done.returncode, done.stdout
    except subprocess.TimeoutExpired as e:
        return None, (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")


def failed_tests(out: str) -> list[str]:
    return sorted(set(re.findall(r"(test_\w+):FAIL", out)))


def evaluate(job, work: Path, template: Path, timeout: int):
    index, mutant = job
    base = work / f"m{index}"
    package = base / "pkg"
    shutil.copytree(ROOT / "virtulab", package / "virtulab", ignore=shutil.ignore_patterns("__pycache__"))
    (package / "virtulab" / "devices" / mutant["file"]).write_text(mutant["text"])
    project = base / "project"
    shutil.copytree(template, project, ignore=shutil.ignore_patterns(".virtulab"))
    code, out = run(["run", "-C", str(project), "--only", "unit"], project, package, timeout)
    result = {k: v for k, v in mutant.items() if k != "text"}
    if code is None:
        result["status"] = "killed"
        result["by"] = ["timeout"]
    elif code == 0:
        result["status"] = "survived"
    elif failed_tests(out):
        result["status"] = "killed"
        result["by"] = failed_tests(out)
    elif re.search(r"[1-9]\d*/\d+ tests passed", out) and "0/0" not in out:
        result["status"] = "crashed"  # every test passed, then the emulator aborted: the run fails, no test says why
        result["tail"] = out[-400:]
    else:
        result["status"] = "invalid"  # did not compile or did not start: tells nothing
        result["tail"] = out[-400:]
    shutil.rmtree(base, ignore_errors=True)
    print(f"{result['status']:9} {result['file']}:{result['line']} {result['operator']}", flush=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--per-file", type=int, default=15, help="mutants sampled per model file (0 = all)")
    ap.add_argument("--only", nargs="*", help="model files, e.g. SHT31.cs")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out", default="mutants.json")
    opts = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="vl-mutate-"))
    template = work / "template"
    code, out = run(["init", "-C", str(template), "-b", "stm32f4_discovery", "-t", "unit", *SENSORS,
                     "--template", "starter", "--ci", "none", "-y"], work, ROOT, 120)
    if code != 0:
        print(out)
        return 2
    code, out = run(["run", "-C", str(template), "--only", "unit"], template, ROOT, opts.timeout)
    if code != 0:
        print("the unmutated project does not pass; fix that first\n" + out[-2000:])
        return 2
    shutil.rmtree(template / ".virtulab", ignore_errors=True)

    rng = random.Random(opts.seed)
    jobs = []
    for path in sorted((ROOT / "virtulab" / "devices").glob("*.cs")):
        if opts.only and path.name not in opts.only:
            continue
        found = list(mutants(path))
        if opts.per_file and len(found) > opts.per_file:
            found = rng.sample(found, opts.per_file)
        jobs += sorted(found, key=lambda m: m["line"])
    print(f"{len(jobs)} mutants", flush=True)
    with ThreadPoolExecutor(opts.workers) as pool:
        results = list(pool.map(lambda j: evaluate(j, work, template, opts.timeout), enumerate(jobs)))
    shutil.rmtree(work, ignore_errors=True)
    Path(opts.out).write_text(json.dumps(results, indent=1))
    counts = {s: sum(r["status"] == s for r in results) for s in ("killed", "crashed", "survived", "invalid")}
    valid = counts["killed"] + counts["survived"] + counts["crashed"]
    print(f"\n{counts}; score {counts['killed'] / valid:.0%} (crashed mutants counted as not caught by a test)" if valid else counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
