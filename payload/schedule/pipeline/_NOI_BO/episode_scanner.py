from __future__ import annotations
from media_labels import is_no_next, canonical_no_next, NO_NEXT_PATTERN

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from import_sources import read_shared_strings, read_sheet, sheet_targets
from schedule_engine import build_schedule, show_code
from max_options import is_max, is_no_max, apply_choices, remember


BASE_DIR = Path(__file__).resolve().parent
from portable_paths import WORKBOOK_PATH, ADS_CATALOG_PATH, EXPORT_ROOT, LOCAL_ROOT, local_path, open_spreadsheet


def checkbox_preferences():
    path=BASE_DIR/'configs'/'checkbox_preferences.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def clean_title(text: str) -> str:
    """Remove spreadsheet notes that must not become part of a filename."""
    return re.sub(r"\s+", " ", str(text or "").splitlines()[0]).strip()


def shorten_program_title(text: str) -> str:
    """Convert long schedule titles to the compact on-air filename style."""
    title = clean_title(text)
    title = re.sub(r"Supreme Master Ching Hai\s*\(vegan\)", "SMCH", title, flags=re.I)
    title = re.sub(r"Supreme Master Ching Hai", "SMCH", title, flags=re.I)
    title = re.sub(r"\bMedia Interviews? with\b", "Interview", title, flags=re.I)
    title = re.sub(r"\bInterviews? with\b", "Interview", title, flags=re.I)
    title = re.sub(r"\bPart\s+(\d+)\s+of\s+(\d+)\b", r"P\1o\2", title, flags=re.I)
    title = re.sub(
        r"\bPart\s+(\d+)\s+of\s+multi(?:[ -]?part)?\w*(?:\s+(?:series|programs?|episodes?))?\b",
        r"P\1",
        title,
        flags=re.I,
    )
    title = re.sub(r"\s*,\s*", " ", title)
    title=re.sub(r'\s*:\s*',' - ',title)
    title=re.sub(r'[<>"/\\|?*]',' ',title)
    return re.sub(r"\s+", " ", title).strip()


def shorten_show_title(text: str) -> str:
    title=shorten_program_title(text)
    # For a named person followed by a subtitle, retain the person and part.
    person=re.match(r'^(.*?\(vegan\))\s*-\s*',title,re.I)
    if person:
        part=re.search(r'\bP\d+(?:o\d+)?\b',title,re.I)
        return person[1]+(' '+part[0] if part else '')
    return title


def clean_local_filename(name: str) -> str:
    import unicodedata
    stem,ext=os.path.splitext(name)
    # Preserve letters (including accents), numbers and established label parentheses.
    stem=''.join(ch if ch.isalnum() or ch in '() ' or unicodedata.category(ch).startswith('M')
                 else '' if ch in "'\u2018\u2019\u02bc" else ' ' for ch in stem)
    return re.sub(r'\s+',' ',stem).strip()+ext.lower()


def proposed_name(source_name: str, episode: int, program: dict) -> tuple[str, str]:
    name,rule=_proposed_name(source_name,episode,program)
    return clean_local_filename(canonical_no_next(name)),rule


def normalize_episode_order(stem, program=None):
    """Canonicalize CODE EP to EP CODE; leave title numbers and teaser dates alone."""
    codes={'NWN','BMD','WOW','AP','DN','SHOW','VEGC','VEG','GPGW','AJAR','NB','AW'}
    for show in (program or {}).get('active_shows',[]):
        code=show_code(show.get('code','')).upper()
        if code and re.fullmatch(r'[A-Z][A-Z0-9]*',code):codes.add(code)
    pattern='|'.join(re.escape(c) for c in sorted(codes,key=len,reverse=True))
    return re.sub(rf'^({pattern})[ _-]+(\d{{4}})(?=[ _-]|$)',
                  lambda m:m[2]+' '+m[1].upper(),stem,flags=re.I)


def _proposed_name(source_name: str, episode: int, program: dict) -> tuple[str, str]:
    """Return a conservative local filename and the rule used to obtain it."""
    stem = Path(source_name).stem
    stem = re.sub(r'[_]+', ' ', stem)
    stem = normalize_episode_order(stem, program)
    stem = re.sub(r'\bNWN\s+(?:SEG(?:MENT)?|S)\s*([123])\s*([ABC]?)(?=\s|[.(]|$)',
                  lambda m:'NWN SEG '+m[1]+m[2].upper(), stem, flags=re.I)
    upper = stem.upper()
    upper = re.sub(r'NO[ _]*(?:SMTV[ _]*)?MAX', 'NO MAX', upper)
    ext = Path(source_name).suffix.lower()

    if upper == f"{episode} DN TEMP" or re.fullmatch(rf"{episode}\s+NWN DAILY SCROLL(?:\s+V\d+)?", upper):
        return f"{episode} NWN Daily Scroll{ext}", "daily-scroll"
    if "NWN SEG 1A" in upper:
        suffix = " (No Max)" if "NO MAX" in upper else ""
        return f"{episode} NWN S1A FN{suffix}{ext}", "nwn-s1a"
    match = re.search(r"NWN (?:SEG 1B|S1B)\s+(.+?)(?:\s+V\d+)?$", stem, re.I)
    if match:
        detail = re.sub(r"\s+", " ", match.group(1)).strip().replace("_", " ")
        detail = re.sub(r"\s+v\d+$", "", detail, flags=re.I)
        return f"{episode} NWN S1B {detail}{ext}", "nwn-s1b-fn"
    if "NWN SEG 1C" in upper:
        suffix = ' (No Max)' if re.search(r'NO[ _]*MAX',upper) else ''
        return f"{episode} NWN S1C FN{suffix}{ext}", "nwn-s1c"
    if "NWN SEG 2" in upper:
        suffix = " (No Max)" if "NO MAX" in upper else ""
        return f"{episode} NWN S2{suffix}{ext}", "nwn-s2"
    if "NWN SEG 3" in upper:
        suffix = " (No Max)" if "NO MAX" in upper else ""
        return f"{episode} NWN S3{suffix}{ext}", "nwn-s3"

    if re.match(rf'^{episode}\s+AP\b',upper):
        from ap_rules import part_id
        part=part_id(stem)
        if part:
            stem=re.sub(r'\b(?:PART|PT|P)\s*[A-Z]\b','PART'+part,stem,flags=re.I)
            stem=re.sub(r'\s*\(?no[ _]*(?:smtv[ _]*)?max\)?',' (No Max)',stem,flags=re.I)
            stem=re.sub(r'\s+v\d+\b','',stem,flags=re.I)
            return stem+ext,'ap-part'

    canonical=re.match(r'^\d+\s+(BMD|WOW)\s+(IN|OUT)(?=\s|$)',upper)
    if canonical:
        family,part=canonical.groups()
        rule=('bmd-' if family=='BMD' else 'wow-lecture-')+('intro' if part=='IN' else 'outro')
        return stem+ext,rule

    if "BMD INTRO" in upper:
        kind = " LONG" if "WITH M LONG" in upper else " SHORT" if "WITH M SHORT" in upper else ""
        no_max = " (No Max)" if "NO MAX" in upper else ""
        return f"{episode} BMD IN{kind}{no_max}{ext}", "bmd-intro"
    if "BMD MAIN" in upper:
        title = shorten_program_title(program.get("details", {}).get("BMD", "BMD"))
        return f"{episode} BMD MAIN {title} (weblink){ext}", "bmd-main"
    if "BMD OUTRO" in upper:
        if is_no_next(upper):
            nxt = "No NXT"
        else:
            found = re.search(r"NEXT IS\s+([A-Z0-9]+)", upper)
            nxt = f"UP NXT {found.group(1)}" if found else "OUT"
        suffix = ' (No Max)' if re.search(r'NO[ _]*MAX',upper) else ''
        return f"{episode} BMD OUT ({nxt}){suffix}{ext}", "bmd-outro"

    if "WOW INTRO" in upper:
        no_max = " (No Max)" if "NO MAX" in upper else ""
        return f"{episode} WOW IN{no_max}{ext}", "wow-lecture-intro"
    if "WOW MAIN" in upper:
        title = shorten_program_title(program.get("details", {}).get("WOW", "WOW"))
        if program.get('wow_has_intro_outro') is False:
            return f"{episode} WOW {title}{ext}", 'wow-main'
        # The sheet title already contains the part number; keep only one copy.
        return f"{episode} WOW MAIN {title} (weblink){ext}", "wow-lecture-main"
    if "WOW OUTRO" in upper:
        suffix = ' (No NXT)' if is_no_next(upper) else ''
        if 'NO MAX' in upper: suffix += ' (No Max)'
        return f"{episode} WOW OUT{suffix}{ext}", "wow-lecture-outro"
    if re.match(rf'^{episode}\s+WOW\b',upper) and program.get('wow_has_intro_outro') is False:
        title=shorten_program_title(program.get('details',{}).get('WOW','WOW'))
        return f'{episode} WOW {title}{ext}', 'wow-main'

    active_codes = [show_code(item.get("code", "")).upper() for item in program.get("active_shows", [])]
    for code in active_codes:
        short_code = code.split()[0] if code else ""
        if short_code and re.search(rf"\b{re.escape(short_code)}\b", upper) and not re.search(r"\b(?:TSER|TEASER)\b",upper):
            segment=re.search(r'\b(?:SEG(?:MENT)?\s*|S)([12])\b',upper)
            show=next((v for v in program.get('active_shows',[]) if show_code(v.get('code','')).upper()==code),{})
            title=shorten_show_title(show.get('title',''))
            from show_formats import show_part
            role=show_part(stem,short_code)
            if role in ('IN','OUT') or (role=='MAIN' and show.get('has_intro_outro')):
                suffix=' (No Max)' if re.search(r'no[ _]*(?:smtv[ _]*)?max',stem,re.I) else ''
                if is_no_next(stem):suffix+=' (No NXT)'
                fallback=re.sub(rf'^\d+\s+{re.escape(short_code)}\s*(?:MAIN\s*)?','',stem,flags=re.I)
                fallback=re.sub(r'\s*\(?no[ _]*(?:smtv[ _]*)?max\)?|\s+v\d+\b','',fallback,flags=re.I).strip()
                label=(title or fallback or 'MAIN') if role=='MAIN' else role
                return f"{episode} {short_code} {label}{suffix}{ext}",'show-'+{'IN':'intro','MAIN':'main','OUT':'outro'}[role]

            if segment and title and not re.search(r'\b(?:TSER|TEASER)\b',upper):
                suffix=' (No Max)' if 'NO MAX' in upper else ''
                if is_no_next(upper):suffix+=' (No NXT)'
                return f"{episode} {short_code} {title} S{segment[1]}{suffix}{ext}", 'active-show'
            remainder = re.sub(rf"^{episode}\s+", "", stem, flags=re.I)
            remainder = re.sub(r"\s+V\d+(?=\s|$)", "", remainder, flags=re.I)
            remainder = re.sub(r"\s+", " ", remainder).strip()
            return f"{episode} {remainder}{ext}", "active-show"

    if upper == "TEASER FN":
        return f"TEASER FN{ext}", "teaser-fn"
    if upper.startswith("TEASER ") or upper.startswith("TSER "):
        teaser = re.sub(r"^TEASER\s+", "TSER ", stem, flags=re.I)
        teaser = re.sub(r"(?:[ _])v\d+$", "", teaser, flags=re.I).strip()
        short = re.match(r'^TSER\s+(\d{4})\s+([A-Z][A-Z0-9]*)\b',teaser,re.I)
        if short and not short[2].upper().startswith('FN'):
            teaser=f'TSER {short[1]} {short[2].upper()}'
            if short[2].upper()=='AP':
                from ap_rules import teaser_phase
                phase=teaser_phase(stem)
                if phase is not None:teaser+=' '+('TODAY','TOMORROW','IN 2 DAYS')[phase]
        return f"{teaser}{ext}", "teaser"
    return f"{stem}{ext}", "review"


