"""A small YAML subset reader/writer, so the engine stays dependency-free.

Supported: block mappings and sequences, flow `[a, b]` / `{k: v}` collections,
quoted and plain scalars (int, hex, float, bool, null), and `#` comments.
Also `|` / `>` block scalars. Not supported: anchors, tags, multiple documents. That is
enough for `virtulab.yml`, and anything outside the subset is a clear error.
"""

import re

from . import VirtulabError


class YamlError(VirtulabError):
    pass


class Hex(int):
    """An int that is written back as 0x.. (addresses stay readable)."""


_INT = re.compile(r"[-+]?\d+")
_HEX = re.compile(r"[-+]?0[xX][0-9a-fA-F]+")
_FLOAT = re.compile(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?")


def _scalar(text: str):
    text = text.strip()
    if text == "" or text in ("~", "null", "Null", "NULL"):
        return None
    if text[0] in "\"'":
        if len(text) < 2 or text[-1] != text[0]:
            raise YamlError(f"Unterminated string: {text}")
        body = text[1:-1]
        if text[0] == '"':
            return body.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
        return body.replace("''", "'")
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    if _HEX.fullmatch(text):
        return int(text, 16)
    if _INT.fullmatch(text):
        return int(text)
    if _FLOAT.fullmatch(text):
        return float(text)
    return text


def _strip_comment(line: str) -> str:
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _split_top(text: str, sep: str) -> list[str]:
    """Split on `sep` outside quotes and nested brackets."""
    parts, depth, quote, start = [], 0, None, 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _find_key_colon(text: str) -> int:
    """Index of the `:` that ends a mapping key, or -1."""
    quote, depth = None, 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0 and (i + 1 == len(text) or text[i + 1] in " \t"):
            return i
    return -1


def _flow(text: str):
    text = text.strip()
    if text.startswith("["):
        if not text.endswith("]"):
            raise YamlError(f"Unterminated list: {text}")
        inner = text[1:-1].strip()
        return [_flow(p) for p in _split_top(inner, ",") if p.strip()] if inner else []
    if text.startswith("{"):
        if not text.endswith("}"):
            raise YamlError(f"Unterminated map: {text}")
        inner = text[1:-1].strip()
        result = {}
        for part in _split_top(inner, ",") if inner else []:
            if not part.strip():
                continue
            idx = _find_key_colon(part)
            if idx < 0:
                raise YamlError(f"Expected 'key: value' in {{...}}: {part.strip()}")
            result[str(_scalar(part[:idx]))] = _flow(part[idx + 1:])
        return result
    return _scalar(text)


class _Parser:
    def __init__(self, text: str):
        self.raw = text.splitlines()
        self.lines: list[tuple[int, str, int]] = []  # (indent, content, line number)
        for number, raw in enumerate(text.splitlines(), 1):
            if "\t" in raw[: len(raw) - len(raw.lstrip())]:
                raise YamlError(f"line {number}: tabs are not allowed for indentation")
            content = _strip_comment(raw).rstrip()
            if content.strip():
                self.lines.append((len(content) - len(content.lstrip()), content.strip(), number))
        self.pos = 0

    def parse(self):
        if not self.lines:
            return {}
        value = self.block(self.lines[0][0])
        if self.pos < len(self.lines):
            raise YamlError(f"line {self.lines[self.pos][2]}: unexpected indentation")
        return value

    def block(self, indent: int):
        content = self.lines[self.pos][1]
        if content == "-" or content.startswith("- "):
            return self.sequence(indent)
        return self.mapping(indent)

    def mapping(self, indent: int) -> dict:
        result: dict = {}
        while self.pos < len(self.lines):
            ind, content, number = self.lines[self.pos]
            if ind < indent:
                break
            if ind > indent:
                raise YamlError(f"line {number}: unexpected indentation")
            if content.startswith("- "):
                break
            idx = _find_key_colon(content)
            if idx < 0:
                raise YamlError(f"line {number}: expected 'key: value', got '{content}'")
            key = str(_scalar(content[:idx]))
            if key in result:
                raise YamlError(f"line {number}: duplicate key '{key}'")
            rest = content[idx + 1:].strip()
            self.pos += 1
            if rest[:1] in ("|", ">") and rest[1:] in ("", "-", "+"):
                result[key] = self.block_scalar(indent, number, rest)
            elif rest:
                result[key] = _flow(rest)
            elif self.pos < len(self.lines) and (
                self.lines[self.pos][0] > indent
                or (self.lines[self.pos][0] == indent and self.lines[self.pos][1].startswith("- "))
            ):
                result[key] = self.block(self.lines[self.pos][0])
            else:
                result[key] = None
        return result

    def block_scalar(self, indent: int, number: int, style: str) -> str:
        """Collect the raw lines indented under `key: |` (comments inside are kept)."""
        body, last = [], number
        for offset in range(number, len(self.raw)):
            line = self.raw[offset]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line)
            if line.strip():
                last = offset + 1
        while self.pos < len(self.lines) and self.lines[self.pos][2] <= last:
            self.pos += 1
        body = body[: last - number]
        base = min((len(l) - len(l.lstrip()) for l in body if l.strip()), default=0)
        lines = [l[base:] for l in body]
        text = (" ".join(l.strip() for l in lines) if style[0] == ">" else "\n".join(lines))
        return text if style.endswith("-") else text + "\n"

    def sequence(self, indent: int) -> list:
        result: list = []
        while self.pos < len(self.lines):
            ind, content, number = self.lines[self.pos]
            if ind != indent or not (content == "-" or content.startswith("- ")):
                if ind > indent:
                    raise YamlError(f"line {number}: unexpected indentation")
                break
            rest = content[1:].strip()
            if not rest:
                self.pos += 1
                if self.pos < len(self.lines) and self.lines[self.pos][0] > indent:
                    result.append(self.block(self.lines[self.pos][0]))
                else:
                    result.append(None)
            elif _find_key_colon(rest) >= 0 and rest[0] not in "[{\"'":
                # "- key: value" starts a mapping whose keys align after the dash.
                inner = indent + (len(content) - len(rest))
                self.lines[self.pos] = (inner, rest, number)
                result.append(self.mapping(inner))
            else:
                self.pos += 1
                result.append(_flow(rest))
        return result


