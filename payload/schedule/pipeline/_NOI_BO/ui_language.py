"""Local UI preference; adding a language does not require another scheduler."""
import json
from pathlib import Path

LANGUAGES={'vi':'Tiếng Việt','en':'English'}
PREFERENCE=Path(__file__).resolve().parent/'configs'/'ui_language.json'

def get_language():
    try:
        value=json.loads(PREFERENCE.read_text('utf-8')).get('language','en')
        return value if value in LANGUAGES else 'en'
    except (OSError,ValueError,TypeError):return 'en'

def save_language(code):
    if code not in LANGUAGES:raise ValueError('Unsupported language: '+str(code))
    PREFERENCE.parent.mkdir(parents=True,exist_ok=True)
    temporary=PREFERENCE.with_suffix('.tmp')
    temporary.write_text(json.dumps({'language':code}),encoding='utf-8')
    temporary.replace(PREFERENCE)

def add_selector(parent):
    import tkinter as tk
    from tkinter import ttk
    frame=ttk.Frame(parent);frame.pack(fill='x',pady=(10,0))
    ttk.Label(frame,text='Language / Ngôn ngữ').pack(anchor='w')
    value=tk.StringVar(value=LANGUAGES[get_language()])
    selector=ttk.Combobox(frame,textvariable=value,values=list(LANGUAGES.values()),state='readonly',width=18)
    selector.pack(fill='x',pady=4)
    note=ttk.Label(frame,text='Applies next launch / Mở lại để áp dụng',wraplength=170,foreground='#666666')
    note.pack(anchor='w')
    def changed(_=None):
        code=next(k for k,v in LANGUAGES.items() if v==value.get())
        try:save_language(code)
        except OSError as exc:
            from tkinter import messagebox
            messagebox.showerror('Language',str(exc),parent=frame);return
        note.configure(text='Saved — reopen SCHEDULER' if code=='en' else 'Đã nhớ — mở lại SCHEDULER')
    selector.bind('<<ComboboxSelected>>',changed)
    return frame
