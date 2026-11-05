"""Read Word schedule lists using only the portable Python standard library."""
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET


def combined_nwn_s1(name):
    """Word may describe the complete S1 block as one entry."""
    text=re.sub(r'\.(?:mp4|mov|mxf)$','',name,flags=re.I).upper().replace('_',' ')
    if not re.search(r'\bNWN\b',text):return False
    text=re.sub(r'\bSEG(?:MENT)?\s*', 'S',text)
    if re.search(r'\bS\s*1\s*ABC\b|\bS\s*1\s*A\s*[-–/]\s*(?:S\s*1\s*)?C\b|\bS\s*1\s*A\s*/\s*B\s*/\s*C\b',text):return True
    if all(re.search(r'\bS\s*1\s*'+part+r'\b',text) for part in 'ABC'):return True
    return bool(re.search(r'\bS\s*1\b',text)) and not re.search(r'\bS\s*1\s*[ABC]\b',text)


def read_docx_schedule(path):
    path=Path(path)
    with ZipFile(path) as archive:
        root=ET.fromstring(archive.read('word/document.xml'))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paragraphs=root.findall('.//w:body//w:p',ns)
    sections={};current=None;inherited=set();unknown=[]
    for line,p in enumerate(paragraphs,1):
        text=''.join(t.text or '' for t in p.findall('.//w:t',ns)).strip()
        if not text:continue
        same=re.search(r'cycles?\s+(\d+)\s*[-–]\s*(\d+).*same as\s+cycle\s+1',text,re.I)
        if same:
            lo,hi=map(int,same.groups())
            if hi-lo>100:raise ValueError('Khoảng cycle trong DOCX quá lớn; kiểm tra lại file.')
            inherited.update(range(lo,hi+1));current=None;continue
        heading=re.match(r'^(?:(\d+)(?:st|nd|rd|th)?\s+cycle|cycle\s+(\d+))\b',text,re.I)
        if heading:
            current=int(heading[1] or heading[2]);sections.setdefault(current,dict(line=line,items=[],notes=[]));continue
        if re.match(r'^(Next day will air|Shows\s*:|Ads\s*:|Total\b|List made by|Checked by)',text,re.I):
            current=None;continue
        if current is None:continue
        if re.fullmatch(r'\d{1,2}:\d{2}:\d{2}(?:\.\d+)?|[-–\s]+',text):continue
        numbered=re.match(r'^\s*(\d+)[.)]\s+(.+)',text)
        if numbered:
            name=numbered[2].strip()
            # Some lists place the duration in the same paragraph, after a tab/spaces.
            name=re.sub(r'\s+\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\s*$','',name)
            sections[current]['items'].append(dict(line=line,name=name,path='',hint=None,docx=True))
        elif current in inherited or re.match(r'^[•●▪\uFFFD*+-]\s*',text):
            sections[current]['notes'].append(dict(line=line,text=re.sub(r'^[•●▪\uFFFD*+\-\s]+','',text)))
        elif re.match(r'^(?:\d{4}\s+\w+|AD[_ ]|TSER\b|TEASER\b|M intro\b|MED TIME\b|Slogan\b)',text,re.I):
            sections[current]['items'].append(dict(line=line,name=text,path='',hint=None,docx=True))
        else:
            sections[current]['notes'].append(dict(line=line,text=text))
    if not any(s['items'] for s in sections.values()):raise ValueError('Không đọc được danh sách clip trong DOCX. Cần tiêu đề Cycle và tên clip dạng danh sách hoặc bảng.')
    base=sections.get(1,{}).get('items',[]);rows=[];summaries={}
    for c,s in sections.items():
        items=s['items']
        if not items:
            summaries[c]=s['notes']
            if c in inherited and base:
                items=[dict(r,line=s['line'],docx_inherited=True,source_paragraph=r['line']) for r in base]
            else:unknown.append(c)
        rows.append(dict(line=s['line'],name=f'CYCLE {c}',path='',hint=None,docx=True))
        rows.extend(items)
    info=dict(summary_cycles=summaries,unknown_cycles=unknown,paragraphs=len(paragraphs),notes={c:s['notes'] for c,s in sections.items() if s['notes']})
    rows[0]['document_info']=info
    return rows
