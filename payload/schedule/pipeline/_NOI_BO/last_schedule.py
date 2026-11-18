"""Local per-episode result snapshots. Loading never schedules or probes media."""
import json
from datetime import datetime
from pathlib import Path


def save(directory, config, schedule, report, detail):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    ep=int(config['episode'])
    payload=dict(version=1,episode=ep,saved_at=datetime.now().isoformat(timespec='seconds'),
                 config=config,schedule=schedule,report=report,detail=detail)
    path=directory/f'EP_{ep}_last_result.json'
    def convert(value):
        if isinstance(value,Path):return str(value)
        if isinstance(value,set):return list(value)
        raise TypeError(type(value).__name__)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload,ensure_ascii=False,default=convert),encoding='utf-8')
    temp.replace(path)
    return payload


def load(directory, episode):
    try:
        ep=int(episode)
        data=json.loads((Path(directory)/f'EP_{ep}_last_result.json').read_text('utf-8'))
        if data['version']!=1 or data['episode']!=ep or int(data['config']['episode'])!=ep:return None
        if not isinstance(data['schedule']['cycles'],list):return None
        if not all(k in data for k in ('report','detail','saved_at')):return None
        return data
    except (OSError,ValueError,KeyError,TypeError):return None


def latest_episode(directory, fallback):
    paths=sorted(Path(directory).glob('EP_*_last_result.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    for path in paths:
        ep=path.name.split('_')[1]
        if load(directory,ep):return ep
    return str(fallback)
