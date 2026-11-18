"""Read-only rule audit of another operator's M3U; never fit clock targets."""
import re
from pathlib import Path
from collections import Counter


def read_m3u(path):
    path=Path(path)
    if path.suffix.lower()=='.docx':
        from docx_schedule import read_docx_schedule
        return read_docx_schedule(path)
    raw=path.read_bytes()
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:text=raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('cp1252')
    rows=[];hint=None
    for line_no,line in enumerate(text.splitlines(),1):
        line=line.strip()
        if line.startswith('#EXTINF:'):
            try:hint=float(line.split(':',1)[1].split(',',1)[0])
            except ValueError:hint=None
        elif line and not line.startswith('#'):
            value=line.strip('"');p=Path(value)
            if not p.is_absolute():p=path.parent/p
            rows.append(dict(line=line_no,path=str(p),name=Path(value.replace('\\','/')).name,hint=hint))
            hint=None
    if not rows:raise ValueError('The M3U contains no media entries.')
    return rows


def episode_from_m3u_name(value):
    """Use the playlist basename, never a parent-folder EP or version number."""
    path=Path(str(value).strip().strip('"').replace('\\','/'))
    if path.suffix.lower() not in ('.m3u','.m3u8','.docx'):return None
    explicit=set(re.findall(r'(?<![A-Za-z0-9])EP[ _-]*(\d{1,6})(?!\d)',path.stem,re.I))
    candidates=explicit or set(re.findall(r'(?<![A-Za-z0-9])(\d{4})(?![A-Za-z0-9])',path.stem))
    return str(int(next(iter(candidates)))) if len(candidates)==1 else None


def starting_notice(text):
    """Extract only the show notice, excluding duration and airing-clock lines."""
    lines=[line.strip() for line in str(text).splitlines() if line.strip()]
    return next((line for line in lines if re.search(r'next\s+day\s+will\s+air|followed\s+by',line,re.I)),'')


def check_show_content(program,rows,episode):
    """Compare original playlist names to INPUT; never validate a renamed title against itself."""
    from episode_scanner import shorten_program_title,shorten_show_title,normalize_episode_order
    from schedule_engine import show_code
    import unicodedata
    def normalized(value):
        value=unicodedata.normalize('NFKD',value).casefold()
        value=''.join(ch for ch in value if not unicodedata.combining(ch))
        value=re.sub(r'\bpart\s+(\d+)\s+of\s+(\d+)\b',r'p\1o\2',value)
        value=re.sub(r'\bp(\d+)\s*(?:of|o)\s*(\d+)\b',r'p\1o\2',value)
        return ' '.join(re.findall(r'[a-z0-9]+',value))
    def part(value):
        m=re.search(r'\bp(\d+)o(\d+)\b',normalized(value))
        return tuple(map(int,m.groups())) if m else None
    expected={}
    for show in program.get('active_shows',[]):
        expected.setdefault(show_code(show['code']).upper(),[]).append(show.get('title',''))
    for code in ('BMD','WOW','AP'):
        title=str(program.get('details',{}).get(code,''))
        if title and not re.match(r'^YES\b',title,re.I):expected.setdefault(code,[]).append(title)
    result=[];seen=set();unverified=set()
    for row in rows:
        if row['kind']!='program':continue
        code=row['code'];name=row['name'];identity=(code,name.casefold())
        if identity in seen:continue
        seen.add(identity)
        raw=normalize_episode_order(Path(name).stem.replace('_',' '),program)
        from fn_rules import identity as fn_identity
        if code=='NWN' and fn_identity(name):continue
        if not re.match(rf'^{episode}\s+{re.escape(code)}\b',raw,re.I):
            result.append(('REVIEW',str(row['cycle'] or '—'),str(row['line']),'Số EP hoặc mã show không khớp: '+name))
            continue
        tail=re.sub(rf'^{episode}\s+{re.escape(code)}\s*','',raw,flags=re.I)
        if re.match(r'^(?:IN|INTRO|OUT|OUTRO)\b',tail,re.I):continue
        if code not in expected:
            continue
        actual=normalized(re.sub(r'\b(?:MAIN|weblink|v\d+|S\d+|SEG\s*\d+|No Max|No NXT)\b',' ',tail,flags=re.I))
        choices=expected[code];matched=[]
        for title in choices:
            variants=[normalized(shorten_program_title(title)),normalized(shorten_show_title(title))]
            title_only=lambda value:' '.join(re.sub(r'\bp\d+o\d+\b',' ',value).split())
            stop={'the','and','with','from','part','show','main','of','to','in','a','an','for','vegan'}
            def words(value):return {w for w in title_only(value).split() if not w.isdigit() and w not in stop and len(w)>2}
            if any(title_only(value) and (title_only(value) in title_only(actual) or len(words(value)&words(actual))>=2 or any(len(w)>=6 for w in words(value)&words(actual))) for value in variants):matched.append(title)
        label='INPUT: '+' / '.join(t.replace('\n',' ') for t in choices)+'\nM3U: '+name
        found=part(tail)
        candidates=matched if matched else choices
        known_parts={part(t) for t in candidates if part(t)}
        if found and known_parts and found not in known_parts:
            wanted_text=' / '.join(f'P{a}o{b}' for a,b in sorted(known_parts))
            result.append(('ERROR',str(row['cycle'] or '—'),str(row['line']),f'Khác part: INPUT {wanted_text}, tên file P{found[0]}o{found[1]}.\n'+label))
            continue
        if len(matched)!=1:
            result.append(('REVIEW',str(row['cycle'] or '—'),str(row['line']),'Cannot confirm the show content from this filename (different, abbreviated or ambiguous title).\n'+label))
            continue
        result.append(('PASS',str(row['cycle'] or '—'),str(row['line']),'Khớp EP, mã show và một phần tên; không thấy part khác trong tên file.'+(' Tên file không ghi part.' if part(matched[0]) and not found else '')+'\n'+label))
    return result


def cut_tail_names(rows,groups,cycles,rotations):
    """Only exempt items proven to occur wholly after the last retained show."""
    from schedule_assets import filename_key
    if len(cycles)<2:return set()
    last=cycles[-1]
    kept=[g for g in groups if g['key'][0]==last]
    order=[g['key'][1] for g in kept]
    if not order or not any(len(order)<len(r) and order==r[:len(order)] for r in rotations):return set()
    evidence={}
    for c in cycles[:-1]:
        reference=[g for g in groups if g['key'][0]==c]
        codes=[g['key'][1] for g in reference]
        if codes not in rotations or codes[:len(order)]!=order:continue
        boundary=reference[len(order)-1]['indices'][-1]
        for index,row in enumerate(rows):
            if row['cycle']!=c or row['kind']=='marker':continue
            for key in {filename_key(row.get('canonical',row['name'])),filename_key(row['name'])}:
                evidence.setdefault(key,[]).append(index>boundary)
    return {key for key,locations in evidence.items() if all(locations)}


def omit_cut_tail_reviews(findings,tail_names,last_cycle):
    """Apply the same cut-tail exemption to all report sections and counts."""
    from schedule_assets import filename_key
    prefixes=(
        'Thiếu teaser có trong nguồn EP và hợp lệ cho ngày này; cần xác nhận lựa chọn teaser/FN hoặc ngoại lệ cuối ngày: ',
        'Bộ FN khác nguồn EP (có thể là bộ được chọn tay); cần đối chiếu phần: ',
        'Priority ADS absent; verify matching or permitted end-day exception: ',
    )
    output=[]
    for finding in findings:
        level,cycle,line,message=finding
        prefix=next((p for p in prefixes if message.startswith(p)),None)
        if level=='REVIEW' and str(cycle)==str(last_cycle) and prefix and filename_key(message[len(prefix):]) in tail_names:continue
        output.append(finding)
    return output


def skipped_end_day_items(rows,tail_names,last_cycle):
    from schedule_assets import filename_key
    present={filename_key(r.get('canonical',r['name'])) for r in rows if r['cycle']==last_cycle}
    seen=set();items=[]
    for row in rows:
        key=filename_key(row.get('canonical',row['name']))
        if row['kind'] not in ('program','ad','teaser') or key not in tail_names or key in present or key in seen:continue
        seen.add(key);items.append(row['name'])
    return items


def cut_reference_tail(rows,groups,cycles,rotations):
    """Locate omitted occurrences, including a second occurrence of the same show."""
    if len(cycles)<2:return []
    order=[g['key'][1] for g in groups if g['key'][0]==cycles[-1]]
    if not order or not any(len(order)<len(r) and order==r[:len(order)] for r in rotations):return []
    reference=[g for g in groups if g['key'][0]==cycles[0]]
    if [g['key'][1] for g in reference] not in rotations:return []
    boundary=reference[len(order)-1]['indices'][-1]
    return [r for i,r in enumerate(rows) if i>boundary and r['cycle']==cycles[0] and r['kind'] not in ('marker','meditation')]


