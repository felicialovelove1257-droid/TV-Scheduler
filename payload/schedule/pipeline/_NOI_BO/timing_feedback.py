"""Apply external player feedback to the matching local schedule."""
import csv
import hashlib
import re
from pathlib import Path


def read_timeline(config):
    path=Path(config['config_path']).parent / f"EP_{int(config['episode'])}_schedule_timeline.csv"
    with path.open(encoding='utf-8-sig',newline='') as stream:
        return [dict(cycle=int(r['Cycle']),block=int(r['Block']),kind=r['Kind'],name=r['Name'],
                     path=r['Path'],duration=float(r['Duration'])) for r in csv.DictReader(stream)]


def changes_report(before, schedule):
    from difflib import SequenceMatcher
    after=[r for c in schedule['cycles'] for r in c['rows']]
    elapsed=0.0;wv=None
    for row in before:
        if row['kind']=='meditation':wv=elapsed
        elapsed+=row['duration']
    timing=schedule['timing'];end=schedule['day_end']
    lines=['WV / End — (+) cần thêm, (-) cần giảm:',
           'Trước → Sau (giây)',
           'WV: '+(f"{timing['target_seconds']-wv:+.3f}" if wv is not None else '—')+f" → {timing['gap_seconds']:+.3f}",
           f"End: {end['target_seconds']-elapsed:+.3f} → {end['gap_seconds']:+.3f}", '']
    def key(r):return (str(r['path']).casefold(),round(float(r['duration']),6))
    def label(r):return r['name']+f" ({float(r['duration']):.3f}s)"
    changes=[]
    groups=sorted({(r['cycle'],r['block']) for r in before+after if r['kind']!='marker'})
    for cycle,block in groups:
        old=[r for r in before if (r['cycle'],r['block'])==(cycle,block) and r['kind']!='marker']
        new=[r for r in after if (r['cycle'],r['block'])==(cycle,block) and r['kind']!='marker']
        detail=[]
        for op,i,j,a,b in SequenceMatcher(None,list(map(key,old)),list(map(key,new)),autojunk=False).get_opcodes():
            if op=='equal':continue
            if op=='replace' and j-i==b-a==1:
                detail.append('Thay: '+label(old[i])+' → '+label(new[a]))
            else:
                detail.extend('Bỏ: '+label(r) for r in old[i:j])
                detail.extend('Thêm: '+label(r) for r in new[a:b])
        if detail:changes.extend([f'Cycle {cycle} / Block {block}']+detail+[''])
    if changes:lines.extend(changes)
    elif [key(r) for r in before]!=[key(r) for r in after]:
        lines.append('Chỉ thay đổi marker; nội dung giữ nguyên.')
    else:lines.append('Không có thay đổi trong lịch.')
    lines.append('ĐẠT' if schedule.get('valid') else 'BẢN NHÁP — xem QC')
    lines.append('Kiểm tra lại M3U mới trên máy phát.')
    return '\n'.join(lines)


def show_changes(parent, text):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText
    previous=parent.grab_current()
    window=tk.Toplevel(parent);window.title('Đã điều chỉnh những gì')
    window.transient(parent)
    body=ScrolledText(window,width=100,height=26,wrap='word')
    body.pack(fill='both',expand=True,padx=12,pady=12)
    body.insert('1.0',text);body.configure(state='disabled')
    ttk.Button(window,text='Đóng',command=window.destroy).pack(pady=(0,10))
    window.grab_set();parent.wait_window(window)
    if previous is not None and previous.winfo_exists():previous.grab_set()


def save_history(config, before, schedule, report):
    import json
    from datetime import datetime
    elapsed=0.0;wv=None
    for row in before:
        if row['kind']=='meditation':wv=elapsed
        elapsed+=float(row['duration'])
    timing=schedule['timing'];end=schedule['day_end']
    entry=dict(recorded_at=datetime.now().astimezone().isoformat(),episode=int(config['episode']),
               mode='feedback' if config.get('timing_feedback') else 'original_targets',
               feedback=config.get('timing_feedback'),
               wv_before_seconds=wv,wv_after_seconds=timing.get('actual_seconds'),
               end_before_seconds=elapsed,end_after_seconds=end.get('actual_seconds'),
               wv_remaining_seconds=timing.get('gap_seconds'),end_remaining_seconds=end.get('gap_seconds'),
               report=report,playback_verified=False)
    path=Path(config['config_path']).parent/'timing_adjustment_history.jsonl'
    with path.open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(entry,ensure_ascii=False)+'\n')
    return entry