def create_rename_preview(source_dir: Path, local_dir: Path, episode: int, program: dict) -> dict:
    from show_formats import configure_shows
    configure_shows(program,[p.name for p in list(source_dir.glob('*.mp4'))+list(local_dir.glob('*.mp4'))])
    rows = []
    sources = sorted(source_dir.glob("*.mp4"), key=lambda p: p.name.lower())
    # Only fall back one day, never silently take day one's new-event set.
    fn_enabled = program.get("schedule_type") == "FN"
    has_fn = lambda p: bool(re.search(r"NWN[ _]+(?:SEG(?:MENT)?|S)[ _]*1[ _]*B\b", normalize_episode_order(p.name, program), re.I))
    fn_source_episode = episode
    if fn_enabled and not any(has_fn(p) for p in sources):
        previous = source_dir.parent / f"EP {episode - 1}"
        fallback = [p for p in previous.glob("*.mp4") if has_fn(p)]
        if not fallback:
            previous = source_dir.parent / '@ ARCHIVES' / f'EP {episode - 1}'
            fallback = [p for p in previous.glob('*.mp4') if has_fn(p)]
        sources.extend(fallback)
        fn_source_episode = episode - 1 if fallback else None
    # A real Daily Scroll supersedes DN TEMP; they are not two schedule slots.
    if any(re.search(r"NWN DAILY SCROLL", normalize_episode_order(p.name, program), re.I) for p in sources):
        sources = [p for p in sources if p.stem.upper() != f"{episode} DN TEMP"]
    for source in sources:
        if program.get('wow_has_intro_outro') is False and re.search(r'\bWOW\s+(?:INTRO|OUTRO)\b',source.name,re.I):continue
        source_episode = episode - 1 if has_fn(source) and source.parent != source_dir else episode
        if has_fn(source):
            prefix=re.match(r'(\d{4})\b',normalize_episode_order(source.name, program))
            if prefix:source_episode=int(prefix[1])
        target_name, rule = proposed_name(source.name, source_episode, program)
        rows.append({
            "rule": rule,
            "source_name": source.name,
            "target_name": target_name,
            "source_path": str(source),
            "target_path": str((local_dir.parent / f'EP {source_episode}' if source_episode != episode else local_dir) / target_name),
        })
    from missing_media import source_choices
    from teaser_selection import is_fn_teaser
    source_fn_teaser=any(is_fn_teaser(r['source_name']) for r in rows)
    manual=[]
    for choice in source_choices(episode)['items']:
        if source_fn_teaser and choice.get('manual_slot')=='FN':continue
        if Path(choice['source_path']).is_file():manual.append(dict(choice))
        elif Path(choice['target_path']).is_file():
            manual.append(dict(choice,source_path=choice['target_path'],source_name=choice['target_name'],local_fallback=True))
    manual_fn=[r for r in manual if r.get('manual_kind')=='fn'] if fn_enabled else []
    if manual_fn:
        rows=[r for r in rows if not has_fn(Path(r['source_name']))]
        fn_source_episode=int(re.match(r'(\d{4})',manual_fn[0]['target_name'])[1])
    for choice in manual:
        if choice.get('manual_kind')=='fn' and not fn_enabled:continue
        rows=[r for r in rows if r['target_name'].casefold()!=choice['target_name'].casefold()]
        rows.append(choice)
    from teaser_selection import eligible_teaser
    rows=[r for r in rows if eligible_teaser(r['target_name'],episode)]
    # Windows duplicate copies are redundant when their original is present.
    originals={str(Path(row['source_path']).parent).casefold()+'|'+Path(row['source_name']).stem.casefold()
               for row in rows}
    def redundant_copy(row):
        stem=Path(row['source_name']).stem
        base=re.sub(r'\s*-\s*copy(?:\s*\(\d+\))?$', '', stem, flags=re.I)
        if base==stem:return False
        return str(Path(row['source_path']).parent).casefold()+'|'+base.casefold() in originals
    rows=[row for row in rows if not redundant_copy(row)]
    # For identical local names, automatically keep the highest source version.
    grouped = {}
    for row in rows:
        grouped.setdefault(row["target_name"].casefold(), []).append(row)
    for group in grouped.values():
        if len(group) < 2:
            continue
        versions = []
        for row in group:
            found = re.findall(r"(?:^|[ _])v(\d+)(?=[ _.(]|$)", Path(row["source_name"]).stem, re.I)
            versions.append(max((int(number) for number in found), default=0))
        highest = max(versions)
        candidates=[row for row,version in zip(group,versions) if version==highest]
        newest=max(Path(row['source_path']).stat().st_mtime_ns for row in candidates)
        winners=[row for row in candidates if Path(row['source_path']).stat().st_mtime_ns==newest]
        if len(winners)==1:
            for row in group:
                if row is not winners[0]:
                    row["_skip_older_source"] = True
    ignored_lower_version_count = sum(bool(row.get("_skip_older_source")) for row in rows)
    rows = [row for row in rows if not row.get("_skip_older_source")]
    for row in rows:
        row.pop("status", None)
    from draft_input import item_key
    def scan_key(row):
        if row.get('rule') in ('nwn-s1b-fn','bmd-intro','bmd-outro','ap-part','show-intro','show-main','show-outro'):return row['target_name'].casefold()
        return item_key(row)
    occupied={scan_key(row) for row in rows if scan_key(row)}
    draft_targets=set()
    manifest=local_dir/'pipeline_manifest.csv'
    if manifest.exists():
        with manifest.open(encoding='utf-8-sig',newline='') as handle:
            draft_targets={r['target_name'] for r in csv.DictReader(handle) if r.get('method')=='reported-duration'}
    for source in sorted(local_dir.glob('*.mp4')):
        if manual_fn and has_fn(source):continue
        if program.get('wow_has_intro_outro') is False and re.search(r'\bWOW\s+(?:INTRO|OUTRO|IN|OUT)\b',source.name,re.I):continue
        if source.name in draft_targets:continue
        local_ep=episode
        if has_fn(source):
            prefix=re.match(r'(\d{4})\b',normalize_episode_order(source.name, program))
            if prefix:local_ep=int(prefix[1])
        target_name,rule=proposed_name(source.name,local_ep,program)
        if source_fn_teaser and is_fn_teaser(target_name):continue
        candidate=dict(rule=rule,source_name=source.name,target_name=target_name,source_path=str(source),target_path=str(local_dir/target_name),local_fallback=True)
        if not eligible_teaser(target_name,episode):continue
        key=scan_key(candidate)
        if key and key not in occupied:
            rows.append(candidate);occupied.add(key)
    preview_dir = BASE_DIR / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / f"EP_{episode}_rename_preview.csv"
    try:
        handle = preview_path.open("w", newline="", encoding="utf-8-sig")
    except PermissionError:
        # Excel commonly locks an opened CSV. Keep the opened file and emit a fresh preview.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        preview_path = preview_dir / f"EP_{episode}_rename_preview_{stamp}.csv"
        handle = preview_path.open("w", newline="", encoding="utf-8-sig")
    with handle:
        writer = csv.DictWriter(handle, fieldnames=["rule", "source_name", "target_name", "source_path", "target_path"],extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    target_counts = {}
    for row in rows:
        key = row["target_name"].casefold()
        target_counts[key] = target_counts.get(key, 0) + 1
    return {
        "path": str(preview_path),
        "fn_source_episode": fn_source_episode if fn_enabled else None,
        "fn_manual_selection": bool(manual_fn),
        "count": len(rows),
        "review_count": sum(row["rule"] == "review" for row in rows),
        "ignored_lower_version_count": ignored_lower_version_count,
        "duplicate_target_count": sum(count > 1 for count in target_counts.values()),
        "items": rows,
    }


def value(rows: list[list[str]], row: int, col: int) -> str:
    if row < 0 or row >= len(rows) or col < 0 or col >= len(rows[row]):
        return ""
    return str(rows[row][col]).strip()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).upper()


