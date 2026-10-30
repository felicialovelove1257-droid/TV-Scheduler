"""AP Sunday slot and its three-day teaser campaign (EP 3309 reference)."""
import re
from pathlib import Path
AP_SUNDAY_EP = 3309

def ap_campaign(episode):
    days=(AP_SUNDAY_EP-int(episode))%7
    return {'episode':int(episode)+days,'days_before':days,'phase':('TODAY','TOMORROW','IN 2 DAYS')[days]} if days<=2 else None

def slot_family(episode,program,files=()):
    if program.get('slot1_family') in ('AP','WOW'):return program['slot1_family']
    if program.get('details',{}).get('AP'):return 'AP'
    names=[Path(p).name for p in files]
    if any(re.match(rf'^{episode}\s+AP\b',n,re.I) for n in names):return 'AP'
    if any(re.match(rf'^{episode}\s+WOW\b',n,re.I) for n in names):return 'WOW'
    return 'AP' if (int(episode)-AP_SUNDAY_EP)%7==0 else 'WOW'

def part_id(name):
    m=re.search(r'\b(?:PART|PT|P)\s*([A-Z])\b',name,re.I)
    return m[1].upper() if m else None

def teaser_phase(name):
    if re.search(r'\bTODAY\b',name,re.I):return 0
    if re.search(r'\b(?:TOMORROW|TMR)\b',name,re.I):return 1
    if re.search(r'\b(?:IN\s*)?(?:2|TWO)\s*DAYS?\b',name,re.I):return 2
    return None

def valid_teaser(name,episode):
    campaign=ap_campaign(episode)
    if not campaign:return False
    ep=re.search(r'\b(\d{4})\s+AP\b',name,re.I)
    phase=teaser_phase(name)
    return bool(ep and int(ep[1])==campaign['episode'] and (phase is None or phase==campaign['days_before']))

def select_parts(files,episode,expected_parts=()):
    groups={};missing=[]
    for p in files:
        if not re.match(rf'^{episode}\s+AP\b',p.name,re.I):continue
        if re.search(r'NO[ _]*(?:UP[ _]*)?(?:NEXT|NXT)',p.name,re.I):continue
        part=part_id(p.name)
        if part:groups.setdefault(part,[]).append(p)
    selected=[]
    letters=set(groups)|set(expected_parts)
    last=max(letters) if letters else 'C'
    for part in (chr(n) for n in range(ord('A'),ord(last)+1)):
        candidates=groups.get(part,[])
        no_max=[p for p in candidates if re.search(r'no[ _]*(?:smtv[ _]*)?max',p.name,re.I)]
        candidates=no_max or candidates
        if len(candidates)==1:selected.append(candidates[0])
        else:missing.append('Block 1: AP PART '+part+(' — nhiều file, cần chọn' if candidates else ' — thiếu file'))
    return selected,missing


def expected_parts(config, default="C"):
    names=[i.get('target_name','') for i in config.get('rename_preview',{}).get('items',[]) if i.get('rule')=='ap-part']
    names += [k for k in config.get('reported_durations',{}) if k.startswith('AP PART')]
    letters=[part_id(n) for n in names if part_id(n)]
    last=max(letters) if letters else default
    if not last:return []
    return [chr(n) for n in range(ord('A'),ord(last)+1)]
