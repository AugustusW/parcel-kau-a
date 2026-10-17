"""本機快照的呈現語意。

兩種時間不可混用（spec §5.2）：
- event_time：物流商回傳的最新事件原始字串（history 內部欄位 last_event_time）
- checked_at：本工具最後一次向物流商取得這份結果的時間（內部欄位 last_checked）

新鮮度只看 checked_at——它是本機產生、帶 offset 的時間。event_time 的時區只有在
adapter 宣告時才可信（CARRIER_META.event_timezone），未知就不換算，只顯示原字串。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import carriers
from carriers.base import parse_event_time

FRESH_MAX = timedelta(hours=24)
RECENT_MAX = timedelta(hours=168)


def now() -> datetime:
    """帶本機時區的現在時間；測試以 monkeypatch 注入。"""
    return datetime.now(timezone.utc).astimezone()


def _str(value) -> str | None:
    """手動編輯過的紀錄可能有任何型別；不是非空字串就當缺值。"""
    return value if isinstance(value, str) and value else None


def _parse_aware(text) -> datetime | None:
    text = _str(text)
    if text is None:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def checked_problem(checked_at, *, now: datetime) -> str | None:
    """unknown 的兩種成因要分開講：時間字串看不懂（unparseable）與本機時鐘倒退（future）。"""
    if _str(checked_at) is None:
        return "unparseable" if checked_at not in (None, "") else None
    checked = _parse_aware(checked_at)
    if checked is None:
        return "unparseable"
    return "future" if checked > now else None


def freshness(checked_at, *, now: datetime) -> tuple[str, int | None]:
    """回 (fresh|recent|stale|unknown, 經過秒數)。時鐘倒退（checked_at 在未來）視為 unknown。"""
    checked = _parse_aware(checked_at)
    if checked is None:
        return "unknown", None
    age = now - checked
    if age < timedelta(0):
        return "unknown", None
    seconds = int(age.total_seconds())
    if age < FRESH_MAX:
        return "fresh", seconds
    if age < RECENT_MAX:
        return "recent", seconds
    return "stale", seconds


def relative(age_seconds: int) -> str:
    if age_seconds < 60:
        return "剛剛"
    if age_seconds < 3600:
        return f"約 {age_seconds // 60} 分鐘前"
    if age_seconds < 86400:
        return f"約 {age_seconds // 3600} 小時前"
    return f"約 {age_seconds // 86400} 天前"


def _tz(offset: str) -> timezone:
    sign = 1 if offset[0] == "+" else -1
    hours, minutes = offset[1:].split(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))


def view(number: str, entry: dict, *, label: str | None, now: datetime,
         record_missing: bool = False) -> dict:
    """把 history 的一筆紀錄組成對外欄位（spec §4.5、§5.5）。不改動 history 的內部欄位名。"""
    code = _str(entry.get("carrier"))
    meta = carriers.CARRIER_META.get(code or "", {})
    tz = meta.get("event_timezone")
    raw_event = _str(entry.get("last_event_time"))
    parsed = parse_event_time(raw_event) if (tz and raw_event) else None
    event_at = parsed.replace(tzinfo=_tz(tz)) if parsed else None
    checked_at = _str(entry.get("last_checked"))
    fresh, age = freshness(checked_at, now=now)
    retention = meta.get("retention_days")
    # 保留期看的是物流事件時間（站方從那時起算），不是我們上次查詢的時間
    past_retention = bool(retention and event_at
                          and now - event_at > timedelta(days=retention))
    return {
        "number": number,
        "carrier": code,
        "label": label,
        "latest_status": _str(entry.get("last_status")) or "",
        "event_time": raw_event,
        "event_at": event_at.isoformat(timespec="seconds") if event_at else None,
        "event_timezone": tz,
        "checked_at": checked_at,
        "checked_age_seconds": age,
        "freshness": fresh,
        "checked_problem": checked_problem(entry.get("last_checked"), now=now),
        "source_type": meta.get("source_type"),
        "past_retention": past_retention,
        "looks_complete": entry.get("looks_complete") is True,
        # 名稱還在 labels.json、查詢紀錄卻已不在（例如紀錄檔曾毀損被另存）
        "record_missing": record_missing,
    }
