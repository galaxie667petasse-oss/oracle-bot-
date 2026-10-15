STATUS_MAP = {
    "TBD": "SCHEDULED",
    "NS": "SCHEDULED",
    "NOT STARTED": "SCHEDULED",
    "1H": "LIVE",
    "2H": "LIVE",
    "ET": "LIVE",
    "BT": "LIVE",
    "P": "LIVE",
    "SUSP": "ABANDONED",
    "INT": "ABANDONED",
    "HT": "HALFTIME",
    "FT": "FINISHED",
    "AET": "FINISHED",
    "PEN": "FINISHED",
    "PST": "POSTPONED",
    "CANC": "CANCELLED",
    "ABD": "ABANDONED",
    "AWD": "FINISHED",
    "WO": "FINISHED",
}


def canonical_status(provider_status: str | None) -> str:
    key = str(provider_status or "").strip().upper()
    return STATUS_MAP.get(key, "UNKNOWN")

