"""SMTV INTRO is an optional fitting candidate, exclusively at cycle start."""
import re
from pathlib import Path


def is_intro(path):
    return bool(re.search(r'\b(?:AD[ _]+)?SMTV[ _]+INTRO\b',Path(path).stem,re.I))


def start_slots(rows):
    from schedule_timing import INSERT_KINDS
    seen=set();slots=[];previous=None
    for i,row in enumerate(rows):
        if row['kind']=='marker':continue
        cycle=row['cycle']
        if cycle not in seen:
            seen.add(cycle)
            if row['kind']=='program' and not row.get('_intro_disabled') and (previous is None or previous['kind'] not in INSERT_KINDS):slots.append(i)
        previous=row
    return slots
