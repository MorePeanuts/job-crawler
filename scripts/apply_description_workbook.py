"""Transplant authored description values into an exact copy of a historical XLSX.

An optional authored workbook's first sheet has target address in column A and
literal value in column B, one row per patch. Only I/J text cells in
the original first sheet may change. All other ZIP entries remain byte-identical.
"""

import argparse
import json
import re
from contextlib import ExitStack
from copy import copy
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict

from job_crawler.storage import write_json

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SHEET = "xl/worksheets/sheet1.xml"
CELL = re.compile(r'(<c\b[^>]*?\br="([^"]+)"[^>]*?)(?:/>|>.*?</c>)', re.S)


class Patch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell: str
    old: str
    new: str
    key: str


def values(archive: ZipFile) -> dict[str, str]:
    shared = []
    if "xl/sharedStrings.xml" in archive.namelist():
        shared = [
            "".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))
        ]
    result = {}
    for cell in ET.fromstring(archive.read(SHEET)).iter(f"{NS}c"):
        if cell.find(f"{NS}f") is not None:
            raise ValueError("Description sheet must contain literal values")
        value = cell.findtext(f"{NS}v", "")
        if cell.get("t") == "s":
            value = shared[int(value)]
        elif cell.get("t") == "inlineStr":
            value = "".join(t.text or "" for t in cell.iter(f"{NS}t"))
        result[cell.attrib["r"]] = re.sub(
            r"_x([0-9a-fA-F]{4})_", lambda m: chr(int(m[1], 16)), value
        )
    return result


def apply(
    source: Path, patch_path: Path, output: Path, authored: Path | None = None
) -> dict[str, int]:
    if output.exists():
        raise ValueError("Refusing to overwrite an existing workbook")
    patches = [Patch.model_validate(item) for item in json.loads(patch_path.read_text())]
    if len({p.cell for p in patches}) != len(patches):
        raise ValueError("Duplicate patch addresses")
    with ExitStack() as stack:
        original = stack.enter_context(ZipFile(source))
        old_values = values(original)
        authored_map = {patch.cell: patch.new for patch in patches}
        if authored is not None:
            edits = stack.enter_context(ZipFile(authored))
            authored_values = values(edits)
            if len(authored_values) != 2 * len(patches):
                raise ValueError("Authored patch table must match patch count")
            authored_map = {
                authored_values[f"A{index}"]: authored_values[f"B{index}"]
                for index in range(1, len(patches) + 1)
            }
        expected_values = dict(old_values)
        changes = {patch.cell: patch.new for patch in patches}
        for patch in patches:
            if not re.fullmatch(r"[IJ][2-9]\d*|[IJ]1\d+", patch.cell):
                raise ValueError(f"Not a description data cell: {patch.cell}")
            if old_values.get(patch.cell, "") != patch.old:
                raise ValueError(f"Original value mismatch: {patch.cell}")
            # The spreadsheet authoring engine normalizes CRLF to LF. Restore
            # the verified source line endings when transplanting literal text.
            if authored_map.get(patch.cell) not in {patch.new, patch.new.replace("\r\n", "\n")}:
                raise ValueError(f"Authored value mismatch: {patch.cell}")
            expected_values[patch.cell] = patch.new

        written: set[str] = set()

        def replace(match: re.Match[str]) -> str:
            address = match[2]
            if address not in changes:
                return match[0]
            tag = match[1] + ">"
            if 't="inlineStr"' not in tag:
                if 't="s"' not in tag and old_values.get(address, ""):
                    raise ValueError(f"Expected original inline-string or empty cell: {address}")
                tag = re.sub(r' t="[^"]*"', "", tag)[:-1] + ' t="inlineStr">'
            content = escape(changes[address]).replace("\r", "&#13;")
            written.add(address)
            return tag + f'<is><t xml:space="preserve">{content}</t></is></c>'

        xml = CELL.sub(replace, original.read(SHEET).decode())
        if written != changes.keys():
            raise ValueError("Some patch addresses were not found")
        with ZipFile(output, "x") as result:
            for entry in original.infolist():
                result.writestr(
                    copy(entry), xml.encode() if entry.filename == SHEET else original.read(entry)
                )
        with ZipFile(output) as result:
            if result.testzip() is not None or values(result) != expected_values:
                raise ValueError("Written workbook failed value verification")
            unchanged = [name for name in original.namelist() if name != SHEET]
            if original.namelist() != result.namelist() or any(
                original.read(name) != result.read(name) for name in unchanged
            ):
                raise ValueError("Unrelated workbook structure changed")

            # Prove that style/layout/XML outside explicitly changed cell bodies is intact.
            def mask(match: re.Match[str]) -> str:
                return (
                    re.sub(r' t="[^"]*"', "", match[1]) + "></c>"
                    if match[2] in changes
                    else match[0]
                )

            before = CELL.sub(mask, original.read(SHEET).decode())
            after = CELL.sub(mask, result.read(SHEET).decode())
            if before != after:
                raise ValueError("Unrelated worksheet content or formatting changed")
    return {"changed_cells": len(patches), "unchanged_zip_parts": len(unchanged)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("patches", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--authored", type=Path)
    args = parser.parse_args()
    result = apply(args.source, args.patches, args.output, args.authored)
    write_json(args.output.parent / "workbook-verification.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
