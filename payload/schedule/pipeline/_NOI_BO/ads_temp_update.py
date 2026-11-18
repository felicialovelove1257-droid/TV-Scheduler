"""Create only missing ADS scheduling temps from INPUT_4; preserve existing media."""
import os
import re
import subprocess
import uuid
from pathlib import Path

def read_inventory(path):
    import csv,json
    path=Path(path)
    if path.suffix.lower()=='.json':
        data=json.loads(path.read_text('utf-8-sig'))
        if not isinstance(data,dict) or not isinstance(data.get('Files'),list):raise ValueError('Invalid ADS_FILES.json / Sai định dạng danh sách ADS')
        if data.get('Complete') is False or data.get('Errors'):raise ValueError('Scan incomplete / Danh sách quét chưa hoàn tất; cần quét lại')
        rows=data['Files']
    else:
        with path.open(encoding='utf-8-sig',newline='') as handle:
            reader=csv.DictReader(handle)
            if not {'FileName','RelativePath','DurationSeconds','ProbeStatus','IsMedia'}.issubset(reader.fieldnames or []):raise ValueError('Invalid ADS_FILES.csv columns / Thiếu cột danh sách ADS')
            rows=list(reader)
    return [r for r in rows if str(r.get('IsMedia','')).casefold()=='true']

def plan_inventory(rows,root):
    import math
    from pathlib import PureWindowsPath
    root=Path(root).resolve();new={};review=[];existing=0
    for row in rows:
        name=str(row.get('FileName',''));relative=PureWindowsPath(str(row.get('RelativePath','')))
        if relative.is_absolute() or relative.drive or '..' in relative.parts or relative.name!=name or not relative.parts:
            review.append(name+' — invalid relative path / đường dẫn không hợp lệ');continue
        if any(re.search(r'[<>:"|?*\x00-\x1f]',p) or p.endswith(('.', ' ')) for p in relative.parts):
            review.append(name+' — invalid filename / tên không hợp lệ');continue
        target=root.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(root):review.append(name+' — outside ADS folder');continue
        if target.exists():existing+=1;continue
        flag=str(row.get('ReviewFlag','')).strip()
        restricted=re.search(r'(^|[\\/ ])old([\\/ ]|$)|need.*fix|not[ _]*air|do[ _]*not[ _]*use',str(relative),re.I)
        if flag or restricted:
            review.append(str(relative)+' — review / cần kiểm tra: '+(flag or 'restricted folder'));continue
        if str(row.get('ProbeStatus','')).upper()!='OK':
            review.append(str(relative)+' — duration probe failed / chưa đo được thời lượng');continue
        try:seconds=float(row['DurationSeconds'])
        except (KeyError,ValueError,TypeError):seconds=float('nan')
        if not math.isfinite(seconds) or not 0<seconds<=86400:
            review.append(str(relative)+' — invalid duration / thời lượng không hợp lệ');continue
        if target.suffix.lower()!='.mp4':
            review.append(str(relative)+' — only MP4 temps supported / chỉ hỗ trợ temp MP4');continue
        identity=str(target).casefold();item=dict(name=name,target=target,seconds=seconds)
        if identity in new and abs(new[identity]['seconds']-seconds)>0.001:
            new[identity]['conflict']=True;review.append(str(relative)+' — conflicting durations / thời lượng mâu thuẫn')
        else:new.setdefault(identity,item)
    return [i for i in new.values() if not i.get('conflict')],review,existing


def plan(entries, assets, root):
    from reserve_ads import resolve_entry
    from schedule_assets import key
    root=Path(root).resolve();new={};review=[];existing=0
    for entry in entries:
        if entry.get('excluded'):continue
        name=entry['name']
        path,status,candidates=resolve_entry(entry,assets)
        if path:
            existing+=1;continue
        if status=='ambiguous':
            review.append(name+' — ambiguous name / tên chưa rõ');continue
        durations=re.findall(r'[\[(]\s*(\d+):([0-5]\d)\s*[\])]',name)
        if len(durations)!=1:
            review.append(name+' — missing/unclear duration / thiếu thời lượng rõ ràng');continue
        seconds=int(durations[0][0])*60+int(durations[0][1])
        if not 0<seconds<=86400:
            review.append(name+' — invalid duration / thời lượng không hợp lệ');continue
        mapped=assets.mapping.get(key(name),set())
        if len(mapped)>1:
            review.append(name+' — multiple mappings / nhiều tên ghép');continue
        if mapped:target=Path(next(iter(mapped))).resolve()
        else:
            folder=entry['folder'].strip()
            clean=re.sub(r'[\[(]\s*\d+:[0-5]\d\s*[\])]','',name).strip()
            clean=re.sub(r'\.mp4$','',clean,flags=re.I).strip()
            if any(re.search(r'[<>:"/\\|?*\x00-\x1f]',v) or v in ('.','..') or v.endswith(('.', ' ')) for v in (folder,clean)):
                review.append(name+' — invalid folder/name / cần kiểm tra tên thư mục hoặc file');continue
            target=(root/folder/(clean+'.mp4')).resolve()
        if not target.is_relative_to(root) or target.suffix.lower()!='.mp4':
            review.append(name+' — mapping outside ADS folder / đường dẫn ngoài thư mục ADS');continue
        if target.exists():existing+=1;continue
        identity=str(target).casefold()
        item=dict(name=name,target=target,seconds=seconds)
        if identity in new and new[identity]['seconds']!=seconds:
            new[identity]['conflict']=True
            review.append(name+' — conflicting durations / thời lượng mâu thuẫn')
        else:new.setdefault(identity,item)
    return [x for x in new.values() if not x.get('conflict')],review,existing


