"""Peripherals a project defines in virtulab.yml, and sensor input on a timeline.

A team's own I²C device is described as a register list and becomes a Renode model, so no
one has to write C#. `stimulus` entries and CSV traces set any readable input of a module
at an exact time on the emulator's virtual clock, so a run gives the same answer every time.
These models say what the project wrote down. Nothing here is checked against a datasheet.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import VirtulabError

_REGISTER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TIME = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(ms|s)?\s*")
_REGISTER_KEYS = ("name", "at", "size", "reset", "access")
PERIPHERAL_KEYS = ("bus", "address", "endian", "registers")


@dataclass
class Register:
    name: str
    at: int
    size: int = 1
    reset: int = 0
    writable: bool = True


@dataclass
class Peripheral:
    name: str
    bus: str
    address: int
    little_endian: bool = False
    registers: list[Register] = field(default_factory=list)

    @property
    def class_name(self) -> str:
        return f"Custom_{self.name}"


@dataclass
class AnalogBlock:
    """An on-chip ADC: named inputs on channels, each holding a voltage until it is changed."""
    name: str
    base: int
    vref: float
    inputs: dict[str, int] = field(default_factory=dict)

    @property
    def class_name(self) -> str:
        return f"Analog_{self.name}"


@dataclass
class Stimulus:
    at_ms: float
    module: str
    prop: str
    value: float


def parse_time_ms(value) -> float:
    m = _TIME.fullmatch(str(value))
    if not m:
        raise VirtulabError(f"virtulab.yml: invalid time '{value}' (use e.g. 250ms or 2s)")
    return float(m[1]) * (1000 if m[2] == "s" else 1)


def parse_register(where: str, spec: dict) -> Register:
    if not isinstance(spec, dict):
        raise VirtulabError(f"virtulab.yml: {where}: each register must be a mapping")
    unknown = [k for k in spec if k not in _REGISTER_KEYS]
    if unknown:
        raise VirtulabError(f"virtulab.yml: {where}: unknown key '{unknown[0]}'. Allowed: {', '.join(_REGISTER_KEYS)}")
    name, at = spec.get("name"), spec.get("at")
    if not isinstance(name, str) or not _REGISTER.fullmatch(name):
        raise VirtulabError(f"virtulab.yml: {where}: register name '{name}' must be letters, digits and underscores")
    if not isinstance(at, int) or not 0 <= at <= 0xFF:
        raise VirtulabError(f"virtulab.yml: {where}: register {name} needs `at`, 0 to 0xFF")
    size, reset = spec.get("size", 1), spec.get("reset", 0)
    if size not in (1, 2, 4):
        raise VirtulabError(f"virtulab.yml: {where}: register {name} size must be 1, 2 or 4 bytes")
    if not isinstance(reset, int) or not 0 <= reset < 1 << (8 * size):
        raise VirtulabError(f"virtulab.yml: {where}: register {name} reset does not fit in {size} byte(s)")
    access = spec.get("access", "rw")
    if access not in ("rw", "ro"):
        raise VirtulabError(f"virtulab.yml: {where}: register {name} access must be rw or ro")
    return Register(name, at, size, reset, access == "rw")


def parse_peripheral(name: str, spec: dict) -> Peripheral:
    where = f"peripheral '{name}'"
    unknown = [k for k in spec if k not in PERIPHERAL_KEYS]
    if unknown:
        raise VirtulabError(f"virtulab.yml: {where}: unknown key '{unknown[0]}'. Allowed: {', '.join(PERIPHERAL_KEYS)}")
    for required in ("bus", "address", "registers"):
        if required not in spec:
            raise VirtulabError(f"virtulab.yml: {where} needs '{required}'")
    if not isinstance(spec["address"], int):
        raise VirtulabError(f"virtulab.yml: {where}: address must be a number, e.g. 0x55")
    endian = spec.get("endian", "big")
    if endian not in ("big", "little"):
        raise VirtulabError(f"virtulab.yml: {where}: endian must be big or little")
    registers = [parse_register(where, r) for r in spec["registers"] or []]
    if not registers:
        raise VirtulabError(f"virtulab.yml: {where} has no registers")
    names, used = set(), {}
    for r in registers:
        if r.name in names:
            raise VirtulabError(f"virtulab.yml: {where}: register {r.name} is defined twice")
        names.add(r.name)
        if r.at + r.size > 0x100:
            raise VirtulabError(f"virtulab.yml: {where}: register {r.name} runs past 0xFF")
        for byte in range(r.at, r.at + r.size):
            if byte in used:
                raise VirtulabError(f"virtulab.yml: {where}: registers {used[byte]} and {r.name} overlap at {byte:#04x}")
            used[byte] = r.name
    return Peripheral(name, str(spec["bus"]), spec["address"], endian == "little", registers)


# ADC1 to ADC3 base addresses, from ST's STM32F40x SVD file.
STM32F4_ADC = {"adc1": 0x40012000, "adc2": 0x40012100, "adc3": 0x40012200}


def parse_analog(name: str, spec: dict) -> AnalogBlock:
    where = f"analog '{name}'"
    if name not in STM32F4_ADC:
        raise VirtulabError(f"virtulab.yml: {where}: use one of {', '.join(STM32F4_ADC)}")
    unknown = [k for k in spec if k not in ("vref", "inputs")]
    if unknown:
        raise VirtulabError(f"virtulab.yml: {where}: unknown key '{unknown[0]}'. Allowed: vref, inputs")
    vref = spec.get("vref", 3.3)
    if isinstance(vref, bool) or not isinstance(vref, (int, float)) or vref <= 0:
        raise VirtulabError(f"virtulab.yml: {where}: vref must be a positive voltage")
    inputs = spec.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        raise VirtulabError(f"virtulab.yml: {where} needs inputs, e.g. {{ thermistor: 1 }}")
    for input_name, channel in inputs.items():
        if not _REGISTER.fullmatch(str(input_name)):
            raise VirtulabError(f"virtulab.yml: {where}: bad input name '{input_name}'")
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 18:
            raise VirtulabError(f"virtulab.yml: {where}: channel of {input_name} must be 0 to 18")
    if len(set(inputs.values())) != len(inputs):
        raise VirtulabError(f"virtulab.yml: {where}: two inputs share a channel")
    return AnalogBlock(name, STM32F4_ADC[name], float(vref), {str(k): v for k, v in inputs.items()})


def parse_stimulus(entries: list) -> list[Stimulus]:
    found = []
    for entry in entries or []:
        if not isinstance(entry, dict) or set(entry) != {"at", "set", "value"}:
            raise VirtulabError("virtulab.yml: each stimulus needs exactly `at`, `set` and `value`")
        found.append(_stimulus(entry["at"], entry["set"], entry["value"]))
    return found


def _stimulus(at, target, value) -> Stimulus:
    module, dot, prop = str(target).partition(".")
    if not dot or not prop:
        raise VirtulabError(f"virtulab.yml: stimulus target '{target}' must be module.Input, e.g. tank.LEVEL")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VirtulabError(f"virtulab.yml: stimulus value for {target} must be a number")
    return Stimulus(parse_time_ms(at), module, prop, float(value))


def read_trace(path: Path) -> list[Stimulus]:
    """A recorded trace: a `time_ms` column, then one column per input, named module.Input."""
    if not path.is_file():
        raise VirtulabError(f"virtulab.yml: stimulus_file '{path.name}' not found")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "time_ms" not in rows[0]:
        raise VirtulabError(f"{path.name}: needs a header with a time_ms column and at least one row")
    found = []
    for number, row in enumerate(rows, 2):
        for column, text in row.items():
            if column == "time_ms" or text in (None, ""):
                continue
            try:
                found.append(_stimulus(f"{row['time_ms']}ms", column, float(text)))
            except ValueError:
                raise VirtulabError(f"{path.name}, line {number}: '{text}' is not a number") from None
    return found


_I2C_TEMPLATE = """\
// Generated by VirtuLab from virtulab.yml. Edit the file, not this model.
using System;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.I2C;