def parse(text):
    result = {}
    for line in text.splitlines():
        label = re.search(r'\b(WV|END)\b', line, re.I)
        if not label:
            continue
        key = label[1].lower()
        match = re.search(r'\b(ADD|MINUS)\s+(\d{1,2}):([0-5]\d):([0-5]\d)\b', line, re.I)
        if not match or key in result:
            raise ValueError('Mỗi dòng WV / End cần có ADD hoặc MINUS và giờ hh:mm:ss.')
        seconds = int(match[2])*3600 + int(match[3])*60 + int(match[4])
        if seconds > 600:
            raise ValueError('Lệch quá 10 phút; kiểm tra lại lịch và kết quả đã dán.')
        result[key] = seconds * (1 if match[1].upper() == 'ADD' else -1)
    if set(result) != {'wv', 'end'}:
        raise ValueError('Dán đủ hai dòng WV và End.')
    return result


def correction(config, text):
    delta = parse(text)
    ep = int(config['episode'])
    mentioned = re.search(r'\bEP\s+(\d+)\b', text, re.I)
    if mentioned and int(mentioned[1]) != ep:
        raise ValueError('Kết quả kiểm tra khác số EP đang mở.')
    previous = config.get('timing_feedback', {})
    if previous.get('text', '').strip() == text.strip():
        return previous.copy()
    directory = Path(config['config_path']).parent
    timeline = directory / f'EP_{ep}_schedule_timeline.csv'
    playlist = Path(config['local_dir']).parent / '_playlist' / f'EP {ep} v1.m3u'
    if not timeline.exists() or not playlist.exists():
        raise ValueError('Hãy tạo lịch của EP này trước khi canh lại giờ.')
    with timeline.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    elapsed = 0.0
    wv = None
    for row in rows:
        if row['Kind'] == 'meditation':
            if wv is not None:
                raise ValueError('Lịch có nhiều mốc WV; cần kiểm tra lại.')
            wv = elapsed
        elapsed += float(row['Duration'])
    if wv is None:
        raise ValueError('Không tìm thấy mốc WV trong lịch hiện tại.')
    return dict(text=text.strip(), mt_target=wv+delta['wv'], day_target=elapsed+delta['end'],
                baseline_wv=wv, baseline_end=elapsed, delta=delta,
                playlist_sha256=hashlib.sha256(playlist.read_bytes()).hexdigest())


def show(parent, config, rebuild):
    import tkinter as tk
    from tkinter import ttk, messagebox
    window = tk.Toplevel(parent)
    window.title('Canh lại giờ')
    window.transient(parent)
    ttk.Label(window, text='Dán kết quả của đúng M3U hiện tại. MINUS: giảm; ADD: thêm.').pack(padx=14, pady=10)
    entry = tk.Text(window, width=76, height=6)
    entry.pack(padx=14, pady=6)
    entry.insert('1.0', config.get('timing_feedback', {}).get('text', ''))
    ttk.Label(window, text='Ví dụ: 21:00:07 WV...to MINUS 00:00:37\n00:59:57 End...to ADD 00:00:03').pack(padx=14, pady=6)

    def apply(reset=False):
        old = config.get('timing_feedback')
        try:
            if reset:
                config.pop('timing_feedback', None)
            else:
                config['timing_feedback'] = correction(config, entry.get('1.0', 'end'))
            if rebuild():
                window.destroy()
        except Exception as exc:
            if old is None:
                config.pop('timing_feedback', None)
            else:
                config['timing_feedback'] = old
            messagebox.showerror('Canh lại giờ', str(exc), parent=window)

    ttk.Button(window, text='Canh lại và xuất lịch', command=apply).pack(pady=6)
    ttk.Button(window, text='Bỏ điều chỉnh, dùng mốc gốc', command=lambda: apply(True)).pack(pady=6)
    window.grab_set()
