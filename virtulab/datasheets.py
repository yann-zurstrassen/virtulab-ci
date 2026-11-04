"""Where each datasheet statement lives in the code.

Every sensor has a map in `virtulab/datasheets/<module>.yml`: one row per
statement of the datasheet (a register, a field, a formula, a timing rule) with
its status (modelled, simplified, not modelled, not checked) and where it is
implemented in three places:

  model   the emulator model that behaves like the chip (virtulab/devices)
  driver  the sample firmware's driver that talks to it
  test    the sample test that checks it

Each row also says where the datasheet states it: `source: "<document id> §section, Table n, p. N"`,
with the documents listed at the top of the file (title, revision, URL, SHA-256 of the file that was read, date).
A row without a source is shown as **unverified**. `corroborated_by` names independent sources that agree
(a vendor's own driver, a standard), and `issue` records a problem in the datasheet itself: an error, an
ambiguity, or a conflict between sources, with what the model does about it.

A place is written `path#anchor`: a file relative to the `virtulab/` package and
a literal piece of text inside it. The line number is looked up when the map is
read, so the references cannot go stale on their own, and a test fails when an
anchor no longer matches anything.
"""

from pathlib import Path

from . import VirtulabError, yamlite

PACKAGE = Path(__file__).resolve().parent
DIR = PACKAGE / "datasheets"
PLACES = ("model", "driver", "test")

STATUS = {
    "modelled": "Modelled",
    "simplified": "Simplified",
    "not-modelled": "Not modelled",
    "unchecked": "Not checked by VirtuLab",
}


def available() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.yml"))


def locate(ref: str) -> dict:
    """`path#anchor` -> {"path", "anchor", "line"}; `line` is None when the anchor is not found."""
    path, _, anchor = ref.partition("#")
    file = (PACKAGE / path).resolve()
    out = {"path": path, "anchor": anchor, "line": None}
    if PACKAGE not in file.parents or not file.is_file():
        return out
    for number, text in enumerate(file.read_text().splitlines(), 1):
        if anchor in text:
            out["line"] = number
            break
    return out


NOT_IN_DATASHEET = "n/a"  # a row about VirtuLab's own fault injection, not about the chip


def load(module_id: str) -> dict:
    """The map of one module with every place resolved to a file and line."""
    path = DIR / f"{module_id}.yml"
    if not path.is_file():
        raise VirtulabError(f"No datasheet map for '{module_id}'. Available: {', '.join(available())}")
    data = yamlite.load(path)
    documents = {d["id"]: d for d in data.get("documents") or []}
    rows = []
    for row in data.get("rows") or []:
        entry = {k: v for k, v in row.items() if k not in PLACES}
        for place in PLACES:
            if row.get(place):
                entry[place] = locate(str(row[place]))
        source = str(row.get("source") or "").strip()
        doc_id = source.split(None, 1)[0] if source else ""
        entry["cited"] = bool(source) and (doc_id in documents or doc_id == NOT_IN_DATASHEET)
        entry["unverified"] = not entry["cited"]
        rows.append(entry)
    data["rows"] = rows
    data["documents"] = list(documents.values())
    data["id"] = module_id
    return data


def summary(module_id: str) -> dict | None:
    """Counts for the catalog: rows per status, rows without a citation, rows with a datasheet issue."""
    if module_id not in available():
        return None
    statuses: dict[str, int] = {}
    unverified = issues = 0
    for row in load(module_id)["rows"]:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
        unverified += row["unverified"]
        issues += bool(row.get("issue"))
    return {"statuses": statuses, "unverified": unverified, "issues": issues}


def source_window(module_id: str, rel_path: str, line: int, before: int = 4, after: int = 14) -> dict:
    """A few lines of one file named by the module's map. Anything else is refused."""
    allowed = {p["path"] for row in load(module_id)["rows"] for place, p in row.items()
               if place in PLACES and p["line"] is not None}
    if rel_path not in allowed:
        raise VirtulabError(f"'{rel_path}' is not referenced by the {module_id} datasheet map")
    lines = (PACKAGE / rel_path).read_text().splitlines()
    start = max(1, line - before)
    end = min(len(lines), line + after)
    return {"path": rel_path, "start": start, "highlight": line,
            "text": "\n".join(lines[start - 1:end])}


