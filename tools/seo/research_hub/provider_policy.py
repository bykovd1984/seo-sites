"""Owner-controlled local report allowance; never a vendor quota override."""
import datetime as dt
import math
from .settings import identifier

MAX_DAILY_LIMIT=150


def effective_policy(config,day):
    ceiling=config.get('dailyLimit',20);delay=config.get('delaySeconds',15)
    if type(ceiling)!=int or not 1<=ceiling<=MAX_DAILY_LIMIT or isinstance(delay,bool) or not isinstance(delay,(int,float)) or not math.isfinite(delay) or delay<10:
        raise ValueError('Invalid ToolsPD daily limit or delay')
    projects=config.get('allowedProjects',[])
    if not isinstance(projects,list) or any(not isinstance(p,str) for p in projects):raise ValueError('Invalid provider project allowance')
    for project in projects:identifier(project)
    expiry=config.get('temporaryAllowanceDay')
    if expiry is not None:
        if not isinstance(expiry,str) or dt.date.fromisoformat(expiry).isoformat()!=expiry:raise ValueError('Invalid temporary allowance day')
        if not projects:raise ValueError('A temporary allowance requires explicit projects')
    expired=expiry is not None and day!=expiry
    enabled=bool(config.get('enabled')) and not expired
    return dict(enabled=enabled,dailyLimit=ceiling,delaySeconds=delay,allowedProjects=projects,
        temporaryAllowanceDay=expiry,allowanceExpired=expired,
        pauseReason='temporary_allowance_day_expired' if expired else 'semrush_collection_paused_in_configuration')
