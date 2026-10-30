"""Resolve approved ADS paths and measure real files, never fuzzy-select for airing."""
import json
import re
import subprocess
import zipfile
from pathlib import Path
from import_sources import read_shared_strings, read_sheet, sheet_targets

from portable_paths import ADS_ROOT, local_path
BASE = Path(__file__).resolve().parent

def key(text):
    text = re.sub(r'\.mp4$', '', text, flags=re.I)
    text = re.sub(r'[\[(]\s*\d+:\d+(?::\d+)?\s*[\])]', '', text)
    return re.sub(r'[^\w]+', ' ', text.casefold()).strip()

def filename_key(text):
    """Formatting-only equivalence; keep content, numbers and edition labels."""
    text=key(text).replace('_',' ')
    text=re.sub(r'^(?:(?:new|ad|ads)\s+)+','',text)
    text=re.sub(r'\s+v\d+$','',text)
    return ' '.join(text.split())

class Assets:
    def __init__(self, config):
        self.local = Path(config['local_dir'])
        self.files = [p for p in ADS_ROOT.rglob('*.mp4') if 'old' not in [s.lower() for s in p.parts]]
        self.files += list(self.local.glob('*.mp4'))
        self.mapping = {}
        self.ad_profile = {}
        profile_path = BASE / 'configs' / f"EP_{config['episode']}_ads_rules.json"
        if profile_path.exists():
            self.ad_profile = json.loads(profile_path.read_text('utf-8'))
            if self.ad_profile.get('episode') != config['episode']:
                raise ValueError('ADS profile khác EP đang làm')
        self.cache_path = BASE / 'duration_cache.json'
        try:
            self.cache = json.loads(self.cache_path.read_text('utf-8'))
        except (OSError, ValueError):
            self.cache = {}
        catalog = BASE / 'ADS_CATALOG.xlsx'
        if catalog.exists():
            with zipfile.ZipFile(catalog) as z:
                rows = read_sheet(z, sheet_targets(z)['ADS Mapping'], read_shared_strings(z))
            for row in rows[4:]:
                row = list(row) + [''] * 8
                if str(row[7]).upper() not in ('YES', 'OK', 'X', 'Y'):
                    continue
                name, actual, folder, path = (str(x).strip() for x in row[:4])
                p = local_path(path) if path else ADS_ROOT / folder / actual
                # An edited filename takes precedence over a stale full path.
                if actual and p.name != actual:
                    p = p.parent / actual
                self.mapping.setdefault(key(name), set()).add(p)
        # Explicitly confirmed names supplement the editable catalog across episodes.
        approved_path = BASE / 'approved_ads.json'
        if approved_path.exists():
            for item in json.loads(approved_path.read_text('utf-8')).get('items', []):
                if item.get('user_selected'):
                    self.mapping[key(item['name'])]={local_path(item['path'])}
                else:
                    self.mapping.setdefault(key(item['name']), {local_path(item['path'])})
        # User-approved catalog edits take precedence over learned episode aliases.
        for item in self.ad_profile.get('items', []):
            self.mapping.setdefault(key(item['name']), {local_path(item['path'])})
        for name,path in self.ad_profile.get('aliases',{}).items():
            self.mapping.setdefault(key(name),{local_path(path)})

    def resolve(self, name):
        aliases = {'m qy warning': 'M QY Warn', 'hygiene': 'Gen Hyg Notes',
                   'abortion 07': 'AD_Abortion 07 Crime'}
        k = key(name)
        paths = self.mapping.get(k)
        if paths is not None:
            return next(iter(paths)) if len(paths) == 1 and next(iter(paths)).is_file() else None
        k = key(aliases.get(k, name))
        hits = [p for p in self.files if key(p.name) == k]
        local_hits = [p for p in hits if p.parent == self.local]
        hits = local_hits or hits
        if hits:return hits[0] if len(hits) == 1 else None
        normalized=filename_key(aliases.get(k,name))
        # A confirmed alias also survives harmless prefix/spacing changes.
        mapped=[paths for alias,paths in self.mapping.items() if filename_key(alias)==normalized]
        if mapped:
            paths=set().union(*mapped)
            return next(iter(paths)) if len(paths)==1 and next(iter(paths)).is_file() else None
        hits=[p for p in self.files if filename_key(p.name)==normalized
              and not re.search(r'need[ _]*fix|do[ _]*not[ _]*air|not[ _]*air',str(p),re.I)]
        # Multiple versions or folders remain a user choice, never a guess.
        return hits[0] if len(hits)==1 else None

    def duration(self, path):
        path = Path(path)
        stat = path.stat()
        signature = [stat.st_size, stat.st_mtime_ns]
        old = self.cache.get(str(path), {})
        if old.get('signature') == signature:
            return old['duration']
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                 '-of', 'default=nw=1:nk=1', str(path)],
                                capture_output=True, text=True, check=True, creationflags=flags)
        seconds = float(result.stdout.strip())
        if seconds <= 0:
            raise ValueError(f'Thời lượng không hợp lệ: {path}')
        self.cache[str(path)] = {'signature': signature, 'duration': seconds}
        return seconds

    def save(self):
        self.cache_path.write_text(json.dumps(self.cache), 'utf-8')