def remaining_cut_items(rows,tail,last_cycle):
    """Do not call a tail item skipped if it was moved into the retained schedule."""
    if not tail:return []
    from schedule_assets import filename_key
    key=lambda r:filename_key(r.get('canonical',r['name']))
    final=Counter(key(r) for r in rows if r['cycle']==last_cycle)
    tail_lines={r['line'] for r in tail}
    prefix=Counter(key(r) for r in rows if r['cycle']==tail[0]['cycle'] and r['line'] not in tail_lines)
    moved=final-prefix
    skipped=[]
    for r in tail:
        if moved[key(r)]>0:moved[key(r)]-=1
        else:skipped.append(r['name'])
    return list(dict.fromkeys(skipped))


def audit(path,episode,notice='',verify_media=False):
    from episode_scanner import load_inputs,extract_program,extract_cycle_rules,extract_ads,proposed_name
    from portable_paths import LOCAL_ROOT,EXPORT_ROOT,local_path
    from schedule_engine import show_code,cycles_from_text
    from schedule_assets import Assets,filename_key
    from show_formats import show_part
    from teaser_selection import eligible_teaser,is_fn_teaser
    from event_ads import identify
    from reserve_ads import read_catalog
    inputs=load_inputs();program=extract_program(inputs['INPUT_1'],episode)
    rules=extract_cycle_rules(inputs['INPUT_2'],episode);ads=extract_ads(inputs['INPUT_3'],episode)
    config=dict(episode=episode,local_dir=str(LOCAL_ROOT/f'EP {episode}'),program=program,ads=ads)
    from ep_content import qc_entries,classify_qc,audit_rows
    config['manual_content']=qc_entries(episode)
    assets=Assets(config);findings=[];rows=read_m3u(path)
    if Path(path).suffix.lower()!='.docx':
        from ad_groups import collapse
        rows,group_findings=collapse(rows,assets);findings.extend(group_findings)
    document_info=rows[0].get('document_info',{})
    summary_cycles=document_info.get('summary_cycles',{})
    is_docx=Path(path).suffix.lower()=='.docx'
    def note(level,cycle,line,message):findings.append((level,str(cycle or '—'),str(line or '—'),message))
    for c in document_info.get('unknown_cycles',[]):note('REVIEW',c,None,'DOCX không có danh sách clip và không ghi rõ kế thừa Cycle 1; chưa kiểm tra được cycle này.')
    for c,notes in document_info.get('notes',{}).items():
        if c not in summary_cycles:
            for n in notes:note('REVIEW',c,n['line'],'Ghi chú DOCX chưa chuyển thành mục lịch: '+n['text'])
    from start_notice import infer_start
    start_block=None;start_issue=''
    if notice.strip():
        start_block,reason=infer_start(notice,program,program.get('schedule_type')=='FN',episode)
        if start_block is None:start_issue='Check the starting-show notice: '+reason
    else:start_issue='Starting-show notice is missing. The required starting position is unverified.'
    if start_issue:note('REVIEW',None,None,start_issue)
    if ads.get('source_row') is None:note('REVIEW',None,None,f'INPUT_3 has no ADS row for EP {episode}; daily ADS checks are incomplete.')
    elif not ads.get('items'):note('REVIEW',None,None,f'INPUT_3 ADS list is empty for EP {episode}; daily ADS checks are incomplete.')
    codes={show_code(s['code']).upper() for s in program.get('active_shows',[])}|{'BMD','WOW','AP','NWN'}
    cycle=0;after_mt=False;markers=[]
    for row in rows:
        name=row['name'];upper=name.upper();row.update(cycle=cycle,after_mt=after_mt,duration=None,kind='ad')
        marker=re.search(r'\bCYCLE\s*(\d+)\b',upper)
        if marker:
            cycle=int(marker[1]);markers.append(cycle);row.update(cycle=cycle,kind='marker');continue
        if re.match(r'^(?:MED[ _]+TIME\b|MEDITATION(?:[ _]+TIME)?(?:[ _]+\d.*)?$)',Path(name).stem,re.I):
            after_mt=True;row.update(kind='meditation',after_mt=True);continue
        if re.fullmatch(r'[- _]+(?:WV[- _]*(?:\(\d+\))?)?[- _]*',Path(name).stem,re.I):row['kind']='marker';continue
        source_name=name+'.mp4' if is_docx and not name.lower().endswith('.mp4') else name
        from fn_rules import identity as fn_identity
        fn_info=fn_identity(source_name)
        canonical,_=proposed_name(source_name,fn_info[0][0] if fn_info else episode,program);row['canonical']=canonical
        if is_docx:
            from docx_schedule import combined_nwn_s1
            if combined_nwn_s1(source_name):
                row['docx_combined_s1']=True
                row['canonical']=canonical=f'{episode} NWN S1ABC.mp4'
        if classify_qc(row,config['manual_content'],episode):pass
        elif re.match(r'^(?:TSER|TEASER)[ _]',name,re.I):row['kind']='teaser'
        else:
            m=re.match(rf'^{episode}\s+([A-Z0-9]+)\b',canonical,re.I)
            if fn_info:
                row.update(kind='program',code='NWN')
            elif m and m[1].upper() in codes:
                row.update(kind='program',code=m[1].upper())
            elif re.match(r'^\d{4}\s+',canonical) and not identify(name,episode):
                note('REVIEW',cycle,row['line'],'Unrecognized program or different EP: '+name)
        if row['kind']=='teaser' and not row.get('manual_explicit') and not eligible_teaser(name,episode):note('ERROR',cycle,row['line'],'Teaser is not eligible for this EP / AP campaign: '+name)
        if not verify_media or is_docx:continue
        p=local_path(row['path'])
        if not p.is_file():
            local=Path(config['local_dir'])/canonical
            if local.is_file():p=local;note('REVIEW',cycle,row['line'],'Playlist path unavailable; duration checked using local counterpart: '+name)
            else:note('REVIEW',cycle,row['line'],'Media path unavailable; cannot verify file or actual duration: '+row['path'])
        if p.is_file():
            try:row['duration']=assets.duration(p)
            except Exception as exc:note('REVIEW',cycle,row['line'],'Cannot measure duration: '+name+' — '+str(exc))
        if row['duration'] is None and row['hint'] and row['hint']>0:row['duration']=row['hint'];row['duration_hint']=True
    if not markers:
        note('REVIEW',None,None,'No CYCLE markers. Cycle-based rules cannot be verified; add cycle markers to the M3U.')
    elif markers!=list(range(1,max(markers)+1)):note('ERROR',None,None,'Cycle markers must be consecutive without repeats: '+str(markers))
    # Consecutive program groups: ADS/teasers never hide which two segments they separate.
    groups=[]
    source_names=[proposed_name(p.name,episode,program)[0] for p in (EXPORT_ROOT/f'EP {episode}').glob('*.mp4')]
    for index,row in enumerate(rows):
        if row['kind']!='program':continue
        key=(row['cycle'],row['code'])
        if not groups or groups[-1]['key']!=key:groups.append(dict(key=key,indices=[]))
        groups[-1]['indices'].append(index)
    for group in groups:
        ids=group['indices'];first=rows[ids[0]];code=first['code'];c=first['cycle']
        programs=[rows[i] for i in ids]
        for left,right in zip(ids,ids[1:]):
            a,b=rows[left],rows[right];gap=[r for r in rows[left+1:right] if r['kind'] in ('ad','teaser')]
            segmented=code not in ('NWN','BMD','WOW','AP') and re.search(r'\bS\d+\b',a['canonical']) and re.search(r'\bS\d+\b',b['canonical'])
            continuous=code!='NWN' and (code=='AP' or code in ('BMD','WOW') or show_part(a['canonical'],code) in ('IN','MAIN','OUT'))
            if segmented:
                if len(gap)!=1:note('ERROR',c,a['line'],'Exactly one ADS/teaser is required between segments after '+a['name'])
                elif not verify_media:pass
                elif gap[0]['kind']=='teaser':pass
                elif gap[0]['duration'] is None:note('REVIEW',c,gap[0]['line'],'Cannot verify that the segment ADS is under 2 minutes.')
                elif gap[0]['duration']>=120:note('ERROR',c,gap[0]['line'],'Segment ADS must be under 2 minutes: '+gap[0]['name'])
            elif continuous:
                unexpected=[r for r in gap if not (code in ('BMD','WOW') and re.match(r'^M intro\b',r['name'],re.I))]
                if unexpected:note('ERROR',c,unexpected[0]['line'],'ADS/teaser inside continuous '+code+' IN/MAIN/OUT or AP parts.')
            if code=='NWN' and gap:
                if len(gap)>1:note('ERROR',c,gap[0]['line'],'More than one insertion between NWN parts.')
                for item in gap:
                    if item['kind']!='teaser' and item['duration'] is not None and item['duration']>=120:note('ERROR',c,item['line'],'ADS inside NWN must be under 2 minutes.')
        if code=='NWN':
            segs=[]
            for r in programs:
                names=[f'NWN S1{part}' for part in 'ABC'] if r.get('docx_combined_s1') else [r['canonical']]
                segs.extend(re.search(r'\bNWN\s+S([123])([ABC]?)\b',n) for n in names)
            order=[(int(m[1]),m[2]) for m in segs if m]
            if order!=sorted(order):note('ERROR',c,first['line'],'NWN segment order is reversed.')
            present={(m[1]+m[2]) for m in segs if m}
            for part in ('1A','1C','2','3'):
                if part not in present:note('ERROR',c,first['line'],'NWN group is missing S'+part)
            from fn_rules import identity as fn_identity,validate as validate_fn
            fn_names=[r['canonical'] for r in programs if 'NWN S1B' in r['canonical']]
            parts=[fn_identity(n) for n in fn_names if fn_identity(n)]
            for problem in validate_fn(fn_names):note('ERROR',c,first['line'],problem)
            if program.get('schedule_type')=='FN' and not parts:
                if is_docx and any('NWN S1B' in r['canonical'] or r.get('docx_combined_s1') for r in programs):
                    pass
                else:note('ERROR',c,first['line'],'FN schedule has no recognized NWN S1B parts.')
        elif code=='AP':
            from ap_rules import part_id
            parts=[part_id(r['canonical']) for r in programs];parts=[p for p in parts if p]
            if parts and parts!=[chr(ord('A')+i) for i in range(len(parts))]:note('ERROR',c,first['line'],'AP parts must run A, B, C… without gaps or repeats.')
            source_parts={part_id(n) for n in source_names if re.match(rf'^{episode}\s+AP\b',n,re.I) and part_id(n)}
            if source_parts-set(parts):note('ERROR',c,first['line'],'AP thiếu part: '+', '.join(sorted(source_parts-set(parts))))
        else:
            parts=[int(m[1]) for r in programs if (m:=re.search(r'\bS(\d+)\b',r['canonical']))]
            if parts and parts!=list(range(1,max(parts)+1)):note('ERROR',c,first['line'],'Show segments are missing, repeated or out of order: '+code)
            if not parts:
                roles=[show_part(r['canonical'],code) for r in programs]
                from wow_rules import has_wow_intro_outro
                triplet=(code=='BMD' or (code=='WOW' and has_wow_intro_outro(rules))
                         or any(role in ('IN','OUT') for role in roles)
                         or (code not in ('BMD','WOW') and any(re.match(rf'^{episode}\s+{re.escape(code)}\b',n,re.I) and show_part(n,code) in ('IN','OUT') for n in source_names)))
                if triplet and roles!=['IN','MAIN','OUT']:
                    note('ERROR',c,first['line'],'Expected IN → MAIN → OUT for '+code+'; found '+str(roles))
        if code=='BMD':
            following=next((g['key'][1] for g in groups[groups.index(group)+1:] if g['key'][1]!='NWN'),None)
            out=programs[-1];m=re.search(r'UP NXT\s+([A-Z0-9]+)',out['canonical'],re.I)
            if following and m and m[1].upper()!=following:note('ERROR',c,out['line'],f'BMD OUT announces {m[1]}, but next show is {following}.')
    active_cycles=sorted({r['cycle'] for r in rows if r['cycle'] and r['kind']=='program'})
    previous_insert=None
    for row in rows:
        if row['kind']=='marker':continue
        if row['kind'] in ('ad','teaser'):
            if previous_insert and not re.match(r'^M intro\b',row['name'],re.I) and not re.match(r'^M intro\b',previous_insert['name'],re.I):
                note('ERROR',row['cycle'],row['line'],'Consecutive insertions share one gap: '+previous_insert['name']+' / '+row['name'])
            previous_insert=row
        else:previous_insert=None
    from ap_rules import slot_family
    family=slot_family(episode,program,[])
    show_slots={s.get('output_slot',s['slot']):show_code(s['code']).upper() for s in program.get('active_shows',[])}
    expected_order=[family]+([show_slots[1]] if 1 in show_slots and program.get('schedule_type')!='FN' else [])+['BMD','NWN']
    expected_order+=([show_slots[2]] if 2 in show_slots else [])+([show_slots[3]] if 3 in show_slots else [])+['BMD','NWN']
    rotations=[expected_order[i:]+expected_order[:i] for i in range(len(expected_order))]
    if start_block is not None:
        block_order=[1]+([2] if 1 in show_slots and program.get('schedule_type')!='FN' else [])+[3,4]
        block_order+=([5] if 2 in show_slots else [])+([6] if 3 in show_slots else [])+[7,8]
        if start_block in block_order:
            position=block_order.index(start_block)
            rotations=[expected_order[position:]+expected_order[:position]]
            actual_first=[g['key'][1] for g in groups if active_cycles and g['key'][0]==active_cycles[0]]
            if actual_first and actual_first!=rotations[0][:len(actual_first)]:
                start_issue='Starting-show order does not match the notice. Expected: '+' → '.join(rotations[0])+'. Found: '+' → '.join(actual_first)+'. Check the notice and M3U.'
                note('ERROR',active_cycles[0],None,start_issue)
        else:
            start_issue='Starting block from the notice is absent from the current INPUT show rotation.'
            note('REVIEW',None,None,start_issue)
    tail_names=cut_tail_names(rows,groups,active_cycles,rotations)
    reference_tail=cut_reference_tail(rows,groups,active_cycles,rotations)
    def omitted_tail(name,c):return bool(active_cycles and c==active_cycles[-1] and filename_key(name) in tail_names)
    fixed_checks=[];daily_checks=[]
    for c in active_cycles:
        content=[r for r in rows if r['cycle']==c and r['kind'] not in ('marker','meditation')]
        actual_order=[g['key'][1] for g in groups if g['key'][0]==c]
        valid_orders=[order for order in rotations if actual_order==order or (c==active_cycles[-1] and actual_order==order[:len(actual_order)])]
        if not valid_orders:note('ERROR',c,None,'Show rotation differs from INPUT. Found: '+' → '.join(actual_order)+'. Expected a rotation of: '+' → '.join(expected_order))
        teasers=Counter(r['canonical'].casefold() for r in content if r['kind']=='teaser')
        for name,count in teasers.items():
            limit=2 if is_fn_teaser(name) else 1
            if count>limit:note('REVIEW',c,None,f'Teaser used {count} times (normal limit {limit}); confirm segment-gap fallback: {name}')
        for i,r in enumerate(content):
            if re.search(r'AD[ _]SMTV INTRO',r['name'],re.I) and i!=0:note('ERROR',c,r['line'],'SMTV INTRO is only allowed at the beginning of the cycle.')
        def rule_label(r):
            n=r.get('canonical',r['name']).upper()
            for family in ('BMD','WOW'):
                if family in n and ('M INTRO' in n or family+' IN' in n):
                    for variant in ('LONG','SHORT'):
                        if variant in n:return f'{family} M intro {variant}'.casefold()
            if 'ABORTION 07' in n:return 'abortion 07'
            if 'HYG' in n:return 'hygiene'
            if 'QY WARN' in n:return 'm qy warning'
        for label,value in rules.items():
            if label=='source_column':continue
            expected=c in cycles_from_text(str(value));found=[r for r in content if rule_label(r)==label.casefold()]
            for r in found:r['fixed_rule']=label
            references=[r for r in rows if r['cycle'] in active_cycles[:-1] and rule_label(r)==label.casefold()]
            if not found and references and all(omitted_tail(r.get('canonical',r['name']),c) for r in references):
                fixed_checks.append(dict(cycle=c,name=label,expected=expected,count=0,cut=True))
                continue
            if c in summary_cycles:
                note_labels=[rule_label({'name':n['text']}) for n in summary_cycles[c]]
                for n,nlabel in zip(summary_cycles[c],note_labels):
                    if nlabel:n['fixed_rule']=nlabel
                count=len(found)
                if 'm intro' in label.casefold() and any(n and 'm intro' in n for n in note_labels):
                    count=int(label.casefold() in note_labels)
                elif label.casefold() in note_labels:count=0 if found else 1
                fixed_checks.append(dict(cycle=c,name=label,expected=expected,count=count))
                if expected!=bool(count):note('ERROR',c,None,f'{label}: expected {"present" if expected else "absent"} in this cycle; found {count}.')
                continue
            fixed_checks.append(dict(cycle=c,name=label,expected=expected,count=len(found)))
            if len(found)>1:note('ERROR',c,found[1]['line'],f'Mục cố định bị lặp {len(found)} lần: '+label)
            if expected!=bool(found):note('REVIEW' if c==active_cycles[-1] else 'ERROR',c,found[0]['line'] if found else None,f'{label}: expected {"present" if expected else "absent"} in this cycle; found {len(found)}. Check any permitted post-MT exception.')
        for ad in ads.get('items',[]):
            resolved=assets.resolve(ad['name']);ident=filename_key(resolved.name if resolved else ad['name'])
            hits=[r for r in content if filename_key(r['name'])==ident]
            if re.search(r'daily\s+(?:news\s+)?scroll',ad['name'],re.I):
                hits=[r for r in content if re.search(r'NWN\s+Daily\s+Scroll',r.get('canonical',''),re.I)]
                resolved=True
            rule=rule_label({'name':ad['name']})
            if c in summary_cycles and rule:
                match=next((x for x in fixed_checks if x['cycle']==c and x['name'].casefold()==rule),None)
                if match is not None:hits=[None]*match['count']
            matched_name=resolved.name if hasattr(resolved,'name') else ad['name']
            daily_checks.append(dict(cycle=c,name=ad['name'],priority=ad.get('priority_class','NORMAL'),count=len(hits),resolved=bool(resolved),matched_name=matched_name,cut=not hits and omitted_tail(matched_name,c)))
    # Do-not-air catalog labels are checked independently of the normal resolver.
    blocked={filename_key(e['name']) for e in read_catalog(inputs.get('INPUT_4',[])) if e['excluded']}
    for r in rows:
        if r['kind'] in ('ad','teaser') and (filename_key(r['name']) in blocked or re.search(r'need[ _]*fix|do[ _]*not[ _]*air',r['name'],re.I)):
            note('ERROR',r['cycle'],r['line'],'File is marked not for airing / needs repair: '+r['name'])
    source=EXPORT_ROOT/f'EP {episode}'
    if source.is_dir():
        campaigns={}
        expected_teasers=set()
        for p in source.glob('*.mp4'):
            match=identify(p.name,episode)
            if match:campaigns.setdefault(match[0].casefold(),set()).add(match[1])
            canon,_=proposed_name(p.name,episode,program)
            if re.match(r'^(TSER|TEASER)[ _]',p.name,re.I) and eligible_teaser(p.name,episode):expected_teasers.add(canon.casefold())
        from missing_media import source_choices
        # Like preparation, a real source FN teaser supersedes an old manual/temp choice.
        real_fn=any(is_fn_teaser(n) for n in expected_teasers)
        for choice in source_choices(episode)['items']:
            name=choice.get('target_name','')
            if not re.match(r'^(TSER|TEASER)[ _]',name,re.I) or not eligible_teaser(name,episode):continue
            if real_fn and is_fn_teaser(name):continue
            if Path(choice['source_path']).is_file() or Path(choice['target_path']).is_file():expected_teasers.add(name.casefold())
        for c in active_cycles:
            present={r.get('canonical','').casefold() for r in rows if r['cycle']==c}
            for r in rows:
                if r['cycle']!=c:continue
                canonical=r.get('canonical','').casefold()
                if r['kind']=='teaser' and not r.get('manual_explicit') and eligible_teaser(r['name'],episode) and canonical not in expected_teasers:
                    note('REVIEW',c,r['line'],'Teaser có trong lịch nhưng không khớp danh sách nguồn EP; kiểm tra tên hoặc file được chọn tay: '+r['name'])
            for missing in sorted(expected_teasers-present):
                if omitted_tail(missing,c):continue
                note('REVIEW',c,None,'Thiếu teaser có trong nguồn EP và hợp lệ cho ngày này; cần xác nhận lựa chọn teaser/FN hoặc ngoại lệ cuối ngày: '+missing)
        for title,parts in campaigns.items():
            if sorted(parts)!=list(range(1,max(parts)+1)):note('REVIEW',None,None,'Event source has missing parts: '+title);continue
            for index,c in enumerate(active_cycles):
                wanted=index%len(parts)+1
                hits=[r for r in rows if r['cycle']==c and (m:=identify(r['name'],episode)) and m[0].casefold()==title]
                if len(hits)!=1 or identify(hits[0]['name'],episode)[1]!=wanted:
                    post_mt=any(r['after_mt'] for r in rows if r['cycle']==c)
                    note('REVIEW' if post_mt and not hits else 'ERROR',c,hits[0]['line'] if hits else None,f'Event {title}: expected AD {wanted} once; verify post-MT exception if omitted.')
    else:note('REVIEW',None,None,'EP source folder unavailable; cannot verify the required holiday ADS campaign.')
    if not is_docx:
        from fn_rules import expected_sources
        expected_fn=expected_sources(episode,program,EXPORT_ROOT,LOCAL_ROOT)
        for group in groups:
            if group['key'][1]!='NWN':continue
            c=group['key'][0]
            fn_rows=[rows[i] for i in group['indices'] if 'NWN S1B' in rows[i].get('canonical','').upper()]
            if program.get('schedule_type')!='FN' and not fn_rows:continue
            present={r['canonical'].casefold() for r in fn_rows}
            for r in fn_rows:
                if r['canonical'].casefold() not in expected_fn:
                    note('REVIEW',c,r['line'],'FN S1B có trong lịch nhưng không khớp bộ nguồn EP; kiểm tra bộ được chọn tay: '+r['name'])
            for missing in sorted(expected_fn-present):
                if not omitted_tail(missing,c):note('REVIEW',c,rows[group['indices'][0]]['line'],'Bộ FN khác nguồn EP (có thể là bộ được chọn tay); cần đối chiếu phần: '+missing)
    if not groups:note('REVIEW',None,None,'No program groups recognized. Check EP and filename conventions.')
    findings.extend(check_show_content(program,[r for r in rows if not r.get('manual_explicit')],episode))
    for cycle,message in audit_rows(config,rows):note('ERROR',cycle,None,message)
    if summary_cycles:
        findings=[('REVIEW',c,line,'Cycle kế thừa từ Cycle 1; cần xác nhận ngoại lệ DOCX trước khi kết luận: '+vietnamese_finding(message))
                  if level=='ERROR' and c.isdigit() and int(c) in summary_cycles and not message.startswith('Teaser is not eligible for this EP / AP campaign: ') else (level,c,line,message)
                  for level,c,line,message in findings]
    findings=omit_cut_tail_reviews(list(dict.fromkeys(findings)),tail_names,active_cycles[-1] if active_cycles else None)
    return dict(episode=episode,path=str(path),rows=len(rows),cycles=active_cycles,findings=findings,notice=notice,start_issue=start_issue,
                document_info=document_info,source_format='DOCX' if is_docx else 'M3U',
                cut_tail_names=sorted(tail_names),
                cut_reference_lines=[r['line'] for r in reference_tail],
                skipped_end_day=remaining_cut_items(rows,reference_tail,active_cycles[-1]) if reference_tail else skipped_end_day_items(rows,tail_names,active_cycles[-1] if active_cycles else None),
                playlist_rows=rows,fixed_checks=fixed_checks,daily_checks=daily_checks,
                expected_order=rotations[0] if len(rotations)==1 else expected_order,order_anchored=start_block is not None,
                scope='Check EP, program code and partial title against INPUT; report differing stated content parts. Media existence, duration and MT/24h targets are not checked by default. REVIEW requires operator confirmation.')


