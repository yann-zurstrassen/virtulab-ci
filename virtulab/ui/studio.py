"""`virtulab studio`: one page with the project's code, its board and its scenarios.

The studio runs the same commands as the terminal (`virtulab trace`, `virtulab run`) in the
background and keeps each result under .virtulab/studio, so a page recorded once opens at once.
A variant is a named set of extra compiler flags, such as "plain=-DPATCH_HARDENED=0", to show the
same scenarios on another build of the firmware.
"""

import json
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .. import VirtulabError, config, subprocess_env

SKIP_DIRS = {".virtulab", ".git", "build", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".c", ".h", ".cc", ".cpp", ".hpp", ".s", ".S", ".yml", ".yaml", ".csv", ".md", ".txt",
                 ".ld", ".cmake", ".py", ".sh", ".repl", ".resc", ".cs", ".json"}
MAX_FILE = 512 * 1024


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "default"


def parse_variants(specs: list[str]) -> dict[str, str]:
    """["plain=-DSAFE=0"] -> {"as written": "", "plain": "-DSAFE=0"}"""
    variants = {"as written": ""}
    for spec in specs:
        name, sep, flags = spec.partition("=")
        if not sep or not name.strip():
            raise VirtulabError(f"--variant '{spec}' must look like NAME=FLAGS, e.g. plain=-DSAFE=0")
        variants[name.strip()] = flags.strip()
    return variants


