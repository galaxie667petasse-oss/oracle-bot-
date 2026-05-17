from typing import Dict, List


def visible_key(p: Dict) -> tuple:
    return (p.get("match_id"), p.get("pari"), p.get("market_type"), p.get("date_key"))


def build_shadow_candidates(all_rows: List[Dict], displayed: List[Dict]) -> List[Dict]:
    displayed_keys = {visible_key(p) for p in displayed}
    shadow = []
    for p in all_rows:
        if visible_key(p) in displayed_keys:
            continue
        item = dict(p)
        item["shadow"] = True
        item["visible"] = False
        shadow.append(item)
    return shadow


def shadow_summary(scan: Dict) -> str:
    return f"{len(scan.get('candidates', []) or [])} candidats fantômes"
