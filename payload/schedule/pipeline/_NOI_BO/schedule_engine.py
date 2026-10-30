from __future__ import annotations
from media_labels import is_no_next, canonical_no_next, NO_NEXT_PATTERN

import json
import re
import subprocess
from schedule_assets import Assets
from pathlib import Path


def duration_seconds(path: Path) -> float:
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True, creationflags=flags,
    )
    return float(result.stdout.strip())


def cycles_from_text(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"\d+", text or "")}


def natural_key(path: Path) -> list:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def fn_order_key(path: Path):
    name=path.stem.upper()
    ep=re.match(r'(\d+)',name)
    reair=bool(re.search(r'RE[ _-]*AIR',name))
    part=re.search(r'\bP(?:ART\s*)?(\d+)([AB]?)(?=[ _.(]|$)',name)
    group=re.sub(r'\bP(?:ART\s*)?\d+[AB]?(?=[ _.(]|$)', '', name)
    return (-(int(ep[1]) if ep else 0), reair, group,
            int(part[1]) if part else 0, part[2] if part else '', name)


def find_one(files: list[Path], *parts: str, exclude: tuple[str, ...] = ()) -> Path | None:
    matches = []
    for path in files:
        upper = path.name.upper()
        if is_no_next(path.name) and not any(is_no_next(part) for part in parts):continue
        if all(part.upper() in upper for part in parts) and not any(part.upper() in upper for part in exclude):
            matches.append(path)
    return sorted(matches, key=natural_key)[0] if matches else None


def choose_in(files: list[Path], prefix: str, treatment: str, no_max: bool) -> Path | None:
    required = [prefix, " IN"]
    if treatment:
        required.append(treatment)
    excluded = []
    if not treatment:
        excluded.extend([" LONG", " SHORT"])
    candidates = []
    for path in files:
        upper = path.name.upper()
        if not all(part in upper for part in required) or any(part in upper for part in excluded):
            continue
        is_no_max = "NO MAX" in upper
        if is_no_max == no_max:
            candidates.append(path)
    if not candidates and no_max:
        return choose_in(files, prefix, treatment, False)
    return sorted(candidates, key=natural_key)[0] if candidates else None


def bmd_treatment(rules: dict, cycle: int) -> str:
    for key, value in rules.items():
        low = key.casefold()
        if "bmd" in low and "long" in low and cycle in cycles_from_text(value):
            return "LONG"
        if "bmd" in low and "short" in low and cycle in cycles_from_text(value):
            return "SHORT"
    return ""


def wow_treatment(rules: dict, cycle: int) -> str:
    for key, value in rules.items():
        low = key.casefold()
        if "wow" in low and "long" in low and cycle in cycles_from_text(value):
            return "LONG"
        if "wow" in low and "short" in low and cycle in cycles_from_text(value):
            return "SHORT"
    return ""


def next_show_after(block: int, order: list[int]) -> str:
    show_types = {1: "WOW", 2: "SHOW1", 5: "SHOW2", 6: "SHOW3"}
    pos = order.index(block)
    for offset in range(1, len(order) + 1):
        candidate = order[(pos + offset) % len(order)]
        if candidate in show_types:
            return show_types[candidate]
    return ""


def bmd_next_code(block, order, program):
    shows={1:program.get('slot1_family','WOW')}
    for show in program.get('active_shows',[]):
        slot=show.get('output_slot',show.get('slot'))
        if slot in (1,2,3):shows[{1:2,2:5,3:6}[slot]]=show_code(show.get('code',''))
    pos=order.index(block)
    for offset in range(1,len(order)+1):
        code=shows.get(order[(pos+offset)%len(order)])
        if code:return code
    return ''


