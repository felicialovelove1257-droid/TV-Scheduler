"""End-day search: prefer the requested edits, combine them when needed."""
import bisect
import re
from collections import Counter
from pathlib import Path

TOLERANCE=15
STATE_LIMIT=16000


def total(rows):return sum(r['duration'] for r in rows)

def identity(row):return row.get('cycle'),row.get('block'),row.get('path',row['name'])

def removal_levels(rows):
    """Never remove a required segmented-show insert; at most one DN elsewhere."""
    from schedule_timing import INSERT_KINDS,mark_insert_slots
    rows=mark_insert_slots([dict(r) for r in rows])
    med=next((i for i,r in enumerate(rows) if r['kind']=='meditation'),len(rows))
    levels={}
    for i,r in enumerate(rows):
        if i<=med:continue
        prev=next((x for x in reversed(rows[:i]) if x['kind']=='program'),None)
        nxt=next((x for x in rows[i+1:] if x['kind']=='program'),None)
        internal=bool(prev and nxt and (prev['cycle'],prev['block'])==(nxt['cycle'],nxt['block']))
        if r['kind'] in INSERT_KINDS and internal and prev.get('required_insert'):continue
        if r['kind']=='program' and re.search(r'\bNWN DAILY SCROLL\b',r['name'],re.I):levels[i]=5
        elif r['kind'] in INSERT_KINDS:
            if internal and re.search(r'\bNWN\b',prev['name'],re.I):levels[i]=2
            elif re.match(r'^M intro (Long|Short)\b',r['name'],re.I):levels[i]=3
            elif r['kind'] in ('PRIORITY','DO_NOT_SKIP') or r.get('priority_name'):levels[i]=4
            elif r['kind'] in ('optional','intro'):levels[i]=1
    return levels


def max_options(rows):
    med=next((i for i,r in enumerate(rows) if r['kind']=='meditation'),len(rows))
    result=[]
    for i,r in enumerate(rows):
        alt=r.get('alternative')
        if i<=med or not alt or r.get('selected_max') or 'NO MAX' not in r['name'].upper():continue
        regular=re.sub(r'\s*\(No Max\)|\s+NO MAX','',r['name'],flags=re.I)
        if regular.casefold()!=alt['name'].casefold():continue
        if alt['duration']>r['duration']:result.append(i)
    return result


def allowed_name(path):
    return not re.search(r'need.{0,12}fix|do[ _]*not[ _]*(?:air|use)|\b(?:error|broken|corrupt)\b',str(path),re.I)


def catalog_pool(entries,assets):
    from reserve_ads import resolve_entry
    blocked=set();found=[]
    for e in entries:
        p,_,_=resolve_entry(e,assets)
        if not p:continue
        if e.get('excluded'):blocked.add(str(p).casefold());continue
        if not allowed_name(p):continue
        try:seconds=assets.duration(p)
        except Exception:continue
        if seconds>0:found.append(dict(name=p.name,path=str(p),duration=seconds,kind='optional',reserve_ads=True,sheet_name=e['name']))
    return [r for r in found if r['path'].casefold() not in blocked]


def one_ad(rows,pool,target,source):
    """One add/replacement position, never two ADS in one gap or a long internal AD."""
    from schedule_timing import INSERT_KINDS,mark_insert_slots,insertion_conflicts
    if not pool or total(rows)>=target-TOLERANCE:return rows,[]
    trial=mark_insert_slots([dict(r) for r in rows]);med=next((i for i,r in enumerate(trial) if r['kind']=='meditation'),len(trial))
    base=total(trial);best=None
    ordered=sorted(pool,key=lambda r:r['duration']);durations=[r['duration'] for r in ordered]
    used={(r['cycle'],str(r.get('path','')).casefold()) for r in trial if r['kind'] in INSERT_KINDS}
    for i,anchor in enumerate(trial):
        if i<=med or anchor['kind']!='program' or not anchor.get('insert_slot'):continue
        j=next((j for j in range(i+1,len(trial)) if trial[j]['kind']!='marker'),None)
        occupied=trial[j] if j is not None and trial[j]['kind'] in INSERT_KINDS else None
        if occupied and (occupied['kind']!='optional' or occupied.get('priority_name')):continue
        if source=='tail' and anchor['insert_slot']!='between_shows':continue
        old=occupied['duration'] if occupied else 0
        need=target-base+old
        pivot=bisect.bisect_right(durations,need+TOLERANCE)
        for ad in reversed(ordered[:pivot]):
            if ad['duration']<=old:continue
            if source=='tail' and ad['cycle']!=anchor['cycle']:continue
            if anchor['insert_slot']=='inside_show' and ad['duration']>=120:continue
            if (anchor['cycle'],ad['path'].casefold()) in used:continue
            new_total=base-old+ad['duration'];gap=target-new_total
            score=(abs(gap)>TOLERANCE,abs(gap),bool(occupied),-anchor['cycle'])
            if best is None or score<best[0]:best=(score,i,j if occupied else None,ad)
            # Durations descend; smaller ones cannot improve a non-overrunning fit.
            if gap>=0:break
    if best is None:return rows,[]
    _,i,j,ad=best;anchor=trial[i]
    replacement=dict(ad,cycle=anchor['cycle'],block=anchor['block']);replacement.pop('priority_name',None)
    result=[]
    for index,r in enumerate(trial):
        if index==j:continue
        result.append(r)
        if index==i:result.append(replacement)
    if insertion_conflicts(result):return rows,[]
    event=dict(cycle=anchor['cycle'],block=anchor['block'],name=ad['name'],duration=ad['duration'],source='discarded_cycle_tail' if source=='tail' else 'INPUT_4',sheet_name=ad.get('sheet_name',ad['name']))
    if j is not None:event['replaces']=trial[j]['name']
    return result,[event]


