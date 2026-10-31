"""Create sample firmware that matches a configuration, so a new project passes on its first run."""

from pathlib import Path

from . import VirtulabError, catalog
from .catalog import board_buses
from .config import ProjectConfig, parse_pin, sim_path

TEMPLATES = Path(__file__).resolve().parent / "templates" / "starter"

# Starter features that are not sensors: (suite function, needs hardware).
_SUITES = {"core": ("test_crc_run", False), "parser": ("test_parser_run", False),
           "auth": ("test_auth_run", False), "nmea": ("test_nmea_run", False),
           "modbus": ("test_modbus_run", False)}
_NO_SUITE = {"stm32f4", "i2c", "spi", "uart", "clock"}  # shared driver code, no tests of its own
_DRIVER_FILES = {"i2c": ["src/i2c.c"], "spi": ["src/spi.c"], "uart": ["src/uart.c"],
                 "clock": ["src/clock.c"]}

# The buses the sample drivers are written for, per protocol.
_SAMPLE_BUSES = {"i2c": ("i2c1",), "spi": ("spi1",), "uart": ("usart1", "usart3", "uart4")}

STARTER_CFLAGS = "-std=c99 -Wall -Wextra"


def _sensors(cfg: ProjectConfig) -> list[catalog.Module]:
    """The catalog entries of the declared sensors that have starter firmware, in catalog order."""
    used = {m.model for m in cfg.modules.values()}
    return [m for m in catalog.MODULES.values() if m.id in used and m.sample]


def _features(cfg: ProjectConfig) -> list[str]:
    features = ["core"]
    if "fuzz" in cfg.tests:
        features.append("parser")
    if "fault" in cfg.tests:
        features.append("auth")
    sensors = _sensors(cfg)
    if sensors:
        features.append("stm32f4")
        features += [proto for proto in _SAMPLE_BUSES if any(s.protocol == proto for s in sensors)]
        for sensor in sensors:
            features += [f for f in sensor.sample.extras if f not in features]
            features.append(sensor.id)
    return features


def _suite(feature: str) -> tuple[str, bool] | None:
    if feature in _SUITES:
        return _SUITES[feature]
    module = catalog.MODULES.get(feature)
    return (module.sample.suite, True) if module and module.sample else None


def _test_files(features: list[str]) -> tuple[str, str]:
    suites = [s for s in map(_suite, features) if s]
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
        hardware_files = {**{k: v for k, v in _DRIVER_FILES.items()},
                          **{m.id: list(m.sample.hardware) for m in _sensors(cfg)}}
        hardware = [f for name in features for f in hardware_files.get(name, [])]
        if hardware:
            cfg.tests["coverage"]["exclude"] = hardware
    if "fuzz" in cfg.tests:
        cfg.tests["fuzz"].update({"harness": "fuzz/fuzz.c", "sources": ["src/parser.c", "src/crc.c"],
                                  "include": ["include"]})
    if "fault" in cfg.tests:
        cfg.tests["fault"].update({"probe": ["fault/probe.c", "fault/probe_count.c", "fault/probe_locked.c"], "sources": ["src/auth.c"],
                                   "target": "src/auth.c", "include": ["include"]})


def scaffold(cfg: ProjectConfig, root: Path, force: bool = False) -> list[str]:
    """Write the sample firmware and align `cfg` (sources, flags, test options) with it."""
    for m in cfg.modules.values():
        catalog.get_module(m.model)  # an unknown model is a clear error, before anything is written
    features = _features(cfg)
    for m in cfg.modules.values():
        module = catalog.MODULES[m.model]
        allowed = _SAMPLE_BUSES.get(module.protocol, ())
        if module.sample and m.bus not in allowed:
            raise VirtulabError(f"The sample {module.title} driver is written for {' or '.join(allowed)}. "
                                f"Attach the sensor to {allowed[0]}, or start without sample firmware and "
                                "bring your own driver.")

    models = [m.model for m in cfg.modules.values() if catalog.MODULES[m.model].sample]
    for model in set(models):
        if models.count(model) > 1:
            raise VirtulabError(f"The sample firmware supports one {catalog.MODULES[model].title}. "
                                "Declare one, or start without sample firmware.")

    files: dict[str, str] = {}
    for feature in features:
        module = next((m for m in cfg.modules.values() if m.model == feature), None)
        subst = {}
        if module:
            default = catalog.MODULES[module.model].default_address
            address = module.address if module.address is not None else default
            cs_port, cs_pin = parse_pin(module.cs or catalog.MODULES[module.model].default_cs or "PA4")
            subst = {"@BUS@": module.bus, "@MODULE@": module.name, "@SIM@": sim_path(cfg, module.name),
                     "@ADDR@": f"0x{address:02X}" if address is not None else "0",
                     "@CS_BASE@": f"0x{0x40020000 + 0x400 * (ord(cs_port) - ord('A')):08X}u",
                     "@CS_PIN@": str(cs_pin), "@UART@": f"uart_{module.bus}"}
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
