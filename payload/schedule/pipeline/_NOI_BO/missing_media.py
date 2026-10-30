"""Explicit file selection and durable missing-media repairs for Run all."""
import json
import os
import re
from pathlib import Path
from portable_paths import ADS_ROOT, EXPORT_ROOT

BASE=Path(__file__).resolve().parent


def atomic_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    stage=path.with_suffix('.saving.json')
    stage.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(stage,path)


def choices_path(episode):
    return BASE/'configs'/f'EP_{episode}_source_choices.json'


def source_choices(episode):
    path=choices_path(episode)
    return json.loads(path.read_text('utf-8')) if path.exists() else {'items':[]}


def fn_set(selected):
    """Use event identity, not the entire folder, to avoid mixing FN sets."""
    selected=Path(selected)
    def identity(path):
        name=path.stem.upper().replace('_',' ')
        if not re.search(r'NWN[ _]+(?:SEG(?:MENT)?|S)[ _]*1[ _]*B\b',name):return None
        ep=re.match(r'(\d{4})\b',name)
        part=re.search(r'\bP(?:ART)?[ _]*(\d+)([A-Z]?)\b',name)
        # Underscores are word characters; normalize separators first.
        clean=re.sub(r'[_]+',' ',name)
        part=re.search(r'\bP(?:ART)?\s*(\d+)([A-Z]?)\b',clean)
        if not ep or not part:return None
        date=re.search(r'(?<!\d)\d{8}(?!\d)',clean)
        fn=re.search(r'\bFN\s*(\d+)\b',clean)
        event=(ep[1],date[0] if date else '',fn[1] if fn else '',bool(re.search(r'\bREAIR\b',clean)))
        if not date and not fn:
            title=re.sub(r'\bP(?:ART)?\s*\d+[A-Z]?\b|\bV\d+\b',' ',clean)
            event+=(' '.join(title.split()),)
        return event,(int(part[1]),part[2])
    if selected.is_dir():
        starts=[p for p in selected.glob('*.mp4') if identity(p) and identity(p)[1] in ((1,'A'),(1,''))]
        if len(starts)!=1:raise ValueError('Choose the P1A file: this folder contains zero or multiple FN sets.')
        selected=starts[0]
    ident=identity(selected)
    if not ident:raise ValueError('Choose an NWN S1B part file (for example P1A).')
    groups={}
    for path in selected.parent.glob('*.mp4'):
        found=identity(path)
        if found and found[0]==ident[0]:groups.setdefault(found[1],[]).append(path)
    if not groups:raise ValueError('The selected FN file is no longer available.')
    for number in {part[0] for part in groups}:
        letters=sorted(part[1] for part in groups if part[0]==number and part[1])
        if letters:
            expected=[chr(c) for c in range(ord('A'),ord(letters[-1])+1)]
            if letters!=expected:raise ValueError('FN set has missing split parts for P'+str(number))
            groups.pop((number,''),None)
    chosen=[]
    for part,paths in sorted(groups.items()):
        def rank(p):
            versions=re.findall(r'(?:^|[ _])V(\d+)(?=[ _.]|$)',p.stem,re.I)
            return max(map(int,versions),default=0),p.stat().st_mtime_ns
        paths.sort(key=rank,reverse=True)
        if len(paths)>1 and rank(paths[0])==rank(paths[1]):raise ValueError('Ambiguous FN versions for part '+str(part))
        chosen.append(paths[0])
    numbers={part[0] for part in groups}
    if numbers!=set(range(1,max(numbers)+1)):raise ValueError('FN set has missing part numbers. Select a complete set.')
    if (1,'A') in groups and (1,'B') not in groups:raise ValueError('FN P1B is missing from the selected set.')
    return chosen,int(ident[0][0])