def finding_group(finding):
    message=finding[3].casefold()
    if any(word in message for word in ('media path','playlist path','measure duration','actual duration','cannot verify the under')):return 'Media paths / duration verification'
    if 'input:' in message or 'content title' in message:return 'Show content vs INPUT'
    if 'starting' in message or 'rotation' in message or 'cycle markers' in message:return 'Starting show / cycle order'
    if 'event' in message or 'holiday' in message:return 'Holiday ADS'
    if 'intro' in message or 'priority ads' in message or 'not for airing' in message:return 'ADS / Long–Short rules'
    if 'teaser' in message:return 'Teasers / segment insertions'
    return 'Show structure / other checks'


def grouped_findings(findings):
    """Group repeated notices across cycles without discarding their locations."""
    result={}
    for level,cycle,line,message in findings:
        key=(level,message)
        item=result.setdefault(key,dict(level=level,message=message,group=finding_group((level,cycle,line,message)),locations=[]))
        item['locations'].append((cycle,line))
    return sorted(result.values(),key=lambda item:({'ERROR':0,'REVIEW':1,'PASS':2}.get(item['level'],3),item['group'],item['message']))


def render_report(result):
    """Standalone final QC report; counts refer to distinct findings, not files."""
    from html import escape
    def esc(value):return escape(str(value),quote=True)
    items=grouped_findings(result['findings'])
    counts=Counter(item['level'] for item in items)
    verdict='NEEDS CORRECTION' if counts['ERROR'] else 'NEEDS REVIEW' if counts['REVIEW'] else 'NO VIOLATIONS FOUND IN CHECKS PERFORMED'
    parts=['<!doctype html><html lang="en"><meta charset="utf-8">',
           '<title>External schedule QC</title><style>body{font:15px Segoe UI,Arial,sans-serif;color:#17324d;background:#f3f5f7;margin:0}main{max-width:1100px;margin:24px auto;padding:30px;background:white}h1{font-size:24px}h2{font-size:18px;margin-top:32px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #dde3e8;text-align:left}.ERROR{color:#c62828}.REVIEW{color:#956600}.PASS{color:#008060}.card{padding:12px;border-left:4px solid currentColor;background:#f7f8fa;margin:10px 0;overflow-wrap:anywhere}.location,small{color:#536575}summary{cursor:pointer;padding:10px}button{padding:8px 18px;cursor:pointer}@media print{button{display:none}main{margin:0;padding:0}}</style><main>',
           '<button onclick="window.print()">Print / Save PDF</button>',
           f'<h1>EP {esc(result.get("episode",""))} — EXTERNAL SCHEDULE QC</h1>',
           f'<p class="{"ERROR" if counts["ERROR"] else "REVIEW" if counts["REVIEW"] else "PASS"}"><b>{verdict}</b></p>',
           f'<p><b>Playlist:</b> {esc(result.get("path",""))}<br><b>Starting-show notice:</b> {esc(result.get("notice",""))}<br><b>Entries:</b> {esc(result["rows"])} · <b>Cycles:</b> {esc(", ".join(map(str,result["cycles"])))}</p>',
           '<p>'+esc(result['scope'])+'</p>',
           f'<h2>1. SUMMARY</h2><p>{counts["ERROR"]} distinct errors · {counts["REVIEW"]} distinct findings requiring review · {counts["PASS"]} matched findings.</p>',
           '<p>Repeated findings are grouped across cycles. Missing media paths mean the file or duration could not be verified on this machine; they are not automatically schedule-rule errors. A review finding is not a pass.</p>',
           '<table><tr><th>Check group</th><th>Errors</th><th>Review</th><th>Matched</th></tr>']
    for group in dict.fromkeys(item['group'] for item in items):
        tally=Counter(item['level'] for item in items if item['group']==group)
        parts.append(f'<tr><td>{esc(group)}</td><td class="ERROR">{tally["ERROR"]}</td><td class="REVIEW">{tally["REVIEW"]}</td><td class="PASS">{tally["PASS"]}</td></tr>')
    parts.append('</table>')
    sections=[('2. RULE ERRORS',[i for i in items if i['level']=='ERROR'],False),
              ('3. ITEMS REQUIRING ATTENTION',[i for i in items if i['level']=='REVIEW' and i['group']!='Media paths / duration verification'],False),
              ('4. MEDIA / DURATION VERIFICATION',[i for i in items if i['level']=='REVIEW' and i['group']=='Media paths / duration verification'],True),
              ('5. MATCHED FINDINGS',[i for i in items if i['level']=='PASS'],True)]
    for title,findings,collapsed in sections:
        parts.append('<h2>'+title+'</h2>')
        if not findings:parts.append('<p>No findings in this category.</p>');continue
        if collapsed:parts.append(f'<details><summary>{len(findings)} distinct findings — expand details</summary>')
        for item in findings:
            locations='; '.join(f'Cycle {cycle}, M3U line {line}' for cycle,line in item['locations'])
            parts.append(f'<div class="card {item["level"]}"><b>{item["level"]}</b> — {esc(item["message"])}<p class="location">{esc(locations)}</p></div>')
        if collapsed:parts.append('</details>')
    parts.append('</main></html>')
    return '\n'.join(parts)


