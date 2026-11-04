"""Subcommands other than `run`: catalog, check, init, ci, ui, demo."""

import json
import os
import re
import shutil
import sys
from pathlib import Path

from . import VirtulabError, cigen, config
from . import catalog as cat
from .boards import BOARDS
from .check import check as run_check
from .config import ModuleSpec, ProjectConfig
from .report import fmt_capacity
from .scaffold import scaffold

_MODULE_ARG = re.compile(r"(?P<name>[a-z][a-z0-9_]*)=(?P<model>[a-z0-9_]+)@(?P<bus>[a-z0-9]+)(?::(?P<addr>\w+))?")


# ---------------------------------------------------------------------------
# catalog

def catalog(ns) -> int:
    if ns.json:
        print(json.dumps(cat.as_json(), indent=2))
        return 0
    print("BOARDS")
    for n in BOARDS:
        i = cat.board_info(n)
        buses = ", ".join(i["buses"]) or "none"
        print(f"  {n:<18} {i['cpu']:<11} flash {fmt_capacity(i['flash']):>7}  ram {fmt_capacity(i['ram']):>7}  "
              f"{i['emulator']:<6} buses: {buses}")
    print("\nPROTOCOLS")
    for p in cat.PROTOCOLS.values():
        print(f"  {p.id:<5} {p.summary}")
    print("\nSENSORS AND MODULES")
    for m in cat.MODULES.values():
        addr = f"@ {m.default_address:#04x}" if m.default_address is not None else ""
        print(f"  {m.id:<10} {m.protocol:<4} {m.tier:<9} {m.title} {addr}")
    print("\nTESTS")
    for t in cat.TESTS.values():
        mark = "*" if t.on_by_default else " "
        print(f" {mark}{t.id:<10} {t.stage:<10} {t.title}")
    print("\n(* = on by default)")
    return 0


# ---------------------------------------------------------------------------
# datasheet

def datasheet(ns) -> int:
    from . import datasheets
    if ns.issues:
        print(datasheets.issues_markdown())
        return 0
    if ns.markdown:
        print(datasheets.to_markdown(ns.module) if ns.module else datasheets.all_markdown())
        return 0
    if not ns.module:
        print("Sensors with a datasheet map (virtulab datasheet NAME):")
        for name in datasheets.available():
            print(f"  {name:<10} {datasheets.load(name)['title']}")
        return 0
    data = datasheets.load(ns.module)
    print(f"{data['title']}")
    for d in data["documents"]:
        print(f"  read: {d['title']} ({d.get('revision', 'revision unknown')}), {d.get('url', '')}")
    if not data["documents"]:
        print("  read: nothing yet, every row is unverified")
    if data.get("product_page"):
        print(f"  page: {data['product_page']}")
    print(f"  interface: {data.get('interface', '')}\n")
    for r in data["rows"]:
        print(f"[{datasheets.STATUS[r['status']]}] {r['topic']}\n    {r['datasheet']}")
        print(f"    source {r.get('source') or 'UNVERIFIED (no citation)'}"
              + (f"; also {', '.join(r['corroborated_by'])}" if r.get("corroborated_by") else ""))
        if r.get("issue"):
            print(f"    ISSUE  {r['issue']}")
        for place, label in (("model", "model "), ("driver", "driver"), ("test", "test  ")):
            p = r.get(place)
            if p:
                where = f"{p['path']}:{p['line']}" if p["line"] else f"{p['path']} (anchor not found)"
                print(f"    {label} {where}")
        if r.get("note"):
            print(f"    note   {r['note']}")
    return 0


# ---------------------------------------------------------------------------
# check

def check(ns) -> int:
    root = Path(ns.directory)
    cfg = config.load(root)
    if cfg is None:
        raise VirtulabError(f"No virtulab.yml in {root.resolve()}. Run `virtulab init` first.")
    result = run_check(cfg, root.resolve())
    if ns.format == "json":
        print(json.dumps(result.to_json(), indent=2))
    elif ns.format == "markdown":
        print(result.to_markdown())
    else:
        print(result.to_text())
    return 0 if result.ok else 2


# ---------------------------------------------------------------------------
# ci