def select_fn(config, selected):
    from episode_scanner import proposed_name
    from create_episode import source_duration
    paths,episode=fn_set(selected)
    rows=[]
    for path in paths:
        source_duration(path)  # Validate every member before saving the selection.
        target,rule=proposed_name(path.name,episode,config['program'])
        rows.append(dict(rule=rule,source_name=path.name,source_path=str(path),target_name=target,
                         target_path=str(Path(config['local_dir'])/target),manual_kind='fn'))
    data=source_choices(config['episode'])
    data['items']=[r for r in data['items'] if r.get('manual_kind')!='fn']+rows
    atomic_json(choices_path(config['episode']),data)
    return rows


def select_teaser(config, selected, name):
    from episode_scanner import proposed_name
    from create_episode import source_duration
    from teaser_selection import eligible_teaser
    from teaser_selection import is_fn_teaser
    if name=='FN' and not is_fn_teaser(Path(selected).name):
        raise ValueError('Select a TSER/TEASER FN file, not an NWN S1B program part.')
    path=Path(selected);source_duration(path)
    target,rule=proposed_name(path.name,config['episode'],config['program'])
    if name=='FN':target='TEASER FN.mp4';rule='teaser-fn'
    elif not rule.startswith('teaser') or not eligible_teaser(target,config['episode']):
        raise ValueError('Select the correct next-day teaser (or the valid AP campaign file).')
    if name=='WOW' and not re.search(r'\bWOW\b',target,re.I):raise ValueError('Select the WOW teaser.')
    if name=='AP' and not re.search(r'\bAP\b',target,re.I):raise ValueError('Select the AP teaser.')
    if name=='SHOW' and re.search(r'\b(?:FN\d*|WOW|AP)\b',target,re.I):raise ValueError('Select the next-day show teaser.')
    row=dict(rule=rule,source_name=path.name,source_path=str(path),target_name=target,
             target_path=str(Path(config['local_dir'])/target),manual_kind='teaser',manual_slot=name)
    data=source_choices(config['episode'])
    data['items']=[r for r in data['items'] if r.get('manual_slot')!=name]+[row]
    atomic_json(choices_path(config['episode']),data)
    return [row]


def select_ad(config, selected, name):
    from create_episode import make_placeholder,source_duration
    from schedule_assets import key
    source=Path(selected).resolve()
    if re.search(r'need.*fix|do[ _]*not[ _]*air|[\\/]not air[\\/]',str(source),re.I):
        raise ValueError('This file is marked as needing repair or not for airing.')
    try:relative=source.relative_to(ADS_ROOT.resolve())
    except ValueError:
        try:relative=source.relative_to((EXPORT_ROOT/'@ ADS').resolve())
        except ValueError:relative=Path('_SELECTED')/source.parent.name/source.name
    target=ADS_ROOT/relative
    before=(source.stat().st_size,source.stat().st_mtime_ns)
    if source!=target.resolve():
        stage=target.with_suffix('.selected.mp4')
        try:
            detail=make_placeholder(source,stage)
            if before!=(source.stat().st_size,source.stat().st_mtime_ns):raise ValueError('Source changed while reading. Retry after upload finishes.')
            os.replace(stage,target)
        finally:
            if stage.exists():stage.unlink()
    else:detail={'seconds':source_duration(source)[0]}
    path=BASE/'approved_ads.json'
    data=json.loads(path.read_text('utf-8')) if path.exists() else {'items':[]}
    data['items']=[r for r in data['items'] if key(r['name'])!=key(name)]
    data['items'].append(dict(name=name,path=str(target),source=str(source),seconds=detail['seconds'],
                              source_size=before[0],source_mtime_ns=before[1],user_selected=True))
    atomic_json(path,data)
    return [dict(target_name=target.name,source_path=str(source),target_path=str(target))]


