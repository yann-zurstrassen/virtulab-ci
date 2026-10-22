"""`virtulab.yml`: one file describing board, modules and tests.

The CLI, the GitHub Action, the Docker image and the web UI all read this
file, so no CI system duplicates settings. Unknown keys are errors (with a
"did you mean"), so typos never fail silently.
"""

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import VirtulabError, yamlite
from .boards import BOARDS
from .catalog import DEFAULT_TESTS, MODULES, PROTOCOLS, TESTS, get_module, get_test
from .yamlite import Hex

CONFIG_NAMES = ("virtulab.yml", "virtulab.yaml")
SCHEMA_VERSION = 1

_TOP_KEYS = ("version", "board", "build", "timeout", "modules", "tests", "ci")
_BUILD_KEYS = ("sources", "include", "cflags", "ldflags", "linker_script", "runtime")
_MODULE_KEYS = ("model", "bus", "address")
_CI_KEYS = ("provider", "branches")
_PROVIDERS = ("github", "gitlab")
_NAME = re.compile(r"[a-z][a-z0-9_]*")


@dataclass
class ModuleSpec:
    name: str
    model: str
    bus: str
    address: int | None = None


@dataclass
class ProjectConfig:
    board: str = "lm3s6965evb"
    sources: list[str] = field(default_factory=lambda: ["**/*.c"])
    include: list[str] = field(default_factory=list)
    cflags: str = ""
    ldflags: str = ""
    linker_script: str | None = None
    runtime: bool = True
    timeout: str = "30s"
    modules: dict[str, ModuleSpec] = field(default_factory=dict)
    tests: dict[str, dict] = field(default_factory=lambda: {t: {} for t in DEFAULT_TESTS})
    ci_provider: str = "github"
    ci_branches: list[str] = field(default_factory=lambda: ["main"])

    def to_dict(self) -> dict:
        build: dict = {"sources": list(self.sources)}
        if self.include:
            build["include"] = list(self.include)
        if self.cflags:
            build["cflags"] = self.cflags
        if self.ldflags:
            build["ldflags"] = self.ldflags
        if self.linker_script:
            build["linker_script"] = self.linker_script
        if not self.runtime:
            build["runtime"] = False
        data: dict = {"version": SCHEMA_VERSION, "board": self.board, "build": build,
                      "timeout": self.timeout}
        if self.modules:
            data["modules"] = {}
            for name, m in self.modules.items():
                entry: dict = {"model": m.model, "bus": m.bus}
                if m.address is not None:
                    entry["address"] = Hex(m.address)
                data["modules"][name] = entry
        data["tests"] = {t: dict(opts) for t, opts in self.tests.items()}
        data["ci"] = {"provider": self.ci_provider, "branches": list(self.ci_branches)}
        return data

    def dumps(self) -> str:
        header = ("# VirtuLab CI configuration. Edit by hand or with `virtulab ui`.\n"
                  "# Docs: https://github.com/yann-zurstrassen/virtulab-ci\n")
        return header + yamlite.dumps(self.to_dict()) + "\n"


def _unknown(where: str, keys, allowed) -> None:
    for key in keys:
        if key not in allowed:
            hint = difflib.get_close_matches(str(key), allowed, n=1)
            suffix = f" Did you mean '{hint[0]}'?" if hint else f" Allowed: {', '.join(allowed)}."
            raise VirtulabError(f"virtulab.yml: unknown key '{key}' in {where}.{suffix}")


def _str_list(where: str, value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p for p in re.split(r"[\s,]+", value) if p]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    raise VirtulabError(f"virtulab.yml: '{where}' must be a list of strings")


def _expect(where: str, value, kind):
    if value is not None and not isinstance(value, kind):
        raise VirtulabError(f"virtulab.yml: '{where}' must be a {kind.__name__}")
    return value


