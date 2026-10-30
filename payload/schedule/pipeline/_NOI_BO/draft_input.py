"""Reported durations for draft planning; real media always takes precedence."""
import json
from media_labels import is_no_next, canonical_no_next, NO_NEXT_PATTERN
import re
from pathlib import Path

def parse_duration(text):
    hours=re.fullmatch(r'\s*(\d+):(\d{2}):(\d{2})\s*',text)
    if hours:
        if int(hours[2])>=60 or int(hours[3])>=60:raise ValueError('Giờ:phút:giây cần phần phút và giây từ 00 đến 59.')
        seconds=int(hours[1])*3600+int(hours[2])*60+int(hours[3])
        if seconds<=0:raise ValueError('Thời lượng phải lớn hơn 0.')
        return seconds
    parts=re.fullmatch(r'\s*(\d+)\s*([:.])\s*(\d{1,2})\s*',text)
    if not parts:raise ValueError('Nhập phút:giây hoặc phút.giây; 0.4 = 0:40, 1.4 = 1:40, 0.04 = 0:04.')
    seconds=int(parts[3].ljust(2,'0') if parts[2]=='.' else parts[3])
    if seconds>=60:raise ValueError('Phần giây phải từ 00 đến 59; ví dụ 0.4 = 40 giây.')
    value=int(parts[1])*60+seconds
    if value<=0:raise ValueError('Thời lượng phải lớn hơn 0.')
    return value

