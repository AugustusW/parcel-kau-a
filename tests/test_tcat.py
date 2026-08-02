"""黑貓 tcat adapter — parser 對真實 fixtures 的離線行為。

fixtures 取自 2026-08-02 真實查詢（單號已代換為 900000000001）。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers.tcat import (TcatAdapter, parse_detail_page,  # noqa: E402
                           parse_summary_page)

FIXTURES = Path(__file__).parent / "fixtures"
REAL = "900000000001"


def test_detect_accepts_12_digit_numbers():
    a = TcatAdapter()
    assert a.detect("903123456789")
    assert not a.detect("TW254414081298F")
    assert not a.detect("90312345678")  # 11 碼


def test_invalid_number_page_parses_as_not_found():
    """server 回 alert('...非有效單號') → found=False，不 raise。"""
    html = (FIXTURES / "tcat_invalid.html").read_text()
    assert parse_summary_page(html, number="903123456789").found is False


def test_blank_form_page_parses_as_not_found():
    html = (FIXTURES / "tcat_form.html").read_text()
    assert parse_summary_page(html, number="903123456789").found is False


def test_real_summary_page_parses_current_status():
    html = (FIXTURES / "tcat_found_summary.html").read_text()
    result = parse_summary_page(html, number=REAL)
    assert result.found is True
    assert result.latest.status == "超商代收"
    assert result.latest.time == "2026/08/01 20:42"


def test_summary_ignores_builtin_sample_block():
    """頁面內建隱藏樣板（站方範例號）不可被誤判為查詢結果。"""
    html = (FIXTURES / "tcat_found_summary.html").read_text()
    assert parse_summary_page(html, number="111111111111").found is False


def test_real_detail_page_parses_full_history():
    html = (FIXTURES / "tcat_found_detail.html").read_text()
    result = parse_detail_page(html, number=REAL)
    assert result.found is True
    assert len(result.events) >= 2
    assert all(e.status for e in result.events)
    assert "示範門市" in {e.location for e in result.events}


def test_multi_event_detail_page_parses_chronological_history():
    """真實多筆歷程（3 筆，2026-08-02 擷取，單號與營業所已匿名化）。

    先前只有單筆 fixture，多筆的列結構（首列多一格 rowspan 單號欄）沒被鎖住。
    """
    html = (FIXTURES / "tcat_found_multi.html").read_text()
    result = parse_detail_page(html, number="900000000003")
    assert result.found is True
    assert len(result.events) == 3
    assert result.latest.status == "順利送達"
    assert result.latest.time == "2026/06/29 14:37"
    assert result.latest.location == "甲營業所"
    assert {e.status for e in result.events} == {"順利送達", "配送中", "已集貨"}


def test_http_error_is_raised_not_parsed(monkeypatch):
    """站方回 404 時要走網路錯誤分類，不可讓 parser 誤判成「頁面結構已變」。"""
    import requests
    from carriers import tcat as mod

    class _Resp:
        status_code, text, content = 404, "<html>Not Found</html>", b"x"

        def raise_for_status(self):
            raise requests.HTTPError("404", response=self)

    class _Session:
        headers: dict = {}

        def get(self, *a, **kw):
            return _Resp()

        def post(self, *a, **kw):
            return _Resp()

    monkeypatch.setattr(mod.requests, "Session", lambda: _Session())
    with pytest.raises(requests.HTTPError):
        mod.TcatAdapter().track("903123456789")


def test_wellformed_but_unknown_number_is_not_found_not_parse_error():
    """黑貓對「格式正確但查不到」回的是獨立頁（#ContentPlaceHolder1_tblNotFound），
    既無 .orderlist-box 也無 txtQuery1——原本的改版判準會誤判成站方改版。

    與 tcat_invalid.html 不同：那是「格式就錯」（checksum 失敗、回 alert），
    這是「格式對但無資料」，兩條路徑不同頁，所以舊測試抓不到。
    （2026-08-02 使用者於 Windows 實測回報）
    """
    html = (FIXTURES / "tcat_notfound_valid_format.html").read_text()
    result = parse_summary_page(html, number="900000000009")
    assert result.found is False
    assert result.events == []