def ci(ns) -> int:
    root = Path(ns.directory)
    cfg = config.load(root)
    if cfg is None:
        raise VirtulabError("No virtulab.yml found. Run `virtulab init` first.")
    path, content = cigen.render(cfg, ns.provider)
    if not ns.write:
        print(f"# {path}\n{content}")
        return 0
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    print(f"✅ Wrote {target}")
    return 0


# ---------------------------------------------------------------------------
# init (interactive wizard or flags)

def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def _choose(title: str, options: list[tuple[str, str]], default: str) -> str:
    print(f"\n{title}")
    for i, (key, label) in enumerate(options, 1):
        print(f"  {i}) {key:<18} {label}")
    while True:
        answer = _ask("Choose a number or name", default)
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1][0]
        if answer in dict(options):
            return answer
        print("  Not an option, try again.")


def parse_module_arg(text: str) -> ModuleSpec:
    m = _MODULE_ARG.fullmatch(text)
    if not m:
        raise VirtulabError(f"Bad --module '{text}'. Use NAME=MODEL@BUS or NAME=MODEL@BUS:0x48, "
                            "e.g. temp=tmp108@i2c1:0x48")
    try:
        address = int(m["addr"], 0) if m["addr"] else None
    except ValueError:
        raise VirtulabError(f"Bad address '{m['addr']}' in --module '{text}'. Use a number, e.g. 0x48") from None
    return ModuleSpec(m["name"], m["model"], m["bus"], address)


def _wizard(cfg: ProjectConfig, ns) -> tuple[bool, str]:
    """Ask the questions flags did not answer. Returns (create sample firmware, CI provider or none)."""
    ci_choice = ns.ci or "github"
    print("VirtuLab setup — answer a few questions, press Enter to accept [defaults].")
    if not ns.board:
        options = [(n, f"{cat.board_info(n)['cpu']}, {BOARDS[n].description}"
                    + ("  (sensors supported)" if cat.board_buses(n) else ""))
                   for n in BOARDS]
        cfg.board = _choose("1. Which board?", options, "stm32f4_discovery" if "stm32f4_discovery" in BOARDS
                            else next(iter(BOARDS)))
    buses = cat.board_buses(cfg.board)
    if buses and not ns.module:
        print(f"\n2. Sensors. {cfg.board} offers: {', '.join(sorted(set(buses.values())))}.")
        print("   Available sensors:")
        for m in cat.MODULES.values():
            print(f"     {m.id:<8} {m.protocol}  {m.title}")
        while True:
            pick = _ask("Add a sensor (name, or Enter to finish)", "")
            if not pick:
                break
            if pick not in cat.MODULES:
                print("   Unknown sensor.")
                continue
            mod = cat.MODULES[pick]
            options = [b for b, k in buses.items() if k == mod.protocol]
            bus = _ask(f"   Which {mod.protocol} bus ({', '.join(options)})", options[0])
            addr = _ask("   Address", f"{mod.default_address:#04x}" if mod.default_address is not None else "")
            name = _ask("   Name in your tests", mod.kind if mod.kind not in cfg.modules else f"{mod.id}2")
            cfg.modules[name] = ModuleSpec(name, mod.id, bus, int(addr, 0) if addr else None)
    elif not buses and not ns.module:
        print(f"\n2. Sensors: {cfg.board} runs on QEMU (CPU only), so no sensors can be attached. "
              "Pick stm32f4_discovery for that.")
    if not ns.tests:
        print("\n3. Tests. Pick the checks to run on every push.")
        selected = {}
        for t in cat.TESTS.values():
            if t.emulated_boards_only and BOARDS[cfg.board].emulator != "qemu":
                continue
            default = "y" if t.on_by_default else "n"
            note = f"  [{t.limits}]" if t.limits else ""
            if _ask(f"   {t.title}? {t.summary}{note} (y/n)", default).lower().startswith("y"):
                selected[t.id] = {}
        cfg.tests = selected
    if not ns.ci:
        ci_choice = _choose("4. Which CI?", [("github", "GitHub Actions"), ("gitlab", "GitLab CI"),
                                             ("none", "write no CI file")], "github")
    if not ns.template:
        sample = _ask("\n5. Create sample firmware that matches this setup so it passes right away? (y/n)",
                      "y").lower().startswith("y")
    else:
        sample = ns.template != "none"
    return sample, ci_choice