def loads(text: str):
    return _Parser(text).parse()


def load(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return loads(handle.read())
    except YamlError as exc:
        raise YamlError(f"{path}: {exc}") from None


_PLAIN = re.compile(r"[A-Za-z0-9_./*+@-][A-Za-z0-9_./*+@ -]*")


def _dump_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Hex):
        return f"0x{int(value):02X}"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if (_PLAIN.fullmatch(text) and text == text.strip()
            and text not in ("true", "false", "null", "~")
            and not _INT.fullmatch(text) and not _HEX.fullmatch(text) and not _FLOAT.fullmatch(text)
            and ": " not in text and " #" not in text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _is_flat(value) -> bool:
    if isinstance(value, dict):
        return all(not isinstance(v, (dict, list)) for v in value.values())
    if isinstance(value, list):
        return all(not isinstance(v, (dict, list)) for v in value)
    return True


def _dump_flow(value) -> str:
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{ " + ", ".join(f"{k}: {_dump_flow(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_dump_flow(v) for v in value) + "]"
    return _dump_scalar(value)


def dumps(data, indent: int = 0) -> str:
    """Block style for structure, flow style for small leaf collections."""
    pad = " " * indent
    lines: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)) and value and not (_is_flat(value) and (
                    isinstance(value, list) or len(value) <= 4)):
                lines.append(f"{pad}{key}:")
                lines.append(dumps(value, indent + 2))
            else:
                lines.append(f"{pad}{key}: {_dump_flow(value)}")
    else:
        for value in data:
            if isinstance(value, dict) and value and not _is_flat(value):
                body = dumps(value, indent + 2).splitlines()
                lines.append(f"{pad}- {body[0].strip()}")
                lines.extend(body[1:])
            else:
                lines.append(f"{pad}- {_dump_flow(value)}")
    return "\n".join(lines)
