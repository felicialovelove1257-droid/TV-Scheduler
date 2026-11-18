"""Explicit per-EP media edits. UI locks never imply an airing lock."""
import copy
import hashlib
import json
import re
from pathlib import Path

BASE=Path(__file__).resolve().parent
KINDS=('Show','TSER','priority','ad')
KIND_LABELS=dict(zip(KINDS,('Show','TSER','ADS ưu tiên','ADS thường')))

def storage(ep):return BASE/'configs'/f'EP_{int(ep)}_content_edits.json'

def load(ep):
    p=storage(ep)
    return json.loads(p.read_text('utf-8')) if p.exists() else {'schema':1,'episode':int(ep),'rows':[]}

def save(ep,rows):
    from missing_media import atomic_json
    previous=load(ep)
    old={r['target_name'] for r in previous['rows'] if r.get('target_name') and r.get('edited')}
    active={r['target_name'] for r in rows if r.get('target_name') and r.get('edited')}
    retired=(set(previous.get('retired_targets',[]))|old)-active
    atomic_json(storage(ep),dict(schema=1,episode=int(ep),rows=rows,retired_targets=sorted(retired)))

def cycles(text):
    text=re.sub(r'(\d+)\s*-\s*(\d+)',lambda m:','.join(map(str,range(int(m[1]),int(m[2])+1))),str(text))
    values={int(v) for v in re.findall(r'\d+',str(text))}
    if not values or values-set(range(1,7)):raise ValueError('Cycle phải từ 1 đến 6, ví dụ 1,2,3,4,5,6.')
    return sorted(values)

def identity(item):return 'file:'+item['target_name'].casefold()

def kind(item):
    rule=item.get('rule','')
    return 'TSER' if rule.startswith('teaser') else 'ad' if rule in ('event-ad','manual-ad') else 'Show'

def replaced_missing_temp(row, item):
    """An absent native slot's reported duration is a fallback, not a source override."""
    return bool(item and row.get('native_key') and str(row.get('id','')).startswith('missing:')
                and not row.get('source') and not row.get('custom') and not row.get('position_override')
                and not item.get('draft_duration') and not item.get('local_fallback')
                and item.get('source_path') and Path(item['source_path']).is_file())

def catalog(config):
    from draft_input import expected,item_key
    items=config.get('_content_defaults',config['rename_preview']['items'])
    result=[];seen=set()
    for item in items:
        if item.get('content_manual'):continue
        key=identity(item)
        if key in seen:continue
        seen.add(key)
        label=item_key(item) or Path(item['target_name']).stem
        result.append(dict(id=key,base=item['target_name'],label=label,kind=kind(item),
                           source=item.get('source_path',''),duration=(f"{int(item['draft_duration'])//60}:{int(item['draft_duration'])%60:02}" if item.get('draft_duration') else ''),locked=True,custom=False,
                           block='',anchor='',side='after',cycles='1,2,3,4,5,6',edited=False))
    present={item_key(i) for i in items if not i.get('content_manual')}
    for label in expected(config):
        if label in present:continue
        result.append(dict(id='missing:'+label,base='',native_key=label,label=label,
                           kind='TSER' if label.startswith('TSER ') else 'Show',source='',duration='',
                           locked=True,custom=False,block='',anchor='',side='after',cycles='1,2,3,4,5,6',edited=False))
    saved={r['id']:r for r in load(config['episode'])['rows']}
    for key,row in list(saved.items()):
        if any(item_key(item)==row.get('native_key') and replaced_missing_temp(row,item) for item in items):
            saved.pop(key)
    for i,r in enumerate(result):
        if r['id'] in saved:result[i]=dict(r,**saved.pop(r['id']))
    result.extend(saved.values())
    return result

def validate(row,config,probe=False):
    if not row.get('edited'):return
    if row['kind'] not in KINDS:raise ValueError('Chọn loại Show, TSER hoặc ADS.')
    if not row.get('label','').strip():raise ValueError('Nhập chương trình / part hoặc tên nội dung.')
    cycles(row.get('cycles',''))
    if row.get('custom') or row.get('position_override'):
        if str(row.get('block')) not in {str(i) for i in range(1,9)}:raise ValueError('Chọn block cho nội dung thêm hoặc đổi vị trí.')
        if not row.get('anchor'):raise ValueError('Chọn mục đứng trước/sau nội dung này.')
        if row.get('base')==row['anchor']:raise ValueError('Mốc phải là một mục khác.')
        if row.get('side') not in ('before','after'):raise ValueError('Chọn trước hoặc sau.')
    source=row.get('source','').strip()
    if source:
        p=Path(source)
        if not p.is_file():raise ValueError('Không tìm thấy file: '+source)
        if probe:
            from create_episode import source_duration
            row['source_seconds']=source_duration(p)[0]
    else:
        from draft_input import parse_duration
        parse_duration(row.get('duration',''))

