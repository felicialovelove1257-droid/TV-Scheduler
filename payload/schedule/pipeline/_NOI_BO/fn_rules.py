"""Read-only FN identities shared by scheduling and external QC."""
import re
from pathlib import Path


def identity(name):
    from episode_scanner import normalize_episode_order
    text=normalize_episode_order(Path(name).stem.replace('_',' ')).upper()
    if not re.search(r'\bNWN\s+(?:SEG(?:MENT)?|S)\s*1\s*B\b',text):return None
    ep=re.match(r'(\d{4})\b',text)
    part=re.search(r'\bP(?:ART)?\s*(\d+)([A-Z]?)\b',text)
    if not ep or not part:return None
    date=re.search(r'(?<!\d)\d{8}(?!\d)',text)
    fn=re.search(r'\bFN\s*(\d+)\b',text)
    reair=bool(re.search(r'\bRE[ -]*AIR\b',text))
    title=''
    if not date and not fn:
        title=' '.join(re.sub(r'\bP(?:ART)?\s*\d+[A-Z]?\b|\bV\d+\b',' ',text).split())
    return (int(ep[1]),reair,date[0] if date else '',fn[1] if fn else '',title),(int(part[1]),part[2])


def order_key(path):
    found=identity(path.name)
    if not found:return (0,False,'','','',0,'',path.name.upper())
    group,part=found
    return (-group[0],*group[1:],*part,path.name.upper())


def validate(names):
    """A part sequence restarts for each event/EP/reair, never across sets."""
    parsed=[identity(n) for n in names]
    parsed=[p for p in parsed if p]
    errors=[]
    keys=[(-g[0],*g[1:],*p) for g,p in parsed]
    if keys!=sorted(keys):errors.append('FN sai thứ tự bộ/part: EP mới trước, cùng EP bản mới trước reair.')
    groups={}
    for group,part in parsed:groups.setdefault(group,[]).append(part)
    for group,parts in groups.items():
        label=f'FN EP {group[0]} '+('reair ' if group[1] else '')+(group[2] or group[3] or group[4])
        numbers={n for n,_ in parts}
        if len(parts)!=len(set(parts)):errors.append(label+': trùng part.')
        if numbers!=set(range(1,max(numbers)+1)):errors.append(label+': thiếu số part.')
        for n in sorted(numbers):
            letters={s for number,s in parts if number==n and s}
            if letters and (letters!={chr(i) for i in range(65,ord(max(letters))+1)} or (n==1 and 'B' not in letters)):
                errors.append(label+f': thiếu phần tách P{n}.')
            if letters and (n,'') in parts:errors.append(label+f': có cả P{n} và các phần tách.')
    return errors


def expected_sources(episode,program,export_root,local_root):
    from episode_scanner import proposed_name
    from missing_media import source_choices
    manual=[r for r in source_choices(episode)['items'] if r.get('manual_kind')=='fn'
            and (Path(r['source_path']).is_file() or Path(r['target_path']).is_file())]
    if manual:return {proposed_name(r['target_name'],episode,program)[0].casefold() for r in manual}
    paths=[]
    for folder in (export_root/f'EP {episode}',export_root/f'EP {episode-1}',export_root/'@ ARCHIVES'/f'EP {episode-1}'):
        paths=[p for p in folder.glob('*.mp4') if identity(p.name)]
        if paths:break
    # Scanner also accepts existing local FN when no source counterpart exists.
    paths+= [p for p in (local_root/f'EP {episode}').glob('*.mp4') if identity(p.name)]
    return {proposed_name(p.name,episode,program)[0].casefold() for p in paths}


def current_episode_rows(items,episode,local_dir):
    """Keep source identity while all selected FN temps belong to the airing EP."""
    for row in items:
        source=identity(row.get('source_name',''))
        if not identity(row.get('target_name','')):continue
        if source:row['fn_source_episode']=source[0][0]
        row['target_name']=re.sub(r'^\d{4}(?=\s)',str(episode),row['target_name'])
        row['target_path']=str(Path(local_dir)/row['target_name'])
    return items
