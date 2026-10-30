"""Small update dialog; INPUT is optional and always backed up by the updater."""
def show_update(root):
    import tkinter as tk
    from tkinter import ttk,messagebox
    import threading,queue
    from portable_paths import PACKAGE_ROOT
    import pip_updater as updater
    old=getattr(root,'_pip_update_window',None)
    if old is not None and old.winfo_exists():old.lift();return
    window=tk.Toplevel(root);root._pip_update_window=window
    window.title('Update PIP');window.geometry('680x460');window.transient(root);window.grab_set()
    ttk.Label(window,text='TV-Scheduler · program updates from GitHub',font=('Segoe UI',12,'bold')).pack(anchor='w',padx=16,pady=12)
    status=tk.StringVar(value='Checking for updates...');ttk.Label(window,textvariable=status,wraplength=640).pack(fill='x',padx=16)
    text=tk.Text(window,height=14,wrap='word',state='disabled');text.pack(fill='both',expand=True,padx=16,pady=10)
    include=tk.BooleanVar(value=False)
    check=ttk.Checkbutton(window,text='Also replace INPUT.xlsx (current INPUT will be backed up)',variable=include,state='disabled');check.pack(anchor='w',padx=16)
    ttk.Label(window,text='ADS, EP files, playlists, settings and recognition history are kept.').pack(anchor='w',padx=16,pady=8)
    bar=ttk.Frame(window);bar.pack(fill='x',padx=16,pady=12)
    state={'busy':True};messages=queue.Queue()
    def close():
        if not state['busy']:window.destroy()
    close_btn=ttk.Button(bar,text='Close',command=close);close_btn.pack(side='right')
    def start(work,done):
        def run():
            try:messages.put((True,work()))
            except Exception as exc:messages.put((False,str(exc)))
        def poll():
            try:ok,value=messages.get_nowait()
            except queue.Empty:window.after(100,poll);return
            state['busy']=False
            if ok:done(value)
            else:status.set('Could not update: '+value);apply_btn.configure(state='disabled')
        threading.Thread(target=run,daemon=True).start();window.after(100,poll)
    def apply_changes():
        files=[f for f in state['files'] if f['path']!='INPUT.xlsx' or include.get()]
        if not files:messagebox.showinfo('Update PIP','No program changes. Select INPUT if you want to update it.',parent=window);return
        state['busy']=True;apply_btn.configure(state='disabled');check.configure(state='disabled')
        status.set('Downloading changed files and checking SHA-256. Scheduler will restart after installation.')
        def ready(folder):
            try:updater.launch(folder)
            except Exception as exc:status.set('Could not start installer: '+str(exc));return
            root.destroy()
        start(lambda:updater.stage(PACKAGE_ROOT,state['manifest'],files),ready)
    apply_btn=ttk.Button(bar,text='Update and restart',command=apply_changes,state='disabled');apply_btn.pack(side='right',padx=8)
    def checked(result):
        manifest,files=result;state.update(manifest=manifest,files=files)
        status.set('Build '+str(manifest['build'])+' — '+str(len(files))+' changed files' if files else 'You already have the latest program and INPUT.')
        text.configure(state='normal');text.insert('end','\n'.join(f['path'] for f in files));text.configure(state='disabled')
        if any(f['path']=='INPUT.xlsx' for f in files):check.configure(state='normal')
        if files:apply_btn.configure(state='normal')
    window.protocol('WM_DELETE_WINDOW',close)
    start(lambda:updater.inspect(PACKAGE_ROOT),checked)
