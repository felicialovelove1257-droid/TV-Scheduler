"""Infer a starting occurrence from both programs in an airing notice."""
import re
from schedule_engine import show_code

def infer_start(sentence, program, fn, episode=None):
    text=sentence.upper().strip()
    if episode is not None:
        numbers=re.findall(r'\b(?:EP\s*)?(\d{4})\b',text)
        if numbers and any(int(n)!=int(episode) for n in numbers):
            return None, 'Số EP trong thông báo khác EP đang quét.'
    halves=re.split(r'\bFOLLOWED\s+BY\b|\s*/\s*',text)
    aliases={'WOW':{1},'AP':{1},'BMD':{3,7},'NWN':{4,8}}
    active=[1,3,4,5,7,8] if fn else [1,2,3,4,5,7,8]
    for show in program.get('active_shows',[]):
        slot=show.get('output_slot')
        block={1:2,2:5,3:6}.get(slot)
        if not block or (fn and block==2): continue
        code=show_code(show.get('code','')).upper()
        if not code: continue
        if block==6 and block not in active: active.insert(active.index(7),6)
        for token in (code,show.get('code','').upper(),f"SHOW {show.get('slot',slot)}"):
            aliases.setdefault(token,set()).add(block)
        # When a show moves because of FN, accept its original and output slot labels.
        aliases.setdefault(f'SHOW {slot}',set()).add(block)
        aliases.setdefault('SHOW',set()).add(block)
    def find(part):
        found=[]
        for token,blocks in aliases.items():
            pattern=re.escape(token).replace(r'\ ',r'\s*')
            match=re.search(r'(?<![A-Z0-9])'+pattern+r'(?![A-Z0-9])',part)
            if match: found.append((match.start(),len(match.group()),blocks))
        if not found: return set()
        first=min(p for p,_,_ in found)
        longest=max(length for p,length,_ in found if p==first)
        return set().union(*(bs for p,length,bs in found if p==first and length==longest))
    starts=find(halves[0]) & set(active)
    if not starts: return None, 'Chưa nhận diện được chương trình bắt đầu.'
    for offset,part in enumerate(halves[1:],1):
        next_blocks=find(part) & set(active)
        if not next_blocks: return None, 'Chưa nhận diện được chương trình sau “followed by”.'
        starts={b for b in starts if active[(active.index(b)+offset)%len(active)] in next_blocks}
        if not starts: return None, 'Cặp chương trình chưa khớp thứ tự block hiện tại; cần kiểm tra thứ tự hoặc chọn block tay.'
    if len(starts)!=1: return None, 'Có nhiều vị trí phù hợp; thêm “followed by …” hoặc chọn block tay.'
    block=next(iter(starts))
    return block, f'→ Block {block} (đã đối chiếu chương trình kế tiếp)' if len(halves)>1 else f'→ Block {block}'