def create(items):
    made=[];errors=[]
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    for item in items:
        target=item['target'];stage=target.with_name('.ads-temp-'+uuid.uuid4().hex+'.mp4')
        try:
            if target.exists():continue
            target.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(['ffmpeg','-v','error','-nostdin','-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
                            '-t',str(item['seconds']),'-c:a','aac','-b:a','128k','-movflags','+faststart',str(stage)],
                           check=True,capture_output=True,creationflags=flags,timeout=300)
            result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(stage)],
                                  check=True,capture_output=True,text=True,creationflags=flags,timeout=30)
            if abs(float(result.stdout.strip())-item['seconds'])>0.1:raise ValueError('Temp duration mismatch')
            # Atomic no-overwrite publication, even if another process creates the file.
            os.link(stage,target);made.append(str(target))
        except FileExistsError:pass
        except Exception as exc:errors.append(item['name']+' — '+str(exc))
        finally:stage.unlink(missing_ok=True)
    return made,errors


def show_dialog(parent):
    import tkinter as tk
    from tkinter import ttk,filedialog
    from tkinter.scrolledtext import ScrolledText
    import threading,queue,zipfile
    from portable_paths import WORKBOOK_PATH,ADS_ROOT
    from import_sources import read_sheet,read_shared_strings,sheet_targets
    from reserve_ads import read_catalog
    from schedule_assets import Assets
    from ui_language import get_language
    vi=get_language()=='vi'
    def tr(en,vn):return vn if vi else en
    window=tk.Toplevel(parent);window.title(tr('Update ADS temps','Cập nhật temp ADS'));window.geometry('850x580')
    source=tk.StringVar(value=str(WORKBOOK_PATH))
    bar=ttk.Frame(window,padding=12);bar.pack(fill='x')
    ttk.Entry(bar,textvariable=source).pack(side='left',fill='x',expand=True)
    def browse():
        name=filedialog.askopenfilename(parent=window,filetypes=[('ADS lists / INPUT','*.csv *.json *.xlsx'),('ADS_FILES.csv','*.csv'),('ADS_FILES.json','*.json'),('INPUT workbook','*.xlsx')])
        if name:source.set(name)
    choose=ttk.Button(bar,text=tr('Select list','Chọn danh sách'),command=browse);choose.pack(side='left',padx=6)
    ttk.Label(window,text=tr('Select ADS_FILES.csv / ADS_FILES.json or INPUT.xlsx. Creates missing temps only.',
                           'Chọn ADS_FILES.csv / ADS_FILES.json hoặc INPUT.xlsx. Chỉ tạo temp còn thiếu.'),padding=12).pack(anchor='w')
    output=ScrolledText(window,wrap='word');output.pack(fill='both',expand=True,padx=12)
    actions=ttk.Frame(window,padding=12);actions.pack(fill='x')
    busy=[False];jobs=queue.Queue()
    def close():
        if not busy[0]:window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    def start():
        selected=source.get();busy[0]=True;button.configure(state='disabled');choose.configure(state='disabled')
        output.delete('1.0','end');output.insert('end',tr('Checking list…','Đang đối chiếu danh sách…'))
        def worker():
            try:
                if Path(selected).suffix.lower() in ('.csv','.json'):
                    entries=read_inventory(selected)
                    if not entries:raise ValueError('No media in list / Danh sách không có media')
                    items,review,existing=plan_inventory(entries,ADS_ROOT)
                else:
                    with zipfile.ZipFile(selected) as z:
                        targets=sheet_targets(z)
                        if 'INPUT_4' not in targets:raise ValueError('Missing INPUT_4 / Không có bảng INPUT_4')
                        entries=read_catalog(read_sheet(z,targets['INPUT_4'],read_shared_strings(z)))
                    if not entries:raise ValueError('INPUT_4 has no ADS / INPUT_4 không có danh sách ADS')
                    assets=Assets({'episode':0,'local_dir':str(Path(ADS_ROOT)/'__no_ep__')})
                    items,review,existing=plan(entries,assets,ADS_ROOT)
                made,errors=create(items)
                jobs.put((made,review+errors,existing))
            except Exception as exc:jobs.put(exc)
        def poll():
            try:result=jobs.get_nowait()
            except queue.Empty:window.after(150,poll);return
            busy[0]=False;button.configure(state='normal');choose.configure(state='normal');output.delete('1.0','end')
            if isinstance(result,Exception):output.insert('end',str(result));return
            made,review,existing=result
            title=tr('Nothing new in the list.','Danh sách không có gì mới.') if not made and not review else tr('Created temps: ','Đã tạo temp: ')+str(len(made))
            output.insert('end',title+'\n'+tr('Already available: ','Đã có: ')+str(existing)+'\n\n'+'\n'.join(made))
            if review:output.insert('end','\n\n'+tr('Needs review (not created):','Cần kiểm tra (chưa tạo):')+'\n'+'\n'.join(review))
        threading.Thread(target=worker,daemon=True).start();window.after(150,poll)
    button=ttk.Button(actions,text=tr('Update ADS temps','Cập nhật temp ADS'),command=start);button.pack(side='left')
    ttk.Button(actions,text=tr('Close','Đóng'),command=close).pack(side='right')
    return window