def init(ns) -> int:
    root = Path(ns.directory)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "virtulab.yml"
    if target.exists() and not ns.force:
        raise VirtulabError(f"{target} already exists. Edit it, or use --force to start over.")
    cfg = ProjectConfig()
    if ns.board:
        if ns.board not in BOARDS:
            raise VirtulabError(f"Unknown board '{ns.board}'. Run `virtulab catalog`.")
        cfg.board = ns.board
    for text in ns.module:
        spec = parse_module_arg(text)
        cfg.modules[spec.name] = spec
    if ns.tests:
        cfg.tests = {t.strip(): {} for t in ns.tests.split(",") if t.strip()}
    interactive = not ns.yes and sys.stdin.isatty()
    if interactive:
        make_sample, ci_choice = _wizard(cfg, ns)
    else:
        make_sample, ci_choice = ns.template == "starter", ns.ci or "github"
        if ns.board is None and cfg.modules:
            cfg.board = "stm32f4_discovery"
    if ci_choice != "none":
        cfg.ci_provider = ci_choice

    config.from_dict(cfg.to_dict())  # refuse a bad selection before writing anything
    created: list[str] = []
    if make_sample:
        created += scaffold(cfg, root, force=ns.force)
    checked = config.from_dict(cfg.to_dict())  # validates names, tests and board
    result = run_check(checked, None, tools=False)
    if not result.ok:
        print(result.to_text())
        raise VirtulabError("That selection does not work together. Fix it and run init again.")
    target.write_text(checked.dumps())
    created.append("virtulab.yml")
    if ci_choice != "none":
        path, content = cigen.render(checked)
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content)
        created.append(path)

    print("\n✅ Created:")
    for p in sorted(created):
        print(f"   {p}")
    print(f"\nNext:\n   virtulab check -C {root}      # validate board, wiring and tests"
          f"\n   virtulab run -C {root}        # run the selected tests")
    return 0


# ---------------------------------------------------------------------------
# ui, demo

def ui(ns) -> int:
    from .ui.server import serve
    return serve(Path(ns.directory).resolve(), ns.port, open_browser=not ns.no_browser)


def faults(ns) -> int:
    from dataclasses import replace

    from .scenarios import run_faults
    root = Path(ns.directory).resolve()
    cfg = config.load(root)
    if cfg is None or "scenarios" not in cfg.tests:
        raise VirtulabError("virtulab faults needs tests.scenarios in virtulab.yml: the faults are injected into them")
    if ns.cflags is not None:
        cfg = replace(cfg, cflags=ns.cflags)
    print(f"⏺  Generating fault cases from {len(cfg.tests['scenarios'].get('cases', {}))} scenarios", flush=True)
    import shlex
    command = "virtulab faults" + (" " + shlex.quote(f"--cflags={ns.cflags}") if ns.cflags is not None else "")
    data = run_faults(cfg, root, root / ".virtulab", command)
    for case in data["cases"]:
        broken = [r for r in case["runs"] if r["result"] == "broken"]
        if case.get("skipped"):
            print(f"⏭️  {case['name']}: {case['skipped']}")
        else:
            print(f"{'❌' if broken else '✅'} {case['name']}: {len(case['runs'])} fault cases, {len(broken)} broke a rule")
            labels = {f["key"]: f["label"] for f in case["faults"]}
            for r in broken:
                print(f"     {labels[r['fault']]} at {r['at']:g} ms for {data['window_ms']:g} ms → {r['said']}")
    page = root / ".virtulab" / "faults" / "faults.html"
    print(f"{'❌' if data['broken'] else '✅'} {data['broken']} of {data['runs']} generated fault cases broke a rule"
          f", {data['crashed']} crashed or hung")
    print(f"📄 Open {os.path.relpath(page)} in a browser")
    return 1 if data["broken"] or data["crashed"] else 0


def studio(ns) -> int:
    from .ui import studio as st
    from .ui.server import serve
    root = Path(ns.directory).resolve()
    if config.load(root) is None:
        raise VirtulabError(f"No virtulab.yml in {root}. Run `virtulab init` first.")
    variants = st.parse_variants(ns.variant)
    if ns.prepare:
        return st.prepare(root, variants)
    studio = st.Studio(root, variants)
    studio.refresh()   # pages recorded by an older VirtuLab get today's page designs
    return serve(root, ns.port, open_browser=not ns.no_browser, studio=studio, app=ns.app)


