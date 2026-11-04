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

_CASE_KEYS = ("description", "stimulus", "stimulus_file", "rules", "expect", "forbid", "faults")
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
    description: str = ""


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
                          parse_rules(spec.get("rules")), str(spec.get("description") or "").strip()))
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
    from .config import all_stimulus
    from .evidence import sha256
    data: dict = {"cases": len(cases), "swept": 0, "bypass": 0, "crashed": 0, "findings": [],
                  "image": {"sha256": sha256(elf), "flash": result.sizes.flash if result.sizes else None,
                            "ram": result.sizes.ram if result.sizes else None},
                  "case_results": [{
                      "name": c.name, "description": c.description, "expect": c.expect, "forbid": c.forbid,
                      "verdict": v, "output": [line for line in o.splitlines()
                                               if line.strip() and not line.startswith(("VIRTULAB_EXIT", "VL_CHECK"))],
                      "inputs": [{"t": st.at_ms, "target": f"{st.module}.{st.prop}", "value": st.value}
                                 for st in all_stimulus(with_case(cfg, c), root)]}
                      for c, (v, o) in zip(cases, plain)]}
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
    _write_sweep(out, elf, root, target, listing, jobs, outcomes, cases, list(option(cfg, "scenarios", "functions") or []),
                 cfg.cflags)
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


def _write_sweep(out: Path, elf: Path, root: Path, target: str, listing, jobs, outcomes, cases,
                 functions: list[str] | None = None, cfg_flags: str = "") -> None:
    """sweep.json and sweep.html: every instruction swept, its C line, and what each glitch did."""
    import json
    rows = []
    for address, width, where, text in listing:
        rows.append({"address": address, "where": where, "instruction": text, **_source(elf, address, root)})
    runs = [{"case": case.name, "at": at, "address": address,
             "result": ("broken" if verdict == "broken" else "crashed" if verdict == "no_result" else "held")
                       if applied else "not_reached"}
            for (case, at, (address, *_)), (verdict, applied) in zip(jobs, outcomes)]
    import shlex

    from .config import load
    path = root / target
    written = load(root)
    flags = "" if written is None or written.cflags == cfg_flags else " " + shlex.quote(f"--cflags={cfg_flags}")
    data = {"command": f"virtulab run --only scenarios{flags}", "target": target, "functions": functions or [], "source": path.read_text().splitlines() if path.is_file() else [],
            "instructions": rows, "runs": runs,
            "cases": {c.name: {"description": c.description, "forbid": c.forbid, "faults": c.fault_times}
                      for c in cases if c.fault_times}}
    (out / "sweep.json").write_text(json.dumps(data))
    page = (Path(__file__).with_name("ui") / "sweep.html").read_text()
    (out / "sweep.html").write_text(page.replace("/*SWEEP_DATA*/null", json.dumps(data).replace("</", "<\\/"), 1))


def run_faults(cfg: ProjectConfig, root: Path, work: Path, command: str = "virtulab faults") -> dict:
    """The fault sweep: every scenario, with every peripheral fault at every moment its inputs change.

    Generated, not written: the cases come from the scenarios and the fault vocabulary, and each is
    judged with its scenario's own `forbid`. Returns the data behind .virtulab/faults/faults.html.
    """
    import json

    from . import faults as fv
    from .config import all_stimulus
    from .suite import RENODE_WORKERS

    cases = parse_cases(cfg)
    board = BOARDS[cfg.board]
    out = work / "faults"
    shutil.rmtree(out, ignore_errors=True)
    bcfg = BuildConfig(board=board, sources=list(option(cfg, "scenarios", "sources")),
                       include_dirs=list(option(cfg, "scenarios", "include")), cflags=cfg.cflags.split(),
                       runtime=cfg.runtime)
    result = build(root, bcfg, out / "build", exclude=work)
    if not result.ok or result.elf is None:
        raise VirtulabError("the scenario program did not build:\n" + result.log[-3000:])
    elf = result.elf

    def attempt(case: Case, steps: list, run_dir: Path, faulty: bool) -> tuple[str, str]:
        scoped = replace(with_case(cfg, case), stimulus=steps, stimulus_file=None)
        (run_dir / "models").mkdir(parents=True)
        for name, source in generated_models(scoped, root).items():
            (run_dir / "models" / name).write_text(source)
        ran = emulate(board, elf, _RUN_SECONDS, run_dir, renode_repl(scoped, root))
        shutil.rmtree(run_dir / "models", ignore_errors=True)
        verdict = (_fault_verdict if faulty else _verdict)(case, ran.output, ran.exit_code)
        said = [line for line in ran.output.splitlines() if "=" in line and " " not in line.strip()]
        return verdict, " ".join(said)

    plan, report = [], []
    for case in cases:
        steps = all_stimulus(with_case(cfg, case), root)
        entry = {"name": case.name, "description": case.description, "forbid": case.forbid, "expect": case.expect,
                 "moments": [], "faults": [], "runs": []}
        report.append(entry)
        if not case.forbid:
            entry["skipped"] = "no `forbid`: there is nothing a fault could break"
            continue
        entry["moments"] = fv.moments(steps, case.fault_times)
        entry["faults"] = [{"key": f.key, "label": f.label, "kind": f.kind, "module": f.module, "input": f.input}
                           for f in fv.faults_for(cfg, steps)]
        plan.append((case, steps, None, None, entry))
        for f in fv.faults_for(cfg, steps):
            for at in entry["moments"]:
                plan.append((case, steps, f, at, entry))

    def go(job, index):
        case, steps, fault, at, _ = job
        run_dir = out / "runs" / f"{index:05d}"
        if fault is None:
            return attempt(case, steps, run_dir, False)
        return attempt(case, fv.inject(cfg, steps, fault, at), run_dir, True)

    with ThreadPoolExecutor(max_workers=RENODE_WORKERS) as pool:
        outcomes = list(pool.map(go, plan, range(len(plan))))
    for (case, _, fault, at, entry), (verdict, said) in zip(plan, outcomes):
        if fault is None:
            entry["nominal"] = {"verdict": verdict, "said": said}
        else:
            entry["runs"].append({"fault": fault.key, "at": at, "result": {"held": "held", "broken": "broken"}.get(
                verdict, "crashed"), "said": said})
    for entry in report:
        if entry.get("nominal", {}).get("verdict") not in (None, "held"):
            entry["skipped"] = "this scenario already goes wrong without faults: fix that first"
            entry["runs"] = []
    data = {"command": command, "window_ms": fv.WINDOW_MS, "vocabulary": fv.FAULTS, "cases": report,
            "runs": sum(len(e["runs"]) for e in report),
            "broken": sum(r["result"] == "broken" for e in report for r in e["runs"]),
            "crashed": sum(r["result"] == "crashed" for e in report for r in e["runs"])}
    (out / "faults.json").write_text(json.dumps(data))
    page = (Path(__file__).with_name("ui") / "faults.html").read_text()
    (out / "faults.html").write_text(page.replace("/*FAULT_DATA*/null", json.dumps(data).replace("</", "<\\/"), 1))
    return data
