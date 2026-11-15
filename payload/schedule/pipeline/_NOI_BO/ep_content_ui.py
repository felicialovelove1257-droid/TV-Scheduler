"""Per-EP editable content table; imported rows start locked."""
import copy
import uuid
from pathlib import Path
from ep_content import catalog,load,save,validate,apply,KINDS,KIND_LABELS

def open_editor(root,config):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    config_original=config
    config=copy.deepcopy(config)
    rows=catalog(config);accepted=[False];pasted=[False]
    window=tk.Toplevel(root);window.title(f"EP {config['episode']} — Nội dung / thời lượng");window.geometry('1150x700')
    window.transient(root);window.grab_set()
    ttk.Label(window,text='Mục gốc khóa mặc định. Mở khóa để sửa. Khóa chỉ ngăn chỉnh sửa, không khóa vị trí phát.',padding=10).pack(anchor='w')
    frame=ttk.Frame(window);frame.pack(fill='both',expand=True,padx=10)
    table=ttk.Treeview(frame,columns=('lock','kind','label','source','position'),show='headings',selectmode='browse')
    for key,title,width in [('lock','Khóa',65),('kind','Loại',95),('label','Chương trình / part',210),('source','File / thời lượng',420),('position','Vị trí',220)]:
        table.heading(key,text=title);table.column(key,width=width,stretch=key in ('label','source','position'))
    scroll=ttk.Scrollbar(frame,orient='vertical',command=table.yview);table.configure(yscrollcommand=scroll.set)
    horizontal=ttk.Scrollbar(frame,orient='horizontal',command=table.xview);table.configure(xscrollcommand=horizontal.set)
    horizontal.pack(side='bottom',fill='x');scroll.pack(side='right',fill='y');table.pack(fill='both',expand=True)
    status=tk.StringVar(value='Các thay đổi chỉ lưu cho EP đang mở.')
    ttk.Label(window,textvariable=status,padding=8).pack(anchor='w')
    def refresh(select=None):
        table.delete(*table.get_children())
        for r in rows:
            source=r.get('source') or (r.get('duration')+' — temp' if r.get('duration') else 'Chưa có file / thời lượng')
            pos=(str(r.get('block'))+' / '+r.get('side','')+' '+r.get('anchor','')) if r.get('custom') or r.get('position_override') else 'Theo quy tắc hiện tại'
            table.insert('', 'end',iid=r['id'],values=('🔒' if r.get('locked',True) else '🔓',KIND_LABELS[r['kind']],r['label'],source,pos))
        if select and table.exists(select):table.selection_set(select);table.see(select)
    def selected():
        selection=table.selection()
        return next((r for r in rows if selection and r['id']==selection[0]),None)
    def toggle():
        r=selected()
        if not r:return
        r['locked']=not r.get('locked',True);refresh(r['id'])
    def restore():
        r=selected()
        if not r:return
        if r.get('locked',True):messagebox.showinfo('Mở khóa','Mở khóa mục này trước khi khôi phục.',parent=window);return
        # Catalog defaults are reconstructed without changing saved files yet.
        import ep_content
        old=ep_content.load
        try:
            ep_content.load=lambda ep:{'rows':[]}
            original=next((x for x in ep_content.catalog(config) if x['id']==r['id']),None)
        finally:ep_content.load=old
        rows.remove(r)
        if original:rows.append(original)
        refresh(original['id'] if original else None)
    def remove():
        r=selected()
        if not r:return
        if r.get('locked',True):messagebox.showinfo('Mở khóa','Mở khóa mục này trước khi xóa.',parent=window);return
        if not r['id'].startswith('custom:'):
            messagebox.showinfo('Mục gốc','Dùng Khôi phục mặc định cho mục gốc. Dùng Files / Skip để bỏ qua ADS hoặc TSER.',parent=window);return
        rows.remove(r);refresh()
    def edit(new=False):
        original=None if new else selected()
        if not new and not original:return
        if original and original.get('locked',True):
            messagebox.showinfo('Mục đang khóa','Bấm Mở / Khóa để mở khóa mục này trước.',parent=window);return
        r=copy.deepcopy(original) if original else dict(id='custom:'+uuid.uuid4().hex,custom=True,locked=False,edited=True,label='',kind='Show',source='',duration='',block='',anchor='',side='after',cycles='1,2,3,4,5,6')
        dialog=tk.Toplevel(window);dialog.title('Thêm / sửa nội dung');dialog.geometry('820x510');dialog.transient(window);dialog.grab_set()
        fields={}
        labels=[('kind','Loại nội dung'),('label','Chương trình / part (ví dụ AP PARTD)'),('source','File nguồn'),('duration','Thời lượng nếu chưa có file (phút:giây)'),('block','Block / show trong cycle'),('anchor','Mục làm mốc'),('side','Vị trí so với mốc'),('cycles','Cycle áp dụng')]
        for index,(key,title) in enumerate(labels):
            ttk.Label(dialog,text=title).grid(row=index,column=0,sticky='w',padx=10,pady=8)
            var=tk.StringVar(value=KIND_LABELS[r['kind']] if key=='kind' else str(r.get(key,'')));fields[key]=var
            options={'kind':tuple(KIND_LABELS.values()),'block':tuple(str(i) for i in range(1,9)),'side':('before','after')}
            if key in options:widget=ttk.Combobox(dialog,textvariable=var,values=options[key],state='readonly')
            elif key=='anchor':
                anchors=list(dict.fromkeys([i['target_name'] for i in config['rename_preview']['items']]+[x.get('base','') for x in rows if x.get('base')]))
                widget=ttk.Combobox(dialog,textvariable=var,values=anchors,state='readonly')
            else:widget=ttk.Entry(dialog,textvariable=var)
            widget.grid(row=index,column=1,sticky='ew',padx=8)
        dialog.columnconfigure(1,weight=1)
        def browse():
            path=filedialog.askopenfilename(parent=dialog,title='Chọn file',filetypes=[('Media','*.mp4 *.mov *.mxf *.mkv *.avi *.wav *.mp3'),('All files','*.*')])
            if path:fields['source'].set(path)
        ttk.Button(dialog,text='Chọn file…',command=browse).grid(row=2,column=2,padx=8)
        ttk.Button(dialog,text='Dùng thời lượng',command=lambda:fields['source'].set('')).grid(row=3,column=2,padx=8)
        auto=tk.BooleanVar(value=bool(new or r.get('native_key')))
        ttk.Checkbutton(dialog,text='Part chuẩn của chương trình hiện có: tự nhận vị trí (ví dụ AP PARTD, WOW MAIN)',variable=auto).grid(row=8,column=0,columnspan=3,sticky='w',padx=10,pady=8)
        ttk.Label(dialog,text='Block: 1 AP/WOW; 2 Show 1; 3/7 BMD; 4/8 NWN; 5 Show 2; 6 Show 3.\nMục tùy ý cần chọn mốc trước/sau. File được chọn sẽ dùng thời lượng thực tế.',wraplength=780).grid(row=9,column=0,columnspan=3,sticky='w',padx=10)
        def commit():
            try:
                updated=dict(r,**{k:v.get().strip() for k,v in fields.items()},edited=True)
                updated['kind']=next(k for k,v in KIND_LABELS.items() if v==updated['kind'])
                if original and (updated['kind']!=original['kind'] or updated['label']!=original['label'] or updated['anchor'] or updated['cycles']!='1,2,3,4,5,6'):
                    updated['position_override']=True
                if auto.get():
                    from draft_input import expected
                    import re
                    key=updated['label'].upper()
                    known={s.upper():s for s in expected(config)}
                    if re.fullmatch(r'AP PART[A-Z]',key):known[key]=key
                    if key not in known:raise ValueError('Part này chưa có quy tắc tự nhận. Bỏ chọn tự nhận và chọn block + mốc trước/sau.')
                    if updated['kind']!=('TSER' if key.startswith('TSER ') else 'Show'):raise ValueError('Loại nội dung không khớp part chuẩn.')
                    if updated['cycles']!='1,2,3,4,5,6':raise ValueError('Cycle riêng cần bỏ tự nhận và chọn vị trí.')
                    updated.update(native_key=known[key],custom=False,position_override=False)
                validate(updated,config,probe=True)
                if original:rows[rows.index(original)]=updated
                else:rows.append(updated)
                refresh(updated['id']);dialog.destroy();window.grab_set()
            except Exception as exc:messagebox.showerror('Nội dung EP',str(exc),parent=dialog)
        ttk.Button(dialog,text='Áp dụng dòng',command=commit).grid(row=10,column=1,sticky='e',pady=12)
        ttk.Button(dialog,text='Hủy',command=dialog.destroy).grid(row=10,column=2,padx=8)
        window.wait_window(dialog);window.grab_set()
    def finish():
        try:
            for r in rows:validate(r,config)
            # Validate materialization against a copy before making the settings durable.
            import ep_content
            staged=[r for r in rows if r.get('edited') or not r.get('locked',True)]
            trial=copy.deepcopy(config);old=ep_content.load
            try:
                ep_content.load=lambda ep:{'rows':staged}
                apply(trial)
            finally:ep_content.load=old
            targets={e['id']:e['target_name'] for e in trial.get('manual_content',[])}
            staged=[dict(r,target_name=targets[r['id']]) if r['id'] in targets else r for r in staged]
            save(config['episode'],staged)
            apply(trial)
            if pasted[0]:
                from draft_input import storage
                from missing_media import atomic_json
                atomic_json(storage(trial),trial.get('reported_durations',{}))
            config_original.clear();config_original.update(trial)
            accepted[0]=True;window.destroy()
        except Exception as exc:messagebox.showerror('Nội dung EP',str(exc),parent=window)
    def paste_durations():
        from draft_input import open_duration_editor
        before={r['id']:r for r in rows}
        trial=copy.deepcopy(config)
        trial['rename_preview']['items']=copy.deepcopy(config.get('_content_defaults',config['rename_preview']['items']))
        if open_duration_editor(window,trial,persist=False):
            pasted[0]=True
            trial['_content_defaults']=copy.deepcopy(trial['rename_preview']['items'])
            config.clear();config.update(trial)
            updated=catalog(config)
            for i,r in enumerate(updated):
                if r['id'] in before and (before[r['id']].get('edited') or not before[r['id']].get('locked',True)):
                    updated[i]=before.pop(r['id'])
            ids={r['id'] for r in updated}
            updated.extend(r for r in before.values() if r['id'] not in ids and r.get('custom'))
            rows[:]=updated;refresh()
        window.grab_set()
    buttons=ttk.Frame(window,padding=10);buttons.pack(fill='x')
    from pip_help import help_button
    help_button(buttons,'content')
    for label,command in [('＋ Thêm mục / part',lambda:edit(True)),('Mở / Khóa',toggle),('Sửa',edit),('Khôi phục mặc định',restore),('Xóa mục thêm',remove)]:
        ttk.Button(buttons,text=label,command=command).pack(side='left',padx=3)
    ttk.Button(buttons,text='Lưu theo EP',command=finish).pack(side='right',padx=3)
    ttk.Button(buttons,text='Hủy',command=window.destroy).pack(side='right',padx=3)
    ttk.Button(window,text='Dán thời lượng / Chia FN…',command=paste_durations).pack(anchor='w',padx=12,pady=(0,8))
    table.bind('<Double-1>',lambda e:edit())
    refresh();root.wait_window(window)
    return accepted[0]
