import re

def has_wow_intro_outro(rules):
    return any('wow' in key.casefold() and re.search(r'long|short',key,re.I)
               and re.search(r'\d',str(value)) for key,value in rules.items())


def needs_next_wow_teaser(config):
    # The following episode decides whether its WOW has a teaser.
    from ap_rules import ap_campaign
    next_day=ap_campaign(config['episode']+1)
    if next_day and next_day['days_before']==0:return False
    return config.get('next_wow_has_intro_outro') is not True
