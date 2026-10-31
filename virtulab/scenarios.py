"""Physical scenarios: one firmware build, many situations, and faults at a chosen moment.

The build never changes between situations, so every result is about the same image. A case
scripts the inputs and says what the firmware output must and must not contain. With `faults`,
a case skips each instruction of the target at the first execution after a virtual time, which
reaches code that only matters at one moment, like the poll that sees an overheat begin.
"""

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import VirtulabError
from .boards import BOARDS
from .build import BuildConfig, build
from .config import ProjectConfig, generated_models, option, renode_repl
from .emulator import FaultSkip
from .emulator import run as emulate
from .peripherals import parse_rules, parse_stimulus, parse_time_ms

_CASE_KEYS = ("stimulus", "stimulus_file", "rules", "expect", "forbid", "faults")
_RUN_SECONDS = 45.0  # includes Renode's start-up, with runs side by side


@dataclass
class Case:
    name: str
    stimulus: list
    stimulus_file: str | None
    expect: list[str]
    forbid: list[str]
    fault_times: list[float] = field(default_factory=list)
    rules: list = field(default_factory=list)


def parse_cases(cfg: ProjectConfig) -> list[Case]:
    declared = option(cfg, "scenarios", "cases")
    if not isinstance(declared, dict) or not declared:
        raise VirtulabError("virtulab.yml: tests.scenarios needs at least one case")
    cases = []
    for name, spec in declared.items():
        where = f"scenario '{name}'"
        if not isinstance(spec, dict):
            raise VirtulabError(f"virtulab.yml: {where} must be a mapping")
        unknown = [k for k in spec if k not in _CASE_KEYS]
        if unknown:
            raise VirtulabError(f"virtulab.yml: {where}: unknown key '{unknown[0]}'. Allowed: {', '.join(_CASE_KEYS)}")
        expect, forbid = spec.get("expect") or [], spec.get("forbid") or []
        if isinstance(expect, str):
            expect = [expect]
        if isinstance(forbid, str):
            forbid = [forbid]
        if not expect and not forbid:
            raise VirtulabError(f"virtulab.yml: {where} needs `expect` or `forbid`, or it can never fail")
        if spec.get("faults") and not forbid:
            raise VirtulabError(f"virtulab.yml: {where} has faults, so it needs `forbid`: the outcome that must "
                                "not happen")
        times = spec.get("faults") or []
        times = times if isinstance(times, list) else [times]
        cases.append(Case(str(name), parse_stimulus(spec.get("stimulus")), spec.get("stimulus_file"),
                          [str(e) for e in expect], [str(f) for f in forbid], [parse_time_ms(t) for t in times],
                          parse_rules(spec.get("rules"))))
    return cases


def with_case(cfg: ProjectConfig, case: Case) -> ProjectConfig:
    return replace(cfg, stimulus=case.stimulus, stimulus_file=case.stimulus_file, rules=[*cfg.rules, *case.rules])


def _verdict(case: Case, output: str, exit_code: int | None) -> str:
    """held: went as stated. broken: a forbidden outcome, or a clean exit without the expected one.
    no_result: no answer at all, which a fault can cause by breaking the program's flow.
    """
    if any(text in output for text in case.forbid):
        return "broken"
    if exit_code == 0 and all(text in output for text in case.expect):
        return "held"
    return "no_result" if exit_code != 0 or not case.forbid else "broken"


def _fault_verdict(case: Case, output: str, exit_code: int | None) -> str:
    """During a fault, only a forbidden outcome counts as broken. No answer is a crash, reported apart."""
    if any(text in output for text in case.forbid):
        return "broken"
    return "held" if exit_code == 0 and all(text in output for text in case.expect) else "no_result"


