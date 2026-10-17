"""快照的時間語意：物流事件時間 vs 上次查詢時間，兩者不可混用（spec §5.2）。"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import carriers  # noqa: E402
import snapshot  # noqa: E402

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 17, 12, 0, 0, tzinfo=TPE)


def _at(**delta):
    return (NOW - timedelta(**delta)).isoformat(timespec="seconds")


@pytest.mark.parametrize("checked,expected", [
    (_at(hours=23, minutes=59), "fresh"),
    (_at(hours=24), "recent"),
    (_at(hours=167, minutes=59), "recent"),
    (_at(hours=168), "stale"),
])
def test_freshness_boundaries(checked, expected):
    assert snapshot.freshness(checked, now=NOW)[0] == expected


def test_freshness_uses_offsets_not_wall_clock_strings():
    utc = (NOW - timedelta(hours=2)).astimezone(timezone.utc).isoformat()
    assert snapshot.freshness(utc, now=NOW) == ("fresh", 7200)


@pytest.mark.parametrize("checked", [None, "", "不是時間", "2026-10-17T10:00:00", 123, ["x"]])
def test_missing_naive_or_malformed_checked_at_is_unknown(checked):
    """naive 字串無法和帶時區的 now 比較；當成未知，而不是猜一個時區。"""
    assert snapshot.freshness(checked, now=NOW) == ("unknown", None)


def test_future_checked_at_is_unknown_not_negative():
    assert snapshot.freshness(_at(hours=-3), now=NOW) == ("unknown", None)


@pytest.mark.parametrize("age,text", [
    (30, "剛剛"), (600, "約 10 分鐘前"), (7200, "約 2 小時前"), (86400 * 3, "約 3 天前")])
def test_relative(age, text):
    assert snapshot.relative(age) == text


def test_view_maps_internal_fields_to_spec_names():
    entry = {"carrier": "tcat", "last_status": "配送中",
             "last_event_time": "2026/10/16 14:20", "last_checked": _at(hours=21),
             "looks_complete": False}
    v = snapshot.view("900000000001", entry, label="momo 耳機", now=NOW)
    assert v["number"] == "900000000001"
    assert v["latest_status"] == "配送中"
    assert v["event_time"] == "2026/10/16 14:20"
    assert v["event_at"] == "2026-10-16T14:20:00+08:00"
    assert v["event_timezone"] == "+08:00"
    assert v["checked_at"] == entry["last_checked"]
    assert v["checked_age_seconds"] == 21 * 3600
    assert v["freshness"] == "fresh"
    assert v["source_type"] == "official-http"
    assert v["label"] == "momo 耳機"
    assert v["looks_complete"] is False


def test_event_just_before_midnight_keeps_its_own_date():
    now = datetime(2026, 10, 17, 0, 10, tzinfo=TPE)
    v = snapshot.view("1", {"carrier": "tcat", "last_event_time": "2026/10/16 23:50"},
                      label=None, now=now)
    assert v["event_at"] == "2026-10-16T23:50:00+08:00"


def test_view_survives_pre_v020_entries():
    v = snapshot.view("900000000001", {"last_status": "配送中"}, label=None, now=NOW)
    assert v["checked_at"] is None and v["freshness"] == "unknown"
    assert v["event_time"] is None and v["event_at"] is None and v["carrier"] is None


def test_view_survives_wrong_field_types():
    entry = {"carrier": 5, "last_status": None, "last_event_time": ["x"], "last_checked": 123}
    v = snapshot.view("1", entry, label=None, now=NOW)
    assert v["carrier"] is None and v["latest_status"] == ""
    assert v["event_time"] is None and v["checked_at"] is None


def test_unknown_carrier_has_no_timezone_guess():
    v = snapshot.view("1", {"carrier": "chunghwa-post", "last_event_time": "2026/10/16 14:20"},
                      label=None, now=NOW)
    assert v["event_timezone"] is None and v["event_at"] is None


def test_past_retention_uses_the_event_time(monkeypatch):
    monkeypatch.setitem(carriers.CARRIER_META["tcat"], "retention_days", 10)
    entry = {"carrier": "tcat", "last_event_time": "2026/09/01 10:00",
             "last_checked": _at(days=40)}
    assert snapshot.view("1", entry, label=None, now=NOW)["past_retention"] is True
    entry["last_event_time"] = "2026/10/15 10:00"
    assert snapshot.view("1", entry, label=None, now=NOW)["past_retention"] is False


def test_every_registered_carrier_has_complete_metadata():
    keys = {"source_type", "retention_days", "auto_detect_allowed",
            "event_timezone", "verification_date"}
    assert set(carriers.CARRIERS) <= set(carriers.CARRIER_META)
    for code, meta in carriers.CARRIER_META.items():
        assert set(meta) == keys, code
        assert meta["source_type"] in ("official-http", "official-browser",
                                       "third-party-17track"), code


def test_17track_never_takes_part_in_auto_detection():
    assert carriers.CARRIER_META["17track"]["auto_detect_allowed"] is False
