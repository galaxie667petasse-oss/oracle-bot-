import html
import re
from datetime import datetime, timedelta
from config import settings


def esc(x) -> str:
    return html.escape(str(x), quote=False)


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def now_paris():
    return datetime.now(settings.tz)


def target_day():
    n = now_paris()
    d = n + timedelta(days=1) if n.hour >= 21 else n
    return {"key": d.strftime("%Y-%m-%d"), "label": d.strftime("%d/%m/%Y"), "at": n.isoformat()}


def norm_team(name: str) -> str:
    txt = str(name).lower()
    trans = str.maketrans("éèêëàáäâïîíìôöóòûüúùñçł", "eeeeaaaaiiiioooouuuuncl")
    txt = txt.translate(trans)
    txt = re.sub(r"\b(fc|cf|sc|afc|club|f c)\b", " ", txt)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", txt)).strip()


def same_team(a, b) -> bool:
    a, b = norm_team(a), norm_team(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    sa, sb = set(a.split()), set(b.split())
    return bool(sa and sb and len(sa & sb) / max(1, min(len(sa), len(sb))) >= 0.55)
