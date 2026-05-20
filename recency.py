from typing import Any, Dict, Iterable, Optional, Tuple


PERIOD_ORDER = (
    "archive_pre2012",
    "transition_2012_2014",
    "modern_2015_2019",
    "recent_2020_2023",
    "test_2024_plus",
)

PERIOD_LABELS = {
    "archive_pre2012": "archive avant 2012",
    "transition_2012_2014": "transition 2012-2014",
    "modern_2015_2019": "moderne 2015-2019",
    "recent_2020_2023": "récent 2020-2023",
    "test_2024_plus": "test final 2024+",
}

PERIOD_WEIGHTS = {
    "archive_pre2012": 0.15,
    "transition_2012_2014": 0.35,
    "modern_2015_2019": 0.70,
    "recent_2020_2023": 1.00,
    "test_2024_plus": 1.00,
}


def year_from_date(date_key: Any) -> Optional[int]:
    text = str(date_key or "")
    if len(text) < 4:
        return None
    try:
        return int(text[:4])
    except ValueError:
        return None


def period_bucket_from_year(year: Optional[int]) -> str:
    if year is None:
        return "archive_pre2012"
    if year < 2012:
        return "archive_pre2012"
    if year <= 2014:
        return "transition_2012_2014"
    if year <= 2019:
        return "modern_2015_2019"
    if year <= 2023:
        return "recent_2020_2023"
    return "test_2024_plus"


def period_bucket(date_key: Any) -> str:
    return period_bucket_from_year(year_from_date(date_key))


def data_weight_for_period(period: str) -> float:
    return PERIOD_WEIGHTS.get(period, 0.15)


def data_weight_for_date(date_key: Any) -> float:
    return data_weight_for_period(period_bucket(date_key))


def record_period(record: Dict[str, Any]) -> str:
    existing = record.get("period_bucket")
    if existing in PERIOD_WEIGHTS:
        return str(existing)
    return period_bucket(record.get("date_key") or record.get("date"))


def record_weight(record: Dict[str, Any]) -> float:
    try:
        value = float(record.get("data_weight"))
    except Exception:
        value = data_weight_for_period(record_period(record))
    if value <= 0:
        return data_weight_for_period(record_period(record))
    return value


def date_min_max(records: Iterable[Dict[str, Any]]) -> Tuple[str, str]:
    dates = sorted(str(r.get("date_key") or r.get("date") or "") for r in records if str(r.get("date_key") or r.get("date") or ""))
    if not dates:
        return "", ""
    return dates[0], dates[-1]
