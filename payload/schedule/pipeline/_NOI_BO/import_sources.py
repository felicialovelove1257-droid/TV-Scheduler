from __future__ import annotations

import json
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


BASE_DIR = Path(__file__).resolve().parent
from portable_paths import WORKBOOK_PATH
INPUT_SHEETS = ("INPUT_1", "INPUT_2", "INPUT_3")
PLACEHOLDER_PREFIX = "DÁN TOÀN BỘ GOOGLE SHEET"

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref.upper())
    if not letters:
        return 0
    value = 0
    for char in letters.group(0):
        value = value * 26 + ord(char) - 64
    return value - 1


def read_shared_strings(book: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(book.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    result = []
    for item in root.findall(f"{{{NS_MAIN}}}si"):
        result.append("".join(node.text or "" for node in item.iter(f"{{{NS_MAIN}}}t")))
    return result


def sheet_targets(book: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(book.read("xl/workbook.xml"))
    rels = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    relation_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{{{NS_PKG_REL}}}Relationship")
    }
    result = {}
    for sheet in workbook.findall(f".//{{{NS_MAIN}}}sheet"):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{NS_REL}}}id"]
        target = relation_map[rel_id].replace("\\", "/")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = "xl/" + target
        result[name] = target
    return result


def read_sheet(book: zipfile.ZipFile, target: str, shared: list[str]) -> list[list[str]]:
    root = ET.fromstring(book.read(target))
    cells: dict[tuple[int, int], str] = {}
    max_row = -1
    max_col = -1

    for cell in root.findall(f".//{{{NS_MAIN}}}c"):
        ref = cell.attrib.get("r", "A1")
        row_match = re.search(r"\d+", ref)
        row = int(row_match.group(0)) - 1 if row_match else 0
        col = column_index(ref)
        cell_type = cell.attrib.get("t", "")
        value_node = cell.find(f"{{{NS_MAIN}}}v")
        formula_node = cell.find(f"{{{NS_MAIN}}}f")

        if cell_type == "inlineStr":
            inline = cell.find(f"{{{NS_MAIN}}}is")
            value = "" if inline is None else "".join(
                node.text or "" for node in inline.iter(f"{{{NS_MAIN}}}t")
            )
        elif value_node is not None:
            raw = value_node.text or ""
            if cell_type == "s" and raw.isdigit() and int(raw) < len(shared):
                value = shared[int(raw)]
            elif cell_type == "b":
                value = "TRUE" if raw == "1" else "FALSE"
            else:
                value = raw
        elif formula_node is not None:
            value = "=" + (formula_node.text or "")
        else:
            value = ""

        cells[(row, col)] = value
        max_row = max(max_row, row)
        max_col = max(max_col, col)

    if max_row < 0 or max_col < 0:
        return []
    rows = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    for (row, col), value in cells.items():
        rows[row][col] = value
    while rows and not any(str(value).strip() for value in rows[-1]):
        rows.pop()
    return rows


def clean_tsv_value(value: object) -> str:
    return str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " / ")


def main() -> int:
    if not WORKBOOK_PATH.exists():
        print(f"KHÔNG TÌM THẤY: {WORKBOOK_PATH}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = BASE_DIR / "snapshots" / stamp
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(WORKBOOK_PATH) as book:
        shared = read_shared_strings(book)
        targets = sheet_targets(book)
        missing = [name for name in INPUT_SHEETS if name not in targets]
        if missing:
            print("THIẾU TAB: " + ", ".join(missing))
            return 1

        manifest = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "workbook": str(WORKBOOK_PATH),
            "snapshot": str(snapshot_dir),
            "sheets": [],
        }
        has_error = False

        for name in INPUT_SHEETS:
            rows = read_sheet(book, targets[name], shared)
            nonempty = sum(1 for row in rows for value in row if str(value).strip())
            first = rows[0][0].strip() if rows and rows[0] else ""
            pasted = bool(nonempty) and not first.upper().startswith(PLACEHOLDER_PREFIX)
            max_cols = max((len(row) for row in rows), default=0)
            status = "OK" if pasted else "CHƯA DÁN DỮ LIỆU"
            has_error = has_error or not pasted

            tsv_path = snapshot_dir / f"{name}.tsv"
            with tsv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                for row in rows:
                    padded = row + [""] * (max_cols - len(row))
                    handle.write("\t".join(clean_tsv_value(value) for value in padded) + "\n")

            manifest["sheets"].append(
                {
                    "name": name,
                    "status": status,
                    "rows": len(rows),
                    "columns": max_cols,
                    "nonempty_cells": nonempty,
                    "tsv": str(tsv_path),
                }
            )
            print(f"{name}: {status} | {len(rows)} dòng | {max_cols} cột | {nonempty} ô có dữ liệu")

    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE_DIR / "latest_snapshot.txt").write_text(str(snapshot_dir), encoding="utf-8")
    print(f"\nSNAPSHOT: {snapshot_dir}")
    print("Dữ liệu nguồn không bị chỉnh sửa.")
    return 2 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