def trace(ns) -> int:
    from dataclasses import replace

    from . import trace as recorder
    from .config import option
    from .scenarios import parse_cases, with_case

    root = Path(ns.directory).resolve()
    cfg = config.load(root)
    if cfg is None:
        raise VirtulabError(f"No virtulab.yml in {root}. Run `virtulab init` first.")
    sources = include = None
    if ns.cflags is not None:
        cfg = replace(cfg, cflags=ns.cflags)
    skip = target = None
    if ns.skip:
        from .peripherals import parse_time_ms
        address, _, when = ns.skip.partition("@")
        try:
            skip = (int(address, 0), parse_time_ms(when or "0ms"))
        except ValueError:
            raise VirtulabError(f"--skip '{ns.skip}' must look like 0x080002a8@1300ms") from None
        if not ns.case:
            raise VirtulabError("--skip needs --case: a glitch is judged against a scenario")
        target = option(cfg, "scenarios", "target")
    fault = None
    if getattr(ns, "fault", None):
        from . import faults as fv
        from .peripherals import parse_time_ms
        key, _, when = ns.fault.partition("@")
        try:
            fault, fault_at = fv.parse(key), parse_time_ms(when or "0ms")
        except ValueError:
            raise VirtulabError(f"--fault '{ns.fault}' must look like imu.*.silent@1300ms") from None
        if not ns.case:
            raise VirtulabError("--fault needs --case: a fault is injected into a scenario")
    if ns.case:
        if "scenarios" not in cfg.tests:
            raise VirtulabError("--case needs tests.scenarios in virtulab.yml")
        cases = {c.name: c for c in parse_cases(cfg)}
        if ns.case not in cases:
            raise VirtulabError(f"No scenario case '{ns.case}'. Cases: {', '.join(cases)}")
        cfg = with_case(cfg, cases[ns.case])
        sources = list(option(cfg, "scenarios", "sources"))
        include = list(option(cfg, "scenarios", "include"))
    scripted = None
    if fault:
        from .config import all_stimulus
        scripted = all_stimulus(cfg, root)
        if fault.input is None and not fv.wire(cfg, fault.module, fault.kind):
            raise VirtulabError(f"{fault.module} has no '{fault.kind}' fault")
        if fault.input is not None and fault.kind != "stuck" and not fv.input_range(cfg, fault.module, fault.input):
            raise VirtulabError(f"{fault.module}.{fault.input} has no known range, so it cannot be {fault.kind}")
        cfg = replace(cfg, stimulus=fv.inject(cfg, scripted, fault, fault_at), stimulus_file=None)
    print(f"⏺  Recording {'scenario ' + ns.case if ns.case else 'the unit tests'} on {cfg.board}"
          + (f", skipping the instruction at {skip[0]:#x} after {skip[1]:g} ms" if skip else ""), flush=True)
    data = recorder.record(cfg, root, root / ".virtulab", sources, include, skip, target)
    if ns.case:
        from .config import all_stimulus
        from .scenarios import _fault_verdict, _verdict
        case = cases[ns.case]
        judge = _fault_verdict if fault else _verdict
        data["scenario"] = {
            "name": case.name, "description": case.description, "expect": case.expect, "forbid": case.forbid,
            "faults": case.fault_times, "verdict": judge(case, data["output"], data["exit_code"]),
            "inputs": [{"t": s.at_ms, "target": f"{s.module}.{s.prop}", "value": s.value}
                       for s in (scripted or all_stimulus(cfg, root))],
            "rules": [{"when": r.pin, "high": r.level, "for_ms": r.hold_ms, "set": r.target, "to": r.value}
                      for r in cfg.rules],
        }
    import shlex
    data["command"] = " ".join(["virtulab trace", *(["--case", ns.case] if ns.case else []),
                                *([shlex.quote(f"--cflags={ns.cflags}")] if ns.cflags is not None else []),
                                *(["--skip", ns.skip] if ns.skip else []),
                                *(["--fault", shlex.quote(ns.fault)] if getattr(ns, "fault", None) else [])])
    if fault:
        data["fault"] = {"label": fault.label, "kind": fault.kind, "module": fault.module, "input": fault.input,
                         "what": fv.FAULTS[fault.kind], "at": fault_at, "until": fault_at + fv.WINDOW_MS}
    page = recorder.write(data, root / ".virtulab" / "trace")
    kinds = [e["kind"] for e in data["events"]]
    if fault:
        print(f"⚠️  {fault.label} from {fault_at:g} to {fault_at + fv.WINDOW_MS:g} ms: "
              + {"held": "the scenario still held.", "broken": "the scenario broke: a forbidden output appeared.",
                 "no_result": "the firmware gave no result."}[data["scenario"]["verdict"]])
    if skip:
        g = data["glitch"]
        print(f"⚡ {'Skipped' if g['applied'] else 'Never reached:'} {g['instruction']} ({g['where']}"
              + (f", {g['file']}:{g['line']}" if g.get("file") else "") + ")"
              + (f" at {g['t']} ms" if g.get("t") is not None else "")
              + ". " + {"held": "The scenario still held.", "broken": "The scenario broke: a forbidden output appeared.",
                        "no_result": "The firmware gave no result."}[data["scenario"]["verdict"]])
    print(f"✅ {kinds.count('access')} register accesses and {kinds.count('bus')} bus messages "
          f"over {data['duration_ms']} ms of virtual time")
    print(f"📄 Open {os.path.relpath(page)} in a browser")
    print(f"🔌 Board view: {os.path.relpath(page.with_name('board.html'))}")
    return 0


