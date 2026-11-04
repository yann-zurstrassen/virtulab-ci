"""The faults any peripheral can have, and how to inject them into a scenario.

One vocabulary for every input the firmware reads: catalog sensors, sensors described by a register
list, and the chip's ADC. Input faults (stuck, saturated, noisy) are applied through the scenario's
own input timeline, so they need nothing from the model. Wire faults (silent, garbled) switch a
property of the model, the same two names on every VirtuLab I2C model.

The fault sweep (scenarios.run_faults) takes each scenario the user wrote, injects every fault into
every peripheral at the moments the scenario's inputs change, and judges with the scenario's own
`forbid`: a faulty peripheral must never make the firmware report what it must never report.
"""

from dataclasses import dataclass

from .catalog import get_module
from .config import ProjectConfig
from .peripherals import Stimulus

WINDOW_MS = 600.0       # how long each fault lasts: long enough for a slow sensor to be read in it
NOISE_STEP_MS = 10.0
NOISE_SHARE = 0.02      # noisy: +-2 % of the input's range

FAULTS = {
    "stuck": "keeps returning the value it had when the fault began",
    "saturated": "pinned at the top of the range its data format can report",
    "noisy": "jumps +-2 % of its range around the true value, every 10 ms",
    "silent": "stops answering (SPI and UART sensors; not yet on I2C, where the emulator cannot refuse an address)",
    "garbled": "answers with corrupted bytes, or a wrong checksum on sensors that send one",
}

# What each input's data format can represent, read from the model's encoding (virtulab/devices).
RANGES = {
    "mpu6050": {**{f"Acceleration{a}": (-16.0, 16.0) for a in "XYZ"},       # 16-bit, 2048 counts per g at +-16 g
                **{f"AngularRate{a}": (-2000.0, 2000.0) for a in "XYZ"}},   # 16.4 counts per degree/s at +-2000
    "sht31": {"Temperature": (-45.0, 130.0), "Humidity": (0.0, 100.0)},    # -45 + 175 * raw / 65535
    "tmp108": {"Temperature": (-128.0, 127.9375)},                          # 12 bits, 0.0625 degree steps
    "ina219": {"BusVoltage": (0.0, 32.764)},                                # 13 bits, 4 mV steps
}

# How each catalog model exposes the two wire faults: (property, value when faulty, value when not).
# A silent I2C sensor does not acknowledge its address, so the driver sees an error. Renode's I2C
# models cannot refuse an address: their Silent switch answers 0xFF instead, which firmware reads as a
# plausible value. That would report the emulator's limit as a firmware bug, so I2C models are not
# made silent in the sweep until the emulator can refuse an address.
WIRE = {
    "mpu6050": {"garbled": ("Garbled", 1, 0)},
    "sht31": {"garbled": ("Garbled", 1, 0)},
    "tmp108": {"garbled": ("Garbled", 1, 0)},
    "ina219": {"garbled": ("Garbled", 1, 0)},
    "adxl345": {"silent": ("Responding", 0, 1)},
    "max31855": {"silent": ("Responding", 0, 1)},
    "w25q128": {"silent": ("Responding", 0, 1)},
    "at_modem": {"silent": ("Silent", 1, 0)},
    "modbus_rtu": {"silent": ("Silent", 1, 0), "garbled": ("CorruptCrc", 1, 0)},
    "nmea_gps": {"silent": ("Silent", 1, 0), "garbled": ("CorruptChecksum", 1, 0)},
}


@dataclass(frozen=True)
class Fault:
    module: str
    kind: str
    input: str | None = None   # for input faults: the input that misbehaves

    @property
    def label(self) -> str:
        return f"{self.module}.{self.input} {self.kind}" if self.input else f"{self.module} {self.kind}"

    @property
    def key(self) -> str:
        return f"{self.module}.{self.input or '*'}.{self.kind}"


def parse(key: str) -> Fault:
    """'imu.*.silent' or 'imu.AccelerationZ.stuck' -> Fault"""
    module, _, rest = key.partition(".")
    name, _, kind = rest.rpartition(".")
    if kind not in FAULTS or not module:
        raise ValueError(key)
    return Fault(module, kind, None if name in ("", "*") else name)


def input_range(cfg: ProjectConfig, module: str, name: str) -> tuple[float, float] | None:
    if module in cfg.modules:
        return RANGES.get(cfg.modules[module].model, {}).get(name)
    if module in cfg.peripherals:
        reg = next((r for r in cfg.peripherals[module].registers if r.name == name), None)
        return (0.0, float(256 ** reg.size - 1)) if reg else None
    if module in cfg.analog:
        return (0.0, float(cfg.analog[module].vref))
    return None