def split_fn(total,count):
    seconds=parse_duration(total);count=int(count)
    if not 1<=count<=99 or seconds<count:raise ValueError('Số part FN từ 1 đến 99; mỗi part cần ít nhất 1 giây.')
    base,remainder=divmod(seconds,count)
    lengths=[base+(i<remainder) for i in range(count)]
    if lengths[0]<2:raise ValueError('P1 cần ít nhất 2 giây để chia P1A và P1B.')
    parts=[('1A',(lengths[0]+1)//2),('1B',lengths[0]//2)]
    parts.extend((str(i+1),lengths[i]) for i in range(1,count))
    return {f'FN P{part}':{'duration':f'{value//60:02}:{value%60:02}',
                         'variant':'Chưa xác định','fn_estimated_split':True} for part,value in parts}


def read_fn_message(text,ep,default_count=6):
    result={};remaining=[];context=bool(re.search(r'^\s*(?:P|Part\s*)\d+[ab]?\s*[:=-]?\s*\d+[:.]\d',text,re.I|re.M));total=None;count=default_count
    duration=r'(\d+:\d{2}:\d{2}|\d+[:.]\d{1,2})(?![\d.])'
    for line in text.splitlines():
        if re.search(r'\b(?:TSER|TEASER)\b',line,re.I):remaining.append(line);continue
        header=re.search(r'\bFN\d*\b|\bS1B\b',line,re.I)
        if header:
            episode=re.search(r'\b(\d{4})\s+(?:NWN\s+)?(?:FN|S1B)',line,re.I)
            if episode and int(episode[1])!=ep:raise ValueError('Số EP của thông báo FN khác EP đang làm.')
            context=True
        elif re.search(r'\b\d{4}\s*(?:NWN|WOW|BMD|[A-Z]{2,})\b',line,re.I):context=False
        if context:
            part=re.search(r'\b(?:part\s*|p)(\d+[ab]?)\s*[:=-]?\s*'+duration,line,re.I)
            if part:
                seconds=parse_duration(part[2]);result['FN P'+part[1].upper()]={'duration':f'{seconds//60:02}:{seconds%60:02}','variant':'Chưa xác định'}
                continue
            parts=re.search(r'(\d+)\s*(?:parts?|phần)\b|(?:parts?|số part)\s*[:=]?\s*(\d+)\b',line,re.I)
            if parts:count=int(parts[1] or parts[2])
            timing=re.search(duration,line)
            if timing and (header or re.search(r'total|tổng|length|thời lượng',line,re.I) or re.fullmatch(r'\s*'+duration+r'\s*',line)):
                total=timing[1];continue
            if header or parts:continue
        remaining.append(line)
    if result:
        if total and sum(parse_duration(v['duration']) for v in result.values())!=parse_duration(total):
            raise ValueError('Tổng các part FN khác tổng thời lượng đã báo. Hãy kiểm tra lại số liệu.')
    elif total:result=split_fn(total,count)
    return result,'\n'.join(remaining)

def read_message(text,ep,fn_count=6):
    fn,text=read_fn_message(text,ep,fn_count)
    group=None;result={};unread=[]
    for line in text.splitlines():
        teaser=re.search(r'\b(?:tser|teaser)\s*(?:(\d{4})\s*)?(WOW|AP|SHOW|FN\d*|[A-Z]+)\b.*?(\d+[:.]\d{1,2})(?![\d.])',line,re.I)
        if teaser:
            code=teaser[2].upper();key='TSER '+('FN' if code.startswith('FN') else code if code in ('WOW','AP') else 'SHOW')
            if code=='AP':
                from ap_rules import ap_campaign,valid_teaser
                campaign=ap_campaign(ep)
                if not campaign or (teaser[1] and not valid_teaser(line,ep)):raise ValueError('Teaser AP không đúng EP/ngày trong lịch 3 ngày.')
            if teaser[1] and code!='AP' and not code.startswith('FN') and int(teaser[1])!=ep+1:
                raise ValueError(f'Teaser WOW/show của EP {ep} dự kiến mang số {ep+1}; hãy kiểm tra thông báo.')
            seconds=parse_duration(teaser[3]);result[key]={'duration':f'{seconds//60:02}:{seconds%60:02}','variant':'Chưa xác định'}
            continue
        header=re.search(r'\b(\d{4})\s*([A-Z][A-Z0-9]*)\b',line,re.I)
        if header:
            if int(header[1])!=ep:raise ValueError(f'Thông báo có EP {header[1]}, đang làm EP {ep}.')
            group=header[2].upper();continue
        if group=='AP':
            part=re.search(r'\b(?:PART|PT|P)\s*([A-Z])\s*:?\s*(\d+[:.]\d{1,2})(?![\d.])',line,re.I)
            if part:
                seconds=parse_duration(part[2]);result['AP PART'+part[1].upper()]={'duration':f'{seconds//60:02}:{seconds%60:02}','variant':'No Max' if re.search(r'no\s*(?:smtv\s*)?max',line,re.I) else 'Max' if re.search(r'\bmax\b',line,re.I) else 'Chưa xác định'}
                continue
        match=re.search(r'\b(seg\s*\d+[abc]?|s\d+[abc]?|main|in|out|intro|outro|daily\s*scroll)\s*:?\s*(\d+[:.]\d{1,2})(?![\d.])\b',line,re.I)
        if match and group:
            part=re.sub(r'\s+','',match[1].upper()).replace('SEG','S').replace('INTRO','IN').replace('OUTRO','OUT')
            if part=='DAILYSCROLL':part='Daily Scroll'
            variant='No Max' if re.search(r'no\s*max',line,re.I) else 'Max' if re.search(r'\bmax\b',line,re.I) else 'Chưa xác định'
            seconds=parse_duration(match[2]);result[f'{group} {part}']={'duration':f'{seconds//60:02}:{seconds%60:02}','variant':variant}
        elif re.search(r'\d+[:.]\d{2}',line):unread.append(line)
    if unread:raise ValueError('Chưa nhận diện các dòng: '+ '; '.join(unread))
    result.update(fn)
    return result

def read_bulk_message(text,ep):
    from air_notice import without_air_lines
    lines=without_air_lines(text).splitlines()
    notices=[line.strip() for line in lines if re.search(r'\b(?:NEXT\s+DAY\s+WILL\s+AIR|FOLLOWED\s+BY)\b',line,re.I)]
    if len(notices)>1:raise ValueError('Chỉ nhập một câu bắt đầu lịch cho EP đang làm.')
    durations=read_message('\n'.join(line for line in lines if line.strip() not in notices),ep)
    return durations,notices[0] if notices else ''


def item_key(item):
    rule=item['rule'];name=item['target_name'].upper()
    if is_no_next(name):return None
    if rule in ('show-intro','show-main','show-outro'):
        code=re.match(r'\d+\s+(\w+)',name)
        if code:return code[1]+' '+{'show-intro':'IN','show-main':'MAIN','show-outro':'OUT'}[rule]
    if rule=='ap-part':
        from ap_rules import part_id
        part=part_id(name)
        return 'AP PART'+part if part else None
    if rule=='wow-main':return 'WOW MAIN'
    if rule=='nwn-s1b-fn':
        part=re.search(r'\bP(\d+[AB]?)\b',name)
        return 'FN P'+part[1] if part else 'FN S1B'
    if rule.startswith('teaser'):
        return 'TSER '+('FN' if re.search(r'\bFN\d*\b',name) else 'AP' if re.search(r'\bAP\b',name) else 'WOW' if re.search(r'\bWOW\b',name) else 'SHOW')
    if rule.startswith('nwn-s'):return 'NWN '+rule.split('-')[1].upper()
    if rule=='daily-scroll':return 'NWN Daily Scroll'
    for family,prefix in [('BMD','bmd-'),('WOW','wow-lecture-')]:
        if rule.startswith(prefix):
            part=rule[len(prefix):];return family+' '+{'intro':'IN','outro':'OUT','main':'MAIN'}.get(part,part.upper())
    m=re.match(r'\d+\s+(\w+).*?\bS([12])\b',name)
    if m:return f'{m[1]} S{m[2]}'
    return None

def expected(config):
    keys=['NWN S1A','NWN S1C','NWN S2','NWN S3','NWN Daily Scroll','BMD IN','BMD MAIN','BMD OUT','WOW IN','WOW MAIN','WOW OUT']
    from wow_rules import has_wow_intro_outro
    if not has_wow_intro_outro(config['cycle_rules']):keys=[k for k in keys if k not in ('WOW IN','WOW OUT')]
    from ap_rules import slot_family,ap_campaign,expected_parts
    if slot_family(config['episode'],config['program'])=='AP':keys=[k for k in keys if not k.startswith('WOW ')]+['AP PART'+p for p in expected_parts(config)]
    if ap_campaign(config['episode']):keys.append('TSER AP')
    for show in config['program']['active_shows']:
        from schedule_engine import show_code
        code=show_code(show['code'])
        from show_formats import has_intro_outro
        names=[i['target_name'] for i in config.get('rename_preview',{}).get('items',[])]
        roles=('IN','MAIN','OUT') if has_intro_outro(code,names,config.get('reported_durations',{}),show.get('has_intro_outro',False)) else ('S1','S2')
        keys += [code+' '+p for p in roles]
    from wow_rules import needs_next_wow_teaser
    keys += (['TSER WOW'] if needs_next_wow_teaser(config) else [])+['TSER SHOW']
    if config.get('schedule_settings',{}).get('fn',config['program']['schedule_type']=='FN') and config.get('schedule_settings',{}).get('tser_fn',True):keys.append('TSER FN')
    return keys

def storage(config):return Path(config['config_path']).parent/f"EP_{config['episode']}_reported_durations.json"

def expand_bmd_out(config):
    if not config.get('draft_mode'):return
    from schedule_engine import bmd_next_code
    items=config['rename_preview']['items']
    fn=config.get('schedule_settings',{}).get('fn',config['program']['schedule_type']=='FN')
    order=[1,3,4,5,6,7,8] if fn else list(range(1,9))
    codes=list(dict.fromkeys(bmd_next_code(b,order,config['program']) for b in (3,7)))
    def generic(i):
        return i['rule']=='bmd-outro' and ('(OUT)' in i['target_name'].upper() or i.get('draft_out_variant') or
            (i.get('local_fallback') and not is_no_next(i.get('source_name','')) and not re.search(r'NEXT IS|UP NXT|NO.?COMING|NO.?NXT',i.get('source_name',''),re.I)))
    existing={i['target_name'].casefold() for i in items if not generic(i)}
    expanded=[]
    for item in items:
        if not generic(item):
            expanded.append(item);continue
        for code in codes:
            if not code:continue
            name=re.sub(r'\((?:OUT|UP NXT [^)]*)\)',f'(UP NXT {code})',item['target_name'],flags=re.I)
            if name.casefold() in existing:continue
            expanded.append(dict(item,target_name=name,target_path=str(Path(item['target_path']).with_name(name)),draft_out_variant=True))
            existing.add(name.casefold())
    config['rename_preview']['items']=expanded

def merge_reported(config,data):
    from show_formats import configure_shows
    configure_shows(config['program'],[i['target_name'] for i in config['rename_preview']['items']],data)
    if any(k.startswith('AP PART') for k in data):config['program']['slot1_family']='AP'
    from wow_rules import has_wow_intro_outro
    from episode_scanner import shorten_program_title,shorten_show_title,clean_local_filename
    wow_lecture=has_wow_intro_outro(config['cycle_rules'])
    from wow_rules import needs_next_wow_teaser
    items=[x for x in config['rename_preview']['items'] if not x.get('draft_duration') and (needs_next_wow_teaser(config) or item_key(x)!='TSER WOW')]
    present={item_key(x) for x in items}
    if not config.get('schedule_settings',{}).get('tser_fn',True):items=[i for i in items if item_key(i)!='TSER FN']
    for key,entry in data.items():
        if key.startswith('WOW ') and config['program'].get('slot1_family')=='AP':continue
        if key.startswith('AP PART') and config['program'].get('slot1_family')=='WOW':continue
        if key=='TSER FN' and not config.get('schedule_settings',{}).get('tser_fn',True):continue
        if key=='TSER WOW' and not needs_next_wow_teaser(config):continue
        if not wow_lecture and key in ('WOW IN','WOW OUT'):continue
        if not entry.get('duration') or key in present:continue
        seconds=parse_duration(entry['duration']);group,part=key.split(' ',1)
        from schedule_engine import show_code
        declared=next((s for s in config['program'].get('active_shows',[]) if show_code(s.get('code','')).upper()==group.upper()),{})
        if declared.get('has_intro_outro') and re.fullmatch(r'S\d+',part):continue
        if group=='FN':
            rule='nwn-s1b-fn';label='NWN S1B FN '+part
        elif group=='TSER':
            rule='teaser-fn' if part=='FN' else 'teaser'
            label=f'TSER {part}' if part=='FN' else f'TSER {config["episode"]+1} {part}'
            if part=='AP':
                from ap_rules import ap_campaign
                campaign=ap_campaign(config['episode'])
                if not campaign:continue
                label=f"TSER {campaign['episode']} AP {campaign['phase']}"
        elif group=='AP':
            rule='ap-part';label='AP '+config['program'].get('details',{}).get('AP','').strip()+' '+part
        elif group=='NWN':
            rule='daily-scroll' if part=='Daily Scroll' else 'nwn-'+part.lower()
            label=key+(' FN' if part in ('S1A','S1C') and config['program']['schedule_type']=='FN' else '')
        elif group in ('WOW','BMD'):
            rule=('wow-lecture-' if group=='WOW' else 'bmd-')+{'IN':'intro','MAIN':'main','OUT':'outro'}[part]
            label=key+(' (OUT)' if group=='BMD' and part=='OUT' else '')
            if group=='WOW' and part=='MAIN':
                title=shorten_program_title(config['program'].get('details',{}).get('WOW','WOW'))
                label=f'WOW MAIN {title} (weblink)' if wow_lecture else f'WOW {title}'
                if not wow_lecture:rule='wow-main'
        else:
            from schedule_engine import show_code
            rule='active-show'
            show=next((v for v in config['program'].get('active_shows',[]) if show_code(v.get('code','')).upper()==group.upper()),{})
            title=shorten_show_title(show.get('title',''))
            label=' '.join(v for v in (group,title,part) if v)
            if part in ('IN','MAIN','OUT'):
                rule='show-'+{'IN':'intro','MAIN':'main','OUT':'outro'}[part]
                label=group+' '+((title or 'MAIN') if part=='MAIN' else part)
        variant=entry.get('variant','Chưa xác định')
        name=(label if group=='TSER' else f"{config['episode']} {label}")+(' (No Max)' if variant=='No Max' and group!='TSER' else '')+'.mp4'
        name=clean_local_filename(name)
        target_dir=Path(config['local_dir'])
        if group=='FN':
            fn_ep=config['rename_preview'].get('fn_source_episode') or config['episode']
            name=re.sub(r'^\d+',str(fn_ep),name)
            target_dir=target_dir.parent/f'EP {fn_ep}'
        items.append(dict(rule=rule,source_name=f"Báo trước: {key}"+(' MAX' if variant=='Max' else ''),source_path='',target_name=name,
                          target_path=str(target_dir/name),draft_duration=seconds,draft_variant=variant,
                          fn_estimated_split=entry.get('fn_estimated_split',False)))
    config['rename_preview']['items']=items
    config['draft_mode']=True
    config['reported_durations']=data
    expand_bmd_out(config)
    from max_options import apply_choices
    apply_choices(config)

def open_editor(root,config):
    import tkinter as tk
    from tkinter import ttk,messagebox
    path=storage(config);data=json.loads(path.read_text('utf-8')) if path.exists() else {}
    if data.get('FN P1',{}).get('fn_estimated_split') and not any(k in data for k in ('FN P1A','FN P1B')):
        old=data.pop('FN P1');seconds=parse_duration(old['duration'])
        if seconds>=2:
            for key,value in [('FN P1A',(seconds+1)//2),('FN P1B',seconds//2)]:
                data[key]=dict(old,duration=f'{value//60:02}:{value%60:02}')
        else:data['FN P1']=old
    window=tk.Toplevel(root);window.title(f"EP {config['episode']} — Thời lượng báo trước");window.geometry('850x660')
    window.transient(root);window.grab_set();accepted=[False]
    ttk.Label(window,text='Dán thông báo rồi bấm Đọc thời lượng. Nhấp vào ô để sửa. 11.03 = 11 phút 03 giây; 0.4 = 40 giây.',padding=10).pack(anchor='w')
    paste=tk.Text(window,height=7);paste.pack(fill='x',padx=10)
    fn_panel=ttk.LabelFrame(window,text='FN / NWN S1B — tổng thời lượng hoặc từng part',padding=6)
    fn_panel.pack(fill='x',padx=10,pady=6)
    total_var=tk.StringVar();count_var=tk.StringVar(value=str(len({re.sub(r'[AB]$', '', k) for k in data if k.startswith('FN P')}) or 6))
    ttk.Label(fn_panel,text='Tổng (phút:giây)').pack(side='left')
    ttk.Entry(fn_panel,textvariable=total_var,width=12).pack(side='left',padx=6)
    ttk.Label(fn_panel,text='Số part').pack(side='left')
    ttk.Spinbox(fn_panel,from_=1,to=99,textvariable=count_var,width=5).pack(side='left',padx=6)
    area=ttk.Frame(window);area.pack(fill='both',expand=True,padx=10,pady=8)
    canvas=tk.Canvas(area,highlightthickness=0);scroll=ttk.Scrollbar(area,command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
    body=ttk.Frame(canvas);canvas.create_window((0,0),window=body,anchor='nw')
    body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    fields={};present={}
    from max_options import is_no_max
    for item in config['rename_preview']['items']:
        if item.get('draft_duration'):continue
        key=item_key(item)
        if key not in present or (is_no_max(present[key]) and not is_no_max(item)):
            present[key]=item
    for col,text in enumerate(('Chương trình / phần','Phút:giây','Max / No Max','Nguồn sử dụng')):ttk.Label(body,text=text,font=('Segoe UI',10,'bold')).grid(row=0,column=col,padx=8,pady=6,sticky='w')
    def populate():
        from wow_rules import has_wow_intro_outro
        fn_keys=[k for k in set(data)|set(present) if k and k.startswith('FN P')]
        if not fn_keys and config['program'].get('schedule_type')=='FN':
            fn_keys=['FN P1A','FN P1B']+[f'FN P{i}' for i in range(2,int(count_var.get())+1)]
        fn_keys.sort(key=lambda k:(int(re.search(r'P(\d+)',k)[1]),k))
        keys=expected(config)+fn_keys+[k for k in data if not k.startswith('FN P')]
        for key in dict.fromkeys(keys):
            if key=='TSER FN' and not config.get('schedule_settings',{}).get('tser_fn',True):continue
            from wow_rules import needs_next_wow_teaser
            if key=='TSER WOW' and not needs_next_wow_teaser(config):continue
            if key in ('WOW IN','WOW OUT') and not has_wow_intro_outro(config['cycle_rules']):continue
            if key in fields:continue
            row=len(fields)+1;value=data.get(key,{})
            duration=tk.StringVar(value=value.get('duration',''));variant=tk.StringVar(value=value.get('variant','Chưa xác định'))
            display=(f"TSER {config['episode']+1} {key.split()[1]}" if key!='TSER FN' else 'TSER FN') if key.startswith('TSER ') else f"{config['episode']} {key}"
            if key=='TSER AP':
                from ap_rules import ap_campaign
                campaign=ap_campaign(config['episode'])
                if campaign:display=f"TSER {campaign['episode']} AP {campaign['phase']}"
            ttk.Label(body,text=display).grid(row=row,column=0,padx=8,pady=4,sticky='w')
            entry=ttk.Entry(body,textvariable=duration,width=12);entry.grid(row=row,column=1,padx=8)
            combo=ttk.Combobox(body,textvariable=variant,values=('Chưa xác định','Max','No Max'),state='readonly',width=15);combo.grid(row=row,column=2,padx=8)
            item=present.get(key)
            source=('D — file đã có' if item.get('local_fallback') else 'W — file nguồn') if item else 'Nhập để tạo temp'
            if item:
                from max_options import is_max,is_no_max,is_draft_item
                entry.configure(state='disabled')
                if is_no_max(item):
                    variant.set('No Max');combo.configure(values=('No Max',))
                else:
                    variant.set('Max' if is_max(item) else 'Chưa xác định')
                    combo.configure(values=('Chưa xác định','Max'))
                if not is_draft_item(item):combo.configure(state='disabled')
            ttk.Label(body,text=source).grid(row=row,column=3,padx=8,sticky='w')
            fields[key]=(duration,variant)
    populate()
    def replace_fn(values):
        for key in list(data):
            if key.startswith('FN P'):data.pop(key)
        for key,(duration,variant) in fields.items():
            if not key.startswith('FN P'):
                data[key]=dict(data.get(key,{}),duration=duration.get(),variant=variant.get())
        data.update(values)
        for widget in body.winfo_children():
            if int(widget.grid_info().get('row',0))>0:widget.destroy()
        fields.clear();populate()
        for key,value in values.items():
            if key not in present:
                fields[key][0].set(value['duration']);fields[key][1].set(value.get('variant','Chưa xác định'))
    def divide():
        try:replace_fn(split_fn(total_var.get(),int(count_var.get())))
        except Exception as exc:messagebox.showerror('Chia FN',str(exc),parent=window)
    ttk.Button(fn_panel,text='Chia → P1A, P1B, P2…',command=divide).pack(side='left',padx=6)
    ttk.Label(fn_panel,text='P1 chia A/B; giữ nguyên tổng thời lượng.').pack(side='left',padx=6)
    def read():
        try:
            parsed=read_message(paste.get('1.0','end'),config['episode'],int(count_var.get()))
            if not parsed:raise ValueError('Chưa thấy dòng thời lượng. Ví dụ: 3310 WOW, dòng tiếp theo: main 13:28')
            fn_values={k:v for k,v in parsed.items() if k.startswith('FN P')}
            if fn_values:
                replace_fn(fn_values);count_var.set(str(len({re.sub(r'[AB]$', '', k) for k in fn_values})))
            data.update(parsed);populate()
            for key,value in parsed.items():
                if key in fields and key not in present:
                    fields[key][0].set(value['duration']);fields[key][1].set(value['variant'])
        except Exception as exc:messagebox.showerror('Thời lượng',str(exc),parent=window)
    def save():
        try:
            from max_options import remember,is_no_max,is_draft_item
            for item in config['rename_preview']['items']:
                key=item_key(item)
                if is_draft_item(item) and key in fields and not is_no_max(item):
                    item['is_max']=fields[key][1].get()=='Max'
                    remember(config['episode'],item)
            values={key:{'duration':d.get().strip(),'variant':v.get()} for key,(d,v) in fields.items() if d.get().strip()}
            for key,entry in values.items():
                if data.get(key,{}).get('fn_estimated_split'):entry['fn_estimated_split']=True
                try:seconds=parse_duration(entry['duration'])
                except ValueError as exc:raise ValueError(f"{key}: {entry['duration']}\n{exc}") from exc
                entry['duration']=f'{seconds//60:02}:{seconds%60:02}'
                fields[key][0].set(entry['duration'])
            path.write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
            merge_reported(config,values);accepted[0]=True;window.destroy()
        except Exception as exc:messagebox.showerror('Thời lượng',str(exc),parent=window)
    buttons=ttk.Frame(window,padding=10);buttons.pack(fill='x')
    ttk.Button(buttons,text='Đọc thời lượng đã dán',command=read).pack(side='left')
    ttk.Button(buttons,text='Lưu thời lượng',command=save).pack(side='right')
    ttk.Label(window,text='Ô trống được giữ là thiếu dữ liệu. File nguồn thực tế được ưu tiên khi quét lại.',padding=8).pack(anchor='w')
    root.wait_window(window);return accepted[0]
