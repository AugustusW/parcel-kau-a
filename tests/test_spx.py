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


def test_parse_timeline_rows_from_rendered_text():
    rows = [
        {"time": "2026-08-01 09:12", "status": "已送達門市", "location": "台北中山店"},
        {"time": "2026-07-31 18:40", "status": "運送中", "location": None},
    ]
    result = spx_mod.build_result(rows, number="TW254414081298F")
    assert result.found is True
    assert result.latest.status == "已送達門市"


def test_empty_timeline_is_not_found():
    result = spx_mod.build_result([], number="TW254414081298F")
    assert result.found is False


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