def from_dict(data: dict) -> ProjectConfig:
    if not isinstance(data, dict):
        raise VirtulabError("virtulab.yml must contain a mapping at the top level")
    _unknown("the top level", data, _TOP_KEYS)
    version = data.get("version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise VirtulabError(f"virtulab.yml: unsupported version {version} (this is VirtuLab "
                            f"schema version {SCHEMA_VERSION})")
    cfg = ProjectConfig()

    if "board" in data:
        cfg.board = str(data["board"])
    if cfg.board not in BOARDS:
        hint = difflib.get_close_matches(cfg.board, BOARDS, n=1)
        suffix = f" Did you mean '{hint[0]}'?" if hint else ""
        raise VirtulabError(f"virtulab.yml: unknown board '{cfg.board}'.{suffix} "
                            f"Run `virtulab catalog` to list boards.")

    build = _expect("build", data.get("build"), dict) or {}
    _unknown("build", build, _BUILD_KEYS)
    if "sources" in build:
        cfg.sources = _str_list("build.sources", build["sources"])
    cfg.include = _str_list("build.include", build.get("include"))
    cfg.cflags = str(build.get("cflags") or "")
    cfg.ldflags = str(build.get("ldflags") or "")
    cfg.linker_script = build.get("linker_script") or None
    cfg.runtime = bool(build.get("runtime", True))
    if "timeout" in data:
        cfg.timeout = str(data["timeout"])

    modules = _expect("modules", data.get("modules"), dict) or {}
    for name, spec in modules.items():
        if not _NAME.fullmatch(str(name)):
            raise VirtulabError(f"virtulab.yml: module name '{name}' must be lowercase letters, "
                                "digits and underscores, starting with a letter")
        spec = spec or {}
        if not isinstance(spec, dict):
            raise VirtulabError(f"virtulab.yml: module '{name}' must be a mapping")
        _unknown(f"module '{name}'", spec, _MODULE_KEYS)
        for required in ("model", "bus"):
            if required not in spec:
                raise VirtulabError(f"virtulab.yml: module '{name}' needs '{required}'")
        address = spec.get("address")
        if address is not None and not isinstance(address, int):
            raise VirtulabError(f"virtulab.yml: module '{name}' address must be a number, e.g. 0x48")
        cfg.modules[str(name)] = ModuleSpec(str(name), str(spec["model"]), str(spec["bus"]), address)

    tests = data.get("tests")
    if tests is None:
        cfg.tests = {t: {} for t in DEFAULT_TESTS}
    else:
        cfg.tests = {}
        entries = tests if isinstance(tests, list) else [{k: v} for k, v in tests.items()]
        for entry in entries:
            if isinstance(entry, str):
                entry = {entry: {}}
            if not isinstance(entry, dict):
                raise VirtulabError("virtulab.yml: 'tests' must be a mapping or a list of names")
            for tid, opts in entry.items():
                if tid not in TESTS:
                    hint = difflib.get_close_matches(str(tid), TESTS, n=1)
                    suffix = f" Did you mean '{hint[0]}'?" if hint else ""
                    raise VirtulabError(f"virtulab.yml: unknown test '{tid}'.{suffix} "
                                        f"Available: {', '.join(TESTS)}")
                opts = {} if opts in (None, True) else opts
                if opts is False:
                    continue
                if not isinstance(opts, dict):
                    raise VirtulabError(f"virtulab.yml: options of test '{tid}' must be a mapping")
                _unknown(f"tests.{tid}", opts, [o.name for o in get_test(tid).options])
                cfg.tests[str(tid)] = dict(opts)

    ci = _expect("ci", data.get("ci"), dict) or {}
    _unknown("ci", ci, _CI_KEYS)
    cfg.ci_provider = str(ci.get("provider", "github"))
    if cfg.ci_provider not in _PROVIDERS:
        raise VirtulabError(f"virtulab.yml: ci.provider must be one of {', '.join(_PROVIDERS)}")
    cfg.ci_branches = _str_list("ci.branches", ci.get("branches")) or ["main"]
    return cfg


def find(root: Path) -> Path | None:
    for name in CONFIG_NAMES:
        if (root / name).is_file():
            return root / name
    return None


def load(root: Path) -> ProjectConfig | None:
    path = find(root)
    if path is None:
        return None
    return from_dict(yamlite.load(path))


def option(cfg: ProjectConfig, test: str, name: str):
    """A test option: the project's value, or the catalog default."""
    opts = cfg.tests.get(test, {})
    if name in opts:
        return opts[name]
    for o in get_test(test).options:
        if o.name == name:
            return o.default
    raise KeyError(name)


def renode_repl(cfg: ProjectConfig) -> str | None:
    """The generated Renode lines for the declared modules. Users never write these."""
    lines = []
    for m in cfg.modules.values():
        module = get_module(m.model)
        address = m.address if m.address is not None else module.default_address
        target = f"{m.bus} {address:#04x}" if address is not None else m.bus
        lines.append(f"{m.name}: {module.renode_type} @ {target}")
    return "\n".join(lines) + "\n" if lines else None


__all__ = ["ProjectConfig", "ModuleSpec", "from_dict", "load", "find", "option",
           "renode_repl", "MODULES", "PROTOCOLS"]
