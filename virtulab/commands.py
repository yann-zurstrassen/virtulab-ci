"""Subcommands other than `run`: catalog, check, init, ci, ui, demo."""

import json
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
    return ModuleSpec(m["name"], m["model"], m["bus"], int(m["addr"], 0) if m["addr"] else None)


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


def demo(ns) -> int:
    from .demo import run_demo
    return run_demo(Path(ns.directory), ns.seconds)
