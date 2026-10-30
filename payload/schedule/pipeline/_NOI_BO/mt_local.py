"""Keep cycle ADS stable; adjust only the cycles nearest Meditation."""
from pathlib import Path


def repeat_cycle_ads(rows, pending, make, missing):
    cycles=sorted({r['cycle'] for r in rows})
    # A common block boundary avoids scattering a priority ad across cycles.
    available={c:{r['block'] for r in rows if r['cycle']==c and r.get('free_slot')} for c in cycles}
    common=set.intersection(*(available[c] for c in cycles)) if cycles else set()
    order=list(dict.fromkeys(r['block'] for r in rows if r.get('free_slot')))
    placements={}
    for path,kind in pending:
        block=next((b for b in order if b in common),None)
        if block is None:
            missing.append('Thiếu vị trí ADS chung giữa các cycle: '+path.name)
            continue
        common.remove(block);placements[block]=(path,kind)
    result=[]
    for row in rows:
        r=dict(row);result.append(r)
        if r.get('free_slot') and r['block'] in placements:
            path,kind=placements[r['block']]
            r.pop('free_slot',None);boundary=r.pop('boundary','program')
            result.append(dict(make(path,r['cycle'],r['block'],kind),boundary=boundary,cycle_template=True))
    return result


def optimize_near_mt(rows, options, assets, target, optimize, assign):
    """Exhaust normal boundaries and ADS adjustments before interrupting NWN."""
    import re
    preferred=[];previous_program=None
    for row in rows:
        r=dict(row)
        if r.get('kind')=='program':previous_program=r
        if r.get('boundary') and previous_program and re.search(r'\bNWN\s+S(?:1[ABC]?|2)\b',previous_program.get('name',''),re.I):
            r['_mt_saved_boundary']=r.pop('boundary')
        preferred.append(r)
    for allow_priority in (False,True):
        result=_optimize_near_mt(preferred,options,assets,target,optimize,assign,allow_priority)
        if result[1] and abs(result[1][3])<=15:
            for r in result[0]:
                if '_mt_saved_boundary' in r:r['boundary']=r.pop('_mt_saved_boundary')
            return result
        fallback=_optimize_near_mt(rows,options,assets,target,optimize,assign,allow_priority)
        if fallback[1] and abs(fallback[1][3])<=15:return fallback
    return fallback