def run(cfg: ProjectConfig, root: Path, work: Path):
    from .suite import FAIL, PASS, RENODE_WORKERS, CheckOutcome, _instructions

    cases = parse_cases(cfg)
    board = BOARDS[cfg.board]
    out = work / "scenarios"
    shutil.rmtree(out, ignore_errors=True)
    bcfg = BuildConfig(board=board, sources=list(option(cfg, "scenarios", "sources")),
                       include_dirs=list(option(cfg, "scenarios", "include")), cflags=cfg.cflags.split(),
                       runtime=cfg.runtime)
    result = build(root, bcfg, out / "build", exclude=work)
    if not result.ok or result.elf is None:
        return CheckOutcome("scenarios", FAIL, "the scenario program did not build", result.log)
    elf = result.elf

    def attempt(case: Case, label: str, skip: FaultSkip | None, run_dir: Path) -> tuple[str, str]:
        scoped = with_case(cfg, case)
        (run_dir / "models").mkdir(parents=True)
        for name, source in generated_models(scoped, root).items():
            (run_dir / "models" / name).write_text(source)
        ran = emulate(board, elf, _RUN_SECONDS, run_dir, renode_repl(scoped, root), skip)
        judge = _fault_verdict if skip else _verdict
        return judge(case, ran.output, ran.exit_code), ran.output

    workers = RENODE_WORKERS
    with ThreadPoolExecutor(max_workers=workers) as pool:
        plain = list(pool.map(lambda c: attempt(c, "", None, out / "runs" / c.name / "plain"), cases))
    wrong = [c.name for c, (verdict, _) in zip(cases, plain) if verdict != "held"]
    log = "\n".join(f"--- {c.name}: {v}\n{o}" for c, (v, o) in zip(cases, plain))
    data: dict = {"cases": len(cases), "swept": 0, "bypass": 0, "crashed": 0, "findings": []}
    if wrong:
        return CheckOutcome("scenarios", FAIL, f"{len(wrong)} of {len(cases)} scenarios went wrong: "
                                               f"{', '.join(wrong)}", log, data)

    timed = [c for c in cases if c.fault_times]
    if not timed:
        return CheckOutcome("scenarios", PASS, f"all {len(cases)} scenarios held", log, data)
    target = option(cfg, "scenarios", "target")
    if not target:
        return CheckOutcome("scenarios", FAIL, "a scenario has faults, but tests.scenarios has no target", log, data)
    listing = _instructions(elf, target, option(cfg, "scenarios", "functions"))
    if not listing:
        return CheckOutcome("scenarios", FAIL, f"inconclusive, no instructions found for {target}", log, data)

    jobs = [(c, t, i) for c in timed for t in c.fault_times for i in listing]

    def strike(job, index):
        case, at, (address, width, _, _) = job
        run_dir = out / "runs" / case.name / f"{index:05d}"
        run_dir.mkdir(parents=True)
        skip = FaultSkip(address, address + width, run_dir / "applied", at)
        verdict, _ = attempt(case, "", skip, run_dir)
        applied = skip.marker.exists()
        shutil.rmtree(run_dir / "models", ignore_errors=True)
        return verdict, applied

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(strike, jobs, range(len(jobs))))
    lines = []
    for (case, at, (address, _, where, text)), (verdict, applied) in zip(jobs, outcomes):
        if not applied:
            if verdict == "no_result":
                return CheckOutcome("scenarios", FAIL, f"inconclusive, no fault applied at {address:#x} in "
                                                       f"{case.name} and the firmware did not finish", log, data)
            continue
        data["swept"] += 1
        if verdict == "no_result":
            data["crashed"] += 1
        elif verdict == "broken":
            data["bypass"] += 1
            lines.append(f"{case.name} after {at:g} ms  0x{address:08x}  {where}  {text}")
            data["findings"].append({"probe": f"{case.name} after {at:g} ms", "address": hex(address),
                                     "function": where.split("+")[0], "instruction": text,
                                     **_source(elf, address, root)})
    log = "\n".join(lines) + "\n" + log
    if not data["swept"]:
        return CheckOutcome("scenarios", FAIL, "inconclusive, no fault reached the target", log, data)
    done = f"all {len(cases)} scenarios held without faults"
    if data["bypass"]:
        return CheckOutcome("scenarios", FAIL, f"{done}, but {data['bypass']} of {data['swept']} timed skips broke "
                                               "one", log, data)
    return CheckOutcome("scenarios", PASS, f"{done}, and no forbidden outcome in {data['swept']} timed skips. "
                                           f"{data['crashed']} crashed or hung: that is not proof of safety, "
                                           "so a real product needs a watchdog", log, data)


def _source(elf: Path, address: int, root: Path) -> dict:
    from .build import addr2line
    _, location = addr2line(elf, address)
    if not location:
        return {}
    path, _, line = location.rpartition(":")
    if Path(path).is_absolute() and Path(path).resolve().is_relative_to(root):
        path = Path(path).resolve().relative_to(root).as_posix()
    return {"file": path, "line": int(line) if line.isdigit() else None}
