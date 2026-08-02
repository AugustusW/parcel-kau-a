"""宅配通 ecan adapter — Big5 頁面的離線解析。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers.ecan import EcanAdapter, parse_result_page  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def test_detect_accepts_12_digit_numbers():
    a = EcanAdapter()
    assert a.detect("123456789012")
    assert not a.detect("TW254414081298F")


def test_notfound_page_parses_as_not_found():
    html = (FIXTURES / "ecan_notfound.html").read_bytes().decode("big5", errors="replace")
    result = parse_result_page(html, number="123456789012")
    assert result.found is False
    assert result.events == []


def test_found_page_parses_rows():
    """合成 found 頁（真實表頭，row 值 UNVERIFIED 需真實單號校準）。"""
    html = """<html><body><table>
    <tr><td>項次</td><td>宅配單號</td><td>出貨單號</td><td>結案?</td>
        <td>最新狀態</td><td>細節說明</td><td>處理日期</td><td>營業所</td></tr>
    <tr><td>1</td><td>123456789012</td><td></td><td>Y</td>
        <td>順利送達</td><td>已簽收</td><td>2026/08/01 14:30</td><td>台北營業所</td></tr>
    </table></body></html>"""
    result = parse_result_page(html, number="123456789012")
    assert result.found is True
    assert result.latest.status == "順利送達"
    assert result.latest.location == "台北營業所"


def test_unrecognized_page_raises_parse_error():
    """站方改版：既無「查無資料」也無結果表 → ParseError（非靜默 found=False）。"""
    from carriers.base import ParseError

    import pytest
    with pytest.raises(ParseError):
        parse_result_page("<html><body>宅配通 網站維護中</body></html>",
                          number="900000000001")


def test_http_error_is_raised_not_parsed(monkeypatch):
    """同 tcat：404 該走錯誤分類，不是被 parser 當成改版。"""
    import pytest
    import requests
    from carriers import ecan as mod

    class _Resp:
        status_code, text, content, encoding = 404, "<html>404</html>", b"x", "big5"

        def raise_for_status(self):
            raise requests.HTTPError("404", response=self)

    monkeypatch.setattr(mod.requests, "post", lambda *a, **kw: _Resp())
    with pytest.raises(requests.HTTPError):
        mod.EcanAdapter().track("123456789012")
