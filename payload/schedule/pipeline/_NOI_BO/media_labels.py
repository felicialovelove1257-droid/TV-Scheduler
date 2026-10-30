"""Shared, bounded recognition of media filename labels."""
import re
NO_NEXT_PATTERN=r'(?<![a-z0-9])no[\s_.-]*(?:(?:up[\s_.-]*)?(?:next|nxt)|coming[\s_.-]*up)(?![a-z0-9])'

def is_no_next(name):
    return bool(re.search(NO_NEXT_PATTERN,name,re.I))

def canonical_no_next(name):
    return re.sub(r'\(?'+NO_NEXT_PATTERN+r'\)?','(No NXT)',name,flags=re.I)