class Studio:
    def __init__(self, root: Path, variants: dict[str, str]):
        self.root = root
        self.variants = variants
        self.store = root / ".virtulab" / "studio"
        self.lock = threading.Lock()
        self.job: dict | None = None

    # ---------- reading the project ----------
    def files(self) -> list[str]:
        found = []
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root)
            if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]) or rel.parts[0] in SKIP_DIRS:
                continue
            if path.is_file() and (path.suffix in TEXT_SUFFIXES or path.name in ("Makefile", "CMakeLists.txt")):
                found.append(rel.as_posix())
        return found

    def provided(self) -> dict[str, Path]:
        """VirtuLab's own files behind this firmware, shown read-only: the runtime linked into every
        build, and the sensor models the emulator runs in place of the real chips."""
        from .. import DEVICES_DIR, catalog
        runtime = Path(__file__).resolve().parent.parent / "runtime"
        shown = {f"virtulab/runtime/{n}": runtime / n for n in ("startup.c", "virtulab.h", "virtulab_test.c", "virtulab_test.h")}
        cfg = config.load(self.root)
        for m in cfg.modules.values():
            kind = catalog.get_module(m.model).renode_type
            if kind.startswith("VirtuLab."):
                model = DEVICES_DIR / f"{kind.split('.', 1)[1]}.cs"
                if model.is_file():
                    shown[f"virtulab/models/{model.name}"] = model
        return shown

    def origins(self) -> dict[str, str]:
        """Who wrote each file: "yours", "project" (virtulab.yml: setup written by VirtuLab, scenarios by
        you), "starter" (VirtuLab's sample, unchanged), "edited" (VirtuLab's sample, changed in this
        project) or "virtulab" (read-only, VirtuLab's own)."""
        from ..scaffold import starter_files
        cfg = config.load(self.root)
        try:
            starter = starter_files(cfg)
        except VirtulabError:
            starter = {}
        found = {}
        for rel in self.files():
            if rel in starter:
                found[rel] = "starter" if (self.root / rel).read_text(errors="replace") == starter[rel] else "edited"
            elif rel == "virtulab.yml":
                found[rel] = "project"   # VirtuLab writes the setup part, the user writes the scenarios
            else:
                found[rel] = "yours"
        found.update({rel: "virtulab" for rel in self.provided()})
        return found

    def file(self, rel: str) -> dict:
        provided = self.provided()
        if rel in provided:
            return {"path": rel, "text": provided[rel].read_text(errors="replace"), "origin": "virtulab"}
        path = (self.root / rel).resolve()
        if not path.is_relative_to(self.root) or rel not in self.files():
            raise VirtulabError(f"not a project file: {rel}")
        if path.stat().st_size > MAX_FILE:
            raise VirtulabError(f"{rel} is too large to show")
        return {"path": rel, "text": path.read_text(errors="replace"), "origin": self.origins().get(rel, "yours")}

    def project(self) -> dict:
        from ..scenarios import parse_cases
        cfg = config.load(self.root)
        if cfg is None:
            raise VirtulabError(f"No virtulab.yml in {self.root}")
        cases = []
        if "scenarios" in cfg.tests:
            for c in parse_cases(cfg):
                cases.append({"name": c.name, "description": c.description, "expect": c.expect, "forbid": c.forbid,
                              "faults": c.fault_times, "stimulus_file": c.stimulus_file})
        return {"name": self.root.name, "board": cfg.board, "cflags": cfg.cflags, "tests": list(cfg.tests),
                "summary": {slug(v): self.summary(slug(v)) for v in self.variants},
                "modules": {n: {"model": m.model, "bus": m.bus} for n, m in cfg.modules.items()},
                "cases": cases, "variants": self.variants, "results": self.results()}

    def summary(self, v: str) -> dict:
        """The headline numbers of one build, from the pages already recorded for it."""
        def load(rel):
            path = self.store / rel
            return json.loads(path.read_text()) if path.is_file() else None
        out = {}
        ev = load(f"evidence/{v}/evidence.json")
        if ev:
            for c in ev.get("checks", []):
                out[c["test"]] = {"status": c["status"], "summary": c["summary"]}
            out["commit"] = (ev.get("commit") or "")[:7] + ("+" if ev.get("tree_clean") is False else "")
        sw = load(f"sweeps/{v}/sweep.json")
        if sw:
            reached = [r for r in sw["runs"] if r["result"] != "not_reached"]
            out["glitch"] = {"runs": len(reached), "broken": sum(r["result"] == "broken" for r in reached)}
        fl = load(f"faults/{v}/faults.json")
        if fl:
            active = [c for c in fl["cases"] if not c.get("skipped")]
            out["faults"] = {"runs": fl["runs"], "broken": fl["broken"], "crashed": fl["crashed"],
                             "scenarios": len(active),
                             "faults": sorted({len(c["faults"]) for c in active}),
                             "moments": sorted({len(c["moments"]) for c in active})}
        return out

    def results(self) -> list[str]:
        """Pages already recorded, as paths under /view/."""
        if not self.store.is_dir():
            return []
        return sorted(p.relative_to(self.store).as_posix() for p in self.store.glob("*/*/*.html")
                      if p.name in ("board.html", "sweep.html", "faults.html", "evidence.html", "report.html"))

    # ---------- running ----------
    def _flags(self, variant: str) -> str | None:
        if variant not in self.variants:
            raise VirtulabError(f"unknown variant '{variant}'")
        extra = self.variants[variant]
        if not extra:
            return None
        cfg = config.load(self.root)
        return f"{cfg.cflags} {extra}".strip()

    def plan(self, kind: str, case: str | None, variant: str, skip: str | None,
             fault: str | None = None) -> tuple[list[str], str, str]:
        """The command for a job, where its page is kept, and the page's file name."""
        cmd = [sys.executable, "-m", "virtulab"]
        flags = self._flags(variant)
        v = slug(variant)
        if kind == "trace":
            if not case:
                raise VirtulabError("a run needs a scenario")
            cmd += ["trace", "-C", str(self.root), "--case", case]
            key = f"runs/{slug(case)}--{v}" + (f"--glitch-{slug(skip)}" if skip else "") + \
                (f"--fault-{slug(fault)}" if fault else "")
            if fault:
                if not re.fullmatch(r"[A-Za-z_]\w*\.(\*|[A-Za-z_]\w*)\.[a-z]+@\d+(\.\d+)?ms", fault):
                    raise VirtulabError("fault must look like imu.*.silent@1300ms")
                cmd += ["--fault", fault]
            if skip:
                if not re.fullmatch(r"0x[0-9a-fA-F]+@\d+(\.\d+)?ms", skip):
                    raise VirtulabError("skip must look like 0x080002a8@1300ms")
                cmd += ["--skip", skip]
            page = "board.html"
        elif kind == "faults":
            cmd += ["faults", "-C", str(self.root)]
            key, page = f"faults/{v}", "faults.html"
        elif kind == "sweep":
            # with the unit tests, so the evidence record of this build covers both
            tests = config.load(self.root).tests
            cmd += ["run", "-C", str(self.root), "--only", "unit,scenarios" if "unit" in tests else "scenarios"]
            key, page = f"sweeps/{v}", "sweep.html"
        elif kind == "unit":
            cmd += ["run", "-C", str(self.root), "--only", "unit"]
            key, page = f"unit/{v}", ""
        else:
            raise VirtulabError(f"unknown job '{kind}'")
        if flags is not None:
            cmd.append(f"--cflags={flags}")
        return cmd, key, page

    def start(self, kind: str, case: str | None, variant: str, skip: str | None, fault: str | None = None) -> dict:
        cmd, key, page = self.plan(kind, case, variant, skip, fault)
        with self.lock:
            if self.job and self.job["proc"].poll() is None:
                raise VirtulabError("Something is already running. Wait for it to finish.")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    text=True, cwd=self.root, env=subprocess_env())
            job = {"proc": proc, "output": [], "kind": kind, "key": key, "page": page, "result": None, "cmd": cmd,
                   "finished": threading.Event(),
                   "title": f"{kind} {case or ''} {variant}".strip()}
            threading.Thread(target=self._pump, args=(job,), daemon=True).start()
            self.job = job
        return {"started": key}

    def _pump(self, job: dict) -> None:
        for line in job["proc"].stdout:
            job["output"].append(line)
        job["proc"].wait()
        try:
            job["result"] = self._keep(job)
        finally:
            job["finished"].set()

    def _keep(self, job: dict) -> str | None:
        """Copy the pages a finished job produced into the studio store."""
        work = self.root / ".virtulab"
        dest = self.store / job["key"]
        if job["kind"] == "trace":
            source = work / "trace"
            if not (source / "board.html").is_file() or job["proc"].returncode != 0:
                return None
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(source, dest, ignore=shutil.ignore_patterns("build", "run"))
            return f"{job['key']}/board.html"
        if job["kind"] == "faults":
            source = work / "faults" / "faults.html"
            if not source.is_file():
                return None
            dest.mkdir(parents=True, exist_ok=True)
            for name in ("faults.html", "faults.json"):
                shutil.copy2(work / "faults" / name, dest / name)
            return f"{job['key']}/faults.html"
        if job["kind"] in ("sweep", "unit"):
            v = job["key"].split("/", 1)[1]
            self._keep_evidence(v, self.display(job["cmd"]))
            report = work / "report.html"
            if report.is_file():
                (self.store / "reports" / v).mkdir(parents=True, exist_ok=True)
                shutil.copy2(report, self.store / "reports" / v / "report.html")
                if (work / "report.json").is_file():
                    shutil.copy2(work / "report.json", self.store / "reports" / v / "report.json")
        if job["kind"] == "sweep":
            source = work / "scenarios" / "sweep.html"
            if not source.is_file():
                return None
            dest.mkdir(parents=True, exist_ok=True)
            for name in ("sweep.html", "sweep.json"):
                shutil.copy2(work / "scenarios" / name, dest / name)
            return f"{job['key']}/sweep.html"
        return None

    def display(self, cmd: list[str]) -> str:
        """A job's command as a developer would type it in the project folder."""
        import shlex
        args, out, skip = cmd[3:], [], False
        for a in args:
            if skip:
                skip = False
                continue
            if a == "-C":
                skip = True
                continue
            out.append(a)
        return "virtulab " + " ".join(shlex.quote(a) for a in out)

    def _keep_evidence(self, variant_slug: str, command: str = "") -> None:
        """The evidence record of the run that just finished, as a page, one per firmware build."""
        source = self.root / ".virtulab" / "evidence" / "evidence.json"
        if not source.is_file():
            return
        dest = self.store / "evidence" / variant_slug
        dest.mkdir(parents=True, exist_ok=True)
        record = json.loads(source.read_text())
        record["command"] = command
        data = json.dumps(record)
        (dest / "evidence.json").write_text(data)
        page = (Path(__file__).with_name("evidence.html")).read_text()
        (dest / "evidence.html").write_text(page.replace("/*EVIDENCE_DATA*/null", data.replace("</", "<\\/"), 1))

    def refresh(self) -> int:
        """Re-render every kept page from its data with the current page designs, so a page recorded
        before an update of VirtuLab looks like one recorded now. Returns the number of pages."""
        from .. import trace
        ui = Path(__file__).parent
        count = 0
        for data_file in sorted(self.store.glob("runs/*/trace.json")):
            trace.write(json.loads(data_file.read_text()), data_file.parent)
            count += 1
        for kind, template, marker in (("sweeps", "sweep", "SWEEP_DATA"), ("faults", "faults", "FAULT_DATA"),
                                       ("evidence", "evidence", "EVIDENCE_DATA"), ("reports", "report", "REPORT_DATA")):
            for data_file in sorted(self.store.glob(f"{kind}/*/{template}.json")):
                page = (ui / f"{template}.html").read_text()
                data = data_file.read_text().replace("</", "<\\/")
                data_file.with_suffix(".html").write_text(page.replace(f"/*{marker}*/null", data, 1))
                count += 1
        return count

    def status(self) -> dict:
        job = self.job
        if not job:
            return {"state": "idle"}
        done = job["finished"].is_set()
        return {"state": "done" if done else "running", "kind": job["kind"], "key": job["key"],
                "exit_code": job["proc"].returncode if done else None,
                "output": "".join(job["output"])[-20000:], "result": job["result"]}

    # ---------- reading a kept page ----------
    def view(self, rel: str) -> tuple[bytes, str]:
        path = (self.store / rel).resolve()
        if not path.is_relative_to(self.store.resolve()) or not path.is_file():
            raise VirtulabError("not found")
        kinds = {".html": "text/html; charset=utf-8", ".json": "application/json", ".csv": "text/csv"}
        return path.read_bytes(), kinds.get(path.suffix, "application/octet-stream")