namespace Antmicro.Renode.Peripherals.VirtuLab
{{
    public class {cls} : II2CPeripheral
    {{
        public {cls}()
        {{
            Reset();
        }}

{properties}
        public void Write(byte[] data)
        {{
            if(data.Length == 0)
            {{
                return;
            }}
            pointer = data[0];
            for(var i = 1; i < data.Length; i++)
            {{
                if(writable[pointer])
                {{
                    memory[pointer] = data[i];
                }}
                else
                {{
                    this.Log(LogLevel.Warning, "Write to read-only register byte {{0:X2}} ignored", pointer);
                }}
                pointer = (byte)(pointer + 1);
            }}
        }}

        public byte[] Read(int count = 1)
        {{
            var result = new byte[count];
            for(var i = 0; i < count; i++)
            {{
                result[i] = memory[pointer];
                pointer = (byte)(pointer + 1);
            }}
            return result;
        }}

        public void FinishTransmission()
        {{
        }}

        public void Reset()
        {{
            pointer = 0;
            Array.Clear(memory, 0, memory.Length);
            Array.Clear(writable, 0, writable.Length);
{resets}
        }}

        private decimal Get(int at, int size)
        {{
            ulong value = 0;
            for(var i = 0; i < size; i++)
            {{
                var index = {little} ? at + i : at + size - 1 - i;
                value |= (ulong)memory[index] << (8 * i);
            }}
            return value;
        }}

        private void Set(int at, int size, decimal value)
        {{
            var maximum = (decimal)((1UL << (8 * size)) - 1);
            if(value < 0 || value > maximum)
            {{
                this.Log(LogLevel.Warning, "{{0}} does not fit in {{1}} byte(s), clamped", value, size);
            }}
            var raw = (ulong)Math.Max(0, Math.Min(maximum, Math.Round(value, MidpointRounding.AwayFromZero)));
            for(var i = 0; i < size; i++)
            {{
                var index = {little} ? at + i : at + size - 1 - i;
                memory[index] = (byte)(raw >> (8 * i));
            }}
        }}

        private byte pointer;
        private readonly byte[] memory = new byte[256];
        private readonly bool[] writable = new bool[256];
    }}
}}
"""

_ADC_TEMPLATE = """\
// Generated by VirtuLab from virtulab.yml. A polled, single-channel STM32F4 ADC.
// Register offsets and bits come from ST's STM32F40x SVD file. Each input holds a voltage until
// it changes, like a bench source. Not modelled: conversion time, sampling, noise, resolution
// other than 12 bits, scan mode, injected channels, DMA and interrupts.
using System;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;