def vietnamese_finding(message):
    translations={
        'Consecutive insertions share one gap: ':'Hai mục chèn liên tiếp trong cùng một khe: ',
        'Media path unavailable; cannot verify file or actual duration: ':'Không có file ở đường dẫn M3U; chưa xác minh file/thời lượng thật: ',
        'Playlist path unavailable; duration checked using local counterpart: ':'Không có đường dẫn M3U; đã đo thời lượng bằng file tương ứng trên máy này: ',
        'Cannot measure duration: ':'Không đo được thời lượng: ',
        'Priority ADS absent; verify matching or permitted end-day exception: ':'Thiếu ADS ưu tiên; kiểm tra nhận diện tên hoặc ngoại lệ cuối ngày: ',
        'Show title and stated content part match INPUT by filename.':'Tên show và số phần trong tên file khớp INPUT.',
        'Cannot confirm the show content from this filename (different, abbreviated or ambiguous title).':'Chưa xác nhận được nội dung show từ tên file (tên khác, viết tắt hoặc chưa rõ).',
        'INPUT has no usable content title to compare. File order can be checked, but the subject/title is unverified.':'INPUT không có tiêu đề nội dung đủ rõ để so sánh. Có thể kiểm tra thứ tự file, chưa xác minh được nội dung.',
        'Exactly one ADS/teaser is required between segments after ':'Phải có đúng một ADS/teaser giữa các segment, sau ',
        'Cannot verify that the segment ADS is under 2 minutes.':'Chưa xác minh được ADS giữa segment có dưới 2 phút.',
        'Segment ADS must be under 2 minutes: ':'ADS giữa segment phải dưới 2 phút: ',
        'Teaser is not eligible for this EP / AP campaign: ':'Teaser không hợp lệ cho EP hoặc đợt AP này: ',
        'SMTV INTRO is only allowed at the beginning of the cycle.':'SMTV INTRO chỉ được đứng đầu cycle.',
        'NWN segment order is reversed.':'Thứ tự segment NWN bị đảo.',
        'NWN group is missing S':'NWN thiếu S',
        'FN schedule has no recognized NWN S1B parts.':'Lịch FN chưa nhận ra phần NWN S1B.',
        'FN parts may be out of order; check event/reair grouping.':'Phần FN có thể sai thứ tự; kiểm tra bộ sự kiện/reair.',
        'FN part numbers have a gap.':'Thiếu số phần trong bộ FN.',
        'FN P1A exists but P1B is missing.':'FN có P1A nhưng thiếu P1B.',
        'AP parts must run A, B, C… without gaps or repeats.':'AP phải chạy A, B, C… không thiếu hoặc lặp phần.',
        'Show segments are missing, repeated or out of order: ':'Segment show bị thiếu, lặp hoặc sai thứ tự: ',
        'File is marked not for airing / needs repair: ':'File được đánh dấu không phát / cần sửa: ',
        'EP source folder unavailable; cannot verify the required holiday ADS campaign.':'Không truy cập được thư mục EP nguồn; chưa kiểm tra được ADS ngày lễ bắt buộc.',
        'Check any permitted post-MT exception.':'Cần kiểm tra ngoại lệ được phép sau MT.',
        'Starting-show notice is missing. The required starting position is unverified.':'Thiếu thông báo show mở đầu; chưa xác minh được vị trí bắt đầu.',
        'Unrecognized program or different EP: ':'Chưa nhận diện được chương trình hoặc khác EP: ',
        'More than one insertion between NWN parts.':'Có hơn một mục chèn giữa các phần NWN.',
        'Starting-show order does not match the notice. Expected: ':'Thứ tự show mở đầu không khớp thông báo. Dự kiến: ',
        '. Found: ':'. Thực tế: ',
        '. Check the notice and M3U.':'. Kiểm tra lại thông báo và M3U.',
        'Show rotation differs from INPUT. Found: ':'Vòng show khác INPUT. Thực tế: ',
        '. Expected a rotation of: ':'. Vòng show trong INPUT: ',
        'Expected IN → MAIN → OUT for ':'Cần có IN → MAIN → OUT cho ',
        '; found ':'; thực tế ',
        'ADS/teaser inside continuous ':'ADS/teaser nằm bên trong chương trình liền mạch ',
        'Check the starting-show notice: ':'Kiểm tra thông báo show mở đầu: ',
        'ADS inside NWN must be under 2 minutes.':'ADS trong NWN phải dưới 2 phút.',
        'No CYCLE markers. Cycle-based rules cannot be verified; add cycle markers to the M3U.':'Không có dấu CYCLE; chưa thể kiểm tra quy tắc từng cycle. Cần thêm dấu cycle vào M3U.',
    }
    for old,new in translations.items():message=message.replace(old,new)
    message=re.sub(r'Teaser used (\d+) times \(normal limit (\d+)\); confirm segment-gap fallback: ',r'Teaser dùng \1 lần (giới hạn thường \2); xác nhận ngoại lệ chèn giữa segment: ',message)
    message=re.sub(r'BMD OUT announces (.*), but next show is (.*)\.',r'BMD OUT báo tiếp theo là \1, nhưng show sau là \2.',message)
    message=re.sub(r': expected (present|absent) in this cycle; found (\d+)\.',lambda m:': quy định '+('có' if m[1]=='present' else 'không có')+f'; thực tế {m[2]} mục.',message)
    return message


