"""Free post-MT show boundaries while retaining priority and rule ADS."""
from itertools import combinations


def arrange_end_ads(rows, entries, assets, target, fill):
    from schedule_timing import INSERT_KINDS, mark_insert_slots, insertion_conflicts

    def marked(items):
        return mark_insert_slots([dict(r) for r in items])

    def next_content(items, index):
        return next((r for r in items[index+1:] if r['kind'] != 'marker'), None)

    baseline, added = fill(rows, entries, assets, target)
    best = (baseline, added, [])
    def rank(items, added, changes):
        gap = target - sum(r['duration'] for r in items)
        return (abs(gap) > 15, abs(gap) if abs(gap) > 15 else 0,
                sum(c['action'] == 'remove' for c in changes), len(changes), abs(gap))
    best_rank = rank(*best)
    if not best_rank[0]:
        return best
    trial = marked(rows)
    med = next((i for i,r in enumerate(trial) if r['kind']=='meditation'), None)
    if med is None:
        return best
    changes = []
    # Rule ADS may change gap within their cycle, but explicit profile placements
    # and program intros remain pinned. No required item is deleted.
    movable = [r for i,r in enumerate(trial) if i > med and
               r['kind'] in ('optional','fixed','PRIORITY','DO_NOT_SKIP') and
               0 < r['duration'] < 120 and not r.get('priority_name') and
               not r['name'].casefold().startswith('m intro')]
    for ad in movable:
        index = next(i for i,r in enumerate(trial) if r is ad)
        anchor = next((r for r in reversed(trial[:index]) if r['kind']=='program'), None)
        if not anchor or anchor.get('insert_slot') != 'between_shows':
            continue
        destinations = [r for i,r in enumerate(trial) if i > med and
                        r['kind']=='program' and r['cycle']==ad['cycle'] and
                        r.get('insert_slot')=='inside_show' and
                        (next_content(trial,i) is None or next_content(trial,i)['kind'] not in INSERT_KINDS)]
        if not destinations:
            continue
        destination = destinations[-1]
        trial.remove(ad)
        ad['block'] = destination['block']
        ad.pop('boundary', None)
        trial.insert(next(i for i,r in enumerate(trial) if r is destination)+1, ad)
        changes.append(dict(action='move',cycle=ad['cycle'],name=ad['name'],after=destination['name']))
    trial = marked(trial)
    # Remove only ordinary ADS at show boundaries. Required segment inserts,
    # teaser campaigns, rule ADS and priority ADS are retained.
    removable = []
    for i,r in enumerate(trial):
        if i <= med or r['kind'] not in ('optional','intro') or r.get('priority_name'):
            continue
        anchor=next((p for p in reversed(trial[:i]) if p['kind']=='program'),None)
        if r['kind']=='intro' or (anchor and anchor.get('insert_slot')=='between_shows'):
            removable.append(i)
    for count in range(len(removable)+1):
        for removed in combinations(removable,count):
            removed=set(removed)
            candidate=[dict(r) for i,r in enumerate(trial) if i not in removed]
            edits=changes+[dict(action='remove',cycle=trial[i]['cycle'],name=trial[i]['name']) for i in sorted(removed)]
            candidate, extra=fill(candidate,entries,assets,target)
            if insertion_conflicts(candidate):
                continue
            score=rank(candidate,extra,edits)
            if score < best_rank:
                best_rank=score;best=(candidate,extra,edits)
        if not best_rank[0]:
            break
    return best
