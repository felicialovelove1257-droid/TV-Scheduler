"""Reserve ADS catalog: explicit status checks and unambiguous name resolution."""
import re
import unicodedata
from pathlib import Path

def normalized(name):
    value=re.sub(r'\.mp4$','',str(name),flags=re.I)
    value=re.sub(r'[\[(]\s*\d+[:.]\d+(?::\d+)?\s*[\])]',' ',value)
    value=re.sub(r'\[ROTATE\]',' ',value,flags=re.I)
    value=re.sub(r'^NEW[\s_:-]*','',value,flags=re.I)
    value=re.sub(r'[ _-]+v\d+(?=[ _-]|$)',' ',value,flags=re.I)
    return re.sub(r'[\W_]+',' ',value.casefold()).strip()

# Expand known filename abbreviations only; numbers and part IDs remain significant.
WORDS = {'drs':'doctors', 'jewlry':'jewelry', 'etern':'eternal',
         'evr':'ever', 'univ':'universes', 'heav':'heavens',
         'ppl':'people', 'r':'are', 'messsage':'message', 'fr':'from'}

def content_key(name, folder=''):
    words=normalized(name).split()
    words=[WORDS.get(w,w) for w in words if w not in ('ad','cc')]
    if 'jewelry' in normalized(folder):
        words=[w for w in words if w not in ('m','sm','the','of','duration','jewelry')]
    return ' '.join(str(int(w)) if w.isdigit() else w for w in words)

def read_catalog(rows):
    entries=[]
    for index,row in enumerate(rows,1):
        row=list(row)+['']*11
        name=str(row[2]).strip()
        if not name or not str(row[1]).strip():continue
        notes=' | '.join(str(x).strip() for x in row[7:11] if str(x).strip())
        folded=''.join(ch for ch in unicodedata.normalize('NFD',(name+' | '+notes).casefold()) if unicodedata.category(ch)!='Mn')
        excluded=bool(re.search(r'need\s*fix|needs?\s*repair|not\s*air|do\s*not\s*(?:air|use)|don.t\s*(?:air|use)|\berrors?\b|\bfault\w*\b|\bbroken\b|\bloi\b|khong\s*(?:dung|xai|phat)|(?:ko|k)\s*(?:dung|xai)|can\s*sua',folded))
        entries.append(dict(name=name,folder=str(row[1]).strip(),notes=notes,excluded=excluded,source_row=index))
    return entries

def resolve_entry(entry,assets):
    # Confirmed mappings take precedence over normalized matches.
    path=assets.resolve(entry['name'])
    if path:return path,'mapped_or_exact',[]
    candidates=[p for p in assets.files if normalized(p.name)==normalized(entry['name'])]
    folder=normalized(entry.get('folder',''))
    in_folder=[p for p in candidates if normalized(p.parent.name)==folder]
    candidates=list(dict.fromkeys(in_folder or candidates))
    if len(candidates)==1:return candidates[0],'normalized_unique',[]
    if not candidates:
        candidates=[p for p in assets.files
                    if normalized(p.parent.name)==folder
                    and content_key(p.name,entry.get('folder',''))==content_key(entry['name'],entry.get('folder',''))]
        if len(candidates)==1:return candidates[0],'abbreviation_unique',[]
    return None,'ambiguous' if candidates else 'unresolved',[str(p) for p in candidates]

def audit_catalog(entries,assets):
    result=[]
    for entry in entries:
        path,status,candidates=resolve_entry(entry,assets)
        result.append(dict(entry,path=str(path) if path else '',match_status=status,candidates=candidates))
    return result


def write_audit(entries, directory, episode):
    """Save a reviewable table alongside the schedule reports."""
    import html
    import json
    directory=Path(directory)
    stem=directory/f'EP_{episode}_reserve_ads_audit'
    stem.with_suffix('.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for e in entries:
        label='Excluded' if e['excluded'] else ('Matched' if e['path'] else 'Needs review')
        color='#946200' if e['excluded'] else ('#087f5b' if e['path'] else '#c62828')
        cells=[label,e['folder'],e['name'],e['path'] or ' | '.join(e['candidates']),e['notes']]
        rows.append('<tr style="color:'+color+'">'+''.join('<td>'+html.escape(str(c))+'</td>' for c in cells)+'</tr>')
    page='<meta charset="utf-8"><title>INPUT_4 ADS matching</title><style>body{font:14px Segoe UI;padding:24px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px;text-align:left}</style><h2>INPUT_4: Sheet name / actual file</h2><p>Excluded entries are not used for end-day filler. Needs review entries are skipped.</p><table><tr><th>Status</th><th>Folder</th><th>Sheet name</th><th>Actual file</th><th>Notes</th></tr>'+''.join(rows)+'</table>'
    stem.with_suffix('.html').write_text(page,encoding='utf-8')
