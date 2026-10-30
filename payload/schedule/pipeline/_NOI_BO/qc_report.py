"""Human-readable scheduling QC, shared by the screen and saved report."""

def time_text(seconds):
    ms=round(seconds*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'

def ads_usage_report(config, rows, assets):
    import re
    from pathlib import Path
    entries={}
    def identity(path):return str(path).replace('\\','/').casefold()
    def add(name,path=None):
        key=identity(path) if path else 'unresolved:'+name.casefold()
        if key not in entries:entries[key]={'name':Path(path).name if path else name,'sheet_name':name,'path':str(path) if path else '', 'cycles':set(),'plays':0}
        return entries[key]
    for item in config.get('ads',{}).get('items',[]):
        if re.search(r'Daily News Scroll',item['name'],re.I):continue
        add(item['name'],assets.resolve(item['name']))
    for label,rule in config.get('cycle_rules',{}).items():
        if re.search(r'Abortion|Hygiene|M QY Warn',label,re.I) and re.search(r'\d',str(rule)):
            add(label,assets.resolve(label))
    for row in rows:
        if row.get('kind') not in ('PRIORITY','DO_NOT_SKIP','optional','fixed','intro'):continue
        if re.match(r'^M intro\b',row['name'],re.I):continue
        item=add(row['name'],row['path'])
        item['cycles'].add(row['cycle']);item['plays']+=1
    result=[]
    for item in entries.values():
        item['cycles']=sorted(item['cycles']);item['cycle_count']=len(item['cycles'])
        item['color']='green' if item['cycle_count']>3 else 'red'
        result.append(item)
    return sorted(result,key=lambda x:(x['cycle_count']>3,x['name'].casefold()))


def next_show_summary(full_rows, kept_rows):
    """Preview show duration plus the internal insert of a two-segment show."""
    last=next((r for r in reversed(kept_rows) if r.get('kind')=='program'),None)
    if not last:return None
    current=(last['cycle'],last['block'])
    indices=[i for i,r in enumerate(full_rows) if r.get('kind')=='program' and (r['cycle'],r['block'])==current]
    if not indices:return None
    following=next((r for r in full_rows[max(indices)+1:] if r.get('kind')=='program'),None)
    if not following:return None
    group=(following['cycle'],following['block'])
    parts=[r for r in full_rows if r.get('kind')=='program' and (r['cycle'],r['block'])==group]
    import re
    excluded=[r for r in parts if re.search(r'\bNWN\s+DAILY\s+SCROLL\b',r['name'],re.I)]
    parts=[r for r in parts if r not in excluded]
    if not parts:return None
    inserts=[]
    two_segments=(len(parts)==2 and not any(r.get('continuous_show') for r in parts)
                  and all(re.search(r'\bS(?:EG\s*)?[12]\b',r['name'],re.I) for r in parts)
                  and not any(re.search(r'\bNWN\b',r['name'],re.I) for r in parts))
    if two_segments:
        positions=[i for i,r in enumerate(full_rows) if any(r is part for part in parts)]
        inserts=[r for r in full_rows[positions[0]+1:positions[-1]]
                 if r.get('kind') in ('teaser','fixed','optional','PRIORITY','DO_NOT_SKIP')
                 and (r['cycle'],r['block'])==group]
    main=next((r for r in parts if ' MAIN ' in r['name'].upper()),parts[0])
    return dict(name=main['name'],cycle=group[0],block=group[1],
                duration=sum(r['duration'] for r in parts+inserts),excludes_daily_scroll=bool(excluded),
                segment_insert_seconds=sum(r['duration'] for r in inserts),
                segment_inserts=[dict(name=r['name'],duration=r['duration']) for r in inserts],
                parts=[dict(name=r['name'],duration=r['duration']) for r in parts])


def render_qc(result):
    timing=result.get('timing',{});end=result.get('day_end',{})
    rows=[r for c in result.get('cycles',[]) for r in c.get('rows',[])]
    def draft_notice(text):return text.startswith(('Bản nháp:','Bản No NXT nháp','Bản nháp dùng'))
    errors=[x for x in result.get('missing',[]) if not draft_notice(x)]
    lines=[f"EP {result['episode']} — {'✗' if errors else '⚠' if result.get('missing') or end.get('forced_extension') else '✓'}",'', '1. MỐC MEDITATION']
    actual=timing.get('actual_seconds');target=timing.get('target_seconds',72000)
    if actual is None:
        lines.append('✗ Chưa xác định được giờ bắt đầu MT.')
    else:
        delta=actual-target
        status='✓' if abs(delta)<=15 else '✗'
        difference='đúng mốc' if abs(delta)<0.001 else f"{'muộn' if delta>0 else 'sớm'} {abs(delta):.3f} giây"
        lines += [f'{status} MT bắt đầu {time_text(actual)} — {difference}.',
                  f'Khoảng cho phép: {time_text(target-15)} đến {time_text(target+15)}.']
        for i,r in enumerate(rows):
            if r.get('kind')=='meditation':
                previous=next((x for x in reversed(rows[:i]) if x.get('kind') not in ('marker',)),None)
                lines.append(f"Vị trí: Cycle {r['cycle']}"+(f", sau {previous['name']}" if previous else '')+'.')
                break
    shift=timing.get('show_shift')
    if shift:
        lines.append(f"MT shift: {shift['shows']:+d} shows; normal cycle {shift['normal_cycle']} / block {shift['normal_block']}; selected cycle {shift['selected_cycle']} / block {shift['selected_block']}, after {shift['after']}.")
    lines += ['', '2. CUỐI NGÀY']
    actual=end.get('actual_seconds');target=end.get('target_seconds',86400)
    if not actual:
        lines.append('✗ Chưa có lịch để tính giờ kết thúc.')
    else:
        status='✓' if target-15<=actual<=target+15 else '⚠' if end.get('forced_extension') else '✗'
        lines += [f'{status} Kết thúc {time_text(actual)}.',
                  f'Khoảng mong muốn: {time_text(target-15)} đến {time_text(target+15)}.']
        if actual<target: lines.append(f'Còn cách cuối ngày {time_text(target-actual)}.')
        elif actual>target: lines.append(f'Vượt cuối ngày {time_text(actual-target)}.')
        last=next((r for r in reversed(rows) if r.get('kind')=='program'),None)
        if last: lines.append('Chương trình cuối: '+last['name'])
        following=end.get('next_show')
        if following:
            lines.append('Chương trình kế tiếp: '+following['name'])
            lines.append('Thời lượng show kế tiếp: '+time_text(following['duration']))
            if following.get('segment_insert_seconds'):
                lines.append('Đã gồm mục chèn giữa 2 segment: '+time_text(following['segment_insert_seconds']))
            else:
                lines.append('Không tính ADS chèn ngoài show.')
            if following.get('excludes_daily_scroll'):
                lines.append('NWN kế tiếp: thời lượng không tính Daily Scroll.')
        elif last:
            lines.append('Chương trình kế tiếp: chưa có dữ liệu trong các cycle đã dựng.')
    exception=end.get('priority_fallback')
    if exception and exception.get('removed'):
        lines.append('Ngoại lệ cuối ngày: đã thử các cách thường; cho phép bỏ ADS ưu tiên/DO_NOT_SKIP sau MT.')
        lines.append('Mốc trước ngoại lệ: '+time_text(exception['before_seconds']))
        for item in exception['removed']:
            lines.append('ADS được bỏ: '+item['name']+' — '+time_text(item['duration']))
    extension=end.get('forced_extension')
    pulled=end.get('pulled_show')
    if pulled and not extension:
        lines.append('Next show pulled forward: '+pulled['name']+' — '+time_text(pulled['show_seconds']))
        lines.append('Previous ending: '+time_text(pulled['before_seconds'])+'; new ending: '+time_text(pulled['after_seconds']))
    if end.get('search_limited'):
        lines.append('Search limit reached: the result is the best candidate retained, not a proof that no other arrangement exists.')
    if extension:
        lines.append('⚠ End-day overrun: the tested combinations did not reach the 15-second tolerance; the next show is retained.')
        lines.append('Mốc cũ trước khi nối: '+time_text(extension['before_seconds']))
        lines.append('Show được nối thêm: '+extension['name']+' — '+time_text(extension['show_seconds']))
        lines.append('Mốc mới sau khi nối: '+time_text(extension['after_seconds']))
        lines.append('Đây là ngoại lệ được phép; không có nghĩa là đã đạt mốc 24h ±15 giây.')
    if end.get('extension_unavailable'):
        lines.append('Không thể nối show: các cycle đã dựng không có show tiếp theo.')
    for error in end.get('extension_errors',[]):lines.append('Không thể nối show: '+error)
    lines += ['', '3. CÁC MỤC CẦN XỬ LÝ']
    issues=[s for s in result.get('missing',[]) if not s.startswith(('Chưa đạt 20:00','Cuối ngày chưa vào khoảng'))]
    for s in issues:
        s=s.replace('source/path','file nguồn hoặc đường dẫn').replace('Slot bị trùng','Hai mục chèn đang nằm sát nhau')
        lines.append(('⚠ ' if draft_notice(s) else '✗ ')+s)
    if not issues: lines.append('✓ Các kiểm tra còn lại không báo lỗi.')
    conflicts=result.get('insertion_conflict_count',0)
    lines.append('✓ Mỗi chỗ chèn chỉ có một mục.' if not conflicts else f'✗ Có {conflicts} chỗ chèn hai mục sát nhau.')
    lines += ['', '4. ĐIỀU CHỈNH ĐÃ THỰC HIỆN']
    changes=[]
    for change in timing.get('max_changes',[])+end.get('max_changes',[]):
        changes.append(f"Cycle {change['cycle']}: {change['before']} → {change['after']} (+{change['added_seconds']:.3f} giây).")
    for ad in timing.get('ads_added',[]):
        changes.append(f"Cycle {ad['cycle']}: thêm {ad['name']} để canh MT ({time_text(ad['duration'])}).")
    for change in timing.get('ads_adjustments',[]):
        action='chuyển xuống sau MT trong cùng cycle' if change['action']=='move_after_mt' else 'bỏ để canh MT'
        changes.append(f"Cycle {change['cycle']}: {change['name']} — {action}.")
    for move in result.get('insertion_slot_moves',[]):
        if move.get('action')=='remove':
            changes.append(f"Cycle {move['cycle']}: removed {move['name']}. {move['reason']}")
            continue
        changes.append(f"Cycle {move['cycle']}: chuyển {move['name']} đến sau {move['after']}.")
    for removed in end.get('removed_inserts',[])+end.get('removed_daily_scroll',[]):
        changes.append(f"Cycle {removed.get('cycle','?')}: bỏ {removed.get('name','mục chèn')} để canh cuối ngày.")
    changes.extend(f"Cycle {item['cycle']}: thêm {item['name']} để canh cuối ngày." for item in end.get('added_ads',[]))
    for move in end.get('ads_reflow',[]):
        if move['action']=='move':
            changes.append(f"Cycle {move['cycle']}: chuyển {move['name']} đến sau {move['after']}.")
        else:
            changes.append(f"Cycle {move['cycle']}: bỏ {move['name']} để canh cuối ngày.")
    change=end.get('outro_change')
    if change: changes.append(f"Cycle {change['cycle']}: {change['before']} → {change['after']}.")
    for move in result.get('teaser_spacing_changes',[]):
        changes.append(f"Cycle {move['cycle']}: giãn teaser {move['teaser']} từ block {move['from_block']} sang {move['to_block']}, đổi chỗ với {move['ad']}.")
    lines.extend('• '+s for s in changes)
    if not changes: lines.append('Chưa có điều chỉnh bổ sung.')
    lines += ['', '5. FILE KẾT QUẢ', result.get('m3u_path','Chưa xuất M3U.')]
    lines += ['', '6. ADS SỬ DỤNG TRONG NGÀY', 'Xanh: hơn 3 cycle; đỏ: 0–3 cycle. Màu thể hiện mức sử dụng.']
    for item in result.get('ads_usage',[]):
        cycles=', '.join(map(str,item['cycles'])) or 'Không dùng'
        lines.append(f"{'✓' if item['cycle_count']>3 else '✗'} {item['name']} — ADS: {item['cycle_count']} cycle; {item['plays']} lần; cycle {cycles}.")
    return '\n'.join(lines)+'\n'


def render_cycle_check(result, rules):
    import re
    from difflib import SequenceMatcher
    cycles=[c for c in result.get('cycles',[]) if any(r.get('kind')=='program' for r in c.get('rows',[]))]
    if not cycles or not cycles[0].get('rows'): return 'Chưa có lịch để kiểm tra các cycle.\n'
    def label(row):
        n=row['name'].upper()
        if 'BMD' in n and ('M INTRO' in n or 'BMD IN' in n):
            if 'LONG' in n:return 'bmd m intro long'
            if 'SHORT' in n:return 'bmd m intro short'
        if 'WOW' in n and ('M INTRO' in n or 'WOW IN' in n):
            if 'LONG' in n:return 'wow m intro long'
            if 'SHORT' in n:return 'wow m intro short'
        if 'ABORTION 07' in n:return 'abortion 07'
        if 'HYG' in n:return 'hygiene'
        if 'QY WARN' in n:return 'm qy warning'
        return None
    rules={k.casefold():v for k,v in rules.items() if isinstance(v,str)}
    lines=['KIỂM TRA CYCLE 1']
    base=cycles[0]['rows'];previous={};errors=[]
    for r in base:
        if r.get('kind')!='program':continue
        n=r['name'].upper();part=re.search(r'\bP(\d+)([AB]?)\b',n) if 'S1B' in n else re.search(r'\bS(\d+)([ABC]?)\b',n)
        if not part:continue
        key=(r['block'],'FN' if 'S1B' in n else 'SEG')
        number=(int(part[1]),part[2]);last=previous.get(key)
        if last and number<last:errors.append(f"Thứ tự phần cần xem lại: {r['name']}.")
        previous[key]=number
    lines.extend('✗ '+x for x in errors)
    if not errors:lines.append('✓ Thứ tự S/P theo tên file: không phát hiện đảo thứ tự.')
    lines += ['', 'KIỂM TRA CÁC MỤC TRONG BẢNG']
    for name,value in rules.items():
        scheduled=set(map(int,re.findall(r'\d+',value)))
        active={c['cycle'] for c in cycles}
        expected=scheduled & active
        actual={c['cycle'] for c in cycles if any(label(r)==name for r in c['rows'])}
        absent=scheduled-active
        state='✗' if actual!=expected else '⚠' if absent else '✓'
        fmt=lambda cs:', '.join(map(str,sorted(cs))) or 'không có'
        actual_text=fmt(actual)+(f' (cycle {fmt(absent)} không có)' if absent else '')
        lines.append(f'{state} {name} — quy định cycle {fmt(scheduled)}; thực tế {actual_text}.')
    lines.append(f"Chỉ kiểm tra các cycle có phát trong lịch; lịch kết thúc ở Cycle {cycles[-1]['cycle']}.")
    lines += ['', 'KHÁC BIỆT SO VỚI CYCLE 1', 'Cycle cuối có thể được rút ngắn để kết thúc ngày.']
    def comparable(c):
        rows=[r for r in c['rows'] if r.get('kind')!='marker']
        output=[]
        for i,r in enumerate(rows):
            name=label(r);expected=set(map(int,re.findall(r'\d+',rules.get(name,''))))
            if name and c['cycle'] in expected:
                # Keep position changes visible by comparing the surrounding program anchors.
                anchor=next((x for x in reversed(rows[:i]) if x.get('kind')=='program'),None)
                token=('RULE',name,r['block'],anchor['name'] if anchor else '')
                output.append((token,r,True))
            else:output.append(((r['block'],r['name']),r,False))
        return output
    reference=comparable(cycles[0])
    for c in cycles[1:]:
        other=comparable(c);lines += ['',f"Cycle {c['cycle']}"]
        # Scheduled table-only items are excluded unless the same rule moves anchors.
        common={a[0][1] for a in reference if a[2]} & {a[0][1] for a in other if a[2]}
        a=[x for x in reference if not x[2] or x[0][1] in common]
        b=[x for x in other if not x[2] or x[0][1] in common]
        def place(row):
            return {1:'WOW',2:'Show 1',3:'BMD lần 1',4:'NWN lần 1',5:'Show 2',6:'Show 3',7:'BMD lần 2',8:'NWN lần 2'}.get(row['block'],str(row['block']))
        def after(items,index):
            return 'đầu cycle' if index==0 else 'sau '+items[index-1][1]['name']
        removed=[];added=[]
        for op,i,j,k,l in SequenceMatcher(None,[x[0] for x in a],[x[0] for x in b],autojunk=False).get_opcodes():
            if op=='equal':continue
            removed.extend(range(i,j));added.extend(range(k,l))
        changes=[]
        for i in list(removed):
            old=a[i][1]
            match=next((k for k in added if b[k][1]['name']==old['name']),None)
            if match is None:continue
            new=b[match][1]
            changes.append(f"Chuyển {old['name']}: {place(old)}, {after(a,i)} → {place(new)}, {after(b,match)}.")
            removed.remove(i);added.remove(match)
        for i in list(removed):
            old=a[i][1]
            match=next((k for k in added if b[k][1]['block']==old['block']),None)
            if match is None:continue
            changes.append(f"Thay tại {place(old)}: {old['name']} → {b[match][1]['name']}.")
            removed.remove(i);added.remove(match)
        for i in removed:
            changes.append(f"Bỏ {a[i][1]['name']} — {place(a[i][1])}, {after(a,i)} ở Cycle 1.")
        for k in added:
            changes.append(f"Thêm {b[k][1]['name']} — {place(b[k][1])}, {after(b,k)}.")
        lines.extend('• '+x for x in changes)
        if not changes:lines.append('✓ Không có thay đổi khác.')
    return '\n'.join(lines)+'\n'


def reported_items_panel(parent, caption, items):
    import tkinter as tk
    from tkinter import ttk
    frame=ttk.Frame(parent)
    details=ttk.Frame(frame,padding=(22,5,8,8))
    opened=[False]
    def toggle():
        opened[0]=not opened[0]
        button.configure(text=('▼ ' if opened[0] else '▶ ')+caption)
        if opened[0]:details.pack(fill='x')
        else:details.pack_forget()
    button=tk.Button(frame,text='▶ '+caption,command=toggle,anchor='w',justify='left',
                     wraplength=800,relief='flat',borderwidth=0,foreground='#8A6500',
                     background='white',activebackground='#FFF4BF',font=('Segoe UI',11),cursor='hand2')
    button.pack(fill='x')
    for item in items:
        seconds=round(float(item['seconds']))
        duration=f'{seconds//60:02}:{seconds%60:02}'
        ttk.Label(details,text=f"• {item['name']} — {duration}"+(" — "+item["note"] if item.get("note") else ""),wraplength=780,justify='left').pack(anchor='w',pady=2)
    if not items:ttk.Label(details,text='Tạo lại lịch để cập nhật danh sách chi tiết.').pack(anchor='w')
    return frame


def combine_temporary_notices(reported_items, rows, missing):
    items={item['name']:dict(item) for item in reported_items}
    for row in rows:
        if row.get('draft_no_next'):
            items[row['name']]={'name':row['name'],'seconds':row['duration'],
                                'note':'No NXT tạm — lấy thời lượng từ bản thường'}
    issues=[text for text in missing if not text.startswith(('Bản nháp:','Bản No NXT nháp'))]
    if items:
        issues.append(f'Bản nháp: {len(items)} mục dùng thời lượng tạm; cần quét lại khi có file chính thức.')
    return list(items.values()),issues
