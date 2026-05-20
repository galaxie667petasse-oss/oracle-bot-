from datetime import datetime
from typing import Optional
from config import settings
from providers import result_fixtures
from store import load_db, save_db, build_learning, scan_records
from utils import same_team


def is_finished(status: str) -> bool:
    return str(status).upper() in {"FT", "AET", "PEN", "FINISHED", "MATCH FINISHED"}


def eval_pick(pick, hg: int, ag: int) -> Optional[str]:
    typ = pick.get("market_type", "")
    bet = str(pick.get("pari", "")).lower()
    total = hg + ag
    if typ == "draw" or "nul" in bet:
        return "win" if hg == ag else "loss"
    if typ == "total":
        over = "plus" in bet or "over" in bet
        return "win" if (over and total >= 3) or ((not over) and total <= 2) else "loss"
    if typ == "btts":
        yes = "oui" in bet or "yes" in bet
        both = hg > 0 and ag > 0
        return "win" if yes == both else "loss"
    if typ == "h2h":
        if same_team(pick.get("home", ""), bet):
            return "win" if hg > ag else "loss"
        if same_team(pick.get("away", ""), bet):
            return "win" if ag > hg else "loss"
    return None


def _has_pending_records(scan) -> bool:
    return any(p.get("result") is None for p in scan_records(scan))


async def auto_settle(context=None, force=False):
    db = load_db()
    today = datetime.now(settings.tz).strftime("%Y-%m-%d")
    dates = [
        d for d, scan in db.get("scans", {}).items()
        if (force or d <= today) and _has_pending_records(scan)
    ]
    wins = losses = pending = settled = shadow_settled = 0
    settled_rows = []
    for d in sorted(set(dates)):
        fixtures = await result_fixtures(d)
        scan = db.get("scans", {}).get(d, {})
        for pick in scan_records(scan):
            if pick.get("result") is not None:
                continue
            fx = next((f for f in fixtures if same_team(pick.get("home", ""), f.get("home", "")) and same_team(pick.get("away", ""), f.get("away", ""))), None)
            if not fx or not is_finished(fx["status"]) or fx["hg"] is None or fx["ag"] is None:
                pending += 1
                continue
            result = eval_pick(pick, int(fx["hg"]), int(fx["ag"]))
            if not result:
                pending += 1
                continue
            pick["result"] = result
            pick["score"] = f"{fx['hg']}-{fx['ag']}"
            pick["settlement_source"] = fx["src"]
            pick["settled_at"] = datetime.now(settings.tz).isoformat()
            settled += 1
            if pick.get("shadow"):
                shadow_settled += 1
            wins += result == "win"
            losses += result == "loss"
            settled_rows.append(pick)
    db["learning"] = build_learning(db)
    save_db(db)
    return {
        "settled": settled,
        "visible_settled": max(0, settled - shadow_settled),
        "shadow_settled": shadow_settled,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "settled_rows": settled_rows,
    }