def prepare(root: Path, variants: dict[str, str]) -> int:
    """Record everything the studio shows, so nothing waits during a demo."""
    studio = Studio(root.resolve(), variants)
    project = studio.project()

    def run(kind, case=None, variant="as written", skip=None, fault=None):
        label = " ".join(filter(None, (kind, case, variant if variant != "as written" else "", skip, fault)))
        print(f"⏺  {label}", flush=True)
        studio.start(kind, case, variant, skip, fault)
        studio.job["finished"].wait()
        result = studio.job["result"]
        print(f"   {'✅ ' + result if result else '❌ no page, see the output below'}", flush=True)
        if not result and studio.job["page"]:
            print("".join(studio.job["output"])[-2000:])
        return result

    for case in project["cases"]:
        run("trace", case["name"])
    if any(c["faults"] for c in project["cases"]):
        for variant in variants:
            if run("sweep", variant=variant):
                data = json.loads((studio.store / "sweeps" / slug(variant) / "sweep.json").read_text())
                text = {i["address"]: i["instruction"] for i in data["instructions"]}
                broken = sorted((r for r in data["runs"] if r["result"] == "broken"),
                                key=lambda r: not text[r["address"]].startswith("str"))
                if broken:
                    b = broken[0]
                    run("trace", b["case"], variant, f"{b['address']:#x}@{b['at']:g}ms")
    if any(c["faults"] or c["forbid"] for c in project["cases"]):
        if run("faults"):
            data = json.loads((studio.store / "faults" / "as-written" / "faults.json").read_text())
            broken = [(c["name"], r) for c in data["cases"] for r in c["runs"] if r["result"] == "broken"]
            for name, r in broken[:10]:    # the first findings, ready to watch
                run("trace", name, "as written", fault=f"{r['fault']}@{r['at']:g}ms")
    print("Ready.")
    return 0
