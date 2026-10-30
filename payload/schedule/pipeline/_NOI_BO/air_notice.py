"""Read actual start time without applying WV/End adjustment requests."""
import re

CLOCK = r'(\d{1,2}:\d{2}:\d{2})'

def parse_air_start(text):
    # Today's final End is tomorrow's start; the header is yesterday's end.
    times=re.findall(CLOCK+r'\s+End\b',text,re.I)
    source='End hôm nay (bắt đầu ngày mai)'
    if not times:return None
    h,m,s=map(int,times[-1].split(':'))
    if h>=24 or m>=60 or s>=60:raise ValueError('Giờ bắt đầu không hợp lệ; dùng HH:MM:SS.')
    return {'start_time':f'{h:02}:{m:02}:{s:02}', 'offset_seconds':h*3600+m*60+s-3600, 'source':source}

def without_air_lines(text):
    # Strip timing-check lines before parsing program durations or start blocks.
    pattern=r'set\s+from\s+air\s+end|current\s+airing|^\s*\d{1,2}:\d{2}:\d{2}\s+(?:WV|End)\b'
    return '\n'.join(line for line in text.splitlines() if not re.search(pattern,line,re.I))
