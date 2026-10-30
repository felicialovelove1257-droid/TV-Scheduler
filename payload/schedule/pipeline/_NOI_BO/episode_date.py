from datetime import date

# User's calendar anchor: 24 October 2026 is EP 3309.
ANCHOR_DATE = date(2026, 10, 24)
ANCHOR_EPISODE = 3309


def episode_today(day=None):
    return ANCHOR_EPISODE + ((day or date.today()) - ANCHOR_DATE).days