def build_schedule(config_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    from ap_rules import slot_family
    config['program']['slot1_family']=slot_family(config['episode'],config['program'],Path(config['local_dir']).glob('*.mp4'))
    settings = config.get("schedule_settings") or {}
    start = settings.get("start_block")
    if not start:
        raise ValueError("Chưa chọn block bắt đầu")
    fn = bool(settings.get("fn"))
    active = [1, 3, 4, 5, 6, 7, 8] if fn else list(range(1, 9))
    if start not in active:
        raise ValueError(f"Block {start} không hợp lệ")
    order = active[active.index(start):] + active[:active.index(start)]
    local = Path(config["local_dir"])
    files = sorted(local.glob("*.mp4"), key=natural_key)
    raw_sources={str(Path(i['source_path'])).casefold() for i in config.get('rename_preview',{}).get('items',[])
                 if i.get('source_path') and i['source_path']!=i['target_path'] and Path(i['target_path']).exists()}
    files=[p for p in files if str(p).casefold() not in raw_sources]
    if fn:
        shared=[Path(item['target_path']) for item in config.get('rename_preview',{}).get('items',[])
                if re.search(r'\bNWN S1B\b',item.get('target_name',''),re.I)]
        known={str(p).casefold() for p in files}
        for path in shared:
            if path.is_file() and str(path).casefold() not in known:
                files.append(path);known.add(str(path).casefold())
    if fn and config.get('rename_preview',{}).get('fn_manual_selection'):
        selected={str(Path(i['target_path'])).casefold() for i in config['rename_preview']['items'] if i.get('manual_kind')=='fn'}
        files=[p for p in files if not re.search(r'\bNWN S1B\b',p.name,re.I) or str(p).casefold() in selected]
    assets = Assets(config)
    durations = {path.name: assets.duration(path) for path in files}
    def external(name):
        path = assets.resolve(name)
        if path:
            durations[path.name] = assets.duration(path)
        else:
            all_missing.add('Thiếu file: ' + name)
        return path
    rules = config.get("cycle_rules", {})
    result_cycles = []
    all_missing = set()
    reported=[r for r in config.get('rename_preview',{}).get('items',[]) if r.get('draft_duration')]
    if reported:
        all_missing.add('Bản nháp: '+str(len(reported))+' mục dùng thời lượng báo trước; cần quét lại khi có file chính thức.')

    for cycle in range(1, 7):
        rows = []
        bmd_seen = 0
        wow_seen = 0
        for block in order:
            selected: list[Path] = []
            if block == 1:
                from ap_rules import slot_family,select_parts,expected_parts
                config['program']['slot1_family']=slot_family(config['episode'],config['program'],files)
                if config['program']['slot1_family']=='AP':
                    selected,ap_missing=select_parts(files,config['episode'],expected_parts(config,default=''))
                    all_missing.update(ap_missing)
                    for part in selected:rows.append(dict(cycle=cycle,block=block,name=part.name,path=str(part),duration=durations[part.name]))
                    continue

                from wow_rules import has_wow_intro_outro
                if not has_wow_intro_outro(rules):
                    main=find_one(files,f"{config['episode']} WOW ",exclude=(' WOW IN',' WOW OUT','TSER','TEASER','(WEBLINK)'))
                    if main:
                        rows.append(dict(cycle=cycle,block=block,name=main.name,path=str(main),duration=durations[main.name]))
                    else:all_missing.add('Block 1: WOW — bản thường, tên show không có weblink')
                    continue
                wow_seen += 1
                treatment = wow_treatment(rules, cycle) if wow_seen == 1 else ""
                intro = choose_in(files, f"{config['episode']} WOW", treatment, True)
                if not intro and treatment:
                    intro = choose_in(files, f"{config['episode']} WOW", "", True)
                main = find_one(files, f"{config['episode']} WOW MAIN")
                out = find_one(files, f"{config['episode']} WOW OUT", 'NO MAX', exclude=('NO NXT','NO UP NXT','NO NEXT','NO UP NEXT')) or find_one(files, f"{config['episode']} WOW OUT", exclude=('NO NXT','NO UP NXT','NO NEXT','NO UP NEXT'))
                selected = [item for item in (intro, main, out) if item]
                if not main: all_missing.add("Block 1: WOW MAIN")
                if not intro: all_missing.add('Block 1: WOW IN')
                if not out: all_missing.add('Block 1: WOW OUT')
                if treatment and intro and treatment not in intro.name.upper():
                    extra = external(f'M intro {treatment.title()} (WOW)')
                    if extra: selected.insert(1, extra)
            elif block in (3, 7):
                bmd_seen += 1
                treatment = bmd_treatment(rules, cycle) if bmd_seen == 1 else ""
                intro = choose_in(files, f"{config['episode']} BMD", treatment, True)
                main = find_one(files, f"{config['episode']} BMD MAIN")
                code = bmd_next_code(block, order, config['program'])
                out_key = f'UP NXT {code}' if code else 'NO NXT'
                out = find_one(files, f"{config['episode']} BMD OUT", out_key, 'NO MAX') or find_one(files, f"{config['episode']} BMD OUT", out_key)
                if not out and config.get('draft_mode'):
                    out=find_one(files,f"{config['episode']} BMD OUT",'(OUT)')
                    if out:all_missing.add(f'Bản nháp dùng BMD OUT chung; cần xác nhận bản {out_key}.')
                selected = [item for item in (intro, main, out) if item]
                if not intro: all_missing.add(f"Block {block}: BMD IN {treatment or 'normal'} No Max")
                if not intro and treatment:
                    intro = choose_in(files, f"{config['episode']} BMD", '', True)
                    if intro:
                        all_missing.discard(f"Block {block}: BMD IN {treatment or 'normal'} No Max")
                        selected.insert(0, intro)
                if treatment and intro and treatment not in intro.name.upper():
                    extra = external(f'M intro {treatment.title()} (BMD)')
                    if extra: selected.insert(1, extra)
                if not main: all_missing.add(f'Block {block}: BMD MAIN')
                if not out: all_missing.add(f'Block {block}: BMD OUT {out_key}')
            elif block in (4, 8):
                s1a = find_one(files, f"{config['episode']} NWN S1A", "NO MAX") or find_one(files, f"{config['episode']} NWN S1A", exclude=("NO MAX",))
                fn_ep = config.get('rename_preview', {}).get('fn_source_episode') or config['episode']
                s1b = sorted([p for p in files if re.search(r'\bNWN S1B\b',p.name,re.I)], key=fn_order_key) if fn else []
                if fn and not s1b: all_missing.add(f'FN S1B thiếu bộ EP {config["episode"]} / {config["episode"]-1}')
                s1c = find_one(files, f"{config['episode']} NWN S1C", 'NO MAX') or find_one(files, f"{config['episode']} NWN S1C")
                s2 = find_one(files, f"{config['episode']} NWN S2", 'NO MAX') or find_one(files, f"{config['episode']} NWN S2")
                s3 = find_one(files, f"{config['episode']} NWN S3", "NO MAX") or find_one(files, f"{config['episode']} NWN S3")
                scroll = find_one(files, f"{config['episode']} NWN DAILY SCROLL")
                selected = [item for item in [s1a, *s1b, s1c, s2, s3, scroll] if item]
                for name, p in [('S1A',s1a),('S1C',s1c),('S2',s2),('S3',s3),('Daily Scroll',scroll)]:
                    if not p: all_missing.add('NWN '+name)
            elif block in (2,5,6):
                slot = {2:1,5:2,6:3}[block]
                active_show = next((s for s in config["program"]["active_shows"] if s.get("output_slot") == slot), {})
                code = show_code(active_show.get('code', ''))
                selected = sorted([p for p in files if re.match(rf"^{config['episode']}\s+{re.escape(code)}\b", p.name, re.I)], key=natural_key) if code else []
                from show_formats import has_intro_outro,select_triplet
                continuous=has_intro_outro(code,[p.name for p in selected],config.get('reported_durations',{}),active_show.get('has_intro_outro',False))
                if continuous:
                    selected,issues=select_triplet(selected,code)
                    all_missing.update(f'Block {block}: '+issue for issue in issues)
                    for path in selected:rows.append(dict(cycle=cycle,block=block,name=path.name,path=str(path),duration=durations[path.name],continuous_show=True))
                    continue
                # Start FN schedules with No Max for the first segment when a pair exists.
                no_max = [p for p in selected if "NO MAX" in p.name.upper()]
                if no_max:
                    selected = no_max + [p for p in selected if " S2" in p.name.upper()]
                if not selected and (block != 6 or active_show): all_missing.add(f'Block {block}: Show {slot}')
            elif block == 6:
                # S3 is optional. INPUT_1 A:H may leave it empty for the episode;
                # keep the block in the rotation without inventing content.
                selected = []
            elif block == 2:
                all_missing.add("Block 2: Show 1 source/path")

            for path in selected:
                if is_no_next(path.name):continue
                rows.append({"cycle": cycle, "block": block, "name": path.name, "path": str(path), "duration": durations[path.name]})
        result_cycles.append({"cycle": cycle, "rows": rows, "duration": sum(row["duration"] for row in rows)})

    output = {
        "episode": config["episode"], "fn": fn, "start_block": start, "block_order": order,
        "cycles": result_cycles, "missing": sorted(all_missing), "valid": not all_missing,
        'reported_items':[{'name':i['target_name'],'seconds':i['draft_duration']} for i in reported],
    }
    assets.save()
    from schedule_timing import finish_schedule
    output = finish_schedule(config, output, assets, config_path.parent)
    out_path = config_path.parent / f"EP_{config['episode']}_schedule_draft.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    output["path"] = str(out_path)
    return output


def show_code(text):
    aliases = {"nature's beauty": 'NB', 'veganism: the noble way of living': 'VEG',
               'animal world': 'AW', 'a journey through aesthetic realms': 'AJAR'}
    return aliases.get(text.casefold(), text.split()[0] if text else '')
