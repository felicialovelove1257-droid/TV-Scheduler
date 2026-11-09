"""Shared row colors for the Cycle 1 and All cycles schedule tables."""
from pathlib import Path


PALETTE = {
    'teaser': dict(background='#DCEBFF', foreground='#174A7E'),
    'fixed': dict(background='#FFE8B3', foreground='#5D4300'),
    'daily': dict(background='#DDF3E4', foreground='#176B46'),
    'daily_low': dict(background='#DDF3E4', foreground='#C62828'),
    'added': dict(background='#EADCF5', foreground='#5E357A'),
    'special': dict(background='#DDF3F5', foreground='#145B63'),
    'warning': dict(background='#FFF29A', foreground='#8A3B00'),
}

INSERT_KINDS = {'teaser', 'fixed', 'optional', 'intro', 'PRIORITY', 'DO_NOT_SKIP'}


def _identity(value):
    return str(value or '').replace('\\', '/').casefold()


def build_context(schedule):
    """Build stable lookup data once, then reuse it for both tables."""
    daily = {}
    for item in schedule.get('ads_usage', []):
        info = dict(item, cycle_count=len(set(item.get('cycles', []))))
        for value in (item.get('path'), item.get('name')):
            if value:
                daily[_identity(value)] = info
    warnings = {_identity(item.get('name')) for item in schedule.get('reported_items', []) if item.get('name')}
    return dict(daily=daily, warnings=warnings, missing=[str(x).casefold() for x in schedule.get('missing', [])])


def row_style(row, context):
    """Return (tag, display name) without changing the saved schedule row."""
    name = str(row.get('name', ''))
    identity = _identity(name)
    explicit_warning = any(row.get(key) for key in ('error', 'warning', 'needs_review', 'temporary_duration', 'draft_duration'))
    named_warning = identity in context['warnings'] or any(identity and len(identity) >= 6 and identity in issue for issue in context['missing'])
    if explicit_warning or named_warning or row.get('duration', 0) <= 0:
        return 'warning', name if name.startswith('⚠ ') else '⚠ ' + name

    kind = row.get('kind', 'program')
    if kind == 'program':
        return '', name
    if kind == 'teaser':
        return 'teaser', name
    if kind == 'fixed':
        return 'fixed', name
    if row.get('mandatory_event') or kind in ('marker', 'meditation'):
        return 'special', name

    daily = context['daily'].get(_identity(row.get('path'))) or context['daily'].get(identity)
    if daily:
        return ('daily_low' if daily['cycle_count'] < 3 else 'daily'), name
    if kind in INSERT_KINDS:
        return 'added', name
    return 'special', name


def configure_tree(tree):
    for tag, colors in PALETTE.items():
        tree.tag_configure(tag, **colors)


def add_legend(parent):
    import tkinter as tk
    frame = tk.Frame(parent, background='#F0F0F0')
    frame.pack(fill='x', pady=(0, 7))
    items = [
        ('Teaser', 'teaser'),
        ('ADS cố định', 'fixed'),
        ('ADS ngày', 'daily'),
        ('ADS ngày dưới 3 cycle', 'daily_low'),
        ('ADS thêm', 'added'),
        ('Đặc biệt', 'special'),
        ('⚠ Lỗi', 'warning'),
    ]
    for text, tag in items:
        colors = PALETTE[tag]
        tk.Label(frame, text=text, padx=7, pady=3, relief='solid', borderwidth=1,
                 background=colors['background'], foreground=colors['foreground']).pack(side='left', padx=(0, 5))
    return frame