def native_template(config,key,seconds):
    from draft_input import merge_reported,item_key
    test=copy.deepcopy(config);test['_content_template']=True
    test['rename_preview']['items']=[]
    merge_reported(test,{key:dict(duration=f'{int(seconds)//60}:{int(seconds)%60:02}',variant='Chưa xác định')})
    found=next((r for r in test['rename_preview']['items'] if item_key(r)==key),None)
    if not found:raise ValueError('Chưa tạo được mục '+key+'. Hãy dùng Thêm mục và chọn vị trí rõ ràng.')
    return found

def apply(config):
    if config.get('_content_template'):return
    raw=config['rename_preview']['items']
    if any(r.get('content_manual') for r in raw):raw=copy.deepcopy(config.get('_content_defaults',raw))
    raw=[r for r in raw if not r.get('content_manual')]
    fn_teaser_enabled=config.get('schedule_settings',{}).get('tser_fn',True)
    if not fn_teaser_enabled:
        from draft_input import item_key
        raw=[r for r in raw if item_key(r)!='TSER FN']
    config['_content_defaults']=copy.deepcopy(raw)
    saved=load(config['episode'])
    edits=[r for r in saved['rows'] if r.get('edited')]
    applied=[];excluded=[n for n in saved.get('retired_targets',[]) if n not in {r['target_name'] for r in raw}]
    occupied=set()
    for row in edits:
        # Disabled native teaser slots must not be reintroduced by saved temp edits.
        if not fn_teaser_enabled and (row.get('native_key')=='TSER FN' or row.get('label','').strip().upper()=='TSER FN'):
            continue
        validate(row,config)
        base=next((r for r in raw if r['target_name'].casefold()==row.get('base','').casefold()),None)
        if base is None and row.get('native_key'):
            from draft_input import item_key
            candidates=[r for r in raw if item_key(r)==row['native_key']]
            if len(candidates)==1:base=candidates[0]
        if replaced_missing_temp(row,base):
            old_target=row.get('target_name','')
            if old_target and old_target!=base['target_name'] and old_target not in {r['target_name'] for r in raw}:
                excluded.append(old_target)
            continue
        source=row.get('source','').strip()
        from draft_input import parse_duration
        seconds=None if source else parse_duration(row['duration'])
        if base is not None and not row.get('position_override') and not row.get('custom'):
            item=dict(base)
        elif row.get('native_key') and not row.get('position_override'):
            item=native_template(config,row['native_key'],seconds or row.get('source_seconds') or 1)
        else:
            token=hashlib.sha256(row['id'].encode()).hexdigest()[:10]
            label=re.sub(r'[<>:"/\\|?*\x00-\x1f]',' ',row['label']).strip()[:120]
            name=f"{config['episode']} USER {label} {token}.mp4"
            item=dict(rule='manual-content',target_name=name,target_path=str(Path(config['local_dir'])/name))
        if base is not None:
            raw.remove(base)
            if base['target_name']!=item['target_name']:excluded.append(base['target_name'])
        # Remove every stale representation on repeated Scan / save cycles.
        raw=[r for r in raw if r['target_name'].casefold()!=item['target_name'].casefold()]
        for key in ('draft_duration','draft_variant','draft_out_variant','local_fallback','source_size','source_mtime_ns'):
            item.pop(key,None)
        item.update(source_path=source,source_name=Path(source).name if source else 'Manual duration: '+row['label'],content_manual=row['id'])
        if not source:item.update(draft_duration=seconds,draft_variant='Chưa xác định')
        entry=dict(row,target_name=item['target_name'],target_path=item['target_path'],explicit=bool(row.get('custom') or row.get('position_override')))
        if item['target_name'].casefold() in occupied:raise ValueError('Có hai chỉnh sửa cùng mục: '+item['target_name'])
        occupied.add(item['target_name'].casefold())
        raw.append(item);applied.append(entry)
    names={r['target_name'] for r in raw}
    for entry in applied:
        if entry['explicit'] and entry['anchor'] not in names:raise ValueError('Không còn mốc: '+entry['anchor'])
    config['rename_preview']['items']=raw
    config['manual_content']=applied;config['manual_excluded']=excluded