def compare(ns) -> int:
    from . import compare as cmp

    def load(path: str) -> list:
        p = Path(path)
        return cmp.from_trace(json.loads(p.read_text())) if p.suffix == ".json" else cmp.read_messages(p)

    size, _, skip = ns.frame.partition("+")
    if not size.isdigit() or (skip and not skip.isdigit()) or int(size) < 1:
        raise VirtulabError(f"--frame '{ns.frame}' must look like 2 or 2+1")
    try:
        tolerance = [int(t) for t in ns.tolerance.split(",")]
    except ValueError:
        raise VirtulabError(f"--tolerance '{ns.tolerance}' must be numbers, e.g. 75 or 75,1311") from None
    result = cmp.compare(load(ns.twin), load(ns.real), tolerance, (int(size), int(skip or 0)))
    print(cmp.report(result))
    return 0 if result.ok else 1


def setup(ns) -> int:
    from . import tools
    names = [n.strip() for n in ns.only.split(",")] if ns.only else list(tools.TOOLS)
    unknown = [n for n in names if n not in tools.TOOLS]
    if unknown:
        raise VirtulabError(f"Unknown tool {', '.join(unknown)}. Choose from {', '.join(tools.TOOLS)}")
    skipped = []
    for name in names:
        tool = tools.TOOLS[name]
        if tools.platform_key() not in tool.assets:
            skipped.append(f"{tool.summary}: no build for {tools.platform_key()}, use the Docker image for it")
            continue
        tools.install(tool, force=ns.force)
    for line in skipped:
        print(f"⏭️  {line}")
    print("Run `virtulab doctor` to see what VirtuLab will use.")
    return 0


def doctor(ns) -> int:
    from . import tools
    from .check import _tool
    print(f"Platform {tools.platform_key()}, tools folder {tools.home()}")
    rows = [("Arm compiler", shutil.which("arm-none-eabi-gcc")), ("Arm GDB", _tool("arm-gdb", "lm3s6965evb")),
            ("QEMU", shutil.which("qemu-system-arm")), ("Renode", shutil.which("renode")),
            ("Host C compiler", _tool("cc", "lm3s6965evb")), ("gcov", shutil.which("gcov")),
            ("STM32F4 register file", str(tools.svd_file()) if tools.svd_file() else None),
            ("Docker", shutil.which("docker"))]
    managed = str(tools.home())
    for label, path in rows:
        where = "missing" if not path else "installed by virtulab setup" if str(path).startswith(managed) else "system"
        print(f"{'✅' if path else '❌'} {label:<22} {where:<28} {path or ''}")
    return 0


def demo(ns) -> int:
    from .demo import run_demo
    return run_demo(Path(ns.directory), ns.seconds)
