"""Ordered ADS groups: one scheduling item, several consecutive playlist files."""
import hashlib
import json
import os
import re
import uuid
from pathlib import Path

def identity(path):return str(Path(path).resolve()).casefold()

def signature(path):
    s=Path(path).stat();return [s.st_size,s.st_mtime_ns]

def valid(group):
    try:
        parts=group['parts']
        return len(parts)>=2 and all(Path(p['path']).is_file() and signature(p['path'])==p['signature'] for p in parts)
    except (OSError,KeyError,TypeError):return False

def save_group(config, paths, name):
    from missing_media import BASE,ADS_ROOT,atomic_json
    from create_episode import make_placeholder,source_duration,run
    from schedule_assets import key
    sources=[Path(p).resolve() for p in paths]
    if len(sources)<2 or len({identity(p) for p in sources})!=len(sources):raise ValueError('Select at least two different files / Chọn ít nhất hai file khác nhau')
    parts=[];folder=ADS_ROOT/'_GROUP_PARTS'
    for source in sources:
        if '_GROUPS' in source.parts:raise ValueError('Select the original group members, not a group temp.')
        if re.search(r'need.*fix|do[ _]*not[ _]*air|[\\/]not air[\\/]',str(source),re.I):raise ValueError('File marked not for airing: '+source.name)
        before=signature(source)
        if source.is_relative_to(ADS_ROOT.resolve()):target=source
        else:
            token=hashlib.sha256(str(source).encode()).hexdigest()[:12]
            target=folder/token/source.name
            if not target.exists():make_placeholder(source,target)
        seconds=source_duration(source)[0]
        if before!=signature(source):raise ValueError('Source changed: '+source.name)
        # Never reuse an old temp after its source changes.
        if target!=source and abs(source_duration(target)[0]-seconds)>0.1:
            target=folder/uuid.uuid4().hex/source.name;make_placeholder(source,target)
        parts.append(dict(path=str(target),source=str(source),seconds=seconds,signature=signature(target)))
    token=uuid.uuid4().hex[:12]
    label=' + '.join(p.stem for p in sources)
    label=re.sub(r'[<>:"/\\|?*\x00-\x1f]',' ',label)[:130]
    proxy=ADS_ROOT/'_GROUPS'/('ADS GROUP '+label+' '+token+'.mp4');proxy.parent.mkdir(parents=True,exist_ok=True)
    seconds=sum(p['seconds'] for p in parts)
    run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(seconds),'-c:a','aac','-b:a','128k',str(proxy)])
    path=BASE/'approved_ads.json';data=json.loads(path.read_text('utf-8')) if path.exists() else {'items':[]}
    data['items']=[r for r in data['items'] if key(r['name'])!=key(name)]
    data['items'].append(dict(name=name,path=str(proxy),seconds=seconds,user_selected=True,parts=parts))
    atomic_json(path,data)
    return [dict(target_name=proxy.name,target_path=str(proxy),source_path=' | '.join(map(str,sources)))]

def attach(assets, records):
    from schedule_assets import key
    assets.groups={identity(r['path']):r for r in records if r.get('parts')}
    members={identity(p['path']) for g in assets.groups.values() for p in g['parts']}
    assets.group_members=members
    # Group components and orphaned proxy files must never enter a separate ADS slot.
    assets.files=[p for p in assets.files if identity(p) not in members and '_GROUP_PARTS' not in p.parts and '_GROUPS' not in p.parts]
    for group in assets.groups.values():
        assets.mapping[key(group['name'])]={Path(group['path'])}
        if valid(group):assets.files.append(Path(group['path']))

def playlist_paths(path,assets):
    group=assets.groups.get(identity(path))
    if not group:return [str(path)]
    if not valid(group):raise ValueError('ADS group missing/changed file: '+group['name'])
    return [p['path'] for p in group['parts']]

