"""Resolve optional portable paths without changing the installed layout."""
import json
import os
import subprocess
from pathlib import Path
BASE = Path(__file__).resolve().parent
PACKAGE_ROOT = BASE.parents[2]
SETTINGS_FILE = BASE / 'portable_settings.json'
if not SETTINGS_FILE.is_file(): SETTINGS_FILE = PACKAGE_ROOT / 'portable_settings.json'
PORTABLE = SETTINGS_FILE.is_file()
SETTINGS = json.loads(SETTINGS_FILE.read_text('utf-8-sig')) if PORTABLE else {}
LOCAL_ROOT = PACKAGE_ROOT if PORTABLE else Path(r'D:\SMTV_LIVE')
EXPORT_ROOT = Path(SETTINGS.get('export_root', r'W:\@ SHOW EXPORTS'))
ADS_ROOT = LOCAL_ROOT / '@ ADS 2'
MARKER_ROOT = LOCAL_ROOT / 'EP List mp4 samples' / 'cycle placeholders'
WORKBOOK_PATH = (PACKAGE_ROOT / 'INPUT.xlsx' if (PACKAGE_ROOT / 'INPUT.xlsx').is_file() else BASE / 'INPUT.xlsx') if PORTABLE else BASE / 'SMTV_Schedule_Input.xlsx'
ADS_CATALOG_PATH = BASE / 'ADS_CATALOG.xlsx'

def local_path(value):
    text = str(value).replace('/', '\\')
    legacy = 'D:\\SMTV_LIVE\\'
    if PORTABLE and text.casefold().startswith(legacy.casefold()):
        return LOCAL_ROOT / Path(text[len(legacy):])
    return Path(value)

def open_spreadsheet(path):
    os.startfile(str(path))