namespace Antmicro.Renode.Peripherals.VirtuLab
{{
    public class {cls} : IDoubleWordPeripheral, IKnownSize
    {{
{properties}
        public long Size => 0x100;

        public uint ReadDoubleWord(long offset)
        {{
            switch(offset)
            {{
            case StatusRegister:
                return status;
            case Control2Register:
                return control2;
            case Sequence3Register:
                return sequence3;
            case DataRegister:
                status &= ~EndOfConversion;
                return data;
            default:
                return 0;
            }}
        }}

        public void WriteDoubleWord(long offset, uint value)
        {{
            switch(offset)
            {{
            case StatusRegister:
                status &= value;
                break;
            case Control2Register:
                control2 = value & ~StartConversion;
                if((value & StartConversion) != 0 && (value & On) != 0)
                {{
                    Convert();
                }}
                break;
            case Sequence3Register:
                sequence3 = value;
                break;
            default:
                break;
            }}
        }}

        public void Reset()
        {{
            status = 0;
            control2 = 0;
            sequence3 = 0;
            data = 0;
        }}

        private void Convert()
        {{
            var volts = channels[sequence3 & 0x1F];
            var counts = Math.Round(volts / Vref * 4095m, MidpointRounding.AwayFromZero);
            data = (uint)Math.Max(0m, Math.Min(4095m, counts));
            status |= EndOfConversion;
        }}

        private uint status;
        private uint control2;
        private uint sequence3;
        private uint data;
        private readonly decimal[] channels = new decimal[32];

        private const decimal Vref = {vref}m;
        private const long StatusRegister = 0x00;
        private const long Control2Register = 0x08;
        private const long Sequence3Register = 0x34;
        private const long DataRegister = 0x4C;
        private const uint EndOfConversion = 1u << 1;
        private const uint On = 1u << 0;
        private const uint StartConversion = 1u << 30;
    }}
}}
"""

_STIMULUS_TEMPLATE = """\
// Generated by VirtuLab from virtulab.yml. Applies sensor input on the emulator's virtual clock.
using System;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals;
using Antmicro.Renode.Peripherals.Timers;
using Antmicro.Renode.Time;