def inventory_items(items):
    selected=[]
    for item in items:
        message=item['message'].casefold()
        if item['level'] not in ('ERROR','REVIEW') or item['group']=='Media paths / duration verification':continue
        if message.startswith('cycle kế thừa từ cycle 1;'):continue
        if message.startswith('starting-show order does not match the notice.'):continue
        if any(word in message for word in ('teaser','fn ','s1b','nwn','show rotation','show segments','show content','content part','starting-show','unrecognized program','expected in →','ap parts','số ep hoặc mã show','khác part')):selected.append(item)
    return selected


def readable_inventory(items):
    """Explain discrepancies once, using short playlist/source comparisons."""
    from teaser_selection import is_fn_teaser
    selected=inventory_items(items)
    extra='Teaser có trong lịch nhưng không khớp danh sách nguồn EP; kiểm tra tên hoặc file được chọn tay: '
    missing='Thiếu teaser có trong nguồn EP và hợp lệ cho ngày này; cần xác nhận lựa chọn teaser/FN hoặc ngoại lệ cuối ngày: '
    def cycles(item):return tuple(dict.fromkeys(str(c) for c,_ in item['locations']))
    def name(item,prefix):return item['message'][len(prefix):]
    extras=[i for i in selected if i['message'].startswith(extra) and is_fn_teaser(name(i,extra))]
    misses=[i for i in selected if i['message'].startswith(missing) and is_fn_teaser(name(i,missing))]
    handled=set();cards=[]
    invalid='Teaser is not eligible for this EP / AP campaign: '
    def teaser_title(value):
        value=re.sub(r'\.(?:mp4|mov)$','',value,flags=re.I).replace('_',' ').casefold()
        value=re.sub(r'^(?:tser|teaser)\s+|(?<!\d)\d{4}(?!\d)|\bv\d+\b',' ',value)
        return ' '.join(value.split())
    for item in selected:
        if not item['message'].startswith(invalid):continue
        wrong=name(item,invalid)
        matches=[m for m in selected if id(m) not in handled and m['message'].startswith(missing)
                 and teaser_title(name(m,missing))==teaser_title(wrong) and set(cycles(m))==set(cycles(item))]
        handled.add(id(item))
        lines=['Cycle: '+', '.join(cycles(item)),'Trong lịch: '+wrong]
        if len(matches)==1:
            handled.add(id(matches[0]));lines.append('Nguồn: '+name(matches[0],missing))
        cards.append(('✗ Teaser sai EP/ngày phát',lines))
    # Only pair when there is one unambiguous FN candidate on each side.
    if len(extras)==len(misses)==1 and set(cycles(extras[0]))==set(cycles(misses[0])):
        a,b=extras[0],misses[0];handled.update((id(a),id(b)))
        cards.append(('⚠ Tên teaser khác nhau',[
            'Cycle: '+', '.join(cycles(a)),
            'Trong lịch: '+name(a,extra),
            'Nguồn: '+name(b,missing)]))
    for item in selected:
        if id(item) in handled:continue
        message=item['message'];where='Cycle: '+', '.join(cycles(item))
        if message.startswith(missing):
            cards.append(('⚠ Thiếu teaser',[
                where,name(item,missing)]))
        elif message.startswith(extra):
            cards.append(('⚠ Tên teaser chưa khớp nguồn',[
                where,'Trong lịch: '+name(item,extra)]))
        elif message.startswith('Show rotation differs from INPUT. Found: '):
            found=message[len('Show rotation differs from INPUT. Found: '):]
            actual,wanted=(found.split('. Expected a rotation of: ',1)+[''])[:2]
            cards.append(('✗ Sai thứ tự show',[
                where,
                'Trong lịch: '+actual.rstrip('.'),
                'INPUT: '+wanted.rstrip('.')]))
        else:
            lines=[where,vietnamese_finding(message)]
            cards.append(('✗ CẦN SỬA' if item['level']=='ERROR' else '⚠ CẦN XÁC NHẬN',lines))
    output=[]
    for index,(title,lines) in enumerate(cards,1):
        output.append(f'{title} — {lines[0]}');output.append('\n'.join(lines[1:]))
    return output