def wire(cfg: ProjectConfig, module: str, kind: str) -> tuple[str, int, int] | None:
    if module in cfg.peripherals:   # I2C: garbled only, see WIRE
        return {"garbled": ("Garbled", 1, 0)}.get(kind)
    if module in cfg.modules:
        return WIRE.get(cfg.modules[module].model, {}).get(kind)
    return None   # the ADC is inside the chip: it has no wire to fail


def faults_for(cfg: ProjectConfig, steps: list[Stimulus]) -> list[Fault]:
    """Every fault worth injecting into a scenario: input faults on the inputs it drives, and wire
    faults on every peripheral that has a wire."""
    found = []
    switches = set().union(*SAME_AS.values()) | {"ConversionTime", "BusyPolls"}   # model settings, not measurements
    for module, name in sorted({(s.module, s.prop) for s in steps if s.prop not in switches}):
        found.append(Fault(module, "stuck", name))
        if input_range(cfg, module, name):
            found += [Fault(module, "saturated", name), Fault(module, "noisy", name)]
    for module in sorted({*cfg.modules, *cfg.peripherals}):
        for kind in ("silent", "garbled"):
            # the scenario already drives this fault itself: injecting it again would undo its own script
            already = {s.prop for s in steps if s.module == module} & SAME_AS.get(kind, set())
            if wire(cfg, module, kind) and not already:
                found.append(Fault(module, kind))
    return found


# Model switches that are the same fault under another name.
SAME_AS = {"garbled": {"Garbled", "CorruptCrc", "CorruptChecksum"}, "silent": {"Silent", "Responding"}}


def moments(steps: list[Stimulus], declared: list[float], limit: int = 4) -> list[float]:
    """When to strike: where the scenario's inputs change, and its declared glitch moments.
    Changes closer than 100 ms count as one moment; at most `limit`, spread over the scenario."""
    times = sorted({s.at_ms for s in steps if s.at_ms > 0} | {t for t in declared if t > 0})
    merged = []
    for t in times:
        if not merged or t - merged[-1] >= 100:
            merged.append(t)
    if not merged:
        return [500.0]
    if len(merged) <= limit:
        return merged
    return [merged[round(i * (len(merged) - 1) / (limit - 1))] for i in range(limit)]


def _value_at(steps: list[Stimulus], module: str, name: str, t: float) -> float | None:
    value = None
    for s in sorted(steps, key=lambda s: s.at_ms):
        if s.module == module and s.prop == name and s.at_ms <= t:
            value = s.value
    return value


def inject(cfg: ProjectConfig, steps: list[Stimulus], fault: Fault, at: float,
           window: float = WINDOW_MS) -> list[Stimulus]:
    """The scenario's input timeline with `fault` from `at` to `at + window`."""
    end = at + window
    if fault.input is None:
        prop, on, off = wire(cfg, fault.module, fault.kind)
        restore = _value_at(steps, fault.module, prop, end)   # the scenario's own state, if it sets one
        return sorted([*steps, Stimulus(at, fault.module, prop, float(on)),
                       Stimulus(end, fault.module, prop, float(off if restore is None else restore))],
                      key=lambda s: s.at_ms)
    others = [s for s in steps if not (s.module == fault.module and s.prop == fault.input and at <= s.at_ms < end)]
    before = _value_at(steps, fault.module, fault.input, at - 0.001)
    after = _value_at(steps, fault.module, fault.input, end)
    added = []
    if fault.kind == "stuck":
        if before is not None:
            added.append(Stimulus(at, fault.module, fault.input, before))
    else:
        lo, hi = input_range(cfg, fault.module, fault.input)
        if fault.kind == "saturated":
            added.append(Stimulus(at, fault.module, fault.input, hi))
        else:   # noisy
            amp, t, sign = (hi - lo) * NOISE_SHARE, at, 1
            while t < end:
                base = _value_at(steps, fault.module, fault.input, t)
                base = 0.0 if base is None else base
                added.append(Stimulus(t, fault.module, fault.input, max(lo, min(hi, base + sign * amp))))
                t, sign = t + NOISE_STEP_MS, -sign
    if after is not None:
        added.append(Stimulus(end, fault.module, fault.input, after))
    return sorted([*others, *added], key=lambda s: s.at_ms)
