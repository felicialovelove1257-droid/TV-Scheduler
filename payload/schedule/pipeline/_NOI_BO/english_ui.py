"""English launcher for the shared PIP sources; scheduling code stays in one place.

Translate text literals in memory on import. No translated source copies or
shared .pyc files are written. Regex/report phrases use the same dictionary.
"""
import ast
import importlib.abc
import importlib.util
import json
import os
import sys
from pathlib import Path

BASE=Path(__file__).resolve().parent
TRANSLATIONS=json.loads((BASE/'english_translations.json').read_text('utf-8'))

class TranslateStrings(ast.NodeTransformer):
    def visit_Constant(self,node):
        if isinstance(node.value,str) and node.value in TRANSLATIONS:
            return ast.copy_location(ast.Constant(value=TRANSLATIONS[node.value]),node)
        return node

class EnglishLoader(importlib.abc.Loader):
    def __init__(self,path):self.path=path
    def create_module(self,spec):return None
    def exec_module(self,module):
        tree=TranslateStrings().visit(ast.parse(self.path.read_text('utf-8-sig'),filename=str(self.path)))
        ast.fix_missing_locations(tree)
        exec(compile(tree,str(self.path),'exec'),module.__dict__)

class EnglishFinder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if '.' in fullname or fullname=='english_ui':return None
        source=BASE/(fullname+'.py')
        if source.is_file():return importlib.util.spec_from_file_location(fullname,source,loader=EnglishLoader(source))
        return None

def display_text(value):
    if not isinstance(value,str):return value
    for source,target in sorted(TRANSLATIONS.items(),key=lambda p:len(p[0]),reverse=True):
        if source in value:value=value.replace(source,target)
    return value

def install():
    if any(isinstance(f,EnglishFinder) for f in sys.meta_path):return
    sys.meta_path.insert(0,EnglishFinder())
    # Keep saved form values compatible with the Vietnamese launcher.
    original_loads=json.loads;original_dumps=json.dumps
    def convert(value,old,new):
        if isinstance(value,str):return new if value==old else value
        if isinstance(value,list):return [convert(v,old,new) for v in value]
        if isinstance(value,dict):return {k:convert(v,old,new) for k,v in value.items()}
        return value
    def loads(*a,**kw):return convert(original_loads(*a,**kw),'Chưa xác định','Unspecified')
    def dumps(value,*a,**kw):return original_dumps(convert(value,'Unspecified','Chưa xác định'),*a,**kw)
    json.loads=loads;json.dumps=dumps
    import app_version
    app_version.APP_VERSION='1.1 ENG'
    app_version.APP_TITLE='SMTV Schedule Pipeline v1.1 ENG'
    # Localize existing reports and subprocess error text at display time too.
    from tkinter import messagebox,Text
    original_show=messagebox._show
    def show(title=None,message=None,*a,**kw):return original_show(display_text(title),display_text(message),*a,**kw)
    messagebox._show=show
    original_insert=Text.insert
    def insert(self,index,chars,*args):return original_insert(self,index,display_text(chars),*args)
    Text.insert=insert

if __name__=='__main__':
    install()
    from episode_scanner import run_gui
    run_gui()