def covered_by_ad_sections(item,result):
    """Suppress only presence/count findings already represented by cycle cells."""
    message=item['message']
    inherited='Cycle kế thừa từ Cycle 1; cần xác nhận ngoại lệ DOCX trước khi kết luận: '
    if message.startswith(inherited):return True
    if message.startswith('Starting-show order does not match the notice.'):return True
    if result.get('order_anchored') and message.startswith('Show rotation differs from INPUT.'):
        first=str(result['cycles'][0]) if result.get('cycles') else ''
        if any(str(c)==first for c,_ in item['locations']):return True
    locations={str(c) for c,_ in item['locations']}
    for check in result.get('fixed_checks',[]):
        name=check['name']
        presence=re.search(re.escape(name)+r': expected (?:present|absent) in this cycle; (?:found|actual|thực tế)\s+\d+',message,re.I)
        duplicate=(message.startswith('Mục cố định bị lặp ') and message.endswith(': '+name))
        if not (presence or duplicate):continue
        covered={str(x['cycle']) for x in result['fixed_checks'] if x['name']==name}
        if locations<=covered:return True
    prefix='Priority ADS absent; verify matching or permitted end-day exception: '
    if message.startswith(prefix):
        from schedule_assets import filename_key
        name=filename_key(message[len(prefix):])
        covered={str(x['cycle']) for x in result.get('daily_checks',[]) if name in
                 (filename_key(x['name']),filename_key(x.get('matched_name',x['name'])))}
        if locations<=covered:return True
    return False


