import json
import re
from pathlib import Path

def is_no_max(item):
    return bool(re.search(r'no[ _]*(?:smtv[ _]*)?max',item.get('source_name','')+' '+item['target_name'],re.I)) or item.get('draft_variant')=='No Max'

def is_draft_item(item):
    return bool(item.get('draft_duration') or item.get('draft_out_variant'))

def is_max(item):
    if is_no_max(item):return False
    if is_draft_item(item) and 'is_max' in item:return bool(item['is_max'])
    if item.get('source_pair_max'):return True
    return item.get('draft_variant')=='Max' or bool(re.search(r'(?<![a-z])max(?![a-z])',item.get('source_name',''),re.I))

def choices_path(ep):
    return Path(__file__).resolve().parent/'configs'/f'EP_{ep}_max_choices.json'

def source_identity(item):
    if item.get('draft_duration'):
        return {'kind':'draft','seconds':item['draft_duration']}
    path=Path(item.get('source_path',''))
    identity={'kind':'file','path':str(path).casefold()}
    try:
        stat=path.stat();identity.update(size=stat.st_size,mtime_ns=stat.st_mtime_ns)
    except OSError:pass
    return identity


def apply_choices(config):
    path=choices_path(config['episode'])
    choices=json.loads(path.read_text('utf-8')) if path.exists() else {}
    items=config['rename_preview']['items']
    def pair_name(name):
        return re.sub(r'\s*\(?no[ _]*(?:smtv[ _]*)?max\)?', '',name,flags=re.I).casefold()
    no_max_pairs={(i.get('rule'),pair_name(i['target_name'])) for i in items if is_no_max(i) and not i.get('draft_duration') and not i.get('local_fallback')}
    for item in items:
        if not is_draft_item(item):
            item.pop('is_max',None)
            item['source_pair_max']=(not is_no_max(item) and (item.get('rule'),pair_name(item['target_name'])) in no_max_pairs)
            continue
        item.pop('source_pair_max',None)
        choice=choices.get(item['target_name'])
        saved_choice=isinstance(choice,dict) and choice.get('source')==source_identity(item)
        if saved_choice:
            item['is_max']=bool(choice.get('is_max')) and not is_no_max(item)
        elif choice is not None:
            item.pop('is_max',None)
        if is_no_max(item):item['is_max']=False



def remember(ep,item):
    if not is_draft_item(item):return
    path=choices_path(ep)
    choices=json.loads(path.read_text('utf-8')) if path.exists() else {}
    choices[item['target_name']]={'is_max':is_max(item),'source':source_identity(item)}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(choices,ensure_ascii=False,indent=2),encoding='utf-8')
