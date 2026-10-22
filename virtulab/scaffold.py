"""Create sample firmware that matches a configuration, so a new project passes on its first run."""

from pathlib import Path

from . import VirtulabError, catalog
from .catalog import board_buses
from .config import ProjectConfig

TEMPLATES = Path(__file__).resolve().parent / "templates" / "starter"

# (feature directory, suite function, needs hardware)
_SUITES = {"core": ("test_crc_run", False), "parser": ("test_parser_run", False),
           "auth": ("test_auth_run", False), "tmp108": ("test_thermostat_run", True),
           "bmp180": ("test_bmp180_run", True)}
_NO_SUITE = {"i2c"}  # shared driver code, no tests of its own
_I2C_PARTS = ("tmp108", "bmp180")

STARTER_CFLAGS = "-std=c99 -Wall -Wextra"


def _features(cfg: ProjectConfig) -> list[str]:
    features = ["core"]
    if "fuzz" in cfg.tests:
        features.append("parser")
    if "fault" in cfg.tests:
        features.append("auth")
    parts = [p for p in _I2C_PARTS if any(m.model == p for m in cfg.modules.values())]
    if parts:
        features.append("i2c")
        features += parts
    return features


def _test_files(features: list[str]) -> tuple[str, str]:
    suites = [_SUITES[f] for f in features if f not in _NO_SUITE]
    header = ["#ifndef TEST_SUITES_H", "#define TEST_SUITES_H", "",
              "/* Each suite returns its number of failures; test_main.c adds them up. */"]
    header += [f"int {name}(void);" for name, _ in suites] + ["", "#endif /* TEST_SUITES_H */", ""]
    body = ['#include "test_suites.h"', "", "int main(void)", "{", "    int failures = 0;", ""]
    for name, hardware in suites:
        if hardware:
            body += ["#ifndef VIRTULAB_HOST /* needs the emulated sensor, not available natively */",
                     f"    failures += {name}();", "#endif"]
        else:
            body.append(f"    failures += {name}();")
    body += ["    return (failures == 0) ? 0 : 1;", "}", ""]
    return "\n".join(header), "\n".join(body)


def apply_defaults(cfg: ProjectConfig) -> None:
    """Point sources, flags and test options at the sample firmware (no files written)."""
    features = _features(cfg)
    cfg.sources = ["src/*.c", "test/*.c"]
    cfg.include = ["include", "test"]
    cfg.cflags = STARTER_CFLAGS
    if "coverage" in cfg.tests:
        cfg.tests["coverage"].setdefault("sources", ["src/*.c"])
        # Code that talks to the emulated sensors cannot run natively; its tests and drivers stay out.
        hardware_files = {"i2c": ["src/i2c.c"],
                          "tmp108": ["src/thermostat.c", "src/tmp108.c", "test/test_thermostat.c"],
                          "bmp180": ["src/bmp180.c", "test/test_bmp180.c"]}
        hardware = [f for name in features for f in hardware_files.get(name, [])]
        if hardware:
            cfg.tests["coverage"]["exclude"] = hardware
    if "fuzz" in cfg.tests:
        cfg.tests["fuzz"].update({"harness": "fuzz/fuzz.c", "sources": ["src/parser.c", "src/crc.c"],
                                  "include": ["include"]})
    if "fault" in cfg.tests:
        cfg.tests["fault"].update({"probe": "fault/probe.c", "sources": ["src/auth.c"],
                                   "target": "src/auth.c", "include": ["include"]})


def scaffold(cfg: ProjectConfig, root: Path, force: bool = False) -> list[str]:
    """Write the sample firmware and align `cfg` (sources, flags, test options) with it."""
    features = _features(cfg)
    for m in cfg.modules.values():
        if m.model in _I2C_PARTS and m.bus != "i2c1":
            raise VirtulabError(f"The sample {m.model.upper()} driver is written for i2c1. Attach the "
                                "sensor to i2c1, or start without sample firmware and bring your own driver.")

    files: dict[str, str] = {}
    for feature in features:
        module = next((m for m in cfg.modules.values() if m.model == feature), None)
        subst = {}
        if module:
            default = catalog.MODULES[module.model].default_address
            subst = {"@BUS@": module.bus, "@MODULE@": module.name,
                     "@ADDR@": f"0x{(module.address if module.address is not None else default):02X}"}
        for path in sorted((TEMPLATES / feature).rglob("*")):
            if path.is_file():
                text = path.read_text()
                for key, value in subst.items():
                    text = text.replace(key, value)
                files[path.relative_to(TEMPLATES / feature).as_posix()] = text
    files["test/test_suites.h"], files["test/test_main.c"] = _test_files(features)

    existing = [p for p in files if (root / p).exists()]
    if existing and not force:
        raise VirtulabError(f"Would overwrite {', '.join(existing[:3])}"
                            f"{' …' if len(existing) > 3 else ''}. Use --force, or start without a template.")
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    apply_defaults(cfg)
    return sorted(files)
