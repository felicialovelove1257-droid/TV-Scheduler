"""Recognize ordinary shows packaged as IN / MAIN / OUT."""
import re
from pathlib import Path
from media_labels import is_no_next

def show_part(name,code):
    text=Path(name).stem.replace('_',' ')
    if re.search(r'\b(?:TSER|TEASER)\b',text,re.I):return None
    match=re.search(r'\b'+re.escape(code)+r'\b',text,re.I)
    if not match:return None
    tail=text[match.end():].strip()
    part=re.match(r'^(INTRO|OUTRO|MAIN|IN|OUT)(?=\s|$|[.(])',tail,re.I)
    if part:return {'INTRO':'IN','OUTRO':'OUT'}.get(part[1].upper(),part[1].upper())
    suffix=re.sub(r'\s*\([^)]*\)|\s+v\d+\b','',tail,flags=re.I).strip()
    part=re.search(r'\b(INTRO|OUTRO|IN|OUT)$',suffix,re.I)
    if part:return {'INTRO':'IN','OUTRO':'OUT'}.get(part[1].upper(),part[1].upper())
    if re.search(r'\b(?:S|SEG(?:MENT)?\s*)\d+\b',tail,re.I):return None
    return 'MAIN'

def has_intro_outro(code,names=(),reported=(),declared=False):
    return declared or any(show_part(n,code) in ('IN','OUT') for n in names) or any(k in (code+' IN',code+' OUT') for k in reported)

def select_triplet(files,code):
    selected=[];missing=[]
    for role in ('IN','MAIN','OUT'):
        group=[p for p in files if show_part(p.name,code)==role and not is_no_next(p.name)]
        no_max=[p for p in group if re.search(r'no[ _]*(?:smtv[ _]*)?max',p.name,re.I)]
        group=no_max or group
        if len(group)==1:selected.append(group[0])
        else:missing.append(f'{code} {role}: '+('nhiều file, cần chọn bản' if group else 'thiếu file'))
    return selected,missing

def configure_shows(program,names=(),reported=()):
    from schedule_engine import show_code
    for show in program.get('active_shows',[]):
        code=show_code(show.get('code',''))
        show['has_intro_outro']=has_intro_outro(code,names,reported,show.get('has_intro_outro',False))