def _place(p: dict | None) -> str:
    """Path only: line numbers move with every edit, so they are shown by the UI and the CLI instead."""
    return f"`{p['path']}`" if p else "—"


def _docs_markdown(data: dict) -> list[str]:
    if not data["documents"]:
        return ["**Documents read:** none yet (every row is unverified)", ""]
    out = ["**Documents read:**", ""]
    for d in data["documents"]:
        link = f"<{d['url']}>" if d.get("url") else "no public link"
        out.append(f"- `{d['id']}`: {d['title']}, {d.get('revision', 'revision unknown')}, "
                   f"retrieved {d.get('retrieved', '?')}, {link}, SHA-256 `{str(d.get('sha256', ''))[:16]}…`")
    return out + [""]


def to_markdown(module_id: str) -> str:
    data = load(module_id)
    out = [f"## {data['title']}", ""]
    if data.get("manufacturer"):
        out.append(f"**Manufacturer:** {data['manufacturer']}  ")
    if data.get("product_page"):
        out.append(f"**Product page:** <{data['product_page']}>  ")
    if data.get("interface"):
        out.append(f"**Interface:** {data['interface']}")
    out.append("")
    out += _docs_markdown(data)
    unverified = sum(r["unverified"] for r in data["rows"])
    if unverified:
        out += [f"> ⚠️ {unverified} of {len(data['rows'])} rows have no citation yet and are unverified.", ""]
    out += ["| Datasheet says | Source | Status | Model | Sample driver | Sample test |",
            "| :-- | :-- | :-- | :-- | :-- | :-- |"]
    for r in data["rows"]:
        test = r.get("test")
        test_text = f"`{test['anchor']}`" if test else "—"
        says = f"**{r['topic']}**: {r['datasheet']}" + (f" _{r['note']}_" if r.get("note") else "")
        if r.get("issue"):
            says += f" ⚠️ **Datasheet issue:** {r['issue']}"
        source = r.get("source") or "unverified"
        if r.get("corroborated_by"):
            source += f" (also: {', '.join(r['corroborated_by'])})"
        out.append(f"| {says} | {source} | {STATUS[r['status']]} | {_place(r.get('model'))} | "
                   f"{_place(r.get('driver'))} | {test_text} |")
    out.append("")
    return "\n".join(out)


def all_markdown() -> str:
    head = ("# Datasheet maps\n\n"
            "Generated by `virtulab datasheet --markdown`; do not edit by hand. Each row says what a "
            "datasheet states, where (document, section, page), whether VirtuLab models it, and where in the code. "
            "Line numbers are left out because they move: `virtulab datasheet NAME` and the setup page look them up, "
            "and a test fails when a reference stops matching the code. A row with no citation is unverified. "
            "Problems found in the datasheets themselves are collected in [DATASHEET_ISSUES.md](DATASHEET_ISSUES.md).\n\n")
    return head + "\n".join(to_markdown(m) for m in available())


def issues_markdown() -> str:
    """Every datasheet problem found while checking the models, one section per sensor."""
    out = ["# Datasheet issues\n",
           "Problems in the manufacturers' documents, or conflicts between a document and an independent source "
           "(a vendor's own driver, a standard), found while checking the models. Generated by "
           "`virtulab datasheet --issues`; the entries live in `virtulab/datasheets/*.yml` as the `issue` of a row. "
           "Each says what the model does about it.\n"]
    found = False
    for module in available():
        data = load(module)
        rows = [r for r in data["rows"] if r.get("issue")]
        if not rows:
            continue
        found = True
        out.append(f"## {data['title']}\n")
        for r in rows:
            out.append(f"- **{r['topic']}** ({r.get('source', 'no source')}): {r['issue']}")
        out.append("")
    if not found:
        out.append("None recorded yet.\n")
    return "\n".join(out)
