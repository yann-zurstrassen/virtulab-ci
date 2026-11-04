"""Compare the twin's bus messages with a recording from real hardware.

Both sides use one plain format, so any capture tool can feed it:

    time_ms,bus,address,write,read
    116,i2c1,0x55,01,03 B6

`write` and `read` are hex bytes separated by spaces. Messages are lined up in order, not by
time, because emulated and real timing differ: time is reported, never compared. A message can
match exactly, or within a tolerance on the values read, for sensors whose readings vary.
"""

import csv
import difflib
from dataclasses import dataclass, field
from pathlib import Path

from . import VirtulabError

HEADER = ["time_ms", "bus", "address", "write", "read"]


@dataclass
class Message:
    time_ms: float
    bus: str
    address: int
    write: tuple[int, ...]
    read: tuple[int, ...]

    @property
    def key(self) -> tuple:
        """What must agree exactly: who was addressed and what was asked. Read data may vary."""
        return (self.bus, self.address, self.write, len(self.read))

    def row(self) -> list[str]:
        b = lambda data: " ".join(f"{x:02X}" for x in data)
        return [f"{self.time_ms:g}", self.bus, f"0x{self.address:02X}", b(self.write), b(self.read)]


def _bytes(text: str, where: str) -> tuple[int, ...]:
    try:
        return tuple(int(t, 16) for t in text.replace(",", " ").split())
    except ValueError:
        raise VirtulabError(f"{where}: '{text}' is not hex bytes, e.g. 03 B6") from None


def read_messages(path: Path) -> list[Message]:
    if not path.is_file():
        raise VirtulabError(f"{path} not found")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or set(HEADER) - set(rows[0]):
        raise VirtulabError(f"{path.name}: needs the columns {', '.join(HEADER)}")
    found = []
    for number, row in enumerate(rows, 2):
        where = f"{path.name}, line {number}"
        try:
            found.append(Message(float(row["time_ms"]), row["bus"].strip(), int(row["address"], 0),
                                 _bytes(row["write"], where), _bytes(row["read"], where)))
        except ValueError:
            raise VirtulabError(f"{where}: time_ms and address must be numbers") from None
    return found


def write_messages(messages: list[Message], path: Path) -> None:
    with path.open("w", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(HEADER)
        out.writerows(m.row() for m in messages)


def from_trace(trace: dict) -> list[Message]:
    return [Message(e["t"], e["bus"], e["address"], tuple(e["write"]), tuple(e["read"]))
            for e in trace["events"] if e["kind"] == "bus"]


@dataclass
class Result:
    matched: int = 0
    within_tolerance: list[tuple] = field(default_factory=list)
    different: list[tuple] = field(default_factory=list)  # (twin, real) read data disagrees
    only_twin: list[Message] = field(default_factory=list)
    only_real: list[Message] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.different or self.only_twin or self.only_real)


def _values(data: tuple[int, ...], frame: tuple[int, int]) -> list[int] | None:
    """Big-endian values in `data`, laid out as repeated groups of value bytes then skipped bytes,
    such as a checksum: (2, 1) is an SHT3x reply. None when the length does not fit the layout."""
    size, skip = frame
    step = size + skip
    if len(data) % step and len(data) % step != size:
        return None
    return [int.from_bytes(bytes(data[i:i + size]), "big") for i in range(0, len(data), step)]


def _reads_agree(a: tuple[int, ...], b: tuple[int, ...], tolerance, frame: tuple[int, int] = (2, 0)) -> bool:
    """Equal, or each value within its tolerance (sensor readings vary). Skipped bytes are not compared.
    `tolerance` is one number, or a list used in turn for the values of a reply, such as [75, 1311]
    for an SHT3x temperature then humidity."""
    if a == b:
        return True
    limits = tolerance if isinstance(tolerance, (list, tuple)) else [tolerance]
    if not any(limits) or len(a) != len(b):
        return False
    va, vb = _values(a, frame), _values(b, frame)
    if va is None or vb is None:
        return False
    return all(abs(x - y) <= limits[i % len(limits)] for i, (x, y) in enumerate(zip(va, vb)))


def compare(twin: list[Message], real: list[Message], tolerance=0,
            frame: tuple[int, int] = (2, 0)) -> Result:
    result = Result()
    matcher = difflib.SequenceMatcher(a=[m.key for m in twin], b=[m.key for m in real], autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for a, b in zip(twin[i1:i2], real[j1:j2]):
                if a.read == b.read:
                    result.matched += 1
                elif _reads_agree(a.read, b.read, tolerance, frame):
                    result.within_tolerance.append((a, b))
                else:
                    result.different.append((a, b))
            continue
        result.only_twin += twin[i1:i2]
        result.only_real += real[j1:j2]
    return result


def report(result: Result, limit: int = 15) -> str:
    total = result.matched + len(result.within_tolerance) + len(result.different)
    lines = [f"{'✅' if result.ok else '❌'} {result.matched} of {total} lined-up messages match exactly, "
             f"{len(result.within_tolerance)} within tolerance, {len(result.different)} read different data. "
             f"{len(result.only_twin)} only in the twin, {len(result.only_real)} only on the hardware."]
    show = lambda m: f"{m.time_ms:g} ms {m.bus} 0x{m.address:02X} write [{' '.join(f'{x:02X}' for x in m.write)}] " \
                     f"read [{' '.join(f'{x:02X}' for x in m.read)}]"
    for a, b in result.different[:limit]:
        lines.append(f"  different: twin {show(a)}\n             real {show(b)}")
    for m in result.only_twin[:limit]:
        lines.append(f"  only twin: {show(m)}")
    for m in result.only_real[:limit]:
        lines.append(f"  only real: {show(m)}")
    lines.append("Time is shown, not compared: emulated and real timing differ.")
    return "\n".join(lines)