def issues(config, result=None):
    from schedule_assets import Assets
    from teaser_selection import eligible_teaser
    from wow_rules import needs_next_wow_teaser
    from ap_rules import ap_campaign
    assets=Assets(config);items=config.get('rename_preview',{}).get('items',[])
    selected=source_choices(config['episode'])['items']
    items=items+selected
    available=[r['target_name'] for r in items if r.get('draft_duration') or Path(r['source_path']).is_file() or Path(r['target_path']).is_file()]
    settings=config.get('schedule_settings',{});out=[]
    if settings.get('fn') and not any(re.search(r'\bNWN S1B\b',n,re.I) for n in available):
        out.append(dict(kind='fn',name='FN S1B set',detail='Choose P1A to load its complete set.'))
    teasers=[n for n in available if re.match(r'^(TSER|TEASER) ',n,re.I) and eligible_teaser(n,config['episode'])]
    required=[]
    if settings.get('fn') and settings.get('tser_fn',True):required.append('FN')
    if needs_next_wow_teaser(config):required.append('WOW')
    if ap_campaign(config['episode']):required.append('AP')
    required.append('SHOW')
    for slot in required:
        found=any((not re.search(r'\b(?:FN\d*|WOW|AP)\b',n,re.I)) if slot=='SHOW' else bool(re.search(r'\b'+slot+r'\d*\b',n,re.I)) for n in teasers)
        if not found:out.append(dict(kind='teaser',name=slot,detail='Missing teaser '+slot))
    for ad in config.get('ads',{}).get('items',[]):
        # These INPUT labels are handled by the program/fixed-slot builder,
        # not by the ordinary ADS resolver (same exclusions as finish_schedule).
        if re.search(r'M QY Warn|Daily News Scroll|AD_SMTV INTRO',ad['name'],re.I):continue
        if not assets.resolve(ad['name']):out.append(dict(kind='ad',name=ad['name'],detail=ad.get('priority_class','OPTIONAL')))
    if result:
        for ad in result.get('unresolved_ads',[]):
            if not assets.resolve(ad['name']):out.append(dict(kind='ad',name=ad['name'],detail=ad.get('priority','OPTIONAL')))
        for message in result.get('missing',[]):
            prefixes=('Thiếu file: ', 'Missing file: ')
            file_name=next((message[len(p):] for p in prefixes if message.startswith(p)),None)
            if file_name and not assets.resolve(file_name):
                out.append(dict(kind='ad',name=file_name,detail='Missing rule / fixed insertion file'))
                continue
            # Known file issues already have selectable rows above. Other QC
            # problems (timing, segment gaps, placeholders) remain visible.
            out.append(dict(kind='qc',name=message,detail='Review QC / INPUT; Retry after corrections.'))
    seen=set();return_rows=[]
    for r in out:
        k=(r['kind'],r['name'])
        if k not in seen:seen.add(k);return_rows.append(r)
    return return_rows


