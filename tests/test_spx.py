"""蝦皮 SPX adapter — optional Playwright 的 degrade 行為（離線）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers import spx as spx_mod  # noqa: E402
from carriers.base import CarrierUnavailable  # noqa: E402
from carriers.spx import SpxAdapter  # noqa: E402


def test_detect_accepts_tw_prefixed_numbers():
    a = SpxAdapter()
    assert a.detect("TW254414081298F")
    assert not a.detect("123456789012")  # 純數字是三家宅配的格式


def test_missing_playwright_package_degrades_with_install_hint(monkeypatch):
    def _boom():
        raise ImportError("No module named 'playwright'")
    monkeypatch.setattr(spx_mod, "_load_playwright", _boom)
    with pytest.raises(CarrierUnavailable) as e:
        SpxAdapter().track("TW254414081298F")
    assert "pip install playwright" in str(e.value)


def test_missing_browser_binary_degrades_with_install_hint(monkeypatch):
    """架構師 finding：套件裝了但 `playwright install chromium` 沒跑過。"""
    class _FakeError(Exception):
        pass

    def _fake_loader():
        def _sync_playwright():
            raise _FakeError("Executable doesn't exist at /path/chromium")
        return _sync_playwright, _FakeError

    monkeypatch.setattr(spx_mod, "_load_playwright", _fake_loader)
    with pytest.raises(CarrierUnavailable) as e:
        SpxAdapter().track("TW254414081298F")
    assert "playwright install chromium" in str(e.value)


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(name):
    import json
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_real_api_response_is_parsed():
    """2026-10-18 真實包裹的 API 回應（去識別化）。v0.5.1 以前用正則找畫面上的
    YYYY-MM-DD，真實頁面是「時間」與「07 Oct 2026」分兩行，所以每一件都被判成查無資料。"""
    result = spx_mod.parse_api(200, _fixture("spx_api_found.json"), "TW0000000000002")
    assert result.found is True
    assert len(result.events) == 8
    assert result.latest.status == "買家取件成功"
    assert result.latest.time == "2026/10/07 09:27"
    assert [e.time for e in result.events][-1] == "2026/10/05 19:48"


def test_timestamps_are_rendered_in_taiwan_time_regardless_of_host_timezone(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    import time
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        result = spx_mod.parse_api(200, _fixture("spx_api_found.json"), "TW0000000000002")
        assert result.latest.time == "2026/10/07 09:27"
    finally:
        monkeypatch.delenv("TZ")
        if hasattr(time, "tzset"):
            time.tzset()


def test_not_found_response_is_not_found():
    """站方對不存在的單號回 retcode -1000、訊息「Server error」、data 為空。"""
    result = spx_mod.parse_api(200, _fixture("spx_api_not_found.json"), "TW0000000000001")
    assert result.found is False and result.events == []


def test_risk_control_block_is_reported_not_disguised_as_not_found():
    with pytest.raises(CarrierUnavailable) as e:
        spx_mod.parse_api(403, _fixture("spx_api_blocked.json"), "TW0000000000001")
    message = str(e.value)
    assert "擋下" in message and "--via-17track" in message


def test_unexpected_response_is_a_parse_error():
    from carriers.base import ParseError
    with pytest.raises(ParseError):
        spx_mod.parse_api(200, {"retcode": 0, "data": {"tracking_list": "oops"}}, "TW1")
    with pytest.raises(ParseError):
        spx_mod.parse_api(500, None, "TW1")
    with pytest.raises(ParseError):
        spx_mod.parse_api(200, {"retcode": 12345, "data": {}}, "TW1")


def test_dom_change_becomes_parse_error_not_traceback(monkeypatch):
    """selector 改版（Playwright TimeoutError）必須是 ParseError，不是裸 traceback。"""
    from carriers.base import ParseError

    class _FakeError(Exception):
        pass

    def _fake_loader():
        def _sync_playwright():
            raise _FakeError("Timeout 30000ms exceeded waiting for locator")
        return _sync_playwright, _FakeError

    monkeypatch.setattr(spx_mod, "_load_playwright", _fake_loader)
    with pytest.raises(ParseError):
        SpxAdapter().track("TW254414081298F")