def load_inputs() -> dict[str, list[list[str]]]:
    if not WORKBOOK_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy {WORKBOOK_PATH}")
    with zipfile.ZipFile(WORKBOOK_PATH) as book:
        shared = read_shared_strings(book)
        targets = sheet_targets(book)
        return {
            name: read_sheet(book, targets[name], shared)
            for name in ("INPUT_1", "INPUT_2", "INPUT_3", "INPUT_4") if name in targets
        }


def find_primary_program_column(rows: list[list[str]], episode: int) -> dict:
    needle = f"EPISODE {episode}"
    candidates = []
    for row_index, row in enumerate(rows):
        # INPUT_1 scheduling data is only in columns A:H. Columns I onward are
        # auxiliary content and must never influence episode/block selection.
        for col_index, cell in enumerate(row[:8]):
            if normalize(cell) == needle:
                end_row = min(len(rows), row_index + 40)
                score = 0
                found_labels = []
                for check_row in range(row_index, end_row):
                    label = normalize(value(rows, check_row, 0))
                    current = value(rows, check_row, col_index)
                    if not current:
                        continue
                    if label in {"S 1", "S1", "SHOW 1"}:
                        score += 5
                        found_labels.append("S1")
                    elif label in {"S 2", "S2", "SHOW 2"}:
                        score += 5
                        found_labels.append("S2")
                    elif label.startswith("NWN"):
                        score += 3
                        found_labels.append(label)
                    elif "BETWEEN MASTER AND DISCIPLES" in normalize(current):
                        score += 4
                        found_labels.append("BMD")
                candidates.append(
                    {
                        "row": row_index,
                        "column": col_index,
                        "score": score,
                        "labels": found_labels,
                    }
                )
    if not candidates:
        raise ValueError(f"Không tìm thấy EPISODE {episode} trong INPUT_1")
    candidates.sort(key=lambda item: (item["score"], -item["column"]), reverse=True)
    selected = candidates[0]
    selected["candidate_count"] = len(candidates)
    return selected


def extract_show(rows: list[list[str]], start_row: int, col: int, number: int) -> dict:
    accepted = {f"S {number}", f"S{number}", f"SHOW {number}"}
    end_row = min(len(rows), start_row + 40)
    for row_index in range(start_row, end_row):
        if normalize(value(rows, row_index, 0)) in accepted:
            code = value(rows, row_index, col)
            title = ""
            for title_row in range(row_index + 1, min(end_row, row_index + 5)):
                if normalize(value(rows, title_row, 0)) == "TITLE":
                    title = value(rows, title_row, col)
                    break
            is_removed = normalize(code) == "FN" or normalize(title) == "FN"
            return {
                "slot": number,
                "code": code,
                "title": title,
                "is_fn_removed": is_removed,
                "source_row": row_index + 1,
            }
    return {"slot": number, "code": "", "title": "", "is_fn_removed": False, "source_row": None}


def extract_program(rows: list[list[str]], episode: int) -> dict:
    selected = find_primary_program_column(rows, episode)
    row = selected["row"]
    col = selected["column"]
    show1 = extract_show(rows, row, col, 1)
    show2 = extract_show(rows, row, col, 2)

    if show1["is_fn_removed"] and show2["is_fn_removed"]:
        raise ValueError("Cả Show 1 và Show 2 đều được đánh dấu FN")
    if show1["is_fn_removed"]:
        schedule_type = "FN"
        active_shows = [{**show2, "output_slot": 2, "moved": False}]
        removed_show = 1
    elif show2["is_fn_removed"]:
        schedule_type = "FN"
        active_shows = [{**show1, "output_slot": 2, "moved": True}]
        removed_show = 2
    else:
        schedule_type = "NORMAL"
        active_shows = [
            {**show1, "output_slot": 1, "moved": False},
            {**show2, "output_slot": 2, "moved": False},
        ]
        removed_show = None

    details = {}
    end_row = min(len(rows), row + 40)
    for row_index in range(row, end_row):
        label = normalize(value(rows, row_index, 0))
        cell = value(rows, row_index, col)
        if not cell:
            continue
        if label.startswith("NWN"):
            details[label] = cell
        elif normalize(cell) == "BETWEEN MASTER AND DISCIPLES":
            details["BMD"] = value(rows, row_index + 1, col)
        elif re.match(r"^AP(?:\s|$)",normalize(cell)):
            details["AP"] = value(rows,row_index+1,col)
        elif normalize(cell) == "WORDS OF WISDOM":
            details["WOW"] = value(rows, row_index + 1, col)

    return {
        "primary_input_column": col + 1,
        "primary_episode_row": row + 1,
        "candidate_columns_found": selected["candidate_count"],
        "selection_score": selected["score"],
        "schedule_type": schedule_type,
        "removed_show": removed_show,
        "show1": show1,
        "show2": show2,
        "active_shows": active_shows,
        "details": details,
    }


def extract_cycle_rules(rows: list[list[str]], episode: int) -> dict:
    if len(rows) < 2:
        return {}
    columns = [index for index, cell in enumerate(rows[1]) if str(cell).strip() == str(episode)]
    if not columns:
        return {}
    col = columns[0]
    result = {"source_column": col + 1}
    for row_index in range(17, min(24, len(rows))):
        key = value(rows, row_index, 0)
        val = value(rows, row_index, col)
        if key:
            result[key] = val
    return result


def load_ads_catalog() -> dict[str, dict]:
    """Load only confirmed mappings; review suggestions never become automatic matches."""
    if not ADS_CATALOG_PATH.exists():
        return {}
    try:
        with zipfile.ZipFile(ADS_CATALOG_PATH) as book:
            shared = read_shared_strings(book)
            target = sheet_targets(book).get("ADS Mapping")
            if not target:
                return {}
            rows = read_sheet(book, target, shared)
    except (OSError, zipfile.BadZipFile, KeyError):
        return {}
    result = {}
    for row in rows[4:]:
        sheet_name = value([row], 0, 0).strip()
        actual_name = value([row], 0, 1).strip()
        actual_path = value([row], 0, 3).strip()
        status = value([row], 0, 5).strip()
        approved = value([row], 0, 7).strip().upper()
        confirmed = status == "AUTO EXACT" or approved in {"YES", "Y", "OK", "X"}
        if sheet_name and actual_name and confirmed:
            result[sheet_name.casefold()] = {
                "actual_name": actual_name,
                "actual_path": str(local_path(actual_path)) if actual_path else "",
                "mapping_status": "CONFIRMED",
            }
    return result


def extract_ads(rows: list[list[str]], episode: int) -> dict:
    matches = [index for index, row in enumerate(rows) if len(row) > 2 and value(rows, index, 2) == str(episode)]
    if not matches:
        return {"source_row": None, "items": []}
    row_index = matches[0]
    headers = rows[1] if len(rows) > 1 else []
    ignore_cols = {0, 1, 2, 3, 4, 5, 6, 7, 8, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109}
    items = []
    catalog = load_ads_catalog()
    for col, cell in enumerate(rows[row_index]):
        text = str(cell).strip()
        if not text or col in ignore_cols or text in {"F", "FALSE", "0"}:
            continue
        category = value([headers], 0, col)
        priority_text = normalize(category + " " + text)
        if "DO NOT SKIP" in priority_text:
            priority_class = "DO_NOT_SKIP"
        elif "PRIORIT" in priority_text:
            priority_class = "PRIORITY"
        else:
            priority_class = "OPTIONAL"
        mapped = catalog.get(text.casefold(), {})
        items.append(
            {
                "column": col + 1,
                "category": category,
                "name": text,
                "priority_class": priority_class,
                "actual_name": mapped.get("actual_name", ""),
                "actual_path": mapped.get("actual_path", ""),
                "mapping_status": mapped.get("mapping_status", "UNRESOLVED"),
            }
        )
    return {
        "source_row": row_index + 1,
        "items": items,
        "mapped_count": sum(item["mapping_status"] == "CONFIRMED" for item in items),
        "unresolved_count": sum(item["mapping_status"] != "CONFIRMED" for item in items),
    }


