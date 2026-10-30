import csv
from media_labels import is_no_next, canonical_no_next, NO_NEXT_PATTERN
import re
from collections import Counter
from pathlib import Path

def clock(seconds):
    ms = round(seconds*1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'

INSERT_KINDS={'teaser','intro','fixed','PRIORITY','DO_NOT_SKIP','optional'}

def insertion_conflicts(rows):
    previous=None; conflicts=[]
    for r in rows:
        if r.get('kind')=='marker': continue
        if r.get('kind') in INSERT_KINDS:
            if previous is not None: conflicts.append((previous,r))
            previous=r
        else: previous=None
    return conflicts

def mark_insert_slots(rows):
    programs=[r for r in rows if r.get('kind')=='program']
    for i,r in enumerate(programs):
        nxt=programs[i+1] if i+1<len(programs) else None
        end=nxt is None or (r['cycle'],r['block'])!=(nxt['cycle'],nxt['block'])
        segmented=r['block'] in (2,5,6) and not end and not r.get('continuous_show')
        r.pop('insert_slot',None)
        r['required_insert']=segmented
        if end: r['insert_slot']='between_shows'
        elif segmented or re.search(r'NWN (S1C|S2|S3)\b',r['name']): r['insert_slot']='inside_show'
    return rows

def allocate_single_slots(rows):
    """Keep one insert per gap and relocate overflow to free gaps in the same cycle."""
    rows=list(rows); moves=[];unplaced=[];overflow=[]
    # Long inserts use show boundaries; intro stays pinned at cycle start.
    anchor=None
    for r in list(rows):
        if r.get('kind')=='program': anchor=r
        elif r.get('kind') in INSERT_KINDS and r['kind']!='intro' and r.get('duration',0)>=120:
            if anchor is not None and anchor.get('insert_slot')=='inside_show':
                rows.remove(r);overflow.append(r)
    rank=lambda r: (0 if r.get('priority_name') else 1 if r['kind'] in ('fixed','DO_NOT_SKIP') else 2 if r['kind']=='PRIORITY' else 3 if r['kind']=='teaser' else 4)
    while insertion_conflicts(rows):
        left,right=insertion_conflicts(rows)[0]
        displaced=right if rank(left)<=rank(right) else left
        rows.remove(displaced);overflow.append(displaced)
    for r in sorted(overflow,key=rank):
        if r['kind']=='intro':
            moves.append(dict(name=r['name'],cycle=r['cycle'],action='remove',reason='Ordinary SMTV INTRO yields to a higher-priority insertion.'))
            continue  # INTRO may only appear at cycle start, never relocate it.
        candidates=[]
        for i,anchor in enumerate(rows):
            if anchor['cycle']!=r['cycle'] or anchor.get('kind')!='program': continue
            slot=anchor.get('insert_slot')
            if not slot and not anchor.get('boundary'): continue
            if r.get('duration',0)>=120 and slot=='inside_show': continue
            if i+1<len(rows) and rows[i+1].get('kind') in INSERT_KINDS: continue
            candidates.append(i)
        if not candidates and r['kind'] in ('PRIORITY','DO_NOT_SKIP'):
            for i,anchor in enumerate(rows[:-1]):
                occupied=rows[i+1]
                if (anchor['cycle']==r['cycle'] and anchor.get('kind')=='program'
                    and anchor.get('insert_slot')=='between_shows'
                    and occupied.get('kind')=='optional' and not occupied.get('priority_name')):
                    rows.pop(i+1)
                    moves.append(dict(name=occupied['name'],cycle=occupied['cycle'],action='remove',reason='Ordinary ADS yields its show-boundary slot to priority ADS.'))
                    candidates.append(i)
                    break
        if not candidates:
            unplaced.append(r);continue
        index=min(candidates,key=lambda i:(rows[i]['block']!=r['block'],i))
        anchor=rows[index]
        moves.append(dict(name=r['name'],cycle=r['cycle'],from_block=r['block'],to_block=anchor['block'],after=anchor['name']))
        r=dict(r,block=anchor['block'])
        r['boundary']=anchor.pop('boundary','program' if anchor.get('insert_slot')=='between_shows' else 'nwn_segment')
        anchor.pop('free_slot',None)
        rows.insert(index+1,r)
    for i,r in enumerate(rows):
        if r.get('kind')!='program' or (i+1<len(rows) and rows[i+1].get('kind') in INSERT_KINDS):
            r.pop('free_slot',None)
    return rows,moves,unplaced

def teaser_limit(path):
    return 2 if re.search(r'\bFN\d*\b', Path(str(path)).name, re.I) else 1


def teaser_key(cycle, path):
    return cycle, str(path).casefold()


def fill_segment_gaps(rows, teasers, options, assets, make, missing):
    result=[]
    short_teasers=[p for p in teasers if 0<assets.duration(p)<120]
    short_ads=[p for p in options if 0<assets.duration(p)<120]
    from collections import Counter
    used=Counter(teaser_key(r['cycle'],r['path']) for r in rows if r.get('kind')=='teaser')
    used_ads={(r['cycle'],str(r.get('path','')).casefold()) for r in rows if r.get('kind') in INSERT_KINDS}
    for i,r in enumerate(rows):
        result.append(r)
        if not r.get('required_insert'): continue
        following=rows[i+1] if i+1<len(rows) else {}
        if following.get('kind') in INSERT_KINDS: continue
        available=[p for p in short_teasers if used[teaser_key(r['cycle'],p)]<teaser_limit(p)]
        choices=available or [p for p in short_ads if teaser_key(r['cycle'],p) not in used_ads]
        if not choices:
            missing.append(f"Cycle {r['cycle']}: cần teaser/ADS dưới 2 phút sau {r['name']}")
            continue
        extra=make(choices[0],r['cycle'],r['block'],'teaser' if available else 'optional')
        if available: used[teaser_key(r['cycle'],choices[0])]+=1
        used_ads.add(teaser_key(r['cycle'],choices[0]))
        extra['boundary']=r.pop('boundary','nwn_segment')
        r.pop('free_slot',None)
        result.append(extra)
    return result

def finish_day(rows, files, assets, target, missing, policy='before_24h', draft=False):
    """Trim whole block groups, including their trailing ads; replace final eligible outro."""
    groups=[]
    for r in rows:
        key=(r['cycle'],r['block'])
        if not groups or groups[-1][0]!=key: groups.append((key,[]))
        groups[-1][1].append(r)
    elapsed=0; keep=len(groups)
    for i,(_,group) in enumerate(groups):
        elapsed+=sum(r['duration'] for r in group)
        if elapsed>=target:
            keep=i+1 if policy=='finish_show' or elapsed<=target+15 else i
            break
    kept=[dict(r) for _,group in groups[:keep] for r in group]
    removed=[r for _,group in groups[keep:] for r in group]
    report=dict(target_seconds=target,policy=policy,removed_rows=len(removed),
                removed_priority=[dict(name=r['priority_name'],cycle=r['cycle'],block=r['block']) for r in removed if r.get('priority_name')],
                outro_change=None)
    last=next((r for r in reversed(kept) if r['kind']=='program' and not re.search(r'\bNWN\b',r['name'],re.I)),None)
    if last and last.get('continuous_show'):
        from show_formats import show_part
        if show_part(last['name'],last['name'].split()[1])!='OUT':
            missing.append('Thiếu OUT của show cuối ngày: '+last['name']);last=None
    if last and re.search(r'\b(?:BMD|WOW)\s+MAIN\b',last['name'],re.I):
        missing.append('Thiếu OUT của show cuối ngày; cần bổ sung trước khi chọn No NXT: '+last['name'])
        last=None
    if last:
        key=(last['cycle'],last['block'])
        outro=next((r for r in reversed(kept) if (r['cycle'],r['block'])==key and r['kind']=='program' and re.search(r'\bOUT\b',r['name'],re.I)),None)
        selected=outro or last
        no_next=NO_NEXT_PATTERN
        def identity(name):
            stem=Path(name).stem
            stem=re.sub(r'\s*\((?:UP[ _]*(?:NXT|NEXT)[^)]*|NO[ _]*(?:UP[ _]*)?(?:NXT|NEXT))\)','',stem,flags=re.I)
            stem=re.sub(r'\s+NO[ _]*(?:UP[ _]*)?(?:NXT|NEXT)\b','',stem,flags=re.I)
            return stem.strip().casefold()
        if outro:
            prefix=re.split(r'\bOUT\b',outro['name'],flags=re.I)[0]+'OUT'
            choices=[p for p in files if p.name.upper().startswith(prefix.upper()) and re.search(no_next,p.name,re.I)]
        else:
            choices=[p for p in files if re.search(no_next,p.name,re.I) and identity(p.name)==identity(last['name'])]
        choices.sort(key=lambda p: ('NO MAX' not in p.name.upper(),p.name.casefold()))
        choices=[p for p in choices if draft or not p.with_suffix('.mp4.draft.json').exists()]
        if choices:
            chosen=choices[0]
            report['outro_change']=dict(cycle=selected['cycle'],before=selected['name'],after=chosen.name)
            selected.update(name=chosen.name,path=str(chosen),duration=assets.duration(chosen))
            if chosen.with_suffix('.mp4.draft.json').exists():selected['draft_no_next']=True
        elif not re.search(no_next,selected['name'],re.I):
            if draft:
                source=selected['path']
                stem=Path(selected['name']).stem
                if outro:
                    stem=prefix+(' (No Max)' if 'NO MAX' in stem.upper() else '')
                else:
                    stem=re.sub(r'\s*\(UP[ _]*(?:NXT|NEXT)[^)]*\)','',stem,flags=re.I)
                name=stem+' (No NXT).mp4'
                selected.update(name=name,path=str(Path(source).with_name(name)),draft_no_next=True)
                report['outro_change']=dict(cycle=selected['cycle'],before=Path(source).name,after=name)
            else: missing.append('Cần bản No NXT cuối ngày: '+selected['name'])
    report['actual_seconds']=sum(r['duration'] for r in kept)
    report['overrun_seconds']=report['actual_seconds']-target
    if policy=='before_24h' and report['actual_seconds']>target+15 and keep:
        # A replacement outro may be longer. Re-evaluate the preceding complete block.
        previous=[r for _,group in groups[:keep-1] for r in group]
        dropped=[r for _,group in groups[keep-1:] for r in group]
        kept,report=finish_day(previous,files,assets,target,missing,policy,draft)
        report['removed_rows']+=len(dropped)
        report['removed_priority'].extend(dict(name=r['priority_name'],cycle=r['cycle'],block=r['block']) for r in dropped if r.get('priority_name'))
    report['gap_seconds']=target-report['actual_seconds']
    if report['actual_seconds']<target and policy=='finish_show':
        missing.append(f"Cuối ngày còn thiếu {target-report['actual_seconds']:.3f} giây tới 24h")
    return kept,report

def top_up_day_max(rows, target):
    """Fill the remaining day with genuine No Max/Max pairs after Meditation."""
    rows=[dict(r) for r in rows]
    med=next((i for i,r in enumerate(rows) if r['kind']=='meditation'),None)
    total=sum(r['duration'] for r in rows)
    if med is None or total>=target: return rows,[]
    choices=[]
    for i,r in enumerate(rows):
        alt=r.get('alternative')
        if i<=med or r.get('selected_max') or not alt or 'NO MAX' not in r['name'].upper(): continue
        regular=re.sub(r'\s*\(No Max\)|\s+NO MAX','',r['name'],flags=re.I)
        # The end-of-day No NXT replacement may invalidate an old Up Next alternative.
        if regular.casefold()!=alt['name'].casefold(): continue
        if not re.search(r'\bNWN\s+S(?:1A|1C|2|3)\b|\bBMD\s+(?:IN|OUT)\b|\bAP\b.*\bPART[A-Z]\b',r['name'],re.I): continue
        delta=alt['duration']-r['duration']
        if delta>0: choices.append((i,round(delta*1000000),'BMD' in r['name'].upper()))
    capacity=round((target+15-total)*1000000);states={0:(0,())}
    for i,delta,bmd in choices:
        for added,(bmd_count,indices) in list(states.items()):
            value=added+delta
            if value>capacity: continue
            choice=(bmd_count+int(bmd),indices+(i,))
            old=states.get(value)
            if old is None or (choice[0],len(choice[1]))<(old[0],len(old[1])): states[value]=choice
        if len(states)>30000:
            states=dict(sorted(states.items(),reverse=True)[:30000])
    chosen=states[min(states,key=lambda v:abs(target-total-v/1000000))][1];changes=[]
    for i in chosen:
        r=rows[i];alt=r['alternative']
        changes.append(dict(cycle=r['cycle'],block=r['block'],before=r['name'],after=alt['name'],added_seconds=alt['duration']-r['duration']))
        r.update({k:alt[k] for k in ('name','path','duration')});r['selected_max']=True
    return rows,changes

def optimize_day_end(rows, files, assets, target, missing, draft=False, allow_priority=False):
    """Try complete show endings and remove whole post-MT inserts to fit the day."""
    med_index=next((i for i,r in enumerate(rows) if r['kind']=='meditation'),None)
    if med_index is None:
        missing.append('Cần xác định MT trước khi tối ưu cuối ngày')
        return finish_day(rows,files,assets,target,missing,draft=draft)
    ends=[i+1 for i,r in enumerate(rows) if i>=med_index and
          (i+1==len(rows) or (r['cycle'],r['block'])!=(rows[i+1]['cycle'],rows[i+1]['block']))]
    best=None;best_rank=None
    for end in ends:
        candidate=[dict(r) for r in rows[:end]];errors=[]
        # Apply the true final outro before calculating required reductions.
        candidate,base_report=finish_day(candidate,files,assets,sum(r['duration'] for r in candidate)+86400,errors,draft=draft)
        if not candidate: continue
        total=sum(r['duration'] for r in candidate)
        protected=set()
        for i,r in enumerate(candidate):
            if r['kind'] not in INSERT_KINDS: continue
            previous=next((p for p in reversed(candidate[:i]) if p['kind']=='program'),None)
            following=next((p for p in candidate[i+1:] if p['kind']=='program'),None)
            if previous and following and (previous['cycle'],previous['block'])==(following['cycle'],following['block']):
                if r['kind']=='teaser' or previous.get('required_insert'):
                    protected.add(i)
        removable=[i for i,r in enumerate(candidate) if i>med_index and i not in protected and r['kind'] in INSERT_KINDS
                   and ((r['kind'] in ('optional','intro') and not r.get('priority_name'))
                        or (allow_priority and r['kind'] in ('PRIORITY','DO_NOT_SKIP')))]
        last_program=next((i for i in range(len(candidate)-1,-1,-1) if candidate[i]['kind']=='program'),None)
        scroll_index=None
        if last_program is not None and last_program>med_index and re.search(r'\bNWN\s+DAILY\s+SCROLL\b',candidate[last_program]['name'],re.I):
            scroll_index=last_program
            removable.append(scroll_index)
        if total-sum(candidate[i]['duration'] for i in removable)>target+15: continue
        # Integer microseconds keep fractional durations accurate in the subset search.
        states={0:(0,())}
        costs={'optional':0,'teaser':0,'PRIORITY':1,'fixed':2,'DO_NOT_SKIP':3}
        for i in removable:
            value=round(candidate[i]['duration']*1000000)
            cost=costs.get(candidate[i]['kind'],0)
            for saved,(level,indices) in list(states.items()):
                key=saved+value; choice=(max(level,cost),indices+(i,))
                old=states.get(key)
                if old is None or (choice[0],len(choice[1]))<(old[0],len(old[1])): states[key]=choice
            if len(states)>60000:
                required=max(0,total-target)*1000000
                keys=sorted(states,key=lambda k:(abs(k-required),states[k][0]))[:60000]
                states={k:states[k] for k in keys}
        for saved,(level,indices) in states.items():
            actual=total-saved/1000000;gap=target-actual
            if gap < -15: continue
            if scroll_index in indices:
                removed_indices=set(indices)
                if insertion_conflicts([r for i,r in enumerate(candidate) if i not in removed_indices]): continue
            rank=(abs(gap)>15,level if abs(gap)<=15 else abs(gap),abs(gap),len(indices),-end,bool(errors))
            if best_rank is None or rank<best_rank:
                best_rank=rank;best=(candidate,indices,end,base_report,errors)
    if best is None: return finish_day(rows,files,assets,target,missing,draft=draft)
    candidate,indices,end,report,errors=best;missing.extend(errors)
    removed_set=set(indices);kept=[]
    for i,r in enumerate(candidate):
        if i in removed_set:
            continue
        kept.append(r)
    dropped=[candidate[i] for i in indices]+rows[end:]
    kept,max_changes=top_up_day_max(kept,target)
    actual=sum(r['duration'] for r in kept)
    report.update(target_seconds=target,policy='reduce_inserts_before_dropping_show',actual_seconds=actual,
                  overrun_seconds=actual-target,gap_seconds=target-actual,in_preferred_window=target-15<=actual<=target+15,
                  removed_rows=len(dropped),tail_removed_rows=len(rows)-end,max_changes=max_changes,
                  removed_inserts=[dict(name=candidate[i]['name'],cycle=candidate[i]['cycle'],kind=candidate[i]['kind'],duration=candidate[i]['duration']) for i in indices if candidate[i]['kind'] in INSERT_KINDS],
                  removed_daily_scroll=[dict(name=candidate[i]['name'],cycle=candidate[i]['cycle'],duration=candidate[i]['duration']) for i in indices if candidate[i]['kind']=='program'],
                  removed_priority=[dict(name=r['priority_name'],cycle=r['cycle'],block=r['block']) for r in dropped if r.get('priority_name')])
    return kept,report

def fill_day_end_gap(rows, options, assets, target):
    """Fill free post-MT slots, starting with the final cycle; never cross midnight."""
    gap=target-sum(r['duration'] for r in rows)
    if abs(gap)<=15:return rows,[]
    med=next((i for i,r in enumerate(rows) if r['kind']=='meditation'),None)
    if med is None:return rows,[]
    cycles=sorted({r['cycle'] for r in rows[med+1:] if r['kind']=='program'},reverse=True)
    best=None;best_added=0
    capacity=int((gap+0.0000001)*1000000)
    for depth in range(1,len(cycles)+1):
        trial=mark_insert_slots([dict(r) for r in rows])
        for i,r in enumerate(trial):
            r.pop('free_slot',None)
            if i<=med or r.get('cycle') not in cycles[:depth] or r['kind']!='program' or not r.get('insert_slot'):continue
            following=next((n for n in trial[i+1:] if n['kind']!='marker'),None)
            if following and following['kind'] in INSERT_KINDS:continue
            r['free_slot']=True
        slots=sum(bool(r.get('free_slot')) for r in trial)
        states={0:()}
        for path in list(dict.fromkeys(options))*depth:
            value=round(assets.duration(path)*1000000)
            if value<=0 or value>capacity:continue
            for added,paths in list(states.items()):
                new=added+value
                if new>capacity or len(paths)>=slots:continue
                candidate=paths+(path,)
                if assign_mt_ads(trial,list(candidate),assets) is None:continue
                if new not in states or len(candidate)<len(states[new]):states[new]=candidate
            if len(states)>8000:states=dict(sorted(states.items(),reverse=True)[:8000])
        added=max(states)
        if added>best_added:
            best_added=added;best=(trial,assign_mt_ads(trial,list(states[added]),assets))
        if gap-best_added/1000000<=15:break
    if not best:return rows,[]
    trial,assigned=best;result=[];changes=[]
    for i,row in enumerate(trial):
        row.pop('free_slot',None);result.append(row)
        if i in assigned:
            path=assigned[i];duration=assets.duration(path)
            result.append(dict(cycle=row['cycle'],block=row['block'],name=path.name,path=str(path),duration=duration,kind='optional'))
            changes.append(dict(cycle=row['cycle'],block=row['block'],name=path.name,duration=duration))
    return result,changes


def fill_from_reserve_catalog(rows, entries, assets, target):
    """Add one confirmed ADS, preferring the closest non-overrunning ending."""
    gap=target-sum(row['duration'] for row in rows)
    if abs(gap)<=15:return rows,[]
    med=next((i for i,row in enumerate(rows) if row['kind']=='meditation'),None)
    if med is None:return rows,[]
    trial=mark_insert_slots([dict(row) for row in rows])
    for i,row in enumerate(trial):
        row.pop('free_slot',None)
        if i<=med or row['kind']!='program' or not row.get('insert_slot'):continue
        following=next((r for r in trial[i+1:] if r['kind']!='marker'),None)
        if not following or following['kind'] not in INSERT_KINDS:row['free_slot']=True
    from reserve_ads import resolve_entry
    blocked={str(resolve_entry(e,assets)[0]).casefold() for e in entries if e.get('excluded')}
    best=None
    for entry in entries:
        if entry.get('excluded'):continue
        from reserve_ads import resolve_entry
        path,match_status,_=resolve_entry(entry,assets)
        if not path or str(path).casefold() in blocked:continue
        try:duration=assets.duration(path)
        except Exception:continue
        remaining=gap-duration
        if remaining < -15:continue
        assigned=assign_mt_ads(trial,[path],assets)
        if not assigned:continue
        index=next(iter(assigned));rank=(abs(remaining),-trial[index]['cycle'])
        if best is None or rank<best[0]:best=(rank,index,path,duration,entry['name'])
    if best is None:return rows,[]
    _,index,path,duration,sheet_name=best
    result=[]
    for i,row in enumerate(trial):
        row.pop('free_slot',None);result.append(row)
        if i==index:
            result.append(dict(cycle=row['cycle'],block=row['block'],name=path.name,path=str(path),duration=duration,kind='optional',reserve_ads=True))
    return result,[dict(cycle=trial[index]['cycle'],block=trial[index]['block'],name=path.name,duration=duration,source='INPUT_4',sheet_name=sheet_name)]


def swap_rounds(rows):
    """Group first/second occurrences across cycles; NWN rounds precede BMD."""
    groups = {}; counts = {}
    for i,r in enumerate(rows):
        if not r.get('alternative'): continue
        name=r['name'].upper().replace('_',' ')
        family='NWN' if re.search(r'\bNWN\s+S(?:1A|1C|2|3)\b',name) else 'BMD' if re.search(r'\bBMD\s+(?:IN|OUT)\b',name) else 'AP' if re.search(r'\bAP\b.*\bPART[A-Z]\b',name) else None
        if family is None: continue
        segment=re.search(r'\bNWN\s+(S\w+)',name).group(1) if family=='NWN' else ('IN' if 'BMD IN' in name else 'OUT')
        if family=='AP':segment=re.search(r'\bPART([A-Z])\b',name)[1]
        key=(r['cycle'],family,segment)
        counts[key]=counts.get(key,0)+1
        groups.setdefault((family,counts[key]),[]).append(i)
    return [(family,turn,groups[family,turn]) for family,turn in sorted(groups,key=lambda g:(g[0]!='NWN',g[1]))]

def assign_mt_ads(rows, ads, assets):
    slots=[i for i,r in reversed(list(enumerate(rows))) if r.get('free_slot')]
    used={(r.get('cycle'),r.get('path')) for r in rows if r.get('kind') in INSERT_KINDS}
    assigned={}
    for p in sorted(ads,key=lambda p:assets.duration(p),reverse=True):
        eligible=[i for i in slots if (rows[i].get('cycle'),str(p)) not in used
                  and (assets.duration(p)<120 or rows[i].get('insert_slot')!='inside_show')]
        if not eligible: return None
        i=eligible[0];slots.remove(i);assigned[i]=p;used.add((rows[i].get('cycle'),str(p)))
    return assigned

def optimize(rows, options, assets, target, tolerance=0, repeat_options=()):
    elapsed=0; candidates=[]
    for i,r in enumerate(rows):
        elapsed+=r['duration']
        if r.get('boundary') and elapsed <= target+tolerance: candidates.append((i,elapsed))
    best=None; best_rank=None
    for end,base in reversed(candidates):
        gap=target-base; capacity=round((gap+tolerance)*1000)
        rounds=swap_rounds(rows[:end+1])
        swaps=[(round(rows[i]['alternative']['delta']*1000),i,None) for _,_,indices in rounds for i in indices]
        free=[i for i,r in enumerate(rows[:end+1]) if r.get('free_slot')]
        # Optional items are used at most once daily in this first scheduling policy.
        additions=swaps+[(round(assets.duration(p)*1000),None,p) for p in dict.fromkeys(options)]
        additions += [(round(assets.duration(p)*1000),None,p) for p in repeat_options]
        if sum(x[0] for x in additions)<capacity:
            # Still keep the nearest achievable draft; never invent filler duration.
            pass
        states={0:((),())}
        def consider(stage):
            nonlocal best,best_rank
            for total in sorted(states,reverse=True)[:10]:
                chosen,ads=states[total]
                remaining=gap-sum(rows[i]['alternative']['delta'] for i in chosen)-sum(assets.duration(p) for p in ads)
                if remaining < -tolerance-0.001: continue
                if assign_mt_ads(rows[:end+1],ads,assets) is None: continue
                # A near result is reviewed at each fallback level. Exact validation
                # remains independent; a 15-second search window is not an on-air pass.
                rank=(abs(remaining)>max(tolerance,0.001),abs(remaining)>15,stage if abs(remaining)<=15 else abs(remaining),
                      rows[end]['boundary']!='program',len(ads),abs(remaining),len(chosen))
                if best_rank is None or rank<best_rank:
                    best_rank=rank;best=(end,chosen,ads,remaining)
        consider(0)
        stage_ends={};n=0
        for stage,(_,_,indices) in enumerate(rounds,1):
            n+=len(indices);stage_ends[n]=stage
        for step,(delta,index,path) in enumerate(additions,1):
            if delta<=0 or delta>capacity: continue
            new={}
            for value,(chosen,ads) in states.items():
                total=value+delta
                if total>capacity or (path and len(ads)>=len(free)): continue
                item=(chosen+((index,) if index is not None else ()),ads+((path,) if path else ()))
                old=new.get(total,states.get(total))
                if old is None or (len(item[1]),len(item[0]))<(len(old[1]),len(old[0])): new[total]=item
            states.update(new)
            if len(states)>30000:
                states={v:states[v] for v in sorted(states,reverse=True)[:30000]}
            if step in stage_ends: consider(stage_ends[step])
        consider(len(rounds)+1)
        if best_rank and best_rank[:3]==(False,False,0): break
        if capacity>sum(x[0] for x in additions)+60000: break
    return best

def finish_schedule(config, output, assets, directory):
    missing=output['missing']; unresolved=[]
    ep=config['episode']; files=list(Path(config['local_dir']).glob('*.mp4'))
    rules=config['cycle_rules']; flat=[]
    def make(path,cycle,block,kind):
        return dict(cycle=cycle,block=block,name=path.name,path=str(path),duration=assets.duration(path),kind=kind)
    def resolve(name,required=True):
        p=assets.resolve(name)
        if not p and required: missing.append('Thiếu file: '+name)
        return p
    from teaser_selection import eligible_teaser
    teasers=[p for p in files if re.match(r'(TSER|TEASER) ',p.name,re.I) and eligible_teaser(p.name,ep)]
    ts_fn=[p for p in teasers if re.search(r'\bFN\d*\b',p.name,re.I)]
    from teaser_selection import current_fn_targets,is_fn_teaser
    active_fn=current_fn_targets(config)
    if active_fn:
        teasers=[p for p in teasers if not is_fn_teaser(p.name) or p.name.casefold() in active_fn]
        ts_fn=[p for p in ts_fn if p.name.casefold() in active_fn]
    from ap_rules import ap_campaign,valid_teaser
    campaign=ap_campaign(ep)
    all_ap=[p for p in teasers if re.search(r'\bAP\b',p.name,re.I)]
    ts_ap=[p for p in all_ap if valid_teaser(p.name,ep)]
    explicit=[p for p in ts_ap if re.search(r'TODAY|TOMORROW|TMR|(?:2|TWO)\s*DAYS?',p.name,re.I)]
    if explicit:ts_ap=explicit
    ts_wow=[p for p in teasers if re.search(r'\bWOW\b',p.name,re.I)]
    ts_other=[p for p in teasers if p not in ts_fn+ts_wow+all_ap]
    need_fn=bool(output['fn'] and config.get('schedule_settings',{}).get('tser_fn',True))
    if not need_fn:ts_fn=[]
    from wow_rules import needs_next_wow_teaser
    need_wow=needs_next_wow_teaser(config)
    if not need_wow:ts_wow=[]
    required_teasers=([('WOW ngày sau',ts_wow)] if need_wow else [])+[('show ngày sau',ts_other)]
    if campaign:required_teasers.append((f"AP {campaign['episode']} {campaign['phase']}",ts_ap))
    ts_slot=ts_wow if need_wow else ts_ap if campaign else []
    for label,group in required_teasers+([('FN',ts_fn)] if need_fn else []):
        if not group:missing.append('Thiếu teaser '+label+'; bổ sung file hoặc thời lượng bản nháp.')
    for p in ts_wow+ts_other:
        numbers=re.findall(r'(?<!\d)\d{4}(?!\d)',p.stem)
        if numbers and int(numbers[0])!=ep+1:
            missing.append(f'Cần xác nhận số EP teaser ngày sau: {p.name}; dự kiến EP {ep+1}.')
    for group in (ts_fn,ts_wow,ts_other,ts_ap):
        if len(group)>1: missing.append('Cần chọn teaser: '+', '.join(p.name for p in group))
    for cycle in output['cycles']:
        c=cycle['cycle']; fixed=[]
        from collections import Counter
        teaser_counts=Counter()
        for label,name in [('M QY Warning','M QY Warn'),('Abortion 07','AD_Abortion 07 Crime'),('Hygiene','Gen Hyg Notes')]:
            text=next((v for k,v in rules.items() if k.casefold()==label.casefold()),'')
            if c in {int(n) for n in re.findall(r'\d+',str(text))}:
                p=resolve(name)
                if p: fixed.append(p)
        first=True
        for block in output['block_order']:
            group=[dict(r,kind='fixed' if re.search(r'^M intro ',r['name'],re.I) else 'program') for r in cycle['rows'] if r['block']==block]
            if not group: continue
            expanded=[]
            for j,r in enumerate(group):
                expanded.append(r)
                if 'NO MAX' in r['name'].upper():
                    regular=re.sub(r'\s*\(No Max\)|\s+NO MAX','',r['name'],flags=re.I)
                    p=next((p for p in files if p.name.casefold()==regular.casefold()),None)
                    if p:
                        seconds=assets.duration(p)
                        if seconds>r['duration']: r['alternative']=dict(path=str(p),name=p.name,duration=seconds,delta=seconds-r['duration'])
                nwn_order=[b for b in output['block_order'] if b in (4,8)]
                ts=[]
                if 'NWN S1C' in r['name']:
                    ts=ts_slot if block==nwn_order[0] else ts_other
                elif block in (2,5) and j==0 and len(group)>1 and not r.get('continuous_show'):
                    ts=ts_fn if output['fn'] else ts_other
                if len(ts)==1 and teaser_counts[teaser_key(c,ts[0])]<teaser_limit(ts[0]):
                    expanded.append(make(ts[0],c,block,'teaser'))
                    teaser_counts[teaser_key(c,ts[0])]+=1
                if block in (4,8) and re.search(r'NWN (S1C|S2|S3)\b',r['name']): expanded[-1]['boundary']='nwn_segment'
            if first:
                p=resolve('AD_SMTV INTRO')
                if p: flat.append(make(p,c,block,'intro'))
            flat.extend(expanded)
            flat[-1]['boundary']='program'
            if first:
                first=False
                flat[-1]['free_slot']=True
            elif fixed: flat.append(make(fixed.pop(0),c,block,'fixed'))
            else: flat[-1]['free_slot']=True
            flat[-1]['boundary']='program'
        if fixed: missing.append(f'Cycle {c}: còn ADS cố định chưa có slot')
    manifest=Path(config['local_dir'])/'do_not_skip_ads_manifest.csv'; specials={}
    if manifest.exists():
        with manifest.open(encoding='utf-8-sig',newline='') as f:
            for ad in csv.DictReader(f):
                if ad.get('target') and Path(ad['target']).is_file(): specials.setdefault(ad['requested'],[]).append(Path(ad['target']))
    pending=[];optional=[]
    profile_items = assets.ad_profile.get('items', [])
    profiled_names = {item['name'] for item in profile_items}
    expected_priority = []
    profile_insertions = {}
    active_ads = {item['name'] for item in config.get('ads',{}).get('items',[])}
    for item in profile_items:
        if item['name'] not in active_ads:
            missing.append('ADS profile cần cập nhật theo bảng đầu vào: '+item['name'])
            continue
        p = assets.resolve(item['name'])
        if not p:
            missing.append(item['priority']+': '+item['name'])
            unresolved.append(dict(name=item['name'],priority=item['priority']))
            continue
        for placement in item['placements']:
            for cycle in placement['cycles']:
                anchors=[i for i,r in enumerate(flat) if r['cycle']==cycle and r['block']==placement['block']
                         and re.search(placement['after'],r['name'],re.I)]
                if len(anchors)!=1:
                    missing.append(f"Cần kiểm tra slot ADS cycle {cycle}: {item['name']}")
                    continue
                index=anchors[0]
                extra=make(p,cycle,placement['block'],item['priority'])
                extra['priority_name']=item['name']
                # Keep required ads on the same side of Meditation as their anchor.
                if flat[index].get('boundary'): extra['boundary']=flat[index].pop('boundary')
                flat[index].pop('free_slot',None)
                profile_insertions.setdefault(index,[]).append(extra)
                expected_priority.append(dict(name=item['name'],cycle=cycle,block=placement['block']))
    expanded=[]
    for i,r in enumerate(flat):
        expanded.append(r);expanded.extend(profile_insertions.get(i,[]))
    flat=expanded
    for ad in config.get('ads',{}).get('items',[]):
        name=ad['name']; priority=ad['priority_class']
        if name in profiled_names: continue
        if re.search(r'M QY Warn|Daily News Scroll|AD_SMTV INTRO',name,re.I): continue
        p=assets.resolve(name); paths=[p] if p else specials.get(name,[])
        if not paths:
            unresolved.append(dict(name=name,priority=priority))
            if priority!='OPTIONAL': missing.append(priority+': '+name)
        for p in paths:
            if priority=='OPTIONAL': optional.append(p)
            else: pending.append((p,priority))
    pending.sort(key=lambda x:x[1]!='DO_NOT_SKIP')
    from mt_local import repeat_cycle_ads, optimize_near_mt
    combined=repeat_cycle_ads(flat,pending,make,missing)
    flat,slot_moves,unplaced=allocate_single_slots(mark_insert_slots(combined))
    flat=fill_segment_gaps(flat,ts_fn+ts_other+ts_slot if output['fn'] else ts_other+ts_slot,optional,assets,make,missing)
    # AP campaign is additional when a next-day WOW teaser is also required.
    if campaign and len(ts_ap)==1:
        for cycle in sorted({r['cycle'] for r in flat}):
            if any(r['cycle']==cycle and r.get('path')==str(ts_ap[0]) for r in flat):continue
            choices=[i for i,r in enumerate(flat) if r['cycle']==cycle and r['kind']=='program' and r.get('insert_slot')
                     and (i+1==len(flat) or flat[i+1]['kind'] not in INSERT_KINDS)
                     and (assets.duration(ts_ap[0])<120 or r['insert_slot']=='between_shows')]
            if not choices:
                missing.append(f'Cycle {cycle}: thiếu chỗ chèn teaser AP');continue
            index=min(choices,key=lambda i:(not bool(re.search(r'NWN S3\b',flat[i]['name'])),i))
            anchor=flat[index];extra=make(ts_ap[0],cycle,anchor['block'],'teaser')
            if anchor.get('boundary'):extra['boundary']=anchor.pop('boundary')
            anchor.pop('free_slot',None);flat.insert(index+1,extra)
    from teaser_spacing import spread_teasers
    flat,teaser_moves=spread_teasers(flat)
    output['teaser_spacing_changes']=teaser_moves
    for r in unplaced: missing.append(f"Cycle {r['cycle']}: cần slot riêng cho {r['name']}")
    # Physical marker clips are part of the exported playlist and elapsed time.
    from portable_paths import MARKER_ROOT
    marker_root=MARKER_ROOT
    def marker(name,cycle,block):
        p=marker_root/name
        if not p.is_file():
            missing.append('Thiếu file mốc: '+str(p))
            return None
        return make(p,cycle,block,'marker')
    marked=[];last_cycle=None
    if flat:
        head=marker('-------------------------------.mp4',flat[0]['cycle'],flat[0]['block'])
        if head: marked.append(head)
    for r in flat:
        if r['cycle']!=last_cycle:
            last_cycle=r['cycle']
            m=marker(f'----------CYCLE {last_cycle}---------.mp4',r['cycle'],r['block'])
            if m: marked.append(m)
        marked.append(r)
    flat=marked
    wv_before=marker('------------WV------------ (1).mp4',0,0)
    wv_after=marker('------------WV------------ (2) .mp4',0,0)
    target=72000-float(config.get('schedule_settings',{}).get('offset_seconds',0))
    if not 0<target<86400: raise ValueError('Giây lệch đầu ngày không hợp lệ')
    mt_target=target-(wv_before['duration'] if wv_before else 0)
    repeatable=list(dict.fromkeys([assets.resolve(a['name']) for a in config.get('ads',{}).get('items',[])
        if a['priority_class']=='PRIORITY' and a['name'] not in profiled_names]+optional))
    repeatable=[p for p in repeatable if p]
    mt_original=[dict(r) for r in flat]
    flat,solution,mt_changes=optimize_near_mt(flat,repeatable,assets,mt_target,optimize,assign_mt_ads)
    mt_shift=int(config.get('schedule_settings',{}).get('mt_show_shift',0))
    shift_report=None
    if mt_shift:
        from mt_shift import shifted_mt
        flat,solution,mt_changes,shift_report=shifted_mt(mt_original,flat,solution,mt_shift,repeatable,assets,mt_target,optimize,assign_mt_ads)
    med=resolve('MED TIME 1H'); timing=dict(target_seconds=target,exact=False,gap_seconds=None,ads_adjustments=mt_changes)
    if shift_report:timing['show_shift']=shift_report
    if solution:
        end,swaps,ads,gap=solution
        timing['max_rounds']=[dict(family=family,occurrence=turn,
                                  available_delta_seconds=sum(flat[i]['alternative']['delta'] for i in indices),
                                  selected_cycles=[flat[i]['cycle'] for i in indices if i in swaps],
                                  selected_delta_seconds=sum(flat[i]['alternative']['delta'] for i in indices if i in swaps))
                              for family,turn,indices in swap_rounds(flat[:end+1])]
        timing['max_changes']=[dict(cycle=flat[i]['cycle'],block=flat[i]['block'],
                                    before=flat[i]['name'],after=flat[i]['alternative']['name'],
                                    added_seconds=flat[i]['alternative']['delta']) for i in swaps]
        for i in swaps:
            alt=flat[i]['alternative']; flat[i].update({k:alt[k] for k in ('path','name','duration')});flat[i]['selected_max']=True
        extras=assign_mt_ads(flat[:end+1],ads,assets);combined=[]
        timing['ads_added']=[dict(cycle=flat[i]['cycle'],block=flat[i]['block'],name=p.name,duration=assets.duration(p)) for i,p in extras.items()]
        for i,r in enumerate(flat):
            combined.append(r)
            if i in extras: combined.append(make(extras[i],r['cycle'],r['block'],'optional'))
            if i==end and med:
                if wv_before: combined.append(dict(wv_before,cycle=r['cycle'],block=r['block']))
                combined.append(make(med,r['cycle'],r['block'],'meditation'))
                if wv_after: combined.append(dict(wv_after,cycle=r['cycle'],block=r['block']))
        flat=combined
        timing.update(gap_seconds=gap,exact=abs(gap)<=0.001,boundary=solution[0])
    day_target=86400-float(config.get('schedule_settings',{}).get('offset_seconds',0))
    full_day_rows=[dict(r) for r in flat]
    from reserve_ads import read_catalog,audit_catalog,write_audit
    from episode_scanner import WORKBOOK_PATH
    from import_sources import read_shared_strings,read_sheet,sheet_targets
    import zipfile
    with zipfile.ZipFile(WORKBOOK_PATH) as book:
        tabs=sheet_targets(book)
        if 'INPUT_4' in tabs:config['reserve_ads']=read_catalog(read_sheet(book,tabs['INPUT_4'],read_shared_strings(book)))
    from day_end_fit import fit_day_end
    flat,day_end,end_ads,reflow,end_errors=fit_day_end(full_day_rows,files,assets,day_target,
        config.get('reserve_ads',[]),config.get('draft_mode',False))
    missing.extend(end_errors)
    day_end['ads_reflow']=reflow
    from qc_report import next_show_summary
    day_end['next_show']=next_show_summary(full_day_rows,flat)
    for row in flat:
        if row.get('draft_no_next'):
            from create_episode import run
            path=Path(row['path'])
            if not path.exists():
                stage=path.with_suffix('.building.mp4')
                run(['ffmpeg','-v','error','-y','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t',str(row['duration']),'-c:a','aac','-b:a','128k','-movflags','+faststart',str(stage)])
                stage.replace(path)
            import json
            path.with_suffix('.mp4.draft.json').write_text(json.dumps({'kind':'no_next','seconds':row['duration']}),encoding='utf-8')
            missing.append('Bản No NXT nháp giữ thời lượng gốc, cần thay bản chính thức: '+row['name'])

    output['reserve_ads_audit']=audit_catalog(config.get('reserve_ads',[]),assets)
    write_audit(output['reserve_ads_audit'],directory,config['episode'])
    assets.save()
    final_duration=sum(r['duration'] for r in flat)
    day_end.update(actual_seconds=final_duration,gap_seconds=day_target-final_duration,
                   overrun_seconds=final_duration-day_target,in_preferred_window=day_target-15<=final_duration<=day_target+15,
                   tolerance_seconds=15,added_ads=end_ads)
    if not day_target-15<=day_end['actual_seconds']<=day_target+15 and not day_end.get('forced_extension'):
        missing.append(f"Cuối ngày chưa vào khoảng 23:59:45–24:00:15; còn cách 24h {day_end['gap_seconds']:.3f} giây")
    elapsed=0
    for r in flat:
        r['start_seconds']=elapsed;elapsed+=r['duration'];r['end_seconds']=elapsed
        if r['kind']=='meditation': timing.update(actual_seconds=r['start_seconds'],gap_seconds=target-r['start_seconds'],exact=abs(target-r['start_seconds'])<=0.001)
    timing['tolerance_seconds']=15
    timing['within_tolerance']=timing['gap_seconds'] is not None and abs(timing['gap_seconds'])<=15
    if not timing['within_tolerance']: missing.append(f"Chưa đạt 20:00 +/-15s; còn lệch {timing['gap_seconds']} giây")
    conflicts=insertion_conflicts(flat)
    for a,b in conflicts: missing.append(f"Slot bị trùng cycle {a['cycle']}: {a['name']} / {b['name']}")
    anchor=None;gap_inserts=[]
    for r in flat:
        if r['kind']=='program':
            if anchor and anchor.get('required_insert') and len(gap_inserts)!=1:
                missing.append(f"Cycle {anchor['cycle']}: cần đúng một mục chèn sau {anchor['name']}")
            anchor=r;gap_inserts=[]
        elif r['kind'] in INSERT_KINDS:
            gap_inserts.append(r)
            if r['kind']!='intro' and r['duration']>=120 and anchor and anchor.get('insert_slot')=='inside_show':
                missing.append(f"Cycle {r['cycle']}: mục từ 2 phút cần đặt giữa show: {r['name']}")
    for cycle in output['cycles']:
        cycle['rows']=[r for r in flat if r['cycle']==cycle['cycle']]
        content=[r for r in cycle['rows'] if r['kind']!='marker']
        for i,r in enumerate(content):
            if r['kind']=='intro' and i!=0:
                missing.append(f"Cycle {cycle['cycle']}: SMTV INTRO cần nằm đầu cycle")
        cycle['duration']=sum(r['duration'] for r in cycle['rows'])
    expected_counts=Counter((r['name'],r['cycle']) for r in expected_priority)
    expected_counts.subtract((r['name'],r['cycle']) for r in day_end['removed_priority'])
    expected_counts=+expected_counts
    actual_counts=Counter((r['priority_name'],r['cycle']) for r in flat if r.get('priority_name'))
    if expected_counts!=actual_counts: missing.append('Số lần ADS ưu tiên chưa khớp lịch đã cấu hình')
    priority_counts=[dict(name=item['name'],cycles=[sum(r.get('priority_name')==item['name'] and r['cycle']==c for r in flat) for c in range(1,7)]) for item in profile_items]
    from qc_report import combine_temporary_notices
    output['reported_items'],missing=combine_temporary_notices(output.get('reported_items',[]),flat,missing)
    output.update(missing=sorted(set(missing)),valid=not missing,unresolved_ads=unresolved,timing=timing,
                  priority_policy='EP reference placements' if profile_items else 'Same ADS slots across cycles; adjust nearest MT cycle first',
                  expected_priority=expected_priority,priority_counts=priority_counts,duration=elapsed,day_end=day_end,
                  insertion_slot_moves=slot_moves,insertion_conflict_count=len(conflicts),unplaced_insertions=unplaced,
                  fn_source_episode=config.get('rename_preview',{}).get('fn_source_episode'))
    from qc_report import ads_usage_report
    output['ads_usage']=ads_usage_report(config,flat,assets)
    stem=f'EP_{ep}_schedule'
    playlist_dir=Path(config['local_dir']).parent/'_playlist'
    playlist_dir.mkdir(parents=True,exist_ok=True)
    m3u=playlist_dir/f'EP {ep} v1.m3u';csv_path=directory/(stem+'_timeline.csv');qc=directory/(stem+'_QC.txt')
    lines=['#EXTM3U']
    with csv_path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['Cycle','Block','Kind','Name','Start','End','Duration','Path'])
        for r in flat:
            lines.append(r['path'])
            writer.writerow([r['cycle'],r['block'],r['kind'],r['name'],clock(r['start_seconds']),clock(r['end_seconds']),r['duration'],r['path']])
    m3u.write_text('\n'.join(lines)+'\n','utf-8-sig')
    output.update(m3u_path=str(m3u),timeline_path=str(csv_path),qc_path=str(qc))
    from qc_report import render_qc
    qc.write_text(render_qc(output), encoding='utf-8-sig')
    assets.save()
    return output
