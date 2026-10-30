from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path


from portable_paths import EXPORT_ROOT
SPECIAL_ADS_ROOT = EXPORT_ROOT / '@ ADS' / 'zzz SPECIALS'


def normalize_ad_name(text: str) -> str:
    value = Path(str(text or "")).stem.casefold()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.replace('_', ' ')
    # Ignore explicit calendar-date notes, not words in the subject's name.
    month=r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
    value=re.sub(r'[([]\s*'+month+r'\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\s*[)\]]',' ',value)
    value=re.sub(r'[([]\s*\d{1,2}\s+'+month+r'\.?(?:\s+\d{4})?\s*[)\]]',' ',value)
    value = re.sub(r"\b(?:19|20)\d{6}\b", " ", value)
    value = re.sub(r"\b(?:19|20)\d{2}\b", " ", value)
    value = re.sub(r"\b\d{1,2}[:.]\d{2}\b", " ", value)
    value = re.sub(r"\b\d+\s*(?:sec|seconds?|mins?|minutes?)\b", " ", value)
    value = re.sub(r"\b(?:ad|bday|birthday|holiday|masters?|saint|lord|prophet|bodhisattva|vegetarian|vegan|today)\b", " ", value)
    value = re.sub(r"\b\d+\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def split_required_ads(name: str) -> list[str]:
    parts = re.split(r"\s*(?:\+{2,}|\+AND\+|\bAND\b)\s*", name, flags=re.I)
    return [part.strip() for part in parts if normalize_ad_name(part)] or [name]


def resolve_do_not_skip(config: dict) -> tuple[list[dict], list[str]]:
    requested = [item["name"] for item in config.get("ads", {}).get("items", [])
                 if item.get("priority_class") == "DO_NOT_SKIP"]
    if not requested:
        return [], []
    from schedule_assets import Assets
    catalog = Assets(config)
    if not SPECIAL_ADS_ROOT.exists():
        return [], requested
    sources = sorted((p for p in SPECIAL_ADS_ROOT.rglob("*.mp4") if not any(part.casefold()=="old" for part in p.relative_to(SPECIAL_ADS_ROOT).parts[:-1])), key=lambda path: path.name.casefold())
    normalized = [(path, normalize_ad_name(path.name)) for path in sources]
    matched = []
    missing = []
    used = set()
    for original in requested:
        manual = catalog.resolve(original)
        if manual:
            matched.append({'requested': original, 'part': original, 'source': manual, 'score': 1.0})
            continue
        found_for_original = False
        for part in split_required_ads(original):
            key = normalize_ad_name(part)
            key_tokens = set(key.split())
            best_path = None
            best_score = 0.0
            for path, candidate in normalized:
                if path in used or not candidate:
                    continue
                candidate_tokens = set(candidate.split())
                coverage = len(key_tokens & candidate_tokens) / max(1, len(key_tokens))
                precision = len(key_tokens & candidate_tokens) / max(1, len(candidate_tokens))
                ratio = SequenceMatcher(None, key, candidate).ratio()
                score = 0.55 * coverage + 0.20 * precision + 0.25 * ratio
                if score > best_score:
                    best_score, best_path = score, path
            exact_candidates = [path for path, candidate in normalized
                                if key and set(key.split()) == set(candidate.split())]
            best_path = exact_candidates[0] if len(exact_candidates) == 1 else None
            best_score = 1.0 if best_path else 0.0
            if best_path is not None:
                used.add(best_path)
                matched.append({"requested": original, "part": part, "source": best_path, "score": round(best_score, 3)})
                found_for_original = True
            else:
                missing.append(part)
        if not found_for_original and original not in missing:
            missing.append(original)
    return matched, missing


def run(command: list[str]) -> subprocess.CompletedProcess:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(command, check=True, text=True, capture_output=True, creationflags=flags)


def source_duration(path: Path) -> tuple[float, int, float, str]:
    probe = json.loads(run([
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,nb_frames,avg_frame_rate,r_frame_rate,duration",
        "-show_entries", "format=duration", "-of", "json", str(path),
    ]).stdout)
    streams=probe.get('streams',[])
    stream=next((s for s in streams if s.get('codec_type')=='video'),None)
    if stream is None:
        audio=next((s for s in streams if s.get('codec_type')=='audio'),None)
        if audio is None:raise RuntimeError(f'No audio/video stream: {path}')
        value=audio.get('duration')
        if value in (None,'N/A',''):value=probe.get('format',{}).get('duration')
        seconds=float(value or 0)
        if seconds<=0:raise RuntimeError(f'Invalid media duration: {path}')
        return seconds,0,0.0,'audio-duration'


    def rational(text: str) -> float:
        if "/" in text:
            top, bottom = text.split("/", 1)
            return float(top) / float(bottom) if float(bottom) else 0.0
        return float(text or 0)

    fps = rational(stream.get("avg_frame_rate", "0")) or rational(stream.get("r_frame_rate", "0"))
    frames = int(stream.get("nb_frames") or 0) if str(stream.get("nb_frames") or "0").isdigit() else 0
    if frames and fps:
        return frames / fps, frames, fps, "frames/fps"
    seconds = float(stream.get("duration") or probe.get("format", {}).get("duration") or 0)
    if seconds <= 0:
        raise RuntimeError(f"Không đọc được thời lượng: {path}")
    return seconds, frames, fps, "duration"


def make_placeholder(source: Path, destination: Path) -> dict:
    seconds, frames, fps, method = source_duration(source)
    run(["ffmpeg", "-v", "error", "-sseof", "-2", "-i", str(source), "-map", "0:a:0" if method == "audio-duration" else "0:v:0", "-f", "null", "NUL"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.with_suffix(".building.mp4")
    if stage.exists():
        stage.unlink()
    run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-t", f"{seconds:.9f}", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(stage),
    ])
    os.replace(stage, destination)
    return {"seconds": seconds, "frames": frames, "fps": fps, "method": method, "built": True}


MAX_SECONDS = 192.6925


def derived_no_max_path(item):
    from max_options import is_max
    if not is_max(item):return None
    target=Path(item['target_path'])
    if re.search(r'no[ _]*max',target.stem,re.I): return None
    stem=re.sub(r'\s*\(?\b(?:SMTV\s+)?MAX\b\)?','',target.stem,flags=re.I).strip()
    return target.with_name(stem+' (No Max)'+target.suffix)


def create_missing_no_max(items, refreshed=()):
    declared={str(Path(i['target_path'])).casefold() for i in items}
    results=[]
    for item in items:
        target=derived_no_max_path(item)
        if target is None or str(target).casefold() in declared or (target.exists() and item['target_name'] not in refreshed): continue
        if item.get('draft_duration'):
            seconds=item['draft_duration']
        else:
            seconds,frames,fps,method=source_duration(Path(item['source_path']))
            run(['ffmpeg','-v','error','-sseof','-2','-i',item['source_path'],'-map','0:a:0' if method=='audio-duration' else '0:v:0','-f','null','NUL'])
        duration=seconds-MAX_SECONDS
        if duration<=0:
            raise ValueError(f'Không thể tạo No Max: {item["source_name"]} chỉ dài {seconds:.6f} giây, nhỏ hơn đoạn Max {MAX_SECONDS} giây.')
        target.parent.mkdir(parents=True,exist_ok=True)
        stage=target.with_suffix('.building.mp4')
        run(['ffmpeg','-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
             '-t',f'{duration:.9f}','-c:a','aac','-b:a','128k','-movflags','+faststart',str(stage)])
        os.replace(stage,target)
        results.append({**item,'target_path':str(target),'target_name':target.name,'built':True,
                        'method':'derived-no-max-minus-192.6925s','seconds':duration,
                        'source_seconds':seconds,'max_seconds':MAX_SECONDS})
    return results


def source_signature(item: dict) -> dict:
    """Track real source revisions, including replacement at the same path."""
    if item.get('draft_duration') or item.get('local_fallback'):
        return {}
    source = Path(item['source_path'])
    target = Path(item['target_path'])
    if str(source).casefold() == str(target).casefold():
        return {}
    stat = source.stat()
    return {'source_size': str(stat.st_size), 'source_mtime_ns': str(stat.st_mtime_ns)}


def source_changed(item: dict, old: dict) -> bool:
    signature = source_signature(item)
    return bool(signature) and (old.get('source_path') != item['source_path'] or
        any(str(old.get(key, '')) != value for key, value in signature.items()))


def create_episode(config_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    from draft_input import expand_bmd_out
    expand_bmd_out(config)
    from max_options import apply_choices
    apply_choices(config)
    config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    episode = int(config["episode"])
    local_dir = Path(config["local_dir"])
    local_dir.mkdir(parents=True, exist_ok=True)
    items = config["rename_preview"]["items"]
    if not config.get('schedule_settings',{}).get('tser_fn',True):
        from draft_input import item_key
        items=[i for i in items if item_key(i)!='TSER FN']
    stage_dir = local_dir / ".pipeline_build"
    stage_dir.mkdir(exist_ok=True)
    results = []
    old_records={}
    previous_manifest=local_dir/'pipeline_manifest.csv'
    if previous_manifest.exists():
        with previous_manifest.open(encoding='utf-8-sig',newline='') as handle:
            old_records={r['target_name']:r for r in csv.DictReader(handle)}
    replacing=set()
    for item in items:
        old=old_records.get(item['target_name'],{})
        if source_changed(item, old):
            replacing.add(item['target_name'])
        item.update(source_signature(item))
        if not item.get('draft_duration') and Path(item['target_path']).with_suffix('.mp4.draft.json').exists():
            replacing.add(item['target_name'])
        if old.get('method')=='reported-duration' and (not item.get('draft_duration') or float(old.get('seconds') or 0)!=item['draft_duration']):
            replacing.add(item['target_name'])
        if old.get('method')=='draft-out-variant' and not item.get('draft_out_variant'):
            replacing.add(item['target_name'])
    special_matches, special_missing = resolve_do_not_skip(config)

    try:
        # Check all network sources together. This preserves upload safety while
        # paying the five-second stability wait only once for the whole episode.
        sources_to_build = []
        declared_targets={str(Path(i['target_path'])).casefold() for i in items}
        for item in items:
            if item.get('draft_duration'):continue
            destination = Path(item.get('target_path') or local_dir / item['target_name'])
            old_placeholder = local_dir / item["source_name"]
            staged_target = stage_dir / item["target_name"]
            if item['target_name'] in replacing or (not destination.exists() and (item.get('draft_out_variant') or not old_placeholder.exists()) and not staged_target.exists()):
                sources_to_build.append(Path(item["source_path"]))
            derived_target=derived_no_max_path(item)
            if derived_target and not derived_target.exists() and str(derived_target).casefold() not in declared_targets:
                sources_to_build.append(Path(item['source_path']))
        sources_to_check = list(dict.fromkeys(sources_to_build + [row["source"] for row in special_matches]))
        first_stats = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in sources_to_check}
        if sources_to_check:
            time.sleep(5)
        for path in sources_to_check:
            fresh = path.stat()
            if first_stats[path] != (fresh.st_size, fresh.st_mtime_ns):
                raise RuntimeError(f"File nguồn còn đang thay đổi: {path.name}")

        for item in items:
            source = Path(item["source_path"])
            destination = Path(item.get('target_path') or local_dir / item['target_name'])
            old_placeholder = local_dir / item["source_name"]
            staged_target = stage_dir / item["target_name"]
            if destination.exists() and item['target_name'] not in replacing:
                old=old_records.get(item['target_name'],{})
                results.append({**item, "built": False, "method": old.get('method') if old.get('method') in ('reported-duration','draft-out-variant') else 'already-existing-target', 'seconds':old.get('seconds','')})
                continue
            if item.get('draft_duration'):
                run(['ffmpeg','-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
                     '-t',str(item['draft_duration']),'-c:a','aac','-b:a','128k','-movflags','+faststart',str(staged_target)])
                detail={'built':True,'method':'reported-duration','seconds':item['draft_duration']}
            elif item['target_name'] in replacing:
                detail=make_placeholder(source,staged_target)
                if item.get('draft_out_variant'):
                    detail['method']='draft-out-variant' 
            elif staged_target.exists():
                detail = {"built": False, "method": "resume-staged-placeholder"}
            elif item.get('draft_out_variant'):
                detail=make_placeholder(source,staged_target)
                detail['method']='draft-out-variant'
            elif old_placeholder.exists():
                detail = make_placeholder(old_placeholder, staged_target)
            else:
                detail = make_placeholder(source, staged_target)
            if item.get('source_mtime_ns'):
                if source_signature(item) != {key: item[key] for key in ('source_size', 'source_mtime_ns')}:
                    raise RuntimeError(f"Source changed while building: {source.name}")
            results.append({**item, **detail})

        target_names = {item["target_name"].casefold() for item in items}
        archive_dir = local_dir / f"_OLD_NAMES_{datetime.now():%Y%m%d_%H%M%S}"
        old_manifest = local_dir / "placeholder_manifest.csv"
        old_names = {name.casefold() for name,row in old_records.items() if row.get('method')=='reported-duration'}
        if old_manifest.exists():
            with old_manifest.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    placeholder = row.get("Placeholder", "")
                    if placeholder:
                        old_names.add(Path(placeholder).name.casefold())
        for existing in local_dir.glob("*.mp4"):
            if existing.name.casefold() in old_names and existing.name.casefold() not in target_names:
                archive_dir.mkdir(exist_ok=True)
                shutil.move(str(existing), archive_dir / existing.name)

        created = 0
        kept = sum(row.get("method") == "already-existing-target" for row in results)
        # Materialize the list first so Windows closes the directory scan handle.
        for staged in list(stage_dir.glob("*.mp4")):
            item = next(item for item in items if item['target_name']==staged.name)
            destination = Path(item.get('target_path') or local_dir / staged.name)
            destination.parent.mkdir(parents=True,exist_ok=True)
            if destination.exists() and staged.name not in replacing:
                kept += 1
                continue
            os.replace(staged, destination)
            marker=destination.with_suffix('.mp4.draft.json')
            if staged.name in replacing and marker.exists():marker.unlink()
            created += 1

        special_results = []
        special_created = 0
        special_kept = 0
        previous_special={}
        special_manifest=local_dir/'do_not_skip_ads_manifest.csv'
        if special_manifest.exists():
            with special_manifest.open(encoding='utf-8-sig',newline='') as handle:
                previous_special={r.get('target'):r for r in csv.DictReader(handle)}
        for match in special_matches:
            source=match['source'];destination=local_dir/source.name
            signature=first_stats[source]
            previous=previous_special.get(str(destination),{})
            unchanged=(previous.get('method')=='source-temp' and previous.get('source')==str(source)
                       and previous.get('source_size')==str(signature[0])
                       and previous.get('source_mtime_ns')==str(signature[1]))
            seconds=previous.get('seconds','')
            if source.resolve()==destination.resolve():
                status='already-existing';method=previous.get('method','local-existing');special_kept+=1
            elif destination.exists() and unchanged:
                status='already-existing';method='source-temp';special_kept+=1
            else:
                stage=stage_dir/('special_'+source.name)
                detail=make_placeholder(source,stage)
                current=source.stat()
                if signature!=(current.st_size,current.st_mtime_ns):
                    raise RuntimeError(f'Source changed while building special ADS: {source.name}')
                os.replace(stage,destination)
                status='created-temp';method='source-temp';seconds=detail['seconds'];special_created+=1
            special_results.append({'requested':match['requested'],'part':match['part'],
                'source':str(source),'target':str(destination),'score':match['score'],'status':status,
                'method':method,'seconds':seconds,'source_size':signature[0],'source_mtime_ns':signature[1]})

        derived=create_missing_no_max(items, replacing)
        results.extend(derived)
        created+=len(derived)
        manifest = local_dir / "pipeline_manifest.csv"
        fields = ["rule", "source_name", "target_name", "source_path", "target_path", "built", "method", "seconds", "source_seconds", "max_seconds", "source_size", "source_mtime_ns"]
        with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
        ads_manifest = local_dir / "do_not_skip_ads_manifest.csv"
        with ads_manifest.open("w", newline="", encoding="utf-8-sig") as handle:
            fields = ["requested", "part", "source", "target", "score", "status", "method", "seconds", "source_size", "source_mtime_ns"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(special_results)
            for name in special_missing:
                writer.writerow({"requested": name, "part": name, "status": "NOT FOUND"})
        return {
            "episode": episode,
            "files": len(items)+len(derived),
            "derived_no_max": [r['target_name'] for r in derived],
            "created": created,
            "kept": kept,
            "archive": str(archive_dir) if archive_dir.exists() else "",
            "manifest": str(manifest),
            "do_not_skip_ads_copied": special_created,
            "do_not_skip_ads_kept": special_kept,
            "do_not_skip_ads_missing": special_missing,
            "do_not_skip_ads_manifest": str(ads_manifest),
        }
    finally:
        if stage_dir.exists():
            shutil.rmtree(stage_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    print(json.dumps(create_episode(args.config), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