def qc_entries(ep):
    p=BASE/'configs'/f'EP_{int(ep)}_scan.json'
    if not p.exists():return []
    config=json.loads(p.read_text('utf-8'))
    active={r['id'] for r in load(ep)['rows'] if r.get('edited')}
    return [r for r in config.get('manual_content',[]) if r['id'] in active]

def explicit_entries(config):return [r for r in config.get('manual_content',[]) if r.get('explicit')]

def insert_rows(rows,entries,make,missing):
    """Explicit positioning is applied before normal slot and timing rules."""
    rows=list(rows)
    pending=list(entries)
    for _ in range(len(pending)+1):
        progress=False
        for entry in list(pending):
            if entry.get('_cycle') not in {r['cycle'] for r in rows}:pending.remove(entry);continue
            wanted=entry['_cycle'];anchor=entry['anchor']
            matches=[i for i,r in enumerate(rows) if r['cycle']==wanted and r['block']==int(entry['block']) and r['name']==anchor]
            if len(matches)!=1:continue
            index=matches[0];item=make(entry,wanted)
            if entry['side']=='after' and item.get('kind')!='program':
                if rows[index].get('boundary'):item['boundary']=rows[index].pop('boundary')
                rows[index].pop('free_slot',None)
            rows.insert(index+(entry['side']=='after'),item)
            pending.remove(entry);progress=True
        if not pending or not progress:break
    for entry in pending:missing.append(f"Cycle {entry['_cycle']}: không xác định được vị trí cho {entry['label']} sau/trước {entry['anchor']}")
    return rows

def apply_program_rows(config,output,assets):
    entries=explicit_entries(config)
    for cycle in output['cycles']:
        c=cycle['cycle'];rows=cycle['rows']
        # Only explicit edits bypass normal name-based program selection.
        names={r['target_name'] for r in entries}
        rows=[r for r in rows if r['name'] not in names]
        additions=[dict(r,_cycle=c) for r in entries if r['kind']=='Show' and c in cycles(r['cycles'])]
        def make(e,c):return dict(cycle=c,block=int(e['block']),name=e['target_name'],path=e['target_path'],duration=assets.duration(Path(e['target_path'])),kind='program',manual_content=e['id'])
        cycle['rows']=insert_rows(rows,additions,make,output['missing'])

def apply_insert_rows(config,rows,assets,missing):
    entries=explicit_entries(config)
    additions=[dict(e,_cycle=c) for e in entries if e['kind']!='Show' for c in cycles(e['cycles'])]
    def make(e,c):
        kind={'TSER':'teaser','priority':'PRIORITY','ad':'optional'}[e['kind']]
        row=dict(cycle=c,block=int(e['block']),name=e['target_name'],path=e['target_path'],duration=assets.duration(Path(e['target_path'])),kind=kind,manual_content=e['id'])
        if kind=='PRIORITY':row['priority_name']=e['target_name']
        return row
    return insert_rows(rows,additions,make,missing)

def audit_rows(config,rows):
    """Check actual explicit placements without demanding the cut end-day tail."""
    messages=[]
    for e in explicit_entries(config):
        for cycle in cycles(e['cycles']):
            content=[r for r in rows if r.get('cycle')==cycle and r.get('kind')!='marker']
            anchors=[i for i,r in enumerate(content) if r.get('name')==e['anchor']]
            hits=[i for i,r in enumerate(content) if r.get('name')==e['target_name']]
            if not anchors:continue
            if len(hits)>1:messages.append((cycle,e['label']+': trùng mục thêm tay'))
            if e['kind']=='Show' and not hits and anchors[0]<len(content)-1:
                messages.append((cycle,e['label']+': thiếu part thêm tay'))
            if hits and ((e['side']=='after' and hits[0]<anchors[0]) or (e['side']=='before' and hits[0]>anchors[0])):
                messages.append((cycle,e['label']+': sai thứ tự đã chọn'))
    return messages


def classify_qc(row,entries,episode):
    """Recognize explicitly configured items without weakening ordinary name checks."""
    entry=next((e for e in entries if e.get('explicit') and e['target_name'].casefold()==row['name'].casefold()),None)
    if not entry:return False
    row.update(manual_explicit=True,manual_content=entry['id'],block=int(entry['block']))
    if entry['kind']=='Show':
        match=re.match(rf'^{episode}\s+(\w+)',entry['anchor'])
        row.update(kind='program',code=match[1].upper() if match else 'USER')
    else:row['kind']='teaser' if entry['kind']=='TSER' else 'ad'
    return True