def scan_episode(episode: int) -> dict:
    inputs = load_inputs()
    source_dir = EXPORT_ROOT / f"EP {episode}"
    local_dir = LOCAL_ROOT / f"EP {episode}"
    root_files = sorted(source_dir.glob("*.mp4")) if source_dir.exists() else []
    program = extract_program(inputs["INPUT_1"], episode)
    result = {
        "episode": episode,
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(source_dir),
        "source_exists": source_dir.exists(),
        "source_root_mp4_count": len(root_files),
        "local_dir": str(local_dir),
        "local_exists": local_dir.exists(),
        "program": program,
        "cycle_rules": extract_cycle_rules(inputs["INPUT_2"], episode),
        "ads": extract_ads(inputs["INPUT_3"], episode),
    }
    from reserve_ads import read_catalog
    result['reserve_ads']=read_catalog(inputs.get('INPUT_4',[]))
    from wow_rules import has_wow_intro_outro
    from ap_rules import slot_family
    program['slot1_family']=slot_family(episode,program,root_files+list(local_dir.glob('*.mp4')))
    program['wow_has_intro_outro']=program['slot1_family']=='WOW' and has_wow_intro_outro(result['cycle_rules'])
    next_rules=extract_cycle_rules(inputs['INPUT_2'],episode+1)
    result['next_wow_has_intro_outro']=has_wow_intro_outro(next_rules) if next_rules else None
    result["rename_preview"] = create_rename_preview(source_dir, local_dir, episode, program)
    if result['next_wow_has_intro_outro'] is True:
        from draft_input import item_key
        result['rename_preview']['items']=[i for i in result['rename_preview']['items'] if item_key(i)!='TSER WOW']
    teaser_options=BASE_DIR/'configs'/f'EP_{episode}_teaser_options.json'
    tser_fn=checkbox_preferences().get('tser_fn',json.loads(teaser_options.read_text(encoding='utf-8')).get('tser_fn',True) if teaser_options.exists() else True)
    result.setdefault('schedule_settings',{})['tser_fn']=tser_fn
    if not tser_fn:
        from draft_input import item_key
        result['rename_preview']['items']=[i for i in result['rename_preview']['items'] if item_key(i)!='TSER FN']
    apply_choices(result)
    config_dir = BASE_DIR / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f"EP_{episode}_scan.json"
    result["config_path"] = str(config_path)
    from draft_input import merge_reported,storage
    reported_path=storage(result)
    reported=json.loads(reported_path.read_text(encoding='utf-8')) if reported_path.exists() else {}
    merge_reported(result,reported)
    result['rename_preview']['count']=len(result['rename_preview']['items'])
    config_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def summary(result: dict) -> str:
    program = result["program"]
    lines = [
        f"EP {result['episode']}",
        f"Nguồn: {result['source_dir']} ({result['source_root_mp4_count']} MP4)",
        f"Local: {result['local_dir']}",
        f"Loại lịch: {program['schedule_type']}",
        f"Cột chương trình chính trong INPUT_1: {program['primary_input_column']}",
    ]
    if program["schedule_type"] == "FN":
        lines.append(f"Show bị bỏ theo Excel: Show {program['removed_show']}")
    for show in program["active_shows"]:
        move_text = " (chuyển vào vị trí Show 2)" if show["moved"] else ""
        lines.append(f"Dùng Show {show['slot']} tại vị trí Show {show['output_slot']}{move_text}: {show['code']} | {show['title']}")
    lines.append(f"Rule cycle: {len(result['cycle_rules']) - (1 if result['cycle_rules'] else 0)} mục")
    lines.append(f"ADS: {len(result['ads']['items'])} mục")
    preview = result["rename_preview"]
    lines.append(f"Bảng đổi tên: {preview['count']} file; cần xem tay: {preview['review_count']}")
    lines.append(f"Tên đích đang trùng (cần chọn file dùng): {preview['duplicate_target_count']}")
    lines.append(f"Tự bỏ version thấp: {preview['ignored_lower_version_count']} file")
    lines.append(f"Preview: {preview['path']}")
    lines.append(f"Config: {result['config_path']}")
    return "\n".join(lines)