def collapse(rows,assets):
    """Only a complete ordered adjacent sequence counts as one ADS in M3U QC."""
    groups=list(assets.groups.values());result=[];issues=[];i=0
    while i<len(rows):
        matches=[g for g in groups if [identity(r['path']) for r in rows[i:i+len(g['parts'])]]==[identity(p['path']) for p in g['parts']]]
        if len(matches)==1:
            g=matches[0];r=dict(rows[i],path=g['path'],name=Path(g['path']).name,hint=g['seconds'])
            result.append(r)
            if not valid(g):issues.append(('ERROR','—',str(r['line']),'ADS group missing/changed file: '+g['name']))
            i+=len(g['parts']);continue
        related=[g for g in groups if identity(rows[i]['path']) in {identity(p['path']) for p in g['parts']}]
        if related:issues.append(('ERROR','—',str(rows[i]['line']),'ADS group incomplete / wrong order: '+related[0]['name']))
        result.append(rows[i]);i+=1
    return result,issues

def choose_group(parent,name):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    from missing_media import BASE
    from schedule_assets import key
    from ui_language import get_language
    vi=get_language()=='vi'
    def t(en,vn):return vn if vi else en
    file=BASE/'approved_ads.json';data=json.loads(file.read_text('utf-8')) if file.exists() else {'items':[]}
    old=next((r for r in data['items'] if key(r['name'])==key(name)),{})
    paths=[p['path'] for p in old.get('parts',[])]
    lengths={p['path']:p['seconds'] for p in old.get('parts',[])}
    win=tk.Toplevel(parent);win.title(t('ADS group — playback order','Nhóm ADS — thứ tự phát'));win.geometry('720x420');win.transient(parent);win.grab_set()
    ttk.Label(win,text=name,wraplength=680,padding=10).pack(anchor='w')
    listing=tk.Listbox(win,exportselection=False);listing.pack(fill='both',expand=True,padx=10)
    total=ttk.Label(win,padding=10);total.pack(anchor='w')
    answer=[]
    def refresh():
        listing.delete(0,'end')
        for n,p in enumerate(paths,1):
            seconds=int(round(lengths.get(p,0)))
            listing.insert('end',f'{n}. {Path(p).name} — {seconds//60}:{seconds%60:02}')
        seconds=int(round(sum(lengths.get(p,0) for p in paths)))
        total.configure(text=t('Group total: ','Tổng nhóm: ')+f'{len(paths)} files — {seconds//60}:{seconds%60:02}')
    def add():
        for p in filedialog.askopenfilenames(parent=win,title=t('Select ADS files','Chọn các file ADS'),filetypes=[('Media','*.mp4 *.mov *.mxf *.mkv *.avi *.wav *.mp3')]):
            if identity(p) not in {identity(x) for x in paths}:
                try:
                    from create_episode import source_duration
                    lengths[p]=source_duration(Path(p))[0];paths.append(p)
                except Exception as exc:messagebox.showerror('ADS',str(exc),parent=win)
        refresh()
    def move(delta):
        selected=listing.curselection()
        if selected and 0<=selected[0]+delta<len(paths):
            a=selected[0];b=a+delta;paths[a],paths[b]=paths[b],paths[a];refresh();listing.selection_set(b)
    def remove():
        if listing.curselection():paths.pop(listing.curselection()[0]);refresh()
    def save():
        if len(paths)<2:messagebox.showerror('ADS',t('Select at least two files','Chọn ít nhất hai file'),parent=win);return
        answer.extend(paths);win.destroy()
    actions=ttk.Frame(win,padding=10);actions.pack(fill='x')
    for text,cmd in [(t('Add files','Thêm file'),add),('↑',lambda:move(-1)),('↓',lambda:move(1)),(t('Remove','Bỏ file'),remove),(t('Save group','Lưu nhóm'),save),(t('Cancel','Hủy'),win.destroy)]:
        ttk.Button(actions,text=text,command=cmd).pack(side='left',padx=3)
    refresh();parent.wait_window(win);parent.grab_set()
    return answer
