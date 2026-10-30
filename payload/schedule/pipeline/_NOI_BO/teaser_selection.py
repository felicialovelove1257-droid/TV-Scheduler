"""Select numbered daily teasers without changing AP campaign rules."""
import re
from pathlib import Path


def is_fn_teaser(name):
    stem=Path(name).stem.replace('_',' ')
    return bool(re.match(r'^(?:TSER|TEASER)\s+',stem,re.I)
                and re.search(r'\bFN\d*\b',stem,re.I))


def current_fn_targets(config):
    """Real scanned FN teasers supersede former manual/temp names."""
    rows=config.get('rename_preview',{}).get('items',[])
    real=[r for r in rows if is_fn_teaser(r.get('target_name',''))
          and is_fn_teaser(r.get('source_name','')) and not r.get('local_fallback')
          and not r.get('draft_duration') and not r.get('manual_kind')
          and Path(r['source_path']).is_file()]
    return {r['target_name'].casefold() for r in real}


def eligible_teaser(name, episode):
    stem=Path(name).stem
    if not re.match(r'^(?:TSER|TEASER)[ _]+',stem,re.I):
        return True
    if re.search(r'\bAP\b',stem,re.I):
        from ap_rules import valid_teaser
        return valid_teaser(stem,int(episode))
    numbers=re.findall(r'(?<!\d)\d{4}(?!\d)',stem)
    # Unnumbered FN/date-based teasers retain their existing checkbox rules.
    return not numbers or int(numbers[0])==int(episode)+1