def run_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    from app_version import APP_TITLE
    root.title(APP_TITLE)
    root.geometry("1240x760")
    root.minsize(980, 600)

    run_header = ttk.Frame(root, padding=(14, 10, 14, 4))
    run_header.pack(fill='x')
    ttk.Label(run_header, text=APP_TITLE, font=('Segoe UI', 13, 'bold')).pack(side='left')
    run_panel = ttk.Frame(run_header, padding=(14, 4))
    run_panel.pack(side='right')

    shell = ttk.Frame(root, padding=10)
    shell.pack(fill="both", expand=True)
    shell.rowconfigure(0, weight=1)
    shell.columnconfigure(1, weight=1)

    sidebar = ttk.Frame(shell, padding=(4, 8), width=185)
    sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
    sidebar.grid_propagate(False)
    ttk.Label(sidebar, text="CÁC BƯỚC", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
    steps = tk.Listbox(sidebar, width=24, borderwidth=0, highlightthickness=0, activestyle="none", font=("Segoe UI", 10))
    steps.pack(fill="both", expand=True)
    from pipeline_flow import show_flow
    flow_footer=ttk.Frame(sidebar,padding=(0,10,0,0))
    flow_footer.pack(side='bottom',fill='x')
    ttk.Separator(flow_footer).pack(fill='x',pady=(0,8))
    ttk.Button(flow_footer,text='Thứ tự xử lý PIP',command=lambda: show_flow(root)).pack(fill='x')
    ttk.Label(flow_footer,text='Xem các ưu tiên đang áp dụng',wraplength=170,foreground='#666666').pack(anchor='w',pady=(5,0))

    step_names = ["1. Quét EP", "2. Tạo EP", "3. Cycle 1", "4. Các cycle", "5. Xuất M3U", "6. QC"]
    steps.insert("end", "0. Nhập thông tin")
    for name in step_names:
        steps.insert("end", name)

    content = ttk.Frame(shell)
    content.grid(row=0, column=1, sticky="nsew")
    content.rowconfigure(3, weight=1)
    content.columnconfigure(0, weight=1)
    command_bar = ttk.Frame(content, padding=(0, 2, 0, 8))
    command_bar.grid(row=0, column=0, sticky="ew")
    ttk.Label(command_bar, text="Số EP").pack(side="left")
    from episode_date import episode_today
    episode_var = tk.StringVar(value=str(episode_today()))
    preview_var = tk.StringVar(value="")
    entry = ttk.Entry(command_bar, textvariable=episode_var, width=14)
    entry.pack(side="left", padx=(8, 10))
    ttk.Button(command_bar,text='Hôm nay ↺',command=lambda: episode_var.set(str(episode_today()))).pack(side='left',padx=(0,8))
    prefs=checkbox_preferences()
    fn_var = tk.BooleanVar(value=prefs.get('fn',False))
    tser_fn_var = tk.BooleanVar(value=prefs.get('tser_fn',True))
    mt_shift_var = tk.StringVar(value=str(max(-5,min(5,int(prefs.get('mt_show_shift',0))))))
    start_block_var = tk.StringVar(value="")
    def save_checkboxes():
        path=BASE_DIR/'configs'/'checkbox_preferences.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'fn':fn_var.get(),'tser_fn':tser_fn_var.get(),'mt_show_shift':int(mt_shift_var.get())}),encoding='utf-8')
    ttk.Checkbutton(command_bar, text="FN", variable=fn_var,command=save_checkboxes).pack(side="left", padx=(4, 8))
    def save_tser_fn():
        save_checkboxes()
        ep=episode_var.get().strip()
        if not ep.isdigit():return
        path=BASE_DIR/'configs'/f'EP_{ep}_teaser_options.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'tser_fn':tser_fn_var.get()}),encoding='utf-8')
        if str(current_result.get('episode',''))==ep:
            current_result.setdefault('schedule_settings',{})['tser_fn']=tser_fn_var.get()
            if not tser_fn_var.get():
                from draft_input import item_key
                current_result['rename_preview']['items']=[i for i in current_result['rename_preview']['items'] if item_key(i)!='TSER FN']
                tree.delete(*tree.get_children())
                for index,item in enumerate(current_result['rename_preview']['items']):
                    tree.insert('','end',iid=str(index),values=(item['rule'],item['source_name'],item['target_name'],'☑' if is_max(item) else '☐'))
    ttk.Checkbutton(command_bar,text='TSER FN',variable=tser_fn_var,command=save_tser_fn).pack(side='left',padx=(0,8))

    ttk.Label(command_bar, text="Bắt đầu block").pack(side="left")
    start_block_combo = ttk.Combobox(command_bar, textvariable=start_block_var, width=5, state="readonly")
    start_block_combo["values"] = tuple(str(number) for number in range(1, 9))
    start_block_combo.pack(side="left", padx=(6, 12))
    offset_var = tk.StringVar(value='0')
    ttk.Label(command_bar, text='Lệch đầu ngày (giây)').pack(side='left')
    ttk.Entry(command_bar, textvariable=offset_var, width=7).pack(side='left', padx=5)
    ttk.Label(command_bar,text='MT shift (shows)').pack(side='left')
    mt_shift_combo=ttk.Combobox(command_bar,textvariable=mt_shift_var,values=tuple(range(-5,6)),state='readonly',width=3)
    mt_shift_combo.pack(side='left',padx=5)
    mt_shift_combo.bind('<<ComboboxSelected>>',lambda event:save_checkboxes())
    notice_bar = ttk.Frame(content, padding=(0, 0, 0, 8))
    notice_bar.grid(row=1, column=0, sticky="ew")
    ttk.Label(notice_bar, text="Thông báo lịch").pack(side="left")
    notice_var = tk.StringVar(value="")
    notice_entry = ttk.Entry(notice_bar, textvariable=notice_var)
    notice_entry.pack(side="left", fill="x", expand=True, padx=(8, 8))
    detect_status = tk.StringVar(value="")
    ttk.Label(notice_bar, textvariable=detect_status).pack(side="right", padx=(8, 0))
    page_title = ttk.Label(content, text="", font=("Segoe UI", 15, "bold"))
    page_title.grid(row=2, column=0, sticky="w", pady=(2, 10))
    page_host = ttk.Frame(content)
    page_host.grid(row=3, column=0, sticky="nsew")
    page_host.rowconfigure(0, weight=1)
    page_host.columnconfigure(0, weight=1)
    pages = []
    for _ in step_names:
        page = ttk.Frame(page_host)
        page.grid(row=0, column=0, sticky="nsew")
        pages.append(page)

    bulk_page=ttk.Frame(page_host)
    bulk_page.grid(row=0,column=0,sticky='nsew')
    pages.append(bulk_page)
    ttk.Label(bulk_page,text='Dán thời lượng, Next day will air… hoặc thông báo set from air end / Current Airing vào đây.',padding=(0,6)).pack(anchor='w')
    ttk.Label(bulk_page,text='File có sẵn được ưu tiên. Phần thiếu dùng thời lượng bạn nhập để tạo temp.',padding=(0,6)).pack(anchor='w')
    from tkinter.scrolledtext import ScrolledText
    bulk_text=ScrolledText(bulk_page,wrap='word',font=('Consolas',11),undo=True)
    bulk_text.pack(fill='both',expand=True,pady=8)
    bulk_buttons=ttk.Frame(bulk_page,padding=(0,8));bulk_buttons.pack(fill='x')
    bulk_ep=[episode_var.get().strip()]
    def persist_bulk():
        if bulk_ep[0].isdigit():
            path=BASE_DIR/'configs'/f'EP_{bulk_ep[0]}_bulk_input.txt'
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(bulk_text.get('1.0','end').strip(),encoding='utf-8')
    def load_bulk(*_args):
        persist_bulk()
        bulk_ep[0]=episode_var.get().strip()
        bulk_text.delete('1.0','end')
        path=BASE_DIR/'configs'/f'EP_{bulk_ep[0]}_bulk_input.txt'
        if path.exists():bulk_text.insert('1.0',path.read_text(encoding='utf-8'))
    initial_bulk=BASE_DIR/'configs'/f'EP_{bulk_ep[0]}_bulk_input.txt'
    if initial_bulk.exists():bulk_text.insert('1.0',initial_bulk.read_text(encoding='utf-8'))
    episode_var.trace_add('write',load_bulk)

    # Step 1: scan and edit the source-to-local naming map.
    scan_page = pages[0]
    scan_page.rowconfigure(2, weight=1)
    scan_page.columnconfigure(2, weight=1)
    output = tk.Text(scan_page, wrap="word", height=8, font=("Consolas", 9))
    output.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 8))

    table_frame = ttk.Frame(scan_page)
    table_frame.grid(row=2, column=0, columnspan=4, sticky="nsew")
    tree = ttk.Treeview(table_frame, columns=("rule", "source", "target", "max"), show="headings")
    tree.heading('max',text='☑ Max')
    tree.column('max',width=75,stretch=False,anchor='center')
    tree.heading("rule", text="Loại")
    tree.heading("source", text="Tên nguồn")
    tree.heading("target", text="Tên local — nhấp đúp để sửa")
    tree.column("rule", width=130, stretch=False)
    tree.column("source", width=450, stretch=True)
    tree.column("target", width=450, stretch=True)
    yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
    tree.tag_configure("duplicate", background="#fff2cc")
    tree.grid(row=0, column=0, sticky="nsew")
    yscroll.grid(row=0, column=1, sticky="ns")
    xscroll.grid(row=1, column=0, sticky="ew")
    table_frame.rowconfigure(0, weight=1)
    table_frame.columnconfigure(0, weight=1)
    current_result: dict = {}

    def refresh_active_blocks() -> None:
        active = [1, 3, 4, 5, 6, 7, 8] if fn_var.get() else list(range(1, 9))
        start_block_combo["values"] = tuple(str(number) for number in active)
        if start_block_var.get() and start_block_var.get() not in {str(number) for number in active}:
            start_block_var.set(str(active[0]))

    fn_var.trace_add("write", lambda *_args: refresh_active_blocks())

    # Step 2: build placeholders. It stays compact when another step is selected.
    build_page = pages[1]
    ttk.Label(build_page, text="Tạo video nhẹ theo danh sách tên đã duyệt.", font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 12))
    build_status = tk.StringVar(value="Hãy quét EP trước.")
    ttk.Label(build_page, textvariable=build_status, wraplength=800).pack(anchor="w", pady=(0, 12))

    # Step 3 is reserved exclusively for the Cycle 1 schedule.
    cycle1_page = pages[2]
    ttk.Label(cycle1_page, text="Danh sách tại đây chỉ dành cho Cycle 1.").pack(anchor="w", pady=(0, 8))
    cycle1_frame = ttk.Frame(cycle1_page)
    cycle1_frame.pack(fill="both", expand=True)
    cycle1_tree = ttk.Treeview(cycle1_frame, columns=("order", "name", "duration", "start", "end"), show="headings")
    for key, label, width in (("order", "STT", 55), ("name", "Nội dung Cycle 1", 520), ("duration", "Thời lượng", 100), ("start", "Bắt đầu", 100), ("end", "Kết thúc", 100)):
        cycle1_tree.heading(key, text=label)
        cycle1_tree.column(key, width=width, stretch=(key == "name"))
    cycle1_tree.pack(fill="both", expand=True)

    for index, text in ((3, "Các cycle sẽ được tạo từ Cycle 1 và rule Excel."), (4, "File M3U sẽ được xuất ở bước này."), (5, "Kết quả kiểm tra lịch — xem mốc MT, cuối ngày và các mục cần xử lý.")):
        ttk.Label(pages[index], text=text, font=("Segoe UI", 11)).pack(anchor="w")
    schedule_result = {}
    all_cycles_frame = ttk.Frame(pages[3])
    all_cycles_frame.pack(fill='both', expand=True)
    all_cycles = ttk.Treeview(all_cycles_frame, columns=('cycle','block','name','length','end'), show='headings')
    for key,label,width in [('cycle','Cycle',60),('block','Block',60),('name','Nội dung',540),('length','Length',110),('end','Kết thúc',110)]:
        all_cycles.heading(key,text=label); all_cycles.column(key,width=width)
    all_cycles_scroll = ttk.Scrollbar(all_cycles_frame, orient='vertical', command=all_cycles.yview)
    all_cycles.configure(yscrollcommand=all_cycles_scroll.set)
    all_cycles_scroll.pack(side='right', fill='y')
    all_cycles.pack(side='left',fill='both',expand=True)
    export_status = tk.StringVar(value='Chưa tạo lịch.')
    ttk.Label(pages[4],textvariable=export_status,wraplength=850).pack(anchor='w',pady=10)
    ttk.Button(pages[4],text='Mở thư mục kết quả',command=lambda: os.startfile(str(Path(schedule_result['m3u_path']).parent)) if schedule_result else None).pack(anchor='w')
    qc_sections=ttk.Frame(pages[5])
    qc_sections.pack(fill='both',expand=True,pady=(8,0))
    qc_sections.columnconfigure(0,weight=1)
    qc_sections.rowconfigure(0,minsize=36)
    qc_sections.rowconfigure(2,minsize=36)
    overview_open=tk.BooleanVar(value=True)
    detail_open=tk.BooleanVar(value=False)
    def refresh_qc_sections():
        overview_button.configure(text=('▼' if overview_open.get() else '▶')+' Tổng quát')
        detail_button.configure(text=('▼' if detail_open.get() else '▶')+' Check bình thường — Cycle 1 và các cycle')
        for row,frame,opened in ((1,qc_frame,overview_open.get()),(3,detail_frame,detail_open.get())):
            qc_sections.rowconfigure(row,weight=1 if opened else 0,minsize=0)
            if opened: frame.grid(row=row,column=0,sticky='nsew')
            else: frame.grid_remove()
    def toggle_overview():
        overview_open.set(not overview_open.get())
        refresh_qc_sections()
    overview_button=ttk.Button(qc_sections,text='▼ Tổng quát',command=toggle_overview)
    overview_button.grid(row=0,column=0,sticky='ew',pady=(0,4))
    qc_frame=ttk.Frame(qc_sections)

    qc_text = tk.Text(qc_frame,wrap='word',height=1,font=('Segoe UI',11),padx=16,pady=12,
                      spacing1=3,spacing3=5,relief='flat',state='disabled')
    qc_scroll=ttk.Scrollbar(qc_frame,orient='vertical',command=qc_text.yview)
    qc_text.configure(yscrollcommand=qc_scroll.set)
    qc_scroll.pack(side='right',fill='y');qc_text.pack(side='left',fill='both',expand=True)
    qc_text.tag_configure('heading',font=('Segoe UI',12,'bold'),foreground='#183C59',spacing1=12)
    qc_text.tag_configure('warning',foreground='#C62828')
    qc_text.tag_configure('pass',foreground='#176B46')
    qc_text.tag_configure('notice',foreground='#8A6500')
    detail_frame=ttk.Frame(qc_sections)
    def toggle_cycle_check():
        detail_open.set(not detail_open.get())
        refresh_qc_sections()
    detail_button=ttk.Button(qc_sections,text='▶ Check bình thường — Cycle 1 và các cycle',command=toggle_cycle_check)
    detail_button.grid(row=2,column=0,sticky='ew',pady=(4,4))
    detail_text=tk.Text(detail_frame,wrap='word',height=1,font=('Segoe UI',11),padx=16,pady=10,spacing3=5,state='disabled')
    detail_scroll=ttk.Scrollbar(detail_frame,orient='vertical',command=detail_text.yview)
    detail_text.configure(yscrollcommand=detail_scroll.set)
    detail_scroll.pack(side='right',fill='y');detail_text.pack(side='left',fill='both',expand=True)
    detail_text.tag_configure('pass',foreground='#176B46')
    detail_text.tag_configure('notice',foreground='#8A6500')
    detail_text.tag_configure('warning',foreground='#C62828')
    detail_text.tag_configure('heading',font=('Segoe UI',12,'bold'),foreground='#183C59',spacing1=10)

    def display_report(widget,report):
        for child in widget.winfo_children(): child.destroy()
        widget.configure(state='normal');widget.delete('1.0','end')
        table=None;ads_table=None
        for line in report.splitlines():
            ads_match=re.match(r'^([✓✗]) (.*?) — ADS: (\d+) cycle; (\d+) lần; cycle (.*?)\.$',line)
            if widget is qc_text and ads_match:
                if ads_table is None:
                    ads_table=ttk.Treeview(widget,columns=('name','count','plays','cycles'),show='headings',height=1)
                    for key,title,width in [('name','Tên ADS',480),('count','Số cycle',80),('plays','Số lần',70),('cycles','Cycle sử dụng',180)]:
                        ads_table.heading(key,text=title);ads_table.column(key,width=width,anchor='w' if key=='name' else 'center')
                    ads_table.tag_configure('green',foreground='#176B46',background='#F1F8F4')
                    ads_table.tag_configure('red',foreground='#C62828',background='#FFF2F2')
                    widget.window_create('end',window=ads_table);widget.insert('end','\n')
                symbol,name,count,plays,cycles=ads_match.groups()
                ads_table.insert('','end',values=(name,count,plays,cycles),tags=('green' if int(count)>3 else 'red',))
                ads_table.configure(height=len(ads_table.get_children()))
                continue
            if widget is qc_text and line.startswith('⚠ Bản nháp:'):
                from qc_report import reported_items_panel
                items=schedule_result.get('reported_items')
                if items is None:
                    items=[{'name':i['target_name'],'seconds':i['draft_duration']} for i in current_result.get('rename_preview',{}).get('items',[]) if i.get('draft_duration')]
                panel=reported_items_panel(widget,line,items)
                widget.window_create('end',window=panel)
                widget.insert('end','\n')
                continue
            match=re.match(r'^([✓✗⚠]) (.*?) — quy định cycle (.*?); thực tế (.*?)\.$',line)
            if widget is detail_text and match:
                if table is None:
                    style=ttk.Style()
                    style.configure('QC.Treeview',font=('Segoe UI',10),rowheight=29)
                    style.configure('QC.Treeview.Heading',font=('Segoe UI',10,'bold'))
                    table=ttk.Treeview(widget,columns=('status','name','expected','actual'),show='headings',height=1,style='QC.Treeview',selectmode='none')
                    for key,title,width in [('status','Kết quả',75),('name','Nội dung',280),('expected','Cycle quy định',170),('actual','Cycle thực tế',170)]:
                        table.heading(key,text=title)
                        table.column(key,width=width,minwidth=60,anchor='w' if key=='name' else 'center',stretch=key=='name')
                    table.tag_configure('pass',foreground='#176B46',background='#F1F8F4')
                    table.tag_configure('warning',foreground='#C62828',background='#FFF2F2')
                    table.tag_configure('notice',foreground='#8A6500',background='#FFF4BF')
                    widget.window_create('end',window=table)
                    widget.insert('end','\n\n')
                symbol,name,expected,actual=match.groups()
                names={'bmd m intro long':'BMD M intro long','bmd m intro short':'BMD M intro short',
                       'wow m intro long':'WOW M intro long','wow m intro short':'WOW M intro short',
                       'm qy warning':'M QY Warning','abortion 07':'Abortion 07','hygiene':'Hygiene'}
                table.insert('','end',values=(symbol,names.get(name,name),expected,actual),tags=('pass' if symbol=='✓' else 'notice' if symbol=='⚠' else 'warning',))
                table.configure(height=len(table.get_children()))
                continue
            tag='warning' if '✗' in line else 'notice' if '⚠' in line else 'pass' if '✓' in line else 'heading' if re.match(r'^\d+\. |^Cycle \d+$|^KIỂM TRA|^KHÁC BIỆT',line) else ''
            widget.insert('end',line+'\n',(tag,) if tag else ())
        widget.configure(state='disabled')

    refresh_qc_sections()

    def mark_step(index: int, done: bool = True) -> None:
        base = step_names[index]
        steps.delete(index+1)
        steps.insert(index+1, ("✓ " if done else "") + base)

    def show_page(index: int) -> None:
        pages[index].tkraise()
        page_title.config(text="0. Nhập thông tin" if index==-1 else step_names[index])
        steps.selection_clear(0, "end")
        steps.selection_set(index+1)
        steps.activate(index+1)

    steps.bind("<<ListboxSelect>>", lambda _event: show_page(steps.curselection()[0]-1) if steps.curselection() else None)

    def apply_air_notice(text):
        from air_notice import parse_air_start
        timing=parse_air_start(text)
        if timing:
            offset_var.set(str(timing['offset_seconds']))
            current_result['air_start_notice']=timing
            detect_status.set(f"Bắt đầu {timing['start_time']} | lệch {timing['offset_seconds']:+d}s so với 01:00:00")
        return timing

    def detect_start_block(show_message: bool = True) -> bool:
        sentence = notice_var.get().strip()
        if not sentence or not current_result:
            if show_message:
                messagebox.showinfo("Nhận diện block", "Hãy nhập thông báo lịch và Scan EP trước.")
            return False
        from start_notice import infer_start
        from air_notice import without_air_lines
        try: timing=apply_air_notice(sentence)
        except ValueError as exc:
            detect_status.set(str(exc))
            if show_message:messagebox.showerror('Giờ bắt đầu',str(exc))
            return False
        sentence=without_air_lines(sentence).strip()
        if timing and not sentence:return True
        block, message = infer_start(sentence, current_result['program'], fn_var.get(), current_result['episode'])
        detect_status.set(message)
        if block is None:
            start_block_var.set('')
            if show_message:
                messagebox.showinfo('Nhận diện block', message)
            return False
        start_block_var.set(str(block))
        current_result['start_notice'] = sentence
        return True

    def do_scan() -> bool:
        try:
            show_page(0)
            episode = int(episode_var.get().strip())
            result = scan_episode(episode)
            output.delete("1.0", "end")
            output.insert("1.0", summary(result))
            preview_var.set(result["rename_preview"]["path"])
            current_result.clear()
            current_result.update(result)
            fn_var.set(checkbox_preferences().get("fn",result["program"]["schedule_type"] == "FN"))
            refresh_active_blocks()
            current_result["schedule_settings"] = {
                "fn": fn_var.get(),
                "tser_fn": tser_fn_var.get(),
                "start_block": int(start_block_var.get()) if start_block_var.get() else None,
                "active_blocks": [int(value) for value in start_block_combo["values"]],
            }
            tree.delete(*tree.get_children())
            names = [item["target_name"].casefold() for item in result["rename_preview"]["items"]]
            for index, item in enumerate(result["rename_preview"]["items"]):
                tags = ("duplicate",) if names.count(item["target_name"].casefold()) > 1 else ()
                tree.insert("", "end", iid=str(index), values=(item["rule"], item["source_name"], item["target_name"], '☑' if is_max(item) else '☐'), tags=tags)
            build_status.set(f"EP {episode} đã quét xong: {len(result['rename_preview']['items'])} file sẵn sàng tạo.")
            mark_step(0)
            show_page(0)
            if notice_var.get().strip():
                detect_start_block(show_message=False)
            return True
        except Exception as exc:
            messagebox.showerror("Scan EP", str(exc))
            return False

    def edit_target(event) -> None:
        if tree.identify_column(event.x) != "#3":
            return
        item_id = tree.identify_row(event.y)
        if not item_id:
            return
        box = tree.bbox(item_id, "target")
        if not box:
            return
        x, y, width, height = box
        editor = ttk.Entry(tree)
        editor.insert(0, tree.set(item_id, "target"))
        editor.select_range(0, "end")
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()
        committed = False

        def commit(_event=None) -> None:
            nonlocal committed
            if committed:
                return
            committed = True
            new_name = editor.get().strip()
            if new_name:
                tree.set(item_id, "target", new_name)
                if current_result:
                    item = current_result["rename_preview"]["items"][int(item_id)]
                    item["target_name"] = new_name
                    item["target_path"] = str(Path(item['target_path']).parent / new_name)
                    if 'is_max' in item:remember(current_result['episode'],item)
            editor.destroy()

        editor.bind("<Return>", commit)
        editor.bind("<Escape>", lambda _event: editor.destroy())
        editor.bind("<FocusOut>", commit)

    def toggle_max(event):
        if tree.identify_column(event.x)!='#4':return
        row=tree.identify_row(event.y)
        if not row:return
        item=current_result['rename_preview']['items'][int(row)]
        from max_options import is_draft_item
        if not is_draft_item(item):return 'break'
        if is_no_max(item):
            messagebox.showinfo('Max','Dòng này là bản No Max. Hãy tick trên dòng bản Max tương ứng.')
            return 'break'
        item['is_max']=not is_max(item)
        remember(current_result['episode'],item)
        tree.set(row,'max','☑' if is_max(item) else '☐')
        return 'break'

    def save_edits(notify: bool = True) -> bool:
        if not current_result:
            messagebox.showinfo("Lưu tên", "Hãy Scan EP trước.")
            return False
        items = current_result["rename_preview"]["items"]
        current_result["schedule_settings"] = {
            "fn": fn_var.get(),
                "tser_fn": tser_fn_var.get(),
            "offset_seconds": float(offset_var.get() or 0),
            "mt_show_shift": int(mt_shift_var.get()),
            "start_block": int(start_block_var.get()) if start_block_var.get() else None,
            "active_blocks": [int(value) for value in start_block_combo["values"]],
        }
        # Respect the FN checkbox even when the pasted sheet does not mark FN.
        preview = current_result['rename_preview']
        want_fn = fn_var.get()
        if want_fn and preview.get('fn_source_episode') is None:
            program = dict(current_result['program'], schedule_type='FN')
            refreshed = create_rename_preview(Path(current_result['source_dir']), Path(current_result['local_dir']), int(current_result['episode']), program)
            saved_names = {r['source_path']: r['target_name'] for r in items if not r.get('draft_out_variant')}
            for r in refreshed['items']:
                if r['source_path'] in saved_names:
                    r['target_name'] = saved_names[r['source_path']]
                    r['target_path'] = str(Path(r['target_path']).parent/r['target_name'])
            current_result['rename_preview'] = refreshed
            items = refreshed['items']
            if current_result.get('draft_mode'):
                from draft_input import merge_reported
                merge_reported(current_result,current_result.get('reported_durations',{}))
                items=current_result['rename_preview']['items']
        targets = [item["target_name"].casefold() for item in items]
        apply_choices(current_result)
        duplicates = sorted({name for name in targets if targets.count(name) > 1})
        if duplicates:
            details=[]
            for name in duplicates:
                group=[item for item in items if item['target_name'].casefold()==name]
                details.append(group[0]['target_name']+'\n'+'\n'.join('  - '+item['source_name'] for item in group))
            messagebox.showerror("Lưu tên", "Có tên local bị trùng. Hãy sửa trước khi lưu."+'\n\n'+'\n\n'.join(details))
            return False
        preview_path = Path(current_result["rename_preview"]["path"])
        try:
            handle = preview_path.open("w", newline="", encoding="utf-8-sig")
        except PermissionError:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            preview_path = preview_path.with_name(f"EP_{current_result['episode']}_rename_preview_{stamp}.csv")
            handle = preview_path.open("w", newline="", encoding="utf-8-sig")
        with handle:
            writer = csv.DictWriter(handle, fieldnames=["rule", "source_name", "target_name", "source_path", "target_path"],extrasaction='ignore')
            writer.writeheader()
            writer.writerows(items)
        current_result["rename_preview"]["path"] = str(preview_path)
        preview_var.set(str(preview_path))
        config_path = Path(current_result["config_path"])
        saved = {key: val for key, val in current_result.items() if key != "config_path"}
        config_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
        if notify:
            messagebox.showinfo("Lưu tên", f"Đã lưu {len(items)} tên.\n{preview_path}")
        return True

    def create_ep(notify: bool = True) -> bool:
        try:
            show_page(1)
            if not save_edits(notify=False):
                return False
            root.config(cursor="watch")
            root.update_idletasks()
            command = [sys.executable, str(BASE_DIR / "create_episode.py"), current_result["config_path"]]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            completed = subprocess.run(command, check=True, capture_output=True, text=True, creationflags=flags)
            result = json.loads(completed.stdout)
            archive = f"\nTên cũ lưu tại: {result['archive']}" if result.get("archive") else ""
            ads_missing = result.get("do_not_skip_ads_missing", [])
            ads_line = (
                f"\nDO NOT SKIP: copy mới {result.get('do_not_skip_ads_copied', 0)}, "
                f"đã có {result.get('do_not_skip_ads_kept', 0)}, chưa tìm thấy {len(ads_missing)}."
            )
            if ads_missing:
                ads_line += "\nChưa tìm: " + "; ".join(ads_missing)
            if notify: messagebox.showinfo(
                "Tạo EP",
                f"Đã tạo EP {result['episode']}: {result['files']} file.\n"
                f"Tạo mới: {result['created']}; đã có sẵn: {result['kept']}"
                f"{ads_line}{archive}\nManifest: {result['manifest']}",
            )
            build_status.set(f"EP {result['episode']} hoàn tất: {result['files']} file. Manifest: {result['manifest']}")
            mark_step(1)
            show_page(1)
            return True
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Tạo EP", (exc.stderr or exc.stdout or str(exc)).strip())
        except Exception as exc:
            messagebox.showerror("Tạo EP", str(exc))
        finally:
            root.config(cursor="")
        return False

    def create_schedule(notify: bool = True) -> bool:
        show_page(2)
        if not current_result:
            messagebox.showinfo("Tạo lịch", "Hãy Scan EP trước.")
            return
        if not start_block_var.get():
            messagebox.showinfo("Tạo lịch", "Hãy chọn block bắt đầu.")
            return
        if not save_edits(notify=False):
            return
        cycle1_tree.delete(*cycle1_tree.get_children())
        try:
            schedule = build_schedule(Path(current_result["config_path"]))
            from schedule_timing import clock as precise_clock
            schedule_result.clear();schedule_result.update(schedule)
            all_cycles.delete(*all_cycles.get_children())
            for c in schedule['cycles']:
                for r in c['rows']:
                    all_cycles.insert('', 'end', values=(c['cycle'],r['block'],r['name'],precise_clock(r['duration']),precise_clock(r['end_seconds'])))
            export_status.set(('ĐẠT' if schedule['valid'] else 'BẢN NHÁP — xem QC')+'\n'+schedule['m3u_path']+'\nTimeline: '+schedule['timeline_path'])
            report=Path(schedule['qc_path']).read_text('utf-8-sig')
            display_report(qc_text,report)
            from qc_report import render_cycle_check
            display_report(detail_text,render_cycle_check(schedule,current_result.get('cycle_rules',{})))
            elapsed = 0.0
            cycle1 = schedule["cycles"][0]["rows"]
            def clock(seconds: float) -> str:
                value = int(round(seconds))
                return f"{value // 3600:02d}:{value % 3600 // 60:02d}:{value % 60:02d}"
            for index, row in enumerate(cycle1, 1):
                start = row.get('start_seconds',elapsed)
                elapsed = row.get('end_seconds',start+row['duration'])
                cycle1_tree.insert("", "end", values=(index, f"[B{row['block']}] {row['name']}", clock(row["duration"]), clock(start), clock(elapsed)))
            if schedule["missing"] and notify:
                messagebox.showwarning("Tạo lịch — bản nháp", '\n'.join(schedule['missing']) + '\n\nM3U: '+schedule['m3u_path']+'\nQC: '+schedule['qc_path'])
            elif not schedule["missing"] and notify:
                mark_step(2, done=True)
                messagebox.showinfo(
                    "Lịch đã tạo",
                    'Đã chèn ADS, chọn Max/No Max và kiểm tra mốc 20:00.\nM3U: '+schedule['m3u_path'],
                )
            show_page(2)
            return True
        except Exception as exc:
            messagebox.showerror("Tạo lịch", str(exc))
            return False

    def refresh_selected_sources():
        saved_names={r['source_path']:r['target_name'] for r in current_result['rename_preview']['items']}
        program=dict(current_result['program'])
        if fn_var.get():program['schedule_type']='FN'
        refreshed=create_rename_preview(Path(current_result['source_dir']),Path(current_result['local_dir']),int(current_result['episode']),program)
        for item in refreshed['items']:
            if item['source_path'] in saved_names and not item.get('manual_kind'):
                item['target_name']=saved_names[item['source_path']]
                item['target_path']=str(Path(item['target_path']).parent/item['target_name'])
        current_result['rename_preview']=refreshed
        if current_result.get('reported_durations'):
            from draft_input import merge_reported
            merge_reported(current_result,current_result['reported_durations'])
        tree.delete(*tree.get_children())
        for index,item in enumerate(current_result['rename_preview']['items']):
            tree.insert('','end',iid=str(index),values=(item['rule'],item['source_name'],item['target_name'],'☑' if is_max(item) else '☐'))
        return save_edits(notify=False)

    def run_all() -> None:
        persist_bulk()
        controls=list(command_bar.winfo_children())+[run_button,prepare_button,update_prepare_button]
        states=[(widget,str(widget.cget('state'))) for widget in controls if 'state' in widget.keys()]
        for widget,_state in states: widget.configure(state='disabled')
        try:
            same_ep=str(current_result.get('episode',''))==episode_var.get().strip()
            saved_names={r['source_path']:r['target_name'] for r in current_result.get('rename_preview',{}).get('items',[]) if not r.get('draft_out_variant')} if same_ep else {}
            selected_fn=fn_var.get() if same_ep or fn_var.get() else None
            build_status.set('1/3 — Đang quét EP…')
            root.update_idletasks()
            if not do_scan(): return
            if selected_fn is not None:
                fn_var.set(selected_fn)
                refresh_active_blocks()
                if notice_var.get().strip(): detect_start_block(show_message=False)
            for index,item in enumerate(current_result['rename_preview']['items']):
                if item['source_path'] in saved_names:
                    item['target_name']=saved_names[item['source_path']]
                    item['target_path']=str(Path(item['target_path']).parent/item['target_name'])
                    tree.set(str(index),'target',item['target_name'])
            bulk_path=BASE_DIR/'configs'/f"EP_{current_result['episode']}_bulk_input.txt"
            if bulk_path.exists() and bulk_path.read_text(encoding='utf-8').strip():
                apply_bulk(bulk_path.read_text(encoding='utf-8'))
            if not start_block_var.get():
                show_page(0)
                messagebox.showinfo('Chạy tất cả', 'Nhập thông báo bắt đầu hoặc chọn block bắt đầu, rồi bấm ▶ Chạy tất cả.')
                return
            if not save_edits(notify=False):return
            from missing_media import resolve_dialog
            while True:
                action,changed=resolve_dialog(root,current_result)
                if action=='cancel':return
                if changed and not refresh_selected_sources():return
                if action!='retry':break
            build_status.set('2/3 — Đang tạo EP, giữ lại các file đã có phù hợp…')
            root.update_idletasks()
            if not create_ep(notify=False): return
            build_status.set('3/3 — Đang xếp lịch, canh giờ và kiểm tra QC…')
            root.update_idletasks()
            while True:
                if not create_schedule(notify=False):return
                action,changed=resolve_dialog(root,current_result,schedule_result)
                if action=='cancel':
                    show_page(5);return
                if changed or action=='retry':
                    if not refresh_selected_sources() or not create_ep(notify=False):return
                    continue
                break
            if schedule_result:
                mark_step(3)
                mark_step(4)
                mark_step(5, done=bool(schedule_result.get('valid')))
                build_status.set('Đã chạy xong — '+('QC đạt.' if schedule_result.get('valid') else 'Xem các mục cần xử lý trong QC.'))
                show_page(5)
        except Exception as exc:
            messagebox.showerror('Chạy tất cả',str(exc))
        finally:
            for widget,state in states: widget.configure(state=state)
            root.config(cursor='')

    prepare_cancel=[None]
    def stop_preparing():
        if prepare_cancel[0] is not None:
            prepare_cancel[0].set()
            stop_prepare_button.configure(state='disabled')
            build_status.set('Đang dừng chuẩn bị file và dọn bản copy dở…')

    def prepare_files(mode="prepare"):
        if str(current_result.get('episode',''))!=episode_var.get().strip():
            if not do_scan():return
        if not save_edits(notify=False):return
        source_dir=Path(current_result['source_dir']).resolve()
        destination=source_dir/'temp'
        saved_names={r['source_path']:r['target_name'] for r in current_result['rename_preview']['items'] if not r.get('draft_out_variant')}
        program=dict(current_result['program'])
        if fn_var.get():program['schedule_type']='FN'
        refreshed=create_rename_preview(source_dir,Path(current_result['local_dir']),int(current_result['episode']),program)
        for item in refreshed['items']:
            if item['source_path'] in saved_names:
                item['target_name']=saved_names[item['source_path']]
                item['target_path']=str(Path(item['target_path']).parent/item['target_name'])
        current_result['rename_preview']=refreshed
        tree.delete(*tree.get_children())
        for index,item in enumerate(refreshed['items']):
            tree.insert('', 'end', iid=str(index), values=(item['rule'],item['source_name'],item['target_name'],'☑' if is_max(item) else '☐'))
        if not save_edits(notify=False):return
        rows=[dict(item) for item in current_result['rename_preview']['items']
              if item.get('source_path') and not item.get('draft_duration')
              and Path(item['source_path']).resolve().parent==source_dir]
        if not rows:
            messagebox.showinfo('Chuẩn bị file','Chưa có file nguồn ở thư mục EP để copy.');return
        import threading,queue
        from prepare_files import copy_prepared_files
        messages=queue.Queue()
        prepare_cancel[0]=threading.Event()
        cancel=prepare_cancel[0]
        def widgets(parent):
            for widget in parent.winfo_children():
                yield widget
                yield from widgets(widget)
        controls=[w for w in widgets(root) if isinstance(w,(tk.Button,ttk.Button))]
        states=[(w,str(w.cget('state'))) for w in controls]
        for w,_ in states:w.configure(state='disabled')
        stop_prepare_button.configure(state='normal')
        root.config(cursor='watch')
        build_status.set(f'Chuẩn bị {len(rows)} file → {destination}')
        def worker():
            try:
                result=copy_prepared_files(rows,destination,lambda n,total,name:messages.put(('progress',f'{n}/{total}: {name}')),cancel=cancel,mode=mode)
                messages.put(('done',result))
            except Exception as exc:messages.put(('error',str(exc)))
        def poll():
            finished=False
            while not messages.empty():
                kind,value=messages.get()
                if kind=='progress':
                    if not cancel.is_set():build_status.set(value)
                    continue
                finished=True
                for w,state in states:w.configure(state=state)
                root.config(cursor='')
                prepare_cancel[0]=None
                stop_prepare_button.configure(state='disabled')
                if kind=='done':
                    status=("Đã dừng" if value.get("stopped") else "Chuẩn bị xong")+f": copy {value['copied']}; đã có {value['kept']}; bỏ qua {len(value['skipped'])} file."
                    build_status.set(status)
                    report=tk.Toplevel(root);report.title('Kết quả chuẩn bị file');report.geometry('850x550')
                    ttk.Label(report,text=status,padding=10).pack(anchor='w')
                    from tkinter.scrolledtext import ScrolledText
                    body=ScrolledText(report,wrap='word');body.pack(fill='both',expand=True,padx=10,pady=6)
                    lines=[value['destination'],'']
                    labels={'recorded':'Đã xử lý trước đó','copied':'Đã copy','kept':'Đã có','skipped':'Bỏ qua','cancelled':'Chưa copy — đã dừng'}
                    for item in value['details']:
                        lines.append(labels[item['status']]+': '+item['target'])
                        if item.get('reason'):lines.append('  Lý do: '+item['reason'])
                    body.insert('1.0','\n'.join(lines));body.configure(state='disabled')
                    ttk.Button(report,text='Đóng',command=report.destroy).pack(pady=8)
                else:
                    build_status.set('Chuẩn bị file chưa hoàn tất. Các file copy xong được giữ để tiếp tục lần sau.')
                    messagebox.showerror('Chuẩn bị file',value)
            if not finished:root.after(150,poll)
        threading.Thread(target=worker,daemon=True).start();root.after(150,poll)

    run_buttons=ttk.Frame(run_panel)
    run_buttons.pack()
    prepare_button=tk.Button(run_header,text='CHUẨN BỊ FILE',command=prepare_files,
                             font=('Segoe UI',10,'bold'),bg='#245B86',fg='white',relief='flat',padx=16,pady=10)
    prepare_button.pack(side='left',padx=(24,0))
    update_prepare_button=tk.Button(run_header,text='UPDATE',command=lambda:prepare_files('update'),font=('Segoe UI',10,'bold'),bg='#245B86',fg='white',relief='flat',padx=12,pady=10)
    update_prepare_button.pack(side='left',padx=(8,0))
    stop_prepare_button=tk.Button(run_header,text='■ DỪNG CHUẨN BỊ',command=stop_preparing,state='disabled',fg='#A42121',padx=10,pady=10)
    stop_prepare_button.pack(side='left',padx=(8,0))
    def update_pip():
        if str(run_button.cget('state'))=='disabled' or str(stop_prepare_button.cget('state'))=='normal':
            messagebox.showinfo('Update PIP','Finish the current operation before updating PIP.')
            return
        from pip_update_ui import show_update
        show_update(root)
    ttk.Button(run_header,text='Update PIP',command=update_pip).pack(side='left',padx=(16,0))
    run_button = tk.Button(run_buttons, text='▶  CHẠY TẤT CẢ', command=run_all,
                           font=('Segoe UI', 11, 'bold'), bg='#176B46', fg='white',
                           activebackground='#125438', activeforeground='white',
                           relief='flat', padx=20, pady=9, cursor='hand2')
    run_button.pack(side='left')
    ttk.Label(run_panel, text='Quét EP → Tạo EP → Tạo lịch → QC', font=('Segoe UI', 9)).pack(pady=(4, 0))
    ttk.Button(command_bar, text="Scan EP", command=do_scan).pack(side="left")
    ttk.Button(command_bar, text="Tạo EP", command=create_ep).pack(side="left", padx=(6, 0))
    ttk.Button(command_bar, text="Tạo lịch", command=create_schedule).pack(side="left", padx=(6, 0))
    ttk.Button(notice_bar, text="Nhận diện", command=detect_start_block).pack(side="right")
    aux_buttons = ttk.Frame(scan_page)
    aux_buttons.grid(row=3, column=0, columnspan=4, sticky="e", pady=(8, 0))
    def edit_draft():
        if not current_result and not do_scan():return False
        from draft_input import open_editor
        if not open_editor(root,current_result):return False
        tree.delete(*tree.get_children())
        for index,item in enumerate(current_result['rename_preview']['items']):
            tree.insert('','end',iid=str(index),values=(item['rule'],item['source_name'],item['target_name'],'☑' if is_max(item) else '☐'))
        return save_edits(notify=False)
    def apply_bulk(text):
        from draft_input import read_bulk_message,storage,merge_reported
        values,notice=read_bulk_message(text,current_result['episode'])
        import hashlib
        digest=hashlib.sha256(text.strip().encode('utf-8')).hexdigest()
        applied=BASE_DIR/'configs'/f"EP_{current_result['episode']}_bulk_applied.txt"
        already_applied=applied.exists() and applied.read_text(encoding='utf-8')==digest
        air_timing=apply_air_notice(text)
        if not values and not notice and not air_timing:raise ValueError('Hãy dán thời lượng hoặc thông báo bắt đầu lịch.')
        path=storage(current_result)
        data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if already_applied:values={}
        if any(k.startswith('FN P') for k in values):
            data={k:v for k,v in data.items() if not k.startswith('FN P')}
        for key,value in values.items():
            if value.get('variant')=='Chưa xác định' and key in data:
                value['variant']=data[key].get('variant','Chưa xác định')
        data.update(values)
        if any(k.startswith('FN P') for k in data) and 'fn' not in checkbox_preferences():
            fn_var.set(True);refresh_active_blocks()
            current_result['program']['schedule_type']='FN'
        if notice:
            notice_var.set(notice)
            if not detect_start_block(show_message=False):raise ValueError(detect_status.get())
        current_result['schedule_settings']={'fn':fn_var.get(),'tser_fn':tser_fn_var.get(),'start_block':int(start_block_var.get()) if start_block_var.get() else None,
                                           'active_blocks':[int(v) for v in start_block_combo['values']]}
        merge_reported(current_result,data)
        tree.delete(*tree.get_children())
        for index,item in enumerate(current_result['rename_preview']['items']):
            tree.insert('','end',iid=str(index),values=(item['rule'],item['source_name'],item['target_name'],'☑' if is_max(item) else '☐'))
        if not save_edits(notify=False):raise ValueError('Cần xử lý thông tin trong bảng tên trước khi tiếp tục.')
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        applied.write_text(digest,encoding='utf-8')

    def save_bulk_input():
        try:
            persist_bulk()
            if str(current_result.get('episode',''))!=episode_var.get().strip() and not do_scan():return
            apply_bulk(bulk_text.get('1.0','end').strip())
            show_page(-1)
            build_status.set('Đã đọc và lưu thông tin. Bấm Chạy tất cả để tiếp tục.')
        except Exception as exc:messagebox.showerror('Thông tin tổng',str(exc))
    ttk.Button(bulk_buttons,text='Đọc và lưu thông tin',command=save_bulk_input).pack(side='right',padx=6)
    ttk.Button(bulk_buttons,text='▶ Chạy tất cả',command=run_all).pack(side='right',padx=6)
    def close_pipeline():
        save_checkboxes();persist_bulk();root.destroy()
    root.protocol('WM_DELETE_WINDOW',close_pipeline)
    ttk.Button(notice_bar,text='Nhập thời lượng',command=edit_draft).pack(side='right',padx=4)
    ttk.Button(aux_buttons, text="Mở bảng đầu vào", command=lambda: open_spreadsheet(WORKBOOK_PATH)).pack(side="left", padx=(0, 8))
    ttk.Button(aux_buttons, text="Mở bảng ADS", command=lambda: open_spreadsheet(ADS_CATALOG_PATH)).pack(side="left", padx=(0, 8))
    ttk.Button(
        aux_buttons,
        text="Mở bảng đổi tên",
        command=lambda: os.startfile(preview_var.get()) if preview_var.get() else None,
    ).pack(side="left")
    ttk.Button(aux_buttons, text="Lưu tên đã sửa", command=save_edits).pack(side="left", padx=(8, 0))
    tree.bind("<Double-1>", edit_target)
    tree.bind('<Button-1>',toggle_max)
    entry.bind("<Return>", lambda _event: do_scan())
    notice_entry.bind("<Return>", lambda _event: detect_start_block())
    bulk_text.focus_set()
    show_page(-1)
    root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", type=int)
    parser.add_argument("--no-gui", action="store_true")
    args = parser.parse_args()
    if args.episode is not None:
        result = scan_episode(args.episode)
        print(summary(result))
        return 0
    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