def report_sections(result):
    """Operator-facing report: explicit comparisons plus sequence differences."""
    from difflib import SequenceMatcher
    rows=result.get('playlist_rows',[]);cycles=result['cycles'];items=grouped_findings(result['findings'])
    sections=[]
    counts=Counter(i['level'] for i in items)
    def order(c):
        out=[]
        for r in rows:
            if r['cycle']==c and r['kind']=='program' and (not out or out[-1]!=r['code']):out.append(r['code'])
        return out
    expected=result.get('expected_order',[]);actual=order(cycles[0]) if cycles else []
    start_ok=bool(actual and actual==expected and result.get('order_anchored'))
    sections.append(('1. SHOW MỞ ĐẦU',[
        ('✓ ' if start_ok else '✗ ')+' → '.join(actual)+(' — Đúng.' if start_ok else ' — Cần kiểm tra. Theo INPUT: '+' → '.join(expected))]))
    fixed=[]
    checks=result.get('fixed_checks',[])
    for name in dict.fromkeys(x['name'] for x in checks):
        subset=[x for x in checks if x['name']==name]
        tokens=[]
        for x in subset:
            if x.get('cut'):continue
            if not x['expected'] and not x['count']:continue
            ok=x['expected'] and x['count']==1
            detail='' if ok else ' (thiếu)' if not x['count'] else ' (thừa)' if not x['expected'] else ' (lặp)'
            tokens.append(('✓ ' if ok else '✗ ')+str(x['cycle'])+detail)
        fixed.append(name+': cycle '+', '.join(tokens) if tokens else '✓ '+name+': không yêu cầu — không có.')
    sections.append(('2. ADS CỐ ĐỊNH / QUY TẮC CỦA NGÀY (INPUT_2)',fixed or ['⚠ Không có dữ liệu đối chiếu quy tắc cycle.']))
    daily=[]
    checks=result.get('daily_checks',[])
    for name in dict.fromkeys(x['name'] for x in checks):
        subset=[x for x in checks if x['name']==name];found=[str(x['cycle']) for x in subset if x['count']]
        priority_class=subset[0]['priority']
        priority={'PRIORITY':'ƯU TIÊN','DO_NOT_SKIP':'DO NOT SKIP','OPTIONAL':'ADS thường','NORMAL':'ADS thường'}.get(priority_class,priority_class)
        tokens=[('✓ ' if x['count'] else '✗ ')+str(x['cycle']) for x in subset if not x.get('cut')]
        used_cycles={x['cycle'] for x in subset if x['count']}
        line=('✓ ' if len(used_cycles)>=3 else '✗ ')+'['+str(priority)+'] '+name+(' (chưa xác nhận tên)' if not subset[0]['resolved'] else '')+': cycle '+(', '.join(tokens) if tokens else '—')
        daily.append((len(used_cycles)<3,{'DO_NOT_SKIP':0,'PRIORITY':1}.get(priority_class,2),line))
    daily=[item[2] for item in sorted(daily,key=lambda item:(item[1],item[0]))]
    sections.append(('3. ADS TRONG DANH SÁCH NGÀY (INPUT_3)',daily or ['⚠ Không có dữ liệu ADS của ngày để đối chiếu.']))
    first_cycle=str(cycles[0]) if cycles else ''
    inventory_source=[i for i in items if not (
        result.get('order_anchored')
        and i['message'].startswith('Show rotation differs from INPUT.')
        and any(str(c)==first_cycle for c,_ in i['locations']))]
    inventory=readable_inventory(inventory_source)
    if inventory:sections.append(('4. SHOW / TEASER / FN BẤT THƯỜNG',inventory))
    differences=[]
    def content(c):return [r['name'] for r in rows if r['cycle']==c and r['kind']!='marker' and not r.get('fixed_rule')]
    if cycles:
        for c in cycles[1:]:
            cut_lines=set(result.get('cut_reference_lines',[])) if c==cycles[-1] else set()
            base=[r['name'] for r in rows if r['cycle']==cycles[0] and r['kind']!='marker' and not r.get('fixed_rule') and r['line'] not in cut_lines]
            current=content(c);differences.extend(['─'*65,f'Cycle {c}'])
            if c==cycles[-1]:
                last_program=next((r for r in reversed(rows) if r['cycle']==c and r['kind']=='program'),None)
                if last_program:differences.append('Kết thúc tại: '+last_program['name'])
            doc_notes=result.get('document_info',{}).get('summary_cycles',{})
            if c in doc_notes:
                other=[n for n in doc_notes[c] if not n.get('fixed_rule')]
                differences.extend('  • '+n['text'] for n in other)
                if not other:differences.append('✓ Không có thay đổi khác.')
                continue
            removed=[];added=[]
            for op,a,b,x,y in SequenceMatcher(None,base,current,autojunk=False).get_opcodes():
                if op!='equal':removed.extend(range(a,b));added.extend(range(x,y))
            for i in list(removed):
                match=next((j for j in added if current[j]==base[i]),None)
                if match is not None:
                    differences.append(f'  Dời: {base[i]} — sau {base[i-1] if i else "đầu cycle"} → sau {current[match-1] if match else "đầu cycle"}.')
                    removed.remove(i);added.remove(match)
            from schedule_assets import filename_key
            # Same-role OUT variants are a replacement, not a removed program.
            def wrapper(name):
                from episode_scanner import normalize_episode_order
                from show_formats import show_part
                normalized=normalize_episode_order(name.replace('_',' '))
                m=re.match(r'^\d{4}\s+([A-Z0-9]+)\b',normalized,re.I)
                role=show_part(normalized,m[1]) if m else None
                return (m[1].upper(),role) if role in ('IN','OUT') else None
            for i in list(removed):
                role=wrapper(base[i])
                match=next((j for j in added if role and wrapper(current[j])==role),None)
                if match is not None:
                    differences.append('  Đổi bản: '+base[i]+' → '+current[match])
                    removed.remove(i);added.remove(match)
            skipped={filename_key(n) for n in result.get('skipped_end_day',[])} if c==cycles[-1] and not cut_lines else set()
            differences.extend('  Bỏ: '+base[i] for i in removed if filename_key(base[i]) not in skipped)
            tail_available=Counter(r['name'] for r in rows if r['cycle']==cycles[0] and r['line'] in cut_lines)
            for j in added:
                moved=tail_available[current[j]]>0
                if moved:tail_available[current[j]]-=1
                differences.append(('  Dời từ phần cuối: ' if moved else '  Thêm: ')+current[j]+' — sau '+(current[j-1] if j else 'đầu cycle'))
            if current==base:differences.append('  ✓ Không có thay đổi khác.')
    sections.append(('5. KHÁC BIỆT SO VỚI CYCLE 1',differences or ['Chưa đủ cycle để so sánh.']))
    shown_inventory={id(i) for i in inventory_items(inventory_source)}
    remaining=[i for i in items if id(i) not in shown_inventory and not covered_by_ad_sections(i,result)]
    for title,selection in [('6. LỖI QUY TẮC',[i for i in remaining if i['level']=='ERROR']),('7. CẦN XÁC NHẬN',[i for i in remaining if i['level']=='REVIEW' and i['group']!='Media paths / duration verification']),('ĐỐI CHIẾU TÊN ĐÃ CHẤP NHẬN',[i for i in remaining if i['level']=='PASS'])]:
        lines=[]
        for item in selection:
            skipped=re.match(r'^(.*?): expected present in this cycle; (?:found|actual)\s+0\.',item['message'])
            if item['level']=='REVIEW' and skipped:
                cycle_text=', '.join(dict.fromkeys(str(c) for c,_ in item['locations']))
                lines.append('⚠ skipped '+skipped[1]+' — Cycle '+cycle_text)
                continue
            priority_prefix='Priority ADS absent; verify matching or permitted end-day exception: '
            message=item['message'][len(priority_prefix):] if item['message'].startswith(priority_prefix) else vietnamese_finding(item['message'])
            lines.append(('✗ ' if item['level']=='ERROR' else '⚠ ' if item['level']=='REVIEW' else '✓ ')+message)
            lines.append('  Vị trí: '+'; '.join(f'cycle {c}, dòng M3U {line}' for c,line in item['locations']))
        sections.append((title,lines or ['Không có mục trong nhóm này.']))
    if result.get('source_format')=='DOCX':
        sections=[(title,[line.replace('dòng M3U','đoạn Word').replace('trong M3U','trong Word').replace('M3U:','Word:') for line in lines]) for title,lines in sections]
    return sections


