"""Copy selected original media under approved local names."""
from pathlib import Path
import os
import json
import hashlib
import shutil
import tempfile
import time


class PreparationStopped(Exception):
    pass


def check_stop(cancel):
    if cancel is not None and cancel.is_set():raise PreparationStopped('Đã dừng theo yêu cầu.')


def copy_with_stop(source,target,cancel,progress=None):
    size=source.stat().st_size;done=0;last=time.monotonic();started=last
    with source.open('rb') as reader,Path(target).open('wb') as writer:
        while True:
            check_stop(cancel)
            block=reader.read(4*1024*1024)
            check_stop(cancel)
            if not block:break
            writer.write(block);done+=len(block)
            now=time.monotonic()
            if progress and now-last>=0.5:
                progress(f'{source.name} — {done/max(1,size):.0%} ({done/1048576/max(0.001,now-started):.1f} MB/s)')
                last=now
    check_stop(cancel)
    shutil.copystat(source,target)


def stamp(path):
    stat=path.stat()
    return stat.st_size,stat.st_mtime_ns


def wait_stable(paths,progress=None,cancel=None):
    snapshots={};errors={}
    for path in paths:
        try:
            snapshots[path]=stamp(path)
            if snapshots[path][0]<=0:raise RuntimeError('File còn trống.')
        except Exception as exc:errors[path]=str(exc)
    for check in range(1):
        if not snapshots:return snapshots,errors
        if progress:progress(0,len(paths),'Kiểm tra cả danh sách — chờ 5 giây')
        if cancel is None:time.sleep(5)
        elif cancel.wait(5):raise PreparationStopped('Đã dừng theo yêu cầu.')
        for path,initial in list(snapshots.items()):
            if path in errors:continue
            try:
                if stamp(path)!=initial:raise RuntimeError('File đang tải lên hoặc còn thay đổi.')
            except Exception as exc:errors[path]=str(exc)
    return snapshots,errors


def preparation_history_path(destination):
    destination=Path(destination).resolve()
    token=hashlib.sha256(str(destination).casefold().encode('utf-8')).hexdigest()[:16]
    return Path(__file__).resolve().parent/'configs'/'prepare_history'/f'{destination.parent.name}_{token}.json'


def copy_prepared_files(rows, destination, progress=None, cancel=None, mode='prepare', history_path=None):
    if mode not in ('prepare', 'update'): raise ValueError('Invalid preparation mode')
    destination=Path(destination).resolve()
    history_path=Path(history_path) if history_path is not None else preparation_history_path(destination)
    history=json.loads(history_path.read_text('utf-8')) if history_path.exists() else {'version':1,'files':{}}
    if history.get('version')!=1 or not isinstance(history.get('files'),dict):
        raise ValueError('Invalid preparation history; keep the file for recovery.')
    records=history['files']
    def key(source,target):return source.name.casefold()+'|'+target.name.casefold()
    def remember(source,target,signature):
        records[key(source,target)]={'source':source.name,'target':target.name,
                                    'size':signature[0],'mtime_ns':signature[1],'completed_at':time.time()}
        history_path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.pip_history_',suffix='.partial',dir=history_path.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as handle:
                json.dump(history,handle,ensure_ascii=False,indent=2)
            os.replace(temp,history_path)
        finally:
            if Path(temp).exists():Path(temp).unlink()
    planned=[];seen=set();details=[];copied=kept=0;stopped=False
    for row in rows:
        source=Path(row['source_path']);name=row['target_name']
        try:
            check_stop(cancel)
            if Path(name).name!=name or '/' in name or chr(92) in name:
                raise ValueError('Tên đích không hợp lệ.')
            target=destination/name
            if name.casefold() in seen:raise ValueError('Tên đích bị trùng.')
            seen.add(name.casefold())
            if source.resolve()==target:raise ValueError('Nguồn và đích cùng một file.')
            if mode=='prepare' and target.exists():
                kept+=1
                # Existing identical copies can seed history; never certify a different source.
                signature=stamp(source)
                if stamp(target)==signature:remember(source,target,signature)
                details.append(dict(source=str(source),target=name,status='kept'))
                continue
            signature=stamp(source)
            old=records.get(key(source,target),{})
            if mode=='update' and (old.get('size'),old.get('mtime_ns'))==signature:
                kept+=1
                details.append(dict(source=str(source),target=name,status='recorded'))
                continue
            planned.append((source,target))
        except PreparationStopped:
            stopped=True;break
        except Exception as exc:
            details.append(dict(source=str(source),target=name,status='skipped',reason=str(exc)))
    try:
        check_stop(cancel)
        snapshots,errors=wait_stable(list(dict.fromkeys(source for source,_ in planned)),progress,cancel) if planned else ({},{})
    except PreparationStopped:
        stopped=True
        details.extend(dict(source=str(source),target=target.name,status='cancelled') for source,target in planned)
        planned=[];snapshots={};errors={}
    if planned:destination.mkdir(parents=True,exist_ok=True)
    for index,(source,target) in enumerate(planned,1):
        temporary=None
        try:
            check_stop(cancel)
            if source in errors:raise RuntimeError(errors[source])
            if stamp(source)!=snapshots[source]:raise RuntimeError('File nguồn còn thay đổi.')
            signature=snapshots[source]
            if progress:progress(index,len(planned),target.name)
            if mode=='prepare' and target.exists():
                kept+=1
                if stamp(target)==signature:remember(source,target,signature)
                details.append(dict(source=str(source),target=target.name,status='kept'))
                continue
            fd,temporary=tempfile.mkstemp(prefix='.copy_',suffix='.partial',dir=destination)
            os.close(fd)
            copy_with_stop(source,temporary,cancel,lambda text:progress(index,len(planned),text) if progress else None)
            if stamp(source)!=signature:raise RuntimeError('Nguồn thay đổi trong lúc copy.')
            if Path(temporary).stat().st_size!=signature[0]:raise RuntimeError('Copy chưa đủ dung lượng.')
            check_stop(cancel)
            os.replace(temporary,target);copied+=1
            remember(source,target,signature)
            details.append(dict(source=str(source),target=target.name,status='copied'))
        except PreparationStopped:
            stopped=True
            details.extend(dict(source=str(p),target=t.name,status='cancelled') for p,t in planned[index-1:])
            break
        except Exception as exc:
            details.append(dict(source=str(source),target=target.name,status='skipped',reason=str(exc)))
        finally:
            if temporary and Path(temporary).exists():
                try:Path(temporary).unlink()
                except OSError:pass
    skipped=[row for row in details if row['status']=='skipped']
    return dict(copied=copied,kept=kept,skipped=skipped,details=details,total=len(rows),destination=str(destination),stopped=stopped,mode=mode,history=str(history_path))
