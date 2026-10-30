"""Download verified program updates; apply after Scheduler closes, with rollback."""
import hashlib,json,os,shutil,subprocess,sys,time,urllib.request,uuid
from pathlib import Path,PurePosixPath
ROOT_URL='https://raw.githubusercontent.com/felicialovelove1257-droid/TV-Scheduler/main/'
PREFIX='schedule/pipeline/_NOI_BO/'
MAX_FILE=32*1024*1024

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def valid_path(name):
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:return False
    if name in ('INPUT.xlsx','SCHEDULER.cmd'):return True
    if not name.startswith(PREFIX) or '/' in name[len(PREFIX):]:return False
    leaf=name[len(PREFIX):]
    return leaf.endswith('.py') or leaf in ('english_translations.json','runtime_env.cmd')

def fetch(url,limit):
    request=urllib.request.Request(url,headers={'User-Agent':'SMTV-Scheduler-Updater','Cache-Control':'no-cache'})
    with urllib.request.urlopen(request,timeout=45) as response:
        data=response.read(limit+1)
    if len(data)>limit:raise ValueError('Update download exceeds allowed size.')
    return data

def inspect(root):
    manifest=json.loads(fetch(ROOT_URL+'update_manifest.json?check='+str(time.time_ns()),2*1024*1024))
    if manifest.get('schema')!=1:raise ValueError('Unsupported update manifest.')
    files=manifest.get('files',[])
    if not files or len(files)>250:raise ValueError('Invalid update file list.')
    seen=set();changed=[]
    for item in files:
        name=item['path']
        if not valid_path(name) or name.casefold() in seen:raise ValueError('Unsafe or duplicate update path: '+name)
        seen.add(name.casefold())
        if not isinstance(item['size'],int) or not 0<item['size']<=MAX_FILE:raise ValueError('Invalid update file size.')
        if len(item['sha256'])!=64 or any(c not in '0123456789abcdef' for c in item['sha256']):raise ValueError('Invalid update checksum.')
        target=Path(root)/name
        if not target.is_file() or digest(target)!=item['sha256']:changed.append(item)
    return manifest,changed

def stage(root,manifest,files):
    base=Path(root)/PREFIX;folder=base/'updates'/('pending-'+uuid.uuid4().hex);folder.mkdir(parents=True)
    try:
        for item in files:
            data=fetch(ROOT_URL+'payload/'+item['path'],item['size'])
            if len(data)!=item['size'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Update changed or checksum mismatch. Check again: '+item['path'])
            path=folder/'payload'/item['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        request={'root':str(Path(root).resolve()),'build':manifest['build'],'files':files,'parent_pid':os.getpid()}
        (folder/'request.json').write_text(json.dumps(request,indent=2),'utf-8')
        shutil.copy2(Path(__file__),folder/'apply_update.py')
        return folder
    except Exception:
        # Leave any failed download for diagnosis; never apply partial payloads.
        raise

def safe_target(root,name):
    if not valid_path(name):raise ValueError('Protected update path: '+name)
    target=(root/name).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('Update path escaped installation.')
    return target

def apply(folder):
    folder=Path(folder);request=json.loads((folder/'request.json').read_text('utf-8'))
    root=Path(request['root']).resolve();files=request['files']
    if len({i['path'].casefold() for i in files})!=len(files):raise ValueError('Duplicate update files.')
    for item in files:
        safe_target(root,item['path'])
        staged=folder/'payload'/item['path']
        if staged.stat().st_size!=item['size'] or digest(staged)!=item['sha256']:raise ValueError('Staged update failed validation.')
    backup=root/PREFIX/'updates'/'backups'/folder.name
    backup.mkdir(parents=True,exist_ok=False);journal=[]
    try:
        for item in files:
            name=item['path'];target=safe_target(root,name);existed=target.exists()
            if existed:
                saved=backup/name;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
            journal.append((name,existed))
            target.parent.mkdir(parents=True,exist_ok=True)
            temp=target.with_name(target.name+'.updating');shutil.copy2(folder/'payload'/name,temp);os.replace(temp,target)
        (backup/'journal.json').write_text(json.dumps({'build':request['build'],'files':journal},indent=2),'utf-8')
        (root/PREFIX/'installed_update.json').write_text(json.dumps({'build':request['build'],'backup':str(backup)}),'utf-8')
    except Exception as exc:
        failures=[]
        for name,existed in reversed(journal):
            try:
                target=safe_target(root,name)
                if existed:shutil.copy2(backup/name,target)
                elif target.exists():target.unlink()
            except Exception as rollback:failures.append(str(rollback))
        if failures:raise RuntimeError(str(exc)+'; rollback needs attention: '+'; '.join(failures)+'; backup: '+str(backup)) from exc
        raise
    return backup

def launch(folder):
    base=Path(__file__).resolve().parent
    subprocess.Popen([str(base/'runtime/python/pythonw.exe'),str(folder/'apply_update.py'),str(folder)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),cwd=str(folder))

def main(folder):
    import ctypes
    request=json.loads((Path(folder)/'request.json').read_text('utf-8'))
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x00100000,False,int(request['parent_pid']))
    if handle:
        result=kernel.WaitForSingleObject(handle,120000);kernel.CloseHandle(handle)
        if result!=0:raise RuntimeError('Scheduler did not close; no files were changed.')
    backup=apply(folder)
    root=Path(request['root']);base=root/PREFIX
    ctypes.windll.user32.MessageBoxW(None,'Update completed. Backup saved at:\n'+str(backup),'Update PIP',0)
    os.startfile(str(root/'SCHEDULER.cmd'))

if __name__=='__main__':
    try:main(sys.argv[1])
    except Exception as exc:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,str(exc),'Update PIP failed',0x10)