namespace Antmicro.Renode.Peripherals.VirtuLab
{{
    public class Stimulus : IPeripheral
    {{
        public Stimulus(IMachine machine)
        {{
            this.machine = machine;
            timer = new LimitTimer(machine.ClockSource, 1000, this, "stimulus", 1, Direction.Descending, true, WorkMode.Periodic, true);
            timer.LimitReached += Tick;
        }}

        public void Reset()
        {{
        }}

        private void Tick()
        {{
            elapsed += 1;
            while(next < Steps.Length && Steps[next].Item1 <= elapsed)
            {{
                Apply(Steps[next].Item2, Steps[next].Item3, Steps[next].Item4);
                next++;
            }}
            if(next == Steps.Length)
            {{
                timer.Enabled = false;
            }}
        }}

        private void Apply(string path, string input, decimal value)
        {{
            IPeripheral target;
            if(!machine.TryGetByName(path, out target))
            {{
                this.Log(LogLevel.Error, "Stimulus: no peripheral {{0}}", path);
                return;
            }}
            var property = target.GetType().GetProperty(input);
            if(property == null)
            {{
                this.Log(LogLevel.Error, "Stimulus: {{0}} has no input {{1}}", path, input);
                return;
            }}
            property.SetValue(target, Convert.ChangeType(value, property.PropertyType));
        }}

        private static readonly Tuple<double, string, string, decimal>[] Steps =
        {{
{steps}
        }};
        private readonly IMachine machine;
        private readonly LimitTimer timer;
        private double elapsed;
        private int next;
    }}
}}
"""


def model_source(p: Peripheral) -> str:
    properties, resets = [], []
    for r in p.registers:
        properties.append(f"        public decimal {r.name} {{ get => Get({r.at}, {r.size}); "
                          f"set => Set({r.at}, {r.size}, value); }}\n")
        resets.append(f"            Set({r.at}, {r.size}, {r.reset}m);")
        if r.writable:
            resets += [f"            writable[{b}] = true;" for b in range(r.at, r.at + r.size)]
    return _I2C_TEMPLATE.format(cls=p.class_name, properties="".join(properties), resets="\n".join(resets),
                                little="true" if p.little_endian else "false")


def analog_source(a: AnalogBlock) -> str:
    properties = "".join(f"        public decimal {name} {{ get => channels[{channel}]; set => channels[{channel}] = value; }}\n"
                         for name, channel in a.inputs.items())
    return _ADC_TEMPLATE.format(cls=a.class_name, properties=properties, vref=repr(a.vref))


def stimulus_source(steps: list[tuple[float, str, str, float]]) -> str:
    lines = [f'            Tuple.Create({at!r}d, "{path}", "{prop}", {value!r}m),' for at, path, prop, value in steps]
    return _STIMULUS_TEMPLATE.format(steps="\n".join(lines))