def show_dialog(parent,default_ep='',notice_provider=None):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    from tkinter.scrolledtext import ScrolledText
    import threading,queue
    window=tk.Toplevel(parent);window.title('QC lịch ngoài — kiểm tra quy tắc');window.geometry('1150x780')
    bar=ttk.Frame(window,padding=12);bar.pack(fill='x')
    check_actions=ttk.Frame(bar);check_actions.pack(side='right',padx=(12,0))
    from pip_help import help_button
    help_button(check_actions,'external',side='right')
    ttk.Label(bar,text='EP').pack(side='left');ep=tk.StringVar(value=str(default_ep));ttk.Entry(bar,textvariable=ep,width=8).pack(side='left',padx=8)
    selected=tk.StringVar();ttk.Entry(bar,textvariable=selected).pack(side='left',fill='x',expand=True,padx=6)
    def browse():
        name=filedialog.askopenfilename(parent=window,title='Chọn lịch M3U hoặc Word',filetypes=[('Lịch M3U / Word','*.m3u *.m3u8 *.docx'),('Word','*.docx'),('M3U','*.m3u *.m3u8')])
        if name:selected.set(name)
    ttk.Button(bar,text='Chọn M3U / Word',command=browse).pack(side='left')
    notice_bar=ttk.Frame(window,padding=(12,0));notice_bar.pack(fill='x')
    ttk.Label(notice_bar,text='Thông báo show mở đầu').pack(side='left')
    notice=tk.StringVar()
    notice_entry=ttk.Entry(notice_bar,textvariable=notice);notice_entry.pack(side='left',fill='x',expand=True,padx=8)
    def load_notice(*_):
        if notice_provider:
            notice.set(starting_notice(notice_provider(ep.get())))
        else:
            saved=Path(__file__).parent/'configs'/f'EP_{ep.get()}_bulk_input.txt'
            notice.set(starting_notice(saved.read_text('utf-8-sig')) if saved.is_file() else '')
    ttk.Button(notice_bar,text='Lấy từ bước 0',command=load_notice).pack(side='left')
    ep.trace_add('write',load_notice);load_notice()
    def detect_playlist_ep(*_):
        value=selected.get().strip().strip('"')
        if Path(value).suffix.lower() not in ('.m3u','.m3u8','.docx'):return
        number=episode_from_m3u_name(value)
        if number!=ep.get():ep.set(number or '')
    selected.trace_add('write',detect_playlist_ep)
    status=tk.StringVar(value='Chọn M3U hoặc DOCX: EP tự lấy từ tên file. Nếu tên không rõ số EP, nhập tay. Không kiểm tra mốc MT/24h.')
    ttk.Label(window,textvariable=status,wraplength=1000).pack(fill='x',padx=12,pady=8)
    tabs=ttk.Notebook(window);tabs.pack(fill='both',expand=True,padx=12,pady=8)
    summary_page=ttk.Frame(tabs);details_page=ttk.Frame(tabs)
    tabs.add(summary_page,text='Báo cáo QC');tabs.add(details_page,text='Chi tiết kỹ thuật')
    qc_body=ScrolledText(summary_page,wrap='word',font=('Segoe UI',11),background='white',padx=20,pady=16)
    qc_body.pack(fill='both',expand=True)
    qc_body.tag_configure('heading',foreground='#163c62',font=('Segoe UI',13,'bold'),spacing1=20,spacing3=10)
    qc_body.tag_configure('cycle_heading',foreground='#163c62',background='#eaf1f8',font=('Segoe UI',12,'bold'),spacing1=8,spacing3=8)
    qc_body.tag_configure('error',foreground='#c62828');qc_body.tag_configure('review',foreground='#c62828');qc_body.tag_configure('pass',foreground='#008060')
    qc_body.tag_configure('priority_notice',foreground='#A07800')
    summary=ttk.Treeview(summary_page,columns=('group','status','errors','reviews','passes'),show='headings',height=7)
    for col,title,width in [('group','Check group',360),('status','Result',150),('errors','Errors',90),('reviews','Review',90),('passes','Matched',90)]:
        summary.heading(col,text=title);summary.column(col,width=width,anchor='w' if col in ('group','status') else 'center')
    summary.tag_configure('ERROR',foreground='#b3261e');summary.tag_configure('REVIEW',foreground='#946200');summary.tag_configure('PASS',foreground='#168047')
    summary_detail=ScrolledText(summary_page,wrap='word',font=('Segoe UI',10),height=10)
    body=ScrolledText(details_page,wrap='word',font=('Segoe UI',10));body.pack(fill='both',expand=True)
    results=queue.Queue();state={'busy':False,'report':'','html':''}
    def open_report():
        tabs.select(summary_page);qc_body.yview_moveto(0)
    def format_group(item):
        locations='; '.join(f'cycle {c}, line {line}' for c,line in item['locations'])
        return f"{item['level']} — {item['message']}\nLocations: {locations}\n"
    def selected_group(_=None):
        selection=summary.selection()
        if not selection:return
        group=summary.item(selection[0],'values')[0]
        items=[item for item in state.get('grouped',[]) if item['group']==group]
        summary_detail.delete('1.0','end');summary_detail.insert('end','\n'.join(format_group(item) for item in items))
    summary.bind('<<TreeviewSelect>>',selected_group)
    def run():
        try:
            number=int(ep.get());path=Path(selected.get())
            if number<=0 or not path.is_file() or path.suffix.lower() not in ('.m3u','.m3u8','.docx'):raise ValueError('Nhập EP hợp lệ và chọn file M3U hoặc DOCX có sẵn.')
        except Exception as exc:messagebox.showerror('Check schedule',str(exc),parent=window);return
        notice_text=notice.get().strip()
        if not notice_text:
            messagebox.showinfo('Starting-show notice required','Enter the first-show notice from step 0, for example: Next day will air 3316 VEGC followed by 3316 BMD.',parent=window)
            notice_entry.focus_set();return
        state['busy']=True;button.configure(state='disabled');status.set('Đang đối chiếu INPUT và quy tắc…')
        def work():
            try:results.put((True,audit(path,number,notice_text)))
            except Exception as exc:results.put((False,str(exc)))
        def poll():
            if not window.winfo_exists():return
            try:ok,value=results.get_nowait()
            except queue.Empty:window.after(100,poll);return
            state['busy']=False;button.configure(state='normal')
            if not ok:status.set('Check failed: '+value);return
            if value.get('start_issue'):
                prompt=tk.Toplevel(window);prompt.title('Check starting-show notice');prompt.transient(window);prompt.grab_set()
                ttk.Label(prompt,text=vietnamese_finding(value['start_issue'])+'\n\nBỏ qua vẫn hiện báo cáo QC và giữ cảnh báo này.',wraplength=640,padding=16).pack(fill='x')
                answer={'pass':False}
                def finish(passed):answer['pass']=passed;prompt.destroy()
                buttons=ttk.Frame(prompt,padding=12);buttons.pack(fill='x')
                ttk.Button(buttons,text='Kiểm tra thông báo',command=lambda:finish(False)).pack(side='left')
                ttk.Button(buttons,text='Bỏ qua — xem QC',command=lambda:finish(True)).pack(side='right')
                window.wait_window(prompt)
                if not answer['pass']:
                    status.set('Check the starting-show notice, then run Check rules again.');notice_entry.focus_set();return
            grouped=grouped_findings(value['findings']);state['grouped']=grouped
            errors=sum(item['level']=='ERROR' for item in grouped)
            media=sum(item['level']=='REVIEW' and item['group']=='Media paths / duration verification' for item in grouped)
            reviews=sum(item['level']=='REVIEW' for item in grouped)-media
            status.set('Đã kiểm tra. Mục 3: tên ADS xanh khi dùng từ 3 cycle, đỏ khi dưới 3. Từng số cycle: xanh = có dùng, đỏ = chưa thấy dùng.')
            summary.delete(*summary.get_children())
            totals=[]
            for group in dict.fromkeys(item['group'] for item in grouped):
                counts=Counter(item['level'] for item in grouped if item['group']==group)
                level='ERROR' if counts['ERROR'] else 'REVIEW' if counts['REVIEW'] else 'PASS'
                iid=summary.insert('','end',values=(group,{'ERROR':'Needs correction','REVIEW':'Needs review','PASS':'Matched'}[level],counts['ERROR'],counts['REVIEW'],counts['PASS']),tags=(level,))
                totals.append(f"{group}: {counts['ERROR']} errors, {counts['REVIEW']} review, {counts['PASS']} matched")
            children=summary.get_children()
            if children:summary.selection_set(children[0]);selected_group()
            else:summary_detail.delete('1.0','end');summary_detail.insert('end','No violations found in the checks performed.')
            tabs.select(summary_page)
            lines=[f"EP {number} — {path}",'Starting-show notice: '+notice_text,value['scope'],f"Entries: {value['rows']}; cycles: {value['cycles']}",'']
            lines += ['SUMMARY',*totals,'','DETAILS (repeated findings grouped)']
            lines += [format_group(item) for item in grouped]
            if not value['findings']:lines.append('No violations found in the checks performed.')
            state['report']='\n'.join(lines);body.delete('1.0','end');body.insert('end',state['report'])
            value.update(episode=number,path=str(path),notice=notice_text)
            state['html']=render_report(value)
            sections=report_sections(value)
            priority_prefix='Priority ADS absent; verify matching or permitted end-day exception: '
            priority_notices={'⚠ '+f[3][len(priority_prefix):] for f in value['findings'] if f[0]=='REVIEW' and f[3].startswith(priority_prefix)}
            qc_body.configure(state='normal');qc_body.delete('1.0','end')
            for heading,paragraphs in sections:
                qc_body.insert('end',heading+'\n','heading')
                for paragraph in paragraphs:
                    if heading.startswith(('2.','3.')) and ': cycle ' in paragraph:
                        prefix,tokens=paragraph.split(': cycle ',1)
                        prefix_tag=('pass' if prefix.startswith('✓') else 'error') if heading.startswith('3.') else ''
                        qc_body.insert('end',prefix+': cycle ',prefix_tag)
                        for i,token in enumerate(tokens.split(', ')):
                            if i:qc_body.insert('end',', ')
                            qc_body.insert('end',token,'pass' if token.startswith('✓') else 'error' if token.startswith('✗') else '')
                        qc_body.insert('end','\n\n')
                        continue
                    tag='cycle_heading' if re.fullmatch(r'Cycle \d+',paragraph) else 'error' if paragraph.startswith('✗') else 'review' if paragraph.startswith('⚠') else 'pass' if paragraph.startswith('✓') else ''
                    if paragraph in priority_notices:tag='priority_notice'
                    qc_body.insert('end',paragraph+'\n\n',tag)
            qc_body.configure(state='disabled')
            state['report']='\n\n'.join(heading+'\n'+'\n'.join(paragraphs) for heading,paragraphs in sections)
            open_report()
        threading.Thread(target=work,daemon=True).start();window.after(100,poll)
    def save():
        if not state['report']:return
        name=filedialog.asksaveasfilename(parent=window,defaultextension='.txt',initialfile=f'EP {ep.get()} QC.txt',filetypes=[('Báo cáo tiếng Việt','*.txt'),('HTML tiếng Anh','*.html')])
        if name:Path(name).write_text(state['report'] if Path(name).suffix.lower()=='.txt' else state['html'],encoding='utf-8-sig')
    footer=ttk.Frame(window,padding=12);footer.pack(fill='x')
    button=tk.Button(check_actions,text='▶  BẮT ĐẦU CHECK',command=run,
                     font=('Segoe UI',11,'bold'),bg='#176B46',fg='white',
                     activebackground='#125438',activeforeground='white',
                     relief='flat',padx=20,pady=9,cursor='hand2')
    button.pack(side='right')
    ttk.Button(footer,text='Lưu báo cáo',command=save).pack(side='left',padx=8)
    ttk.Button(footer,text='Về đầu báo cáo QC',command=open_report).pack(side='left',padx=8)
    window.protocol('WM_DELETE_WINDOW',lambda:None if state['busy'] else window.destroy())