def search_variants(rows,limit,target,pool,tail,allow_fill=True):
    from schedule_timing import insertion_conflicts
    levels=removal_levels(rows);choices=max_options(rows);base=total(rows)
    def cost(value):
        removed,swaps=value
        return tuple(sum(levels[i]==level for i in removed) for level in (5,4,3,2,1))+(len(swaps),)
    states={(0,0):((),())};limited=False
    actions=[(i,-rows[i]['duration'],'remove') for i in levels if levels[i]<=limit]
    actions += [(i,rows[i]['alternative']['duration']-rows[i]['duration'],'max') for i in choices]
    for i,delta,kind in actions:
        for (amount,dn),(removed,swaps) in list(states.items()):
            if kind=='max' and i in removed:continue
            count=dn+int(kind=='remove' and levels[i]==5)
            if count>1:continue
            key=(amount+round(delta*1000),count)
            value=(removed+(i,),swaps) if kind=='remove' else (removed,swaps+(i,))
            if key not in states or cost(value)<cost(states[key]):states[key]=value
        if len(states)>STATE_LIMIT:
            limited=True
            near=sorted(states,key=lambda k:abs(base+k[0]/1000-target))[:STATE_LIMIT//2]
            gentle=sorted(states,key=lambda k:(cost(states[k]),abs(base+k[0]/1000-target)))[:STATE_LIMIT//2]
            states={k:states[k] for k in dict.fromkeys(near+gentle)}
    best=None;best_over=None
    for (_,dn),(removed,swaps) in states.items():
        candidate=[dict(r) for i,r in enumerate(rows) if i not in removed]
        for i in swaps:
            row=next(r for r in candidate if identity(r)==identity(rows[i]));alt=rows[i]['alternative'];row.update({k:alt[k] for k in ('name','path','duration')});row['selected_max']=True
        if insertion_conflicts(candidate):continue
        added=[]
        if allow_fill and total(candidate)<target-TOLERANCE:
            moved,edits=one_ad(candidate,tail,target,'tail')
            filled,extra=one_ad(moved,pool,target,'catalog')
            candidate,added=filled,edits+extra
        gap=target-total(candidate);score=(abs(gap)>TOLERANCE,cost((removed,swaps)) if abs(gap)<=TOLERANCE else (abs(gap),),abs(gap),len(added))
        item=(score,candidate,removed,swaps,added)
        if best is None or score<best[0]:best=item
        if gap< -TOLERANCE and (best_over is None or -gap<total(best_over[1])-target):best_over=item
    return best,best_over,limited


def fit_day_end(full,files,assets,target,entries,draft=False):
    from schedule_timing import finish_day,top_up_day_max,INSERT_KINDS
    from day_end_last_resort import extension_rows
    errors=[]
    baseline,base_report=finish_day(full,files,assets,target,errors,draft=draft)
    med=next((i for i,r in enumerate(baseline) if r['kind']=='meditation'),None)
    if med is None:return baseline,base_report,[],[],errors
    last=next(r for r in reversed(baseline) if r['kind']=='program');group=(last['cycle'],last['block'])
    cut=max(i for i,r in enumerate(full) if (r['cycle'],r['block'])==group)+1
    tail=[dict(r) for r in full[cut:] if r['cycle']==last['cycle'] and r['kind'] in INSERT_KINDS and r['duration']>=120 and not re.match(r'^M intro',r['name'],re.I) and allowed_name(r['path'])]
    pool=catalog_pool(entries,assets)
    attempts=[];limited=False
    # First fill the existing final show, preferring Max, then discarded ADS, then catalog.
    topped,max_edits=top_up_day_max(baseline,target)
    candidate=topped;added=[]
    if abs(target-total(candidate))>TOLERANCE:candidate,edits=one_ad(candidate,tail,target,'tail');added+=edits
    if abs(target-total(candidate))>TOLERANCE:candidate,edits=one_ad(candidate,pool,target,'catalog');added+=edits
    selected=None;extended=False;origin=baseline;report=base_report
    if abs(target-total(candidate))<=TOLERANCE:
        selected=(None,candidate,(),(),added);direct_max=max_edits
    else:
        direct_max=[]
        mixed,_,cap=search_variants(baseline,0,target,pool,tail);limited|=cap
        if mixed and abs(target-total(mixed[1]))<=TOLERANCE:selected=mixed
    following=next((r for r in full[cut:] if r['kind']=='program'),None)
    next_group=None;extension=[];extra_errors=[]
    if selected is None and following:
        next_group=(following['cycle'],following['block'])
        try:extension=extension_rows(full[cut:],next_group)
        except ValueError as exc:extra_errors.append(str(exc))
        if extension:
            # Restart from original rows: never retain a filler added for a shorter ending.
            prefix=[dict(r) for r in full[:cut]]+extension
            origin,report=finish_day(prefix,files,assets,total(prefix)+86400,extra_errors,draft=draft)
            # Search early tiers first; mixed Max/removal/replacement is allowed within each tier.
            over=None;short=None
            for tier in range(6):
                attempt,excess,cap=search_variants(origin,tier,target,pool,[]);limited|=cap
                attempts.append(dict(tier=tier,gap_seconds=target-total(attempt[1]) if attempt else None))
                if attempt and abs(target-total(attempt[1]))<=TOLERANCE:selected=attempt;extended=True;break
                if excess and (over is None or total(excess[1])<total(over[1])):over=excess
                if attempt and (short is None or abs(target-total(attempt[1]))<abs(target-total(short[1]))):short=attempt
            if selected is None:selected=over or short;extended=True
    if selected is None:
        origin=baseline;report=base_report;selected=(None,candidate,(),(),added)
    _,rows,removed,swaps,added=selected
    removed_rows=[origin[i] for i in removed]
    changes=direct_max+[dict(cycle=origin[i]['cycle'],block=origin[i]['block'],before=origin[i]['name'],after=origin[i]['alternative']['name'],added_seconds=origin[i]['alternative']['duration']-origin[i]['duration']) for i in swaps]
    report.update(policy='preferred_edits_then_combined_search',target_seconds=target,max_changes=changes,
        removed_inserts=[dict(cycle=r['cycle'],name=r['name'],kind=r['kind'],duration=r['duration']) for r in removed_rows if r['kind']!='program'],
        removed_daily_scroll=[dict(cycle=r['cycle'],name=r['name'],duration=r['duration']) for r in removed_rows if r['kind']=='program'],
        actual_seconds=total(rows),gap_seconds=target-total(rows),overrun_seconds=total(rows)-target,in_preferred_window=abs(target-total(rows))<=TOLERANCE,
        search_attempts=attempts,search_limited=limited,removed_rows=len(full)-len(rows))
    present=Counter((r.get('priority_name'),r['cycle']) for r in rows if r.get('priority_name'))
    report['removed_priority']=[]
    for r in full:
        if r.get('priority_name'):
            key=(r['priority_name'],r['cycle'])
            if present[key]:present[key]-=1
            else:report['removed_priority'].append(dict(name=key[0],cycle=key[1],block=r['block']))
    waived=[r for r in report['removed_inserts'] if r['kind'] in ('PRIORITY','DO_NOT_SKIP')]
    if waived:report['priority_fallback']=dict(before_seconds=total(origin),after_seconds=total(rows),removed=waived)
    if extended:
        programs=[r for r in extension if r['kind']=='program'];main=next((r for r in programs if ' MAIN ' in r['name']),programs[0])
        detail=dict(before_seconds=total(baseline),after_seconds=total(rows),previous_gap_seconds=target-total(baseline),name=main['name'],cycle=next_group[0],block=next_group[1],show_seconds=sum(r['duration'] for r in programs))
        report['pulled_show']=detail
        if total(rows)>target+TOLERANCE:report['forced_extension']=detail
    if not following and abs(target-total(rows))>TOLERANCE:report['extension_unavailable']=True
    if extra_errors:report['extension_errors']=extra_errors
    return rows,report,added,[],errors+extra_errors
