"""Explicit, reported exceptions after normal day-end fitting has failed."""
from itertools import combinations
import re


def extension_rows(tail, group):
    """Forced NWN extension is program content through S3, without inserts."""
    rows=[]
    for r in tail:
        if r['kind']=='marker' and not rows:
            rows.append(dict(r));continue
        if (r['cycle'],r['block'])==group:rows.append(dict(r))
        elif any(x['kind']=='program' for x in rows):break
    first=next((r for r in rows if r['kind']=='program'),None)
    if not first or not re.search(r'\bNWN\b',first['name'],re.I):return rows
    end=next((i for i,r in enumerate(rows) if r['kind']=='program' and re.search(r'\bNWN\s+S3\b',r['name'],re.I)),None)
    if end is None:raise ValueError('Cannot extend NWN: S3 is missing.')
    return [r for r in rows[:end+1] if r['kind'] in ('program','marker')
            and not re.search(r'\bDAILY\s+SCROLL\b',r['name'],re.I)]


def last_resort(full, kept, report, added, moves, files, assets, target, entries, draft,
                optimize, arrange, fill, finish):
    if abs(target-sum(r['duration'] for r in kept)) <= 15:
        return kept,report,added,moves
    original_end=sum(r['duration'] for r in kept)
    med=next((i for i,r in enumerate(full) if r['kind']=='meditation'),None)
    if med is None:return kept,report,added,moves
    intros=[i for i,r in enumerate(full) if i>med and re.match(r'^M intro (?:Long|Short)\b',r['name'],re.I)]
    best_gap=abs(target-original_end)
    best_fit=None
    for count in range(len(intros)+1):
        for removed in combinations(intros,count):
            candidate=[dict(r) for i,r in enumerate(full) if i not in removed]
            errors=[]
            candidate,trial_report=optimize(candidate,files,assets,target,errors,draft=draft,allow_priority=True)
            candidate,trial_added,trial_moves=arrange(candidate,entries,assets,target,fill)
            if errors:continue
            gap=target-sum(r['duration'] for r in candidate)
            if gap < -15:continue
            groups={(r['cycle'],r['block']) for r in candidate if r['kind']=='program'}
            removed_intros=[full[i] for i in removed if (full[i]['cycle'],full[i]['block']) in groups]
            trial_report['removed_inserts'].extend(dict(cycle=r['cycle'],name=r['name'],kind=r['kind'],duration=r['duration']) for r in removed_intros)
            trial_report['removed_rows']+=len(removed_intros)
            trial_report['intro_fallback']=bool(removed_intros)
            exceptions=[r for r in trial_report['removed_inserts'] if r['kind'] in ('PRIORITY','DO_NOT_SKIP')]
            if abs(gap)<=15:
                rank=(len(exceptions),len(removed_intros),abs(gap))
                if best_fit is None or rank<best_fit[0]:
                    best_fit=(rank,candidate,trial_report,trial_added,trial_moves)
            elif best_fit is None and abs(gap)<best_gap:
                best_gap=abs(gap)
                kept,report,added,moves=candidate,trial_report,trial_added,trial_moves
    if best_fit:
        _,kept,report,added,moves=best_fit
    exceptions=[r for r in report.get('removed_inserts',[]) if r['kind'] in ('PRIORITY','DO_NOT_SKIP')]
    report['priority_fallback']=dict(before_seconds=original_end,
        after_seconds=sum(r['duration'] for r in kept),removed=exceptions)
    if abs(target-sum(r['duration'] for r in kept))<=15:
        return kept,report,added,moves

    # Still short: append exactly the next complete show from the actual rotation.
    last=next((r for r in reversed(kept) if r['kind']=='program'),None)
    indices=[i for i,r in enumerate(full) if last and (r['cycle'],r['block'])==(last['cycle'],last['block'])]
    tail=full[max(indices)+1:] if indices else []
    following=next((r for r in tail if r['kind']=='program'),None)
    if not following:
        report['extension_unavailable']=True
        return kept,report,added,moves
    group=(following['cycle'],following['block'])
    try:extension=extension_rows(tail,group)
    except ValueError as exc:
        report['extension_errors']=[str(exc)]
        return kept,report,added,moves
    before=sum(r['duration'] for r in kept)
    candidate=[dict(r) for r in kept]
    # The former final outro must again announce the following show.
    change=report.get('outro_change')
    if change:
        for r in candidate:
            if r['cycle']==change['cycle'] and r['name']==change['after']:
                source=next((x for x in full if x['cycle']==r['cycle'] and x['name']==change['before']),None)
                if source:r.update({k:source[k] for k in ('name','path','duration')});r.pop('draft_no_next',None)
    candidate.extend(extension)
    errors=[]
    candidate,outro_report=finish(candidate,files,assets,sum(r['duration'] for r in candidate)+86400,errors,draft=draft)
    if errors:
        report['extension_errors']=errors
        return kept,report,added,moves
    report['outro_change']=outro_report.get('outro_change')
    programs=[r for r in extension if r['kind']=='program']
    main=next((r for r in programs if ' MAIN ' in r['name'].upper()),programs[0])
    report['forced_extension']=dict(before_seconds=before,after_seconds=sum(r['duration'] for r in candidate),
        previous_gap_seconds=target-before,name=main['name'],cycle=group[0],block=group[1],
        show_seconds=sum(r['duration'] for r in programs))
    # Refresh waived profile counts now that a previously dropped show is back.
    from collections import Counter
    present=Counter((r.get('priority_name'),r['cycle']) for r in candidate if r.get('priority_name'))
    report['removed_priority']=[]
    for r in full:
        if r.get('priority_name'):
            key=(r['priority_name'],r['cycle'])
            if present[key]:present[key]-=1
            else:report['removed_priority'].append(dict(name=key[0],cycle=key[1],block=r['block']))
    return candidate,report,added,moves
