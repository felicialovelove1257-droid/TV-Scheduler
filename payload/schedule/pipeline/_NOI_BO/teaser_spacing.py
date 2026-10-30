"""Spread repeated teasers by swapping existing insertions within a cycle."""

def spread_teasers(rows, close_seconds=3600):
    rows=[dict(r) for r in rows];changes=[]
    def positions(items,path):
        elapsed=0;found=[]
        for i,r in enumerate(items):
            if r.get('kind')=='teaser' and r.get('path')==path:found.append((i,elapsed))
            elapsed+=r['duration']
        return found
    def score(items,path):
        ps=positions(items,path)
        return tuple(sorted(round(b[1]-a[1],3) for a,b in zip(ps,ps[1:]))) or (float('inf'),)
    def swapped(items,i,j):
        trial=[dict(r) for r in items]
        # Timing-slot metadata belongs to the position, not the media file.
        slot_keys=('cycle','block','boundary','insert_slot','required_insert','free_slot')
        for dest,src in ((i,j),(j,i)):
            moved=dict(items[src])
            for key in slot_keys:
                moved.pop(key,None)
                if key in items[dest]:moved[key]=items[dest][key]
            trial[dest]=moved
        return trial
    for _ in range(sum(r.get('kind')=='teaser' for r in rows)):
        improved=False
        for path in dict.fromkeys(r.get('path') for r in rows if r.get('kind')=='teaser'):
            before=score(rows,path)
            if before[0]>=close_seconds:continue
            best=None
            for i,_ in positions(rows,path):
                if rows[i]['duration']>=120:continue
                for j,ad in enumerate(rows):
                    if ad.get('cycle')!=rows[i]['cycle'] or ad.get('kind') not in ('optional','PRIORITY'):continue
                    if ad.get('priority_name') or ad['duration']>=120:continue
                    trial=swapped(rows,i,j);after=score(trial,path)
                    if after<=before:continue
                    rank=(after,-abs(j-i))
                    if best is None or rank>best[0]:best=(rank,trial,i,j)
            if best:
                _,trial,i,j=best
                changes.append(dict(cycle=rows[i]['cycle'],teaser=rows[i]['name'],ad=rows[j]['name'],from_block=rows[i]['block'],to_block=rows[j]['block']))
                rows=trial;improved=True
        if not improved:break
    return rows,changes