def resolve_dialog(parent, config, result=None):
    """Returns cancel / continue / retry; individual successful repairs persist."""
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    import threading,queue
    pending=issues(config,result)
    if not pending:return 'continue',False
    window=tk.Toplevel(parent);window.title('Run all - missing files and QC');window.geometry('1100x590')
    window.transient(parent);window.grab_set()
    ttk.Label(window,text='Browse beside each item. FN: select P1A to load its set. Green check = file selection checked and saved.').pack(anchor='w',padx=12,pady=10)
    frame=ttk.Frame(window);frame.pack(fill='both',expand=True,padx=12)
    canvas=tk.Canvas(frame,highlightthickness=0)
    scroll=ttk.Scrollbar(frame,orient='vertical',command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
    table=ttk.Frame(canvas);item=canvas.create_window((0,0),window=table,anchor='nw')
    table.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
    window.bind('<MouseWheel>',lambda e:canvas.yview_scroll(int(-e.delta/120),'units'))
    table.columnconfigure(1,weight=3);table.columnconfigure(2,weight=2)
    for col,label in enumerate(('Type','File / QC issue','Status','Select file')):
        ttk.Label(table,text=label,font=('Segoe UI',10,'bold')).grid(row=0,column=col,sticky='w',padx=8,pady=8)
    status=tk.StringVar();ttk.Label(window,textvariable=status,wraplength=1040).pack(fill='x',padx=12,pady=8)
    buttons=ttk.Frame(window);buttons.pack(fill='x',padx=12,pady=10)
    state={'answer':'cancel','changed':False,'busy':False};messages=queue.Queue();controls=[];labels={}
    def row_status(idx,text,ok=False):
        labels[idx].configure(text=text,foreground='#168047' if ok else '#b3261e')
    def finish(answer):
        if state['busy']:return
        state['answer']=answer;window.destroy()
    def choose(idx,folder=False):
        if state['busy']:return
        issue=pending[idx]
        selected=(filedialog.askdirectory(parent=window,title='Select the S1B folder') if folder else
                  filedialog.askopenfilename(parent=window,title='Select file for '+issue['name'],filetypes=[('Media files','*.mp4 *.mov *.mxf *.mkv *.avi *.wav *.mp3'),('All files','*.*')]))
        if not selected:return
        if issue['kind']=='fn':
            try:paths,_=fn_set(selected)
            except Exception as exc:
                row_status(idx,'✗ '+str(exc));return
            if not messagebox.askokcancel('Selected FN set','Use these parts?\n\n'+'\n'.join(p.name for p in paths),parent=window):return
        state['busy']=True;row_status(idx,'Checking duration / creating temp...')
        for child in controls:child.configure(state='disabled')
        def work():
            try:
                if issue['kind']=='fn':rows=select_fn(config,selected)
                elif issue['kind']=='teaser':rows=select_teaser(config,selected,issue['name'])
                else:rows=select_ad(config,selected,issue['name'])
                messages.put((True,rows))
            except Exception as exc:messages.put((False,str(exc)))
        def poll():
            try:ok,value=messages.get_nowait()
            except queue.Empty:window.after(100,poll);return
            state['busy']=False
            for child in controls:child.configure(state='normal')
            if ok:
                state['changed']=True
                row_status(idx,'✓ Checked and saved\n'+selected,True)
                status.set('Saved: '+', '.join(r['target_name'] for r in value))
            else:row_status(idx,'✗ '+value);status.set('Selection failed; choose another file or retry.')
        threading.Thread(target=work,daemon=True).start();window.after(100,poll)
    for i,r in enumerate(pending):
        row=i+1
        ttk.Label(table,text=r['kind'].upper()).grid(row=row,column=0,sticky='nw',padx=8,pady=9)
        ttk.Label(table,text=r['name'],wraplength=440).grid(row=row,column=1,sticky='nw',padx=8,pady=9)
        ready=r.get('ready',False)
        label=ttk.Label(table,text=('✓ Found — can replace' if ready else '✗ '+('Needs review' if r['kind']=='qc' else 'Missing / not recognized'))+'\n'+r['detail'],wraplength=320,foreground='#168047' if ready else '#b3261e')
        label.grid(row=row,column=2,sticky='nw',padx=8,pady=9);labels[i]=label
        if r['kind']!='qc':
            actions=ttk.Frame(table);actions.grid(row=row,column=3,sticky='ne',padx=8,pady=9)
            button=ttk.Button(actions,text='Browse...',command=lambda idx=i:choose(idx));button.pack(side='left');controls.append(button)
            if r['kind']=='fn':
                button=ttk.Button(actions,text='Folder...',command=lambda idx=i:choose(idx,True));button.pack(side='left',padx=4);controls.append(button)
    for text,answer in [('Stop Run all','cancel'),('Continue / view QC','continue'),('Recheck and continue','retry')]:
        button=ttk.Button(buttons,text=text,command=lambda a=answer:finish(a));button.pack(side='right',padx=5);controls.append(button)
    window.protocol('WM_DELETE_WINDOW',lambda:finish('cancel'))
    parent.wait_window(window)
    return state['answer'],state['changed']
