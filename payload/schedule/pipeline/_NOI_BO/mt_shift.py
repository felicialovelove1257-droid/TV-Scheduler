"""User-requested MT boundary relative to the ordinary scheduling result."""
def shifted_mt(original,normal,solution,shift,options,assets,target,optimize,assign):
    from mt_local import optimize_near_mt
    if shift not in range(-5,6):raise ValueError('MT shift must be between -5 and +5 shows.')
    if not solution:raise ValueError('Cannot shift MT: the ordinary schedule has no MT position.')
    preceding=next((r for r in reversed(normal[:solution[0]+1]) if r['kind']=='program'),None)
    groups=list(dict.fromkeys((r['cycle'],r['block']) for r in original if r['kind']=='program'))
    if not preceding:raise ValueError('Cannot identify the ordinary show before MT.')
    base=(preceding['cycle'],preceding['block']);index=groups.index(base)+shift
    if not 0<=index<len(groups):raise ValueError('The requested MT position is outside the available shows.')
    selected=groups[index];rows=[dict(r) for r in original]
    indices=[i for i,r in enumerate(rows) if r['kind']!='marker' and (r['cycle'],r['block'])==selected]
    end=indices[-1]
    # Only this boundary is eligible during fitting. Restore others afterwards.
    for i,r in enumerate(rows):
        if 'boundary' in r:r['_shift_original_boundary']=r.pop('boundary')
        if i==end:r['boundary']='program';r['_shift_target']=True
    fitted,answer,changes=optimize_near_mt(rows,options,assets,target,optimize,assign)
    if not answer:
        fitted=rows;answer=(end,(),(),target-sum(r['duration'] for r in rows[:end+1]))
    anchor=next((r for r in reversed(fitted[:answer[0]+1]) if r['kind']=='program'),None)
    if not anchor or (anchor['cycle'],anchor['block'])!=selected:
        raise ValueError('MT fitting could not retain the requested show boundary.')
    for r in fitted:
        if '_shift_original_boundary' in r:r['boundary']=r.pop('_shift_original_boundary')
        r.pop('_shift_target',None)
    info=dict(shows=shift,normal_cycle=base[0],normal_block=base[1],selected_cycle=selected[0],selected_block=selected[1],after=anchor['name'])
    return fitted,answer,changes,info
