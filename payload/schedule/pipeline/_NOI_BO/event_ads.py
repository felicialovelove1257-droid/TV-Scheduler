"""Numbered event ADS in this EP: one part per cycle, wrapping after the last part."""
import re
from pathlib import Path

def identify(name,episode):
    stem=Path(name).stem.replace('_',' ')
    m=re.fullmatch(rf'{episode}\s+(.+?)\s+AD\s*(\d+)\s*(?:v\s*\d+)?',stem,re.I)
    if not m:return None
    return m[1].strip(),int(m[2])

def insert_events(rows,config,assets,make,missing):
    groups={}
    source_dir=Path(config['source_dir']).resolve() if config.get('source_dir') else None
    for item in config.get('rename_preview',{}).get('items',[]):
        if item.get('excluded') or item.get('local_fallback'):continue
        source=Path(item['source_path']) if item.get('source_path') else None
        if source_dir is None or source is None or source.resolve().parent!=source_dir:continue
        source_match=identify(source.name,config['episode'])
        if not source_match:continue
        match=identify(item.get('target_name',''),config['episode'])
        if not match:continue
        if (source_match[0].casefold(),source_match[1])!=(match[0].casefold(),match[1]):
            missing.append('Event ADS source and local name disagree: '+source.name);continue
        if not source.is_file():
            missing.append('Event ADS source is unavailable; rescan EP: '+str(source));continue
        title,part=match;path=Path(item['target_path'])
        groups.setdefault(title.casefold(),{}).setdefault(part,set()).add(path)
    expected=[];rows=list(rows)
    from schedule_timing import INSERT_KINDS,mark_insert_slots
    mark_insert_slots(rows)
    for title,parts in sorted(groups.items()):
        if sorted(parts)!=list(range(1,max(parts)+1)):
            missing.append('Event ADS parts are incomplete: '+title);continue
        cycles=sorted({r['cycle'] for r in rows if r.get('kind')=='program'})
        for index,cycle in enumerate(cycles):
            part=index % len(parts)+1
            paths=parts[part]
            if len(paths)!=1:
                missing.append(f'Event ADS has ambiguous versions: {title} AD {part}');continue
            path=next(iter(paths));expected.append(dict(cycle=cycle,name=path.name))
            if not path.is_file():missing.append('Missing mandatory event ADS: '+path.name);continue
            candidates=[i for i,r in enumerate(rows) if r['cycle']==cycle and r.get('kind')=='program' and r.get('insert_slot')=='between_shows'
                        and (i+1==len(rows) or rows[i+1].get('kind') not in INSERT_KINDS)]
            if not candidates:
                missing.append(f'Cycle {cycle}: no show-boundary slot for mandatory event ADS {path.name}');continue
            i=candidates[0];anchor=rows[i]
            ad=make(path,cycle,anchor['block'],'DO_NOT_SKIP')
            ad.update(mandatory_event=True,event_part=part,priority_name=path.name)
            ad['boundary']=anchor.pop('boundary','program');anchor.pop('free_slot',None)
            rows.insert(i+1,ad)
    return rows,expected
