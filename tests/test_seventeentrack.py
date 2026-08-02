"""17TRACK aggregator adapter — 使用者自備 API key 的第三方查詢（離線）。

覆蓋驗證碼擋死的四家（中華郵政 / 全家 / 7-11 / 新竹）。額度是使用者的錢，
因此絕不進自動判別，必須明確指定。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers import CARRIERS  # noqa: E402
from carriers import seventeentrack as st  # noqa: E402
from carriers.base import CarrierUnavailable, ParseError  # noqa: E402


def test_not_in_auto_detection_registry():
    """絕不能被自動判別選中——會花掉使用者的付費額度。"""
    assert "17track" in CARRIERS
    assert CARRIERS["17track"].detect("123456789012") is False
    assert CARRIERS["17track"].detect("83546610320956") is False


def test_missing_api_key_degrades_with_setup_hint(monkeypatch):
    monkeypatch.delenv(st.API_KEY_ENV, raising=False)
    with pytest.raises(CarrierUnavailable) as e:
        st.SeventeenTrackAdapter().track("83546610320956")
    assert st.API_KEY_ENV in str(e.value)


def test_parse_events_uses_real_api_time_shape():
    """官方 schema：time_raw 是 {date,time,timezone} 物件，time_iso/time_utc 才是字串。

    先前誤把 time_raw 當字串取用，dict 為 truthy 會一路塞進 TrackEvent.time，
    到 CLI 排序時才炸 TypeError（2026-08-02 code review Critical #1）。
    """
    payload = {
        "code": 0,
        "data": {"accepted": [{"number": "83546610320956", "track_info": {
            "tracking": {"providers": [{"events": [
                {"time_iso": "2026-08-01T14:30:00+08:00",
                 "time_utc": "2026-08-01T06:30:00Z",
                 "time_raw": {"date": "2026-08-01", "time": "14:30:00",
                              "timezone": "+08:00"},
                 "description": "順利投遞", "location": "台北中山郵局"},
                {"time_iso": "2026-07-31T09:05:00+08:00",
                 "time_utc": "2026-07-31T01:05:00Z",
                 "time_raw": {"date": "2026-07-31", "time": "09:05:00",
                              "timezone": "+08:00"},
                 "description": "已收寄", "location": None},
            ]}]}}}]},
    }
    result = st.parse_response(payload, number="83546610320956")
    assert result.found is True
    # 取 time_iso（保留原站時區，符合 base.py「不轉 timezone」的設計）
    assert [e.time for e in result.events] == [
        "2026-08-01T14:30:00+08:00", "2026-07-31T09:05:00+08:00"]
    assert all(isinstance(e.time, str) for e in result.events)
    assert result.latest.status == "順利投遞"
    assert result.latest.location == "台北中山郵局"


def test_time_raw_object_is_flattened_when_iso_absent():
    """只有 time_raw 物件時要攤平成字串，不可讓 dict 進到 TrackEvent.time。"""
    payload = {"code": 0, "data": {"accepted": [{"number": "X", "track_info": {
        "tracking": {"providers": [{"events": [
            {"time_raw": {"date": "2026-08-01", "time": "14:30:00",
                          "timezone": "+08:00"}, "description": "投遞"},
        ]}]}}}]}}
    result = st.parse_response(payload, number="X")
    assert result.events[0].time == "2026-08-01 14:30:00"


def test_events_are_sortable_by_time():
    """CLI 的 _render() 會對 time 排序——型別錯誤會在那裡才炸。"""
    payload = {"code": 0, "data": {"accepted": [{"number": "X", "track_info": {
        "tracking": {"providers": [{"events": [
            {"time_iso": "2026-08-01T10:00:00+08:00", "description": "A"},
            {"time_iso": "2026-08-02T10:00:00+08:00", "description": "B"},
        ]}]}}}]}}
    result = st.parse_response(payload, number="X")
    assert sorted(result.events, key=lambda e: e.time)[-1].status == "B"


def test_rejected_number_is_not_found():
    payload = {"code": 0, "data": {"accepted": [], "rejected": [
        {"number": "83546610320956", "error": {"code": -18019902,
                                               "message": "Tracking number does not exist"}}]}}
    result = st.parse_response(payload, number="83546610320956")
    assert result.found is False
    assert result.events == []


def test_accepted_but_no_events_is_not_found():
    """已註冊但尚無貨態——不是錯誤，是還沒有資料。"""
    payload = {"code": 0, "data": {"accepted": [
        {"number": "83546610320956", "track_info": {"tracking": {"providers": []}}}]}}
    assert st.parse_response(payload, number="83546610320956").found is False


def test_unexpected_payload_shape_raises_parse_error():
    with pytest.raises(ParseError):
        st.parse_response({"unexpected": "shape"}, number="83546610320956")


def test_quota_error_in_rejected_item_surfaces_as_carrier_unavailable():
    """真實情況：頂層 code 仍是 0，額度錯誤藏在 data.rejected[].error

    先前只看頂層 code，這種回應會被當成「查無資料」，使用者永遠不知道額度用完
    （2026-08-02 code review Critical #2）。
    """
    for code, msg in ((-18019908, "Your quotas ran out"),
                      (-18019907, "Exceeds your daily limit")):
        payload = {"code": 0, "data": {"accepted": [], "rejected": [
            {"number": "83546610320956", "error": {"code": code, "message": msg}}]}}
        with pytest.raises(CarrierUnavailable) as e:
            st.parse_response(payload, number="83546610320956")
        assert "額度" in str(e.value)


def test_top_level_quota_error_still_surfaces():
    payload = {"code": -18010012, "data": {},
               "message": "The account quota is insufficient"}
    with pytest.raises(CarrierUnavailable) as e:
        st.parse_response(payload, number="83546610320956")
    assert "額度" in str(e.value)


def test_register_failure_is_not_masked_by_gettrackinfo(monkeypatch):
    """register 的錯誤（如 key 失效）不可被第二支呼叫蓋掉。"""
    import requests

    calls = []

    class _Resp:
        def __init__(self, status, payload):
            self.status_code, self._p = status, payload

        def json(self):
            return self._p

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code}", response=self)

    def fake_post(url, **kw):
        calls.append(url)
        assert kw["headers"]["17token"] == "testkey"
        return _Resp(401, {})

    monkeypatch.setenv(st.API_KEY_ENV, "testkey")
    monkeypatch.setattr(st.requests, "post", fake_post)
    with pytest.raises(CarrierUnavailable) as e:
        st.SeventeenTrackAdapter().track("83546610320956")
    assert "key" in str(e.value).lower()
    assert calls and calls[0].endswith("/register")


def test_carrier_code_lookup_covers_captcha_blocked_four():
    """驗證碼擋死的四家必須都有對應代碼，否則接 17TRACK 沒意義。"""
    for name in ("chunghwa-post", "famiport", "seven-eleven", "hct"):
        assert name in st.CARRIER_CODES
        assert isinstance(st.CARRIER_CODES[name], int)