def _optimize_near_mt(rows, options, assets, target, optimize, assign, allow_priority=False):
    # First exhaust Max/No Max changes while preserving every ADS position.
    initial=optimize(rows,[],assets,target,tolerance=15)
    if initial and abs(initial[3])<=15:return rows,initial,[]
    elapsed=0;boundaries=[]
    for i,r in enumerate(rows):
        elapsed+=r['duration']
        if r.get('boundary'):boundaries.append((i,elapsed))
    if not boundaries:return rows,initial,[]
    best=(rows,initial,[]);best_gap=abs(initial[3]) if initial else float('inf')
    cycles=sorted({r['cycle'] for r in rows})
    options=list(dict.fromkeys(options))
    # Expand backwards by one cycle only after all nearer boundaries fail.
    for depth in range(len(cycles)):
        for end,base in sorted(boundaries,key=lambda v:abs(target-v[1])):
            mt_cycle=rows[end]['cycle']
            prior=[c for c in cycles if c<=mt_cycle]
            allowed=set(prior[-(depth+1):])
            # Cycle immediately before MT is selected naturally when MT is at its end.
            prefix=rows[:end+1]
            free=[i for i,r in enumerate(prefix) if r.get('free_slot') and r['cycle'] in allowed]
            def required_gap(index):
                anchor=next((p for p in reversed(prefix[:index]) if p.get('kind')=='program'),None)
                return bool(anchor and anchor.get('required_insert'))
            removable=[i for i,r in enumerate(prefix) if r['cycle'] in allowed
                       and r.get('kind') in (('optional','intro','PRIORITY') if allow_priority else ('optional','intro')) and not r.get('priority_name')
                       and not required_gap(i)]
            swaps=[i for i,r in enumerate(prefix) if r.get('alternative')]
            gap=target-base
            if gap>sum(rows[i]['alternative']['delta'] for i in swaps)+sum(assets.duration(p) for p in options)*len(allowed)+15:continue
            if gap < -sum(rows[i]['duration'] for i in removable)-15:continue
            # Fallback order: add locally; move to after MT; then remove ADS.
            for mode in ('add','move','remove'):
                actions=[(rows[i]['alternative']['delta'],'max',i) for i in swaps]
                actions += [(assets.duration(p),'ad',p) for _ in allowed for p in options]
                if mode!='add':actions += [(-rows[i]['duration'],'remove',i) for i in removable if mode!='move' or rows[i]['kind']!='intro']
                states={0:((),(),())}
                lower=-sum(rows[i]['duration'] for i in removable) if mode!='add' else 0
                upper=max(0,gap+15-lower)
                for seconds,kind,value in actions:
                    delta=round(seconds*1000);new={}
                    for total,(chosen,ads,removed) in states.items():
                        next_total=total+delta
                        if not lower*1000-1<=next_total<=upper*1000+1:continue
                        if kind=='ad' and len(ads)>=len(free):continue
                        item=(chosen+(value,) if kind=='max' else chosen,
                              ads+(value,) if kind=='ad' else ads,
                              removed+(value,) if kind=='remove' else removed)
                        old=new.get(next_total,states.get(next_total))
                        if old is None or (len(item[1])+len(item[2]),len(item[0]))<(len(old[1])+len(old[2]),len(old[0])):new[next_total]=item
                    states.update(new)
                    if len(states)>8000:
                        states=dict(sorted(states.items(),key=lambda x:abs(x[0]-gap*1000))[:8000])
                for total,(chosen,ads,removed) in sorted(states.items(),key=lambda x:(abs(x[0]-gap*1000)>15000,len(x[1][1])+len(x[1][2]),abs(x[0]-gap*1000))):
                    remaining=gap-sum(rows[i]['alternative']['delta'] for i in chosen)-sum(assets.duration(p) for p in ads)+sum(rows[i]['duration'] for i in removed)
                    if abs(remaining)>15:continue
                    # Keep an occupied slot occupied when an ADS is removed; additions use independent free gaps.
                    trial=[dict(r) for i,r in enumerate(rows) if i not in removed]
                    index_map={old:new for new,old in enumerate(i for i in range(len(rows)) if i not in removed)}
                    new_end=index_map.get(end)
                    if new_end is None:continue
                    for r in trial:
                        if r['cycle'] not in allowed:r.pop('free_slot',None)
                    placements=assign(trial[:new_end+1],ads,assets)
                    if placements is None:continue
                    changes=[];destinations={}
                    if mode=='move':
                        valid=True
                        for i in removed:
                            ad=rows[i]
                            candidates=[j for j,r in enumerate(trial) if j>new_end and r['cycle']==ad['cycle']==mt_cycle
                                        and r.get('free_slot') and j not in destinations
                                        and (ad['duration']<120 or r.get('insert_slot')!='inside_show')]
                            if not candidates:valid=False;break
                            destinations[candidates[0]]=ad
                        if not valid:continue
                    for i in removed:
                        ad=rows[i]
                        changes.append(dict(cycle=ad['cycle'],name=ad['name'],action='move_after_mt' if mode=='move' else 'remove',reason='Canh MT trong ±15 giây; đã thử các phương án gần hơn.'))
                    if destinations:
                        expanded=[]
                        for i,r in enumerate(trial):
                            expanded.append(r)
                            if i in destinations:
                                moved=dict(destinations[i],block=r['block']);r.pop('free_slot',None)
                                moved['boundary']=r.pop('boundary','program');expanded.append(moved)
                        trial=expanded # All inserted destinations follow end, so prefix indices stay valid.
                    answer=(new_end,tuple(index_map[i] for i in chosen),ads,remaining)
                    return trial,answer,changes
    return best
