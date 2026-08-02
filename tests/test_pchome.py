"""網家速配 pchome adapter — SSR 頁面的離線解析。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers.pchome import PchomeAdapter, parse_history_page  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def test_detect_accepts_12_digit_numbers():
    a = PchomeAdapter()
    assert a.detect("900000000002")
    assert not a.detect("TW254414081298F")


def test_notfound_page_parses_as_not_found():
    """站方以「查無此單」表示查無，HTTP 仍是 200。"""
    html = (FIXTURES / "pchome_notfound.html").read_text()
    result = parse_history_page(html, number="900000000002")
    assert result.found is False
    assert result.events == []


def test_found_page_parses_events():
    """合成 found 頁（真實 class 結構，值 UNVERIFIED 需真實命中單號校準）。"""
    html = """<html><body><div class="table">
    <p class="typeBar">一般包裹</p>
    <div class="tr top"><p class="td">包裹號碼</p><p class="td">運送狀態</p><p class="td">資料登入時間</p></div>
    <div class="tr"><p class="td">900000000002</p>
      <div class="innerItem">
        <div class="list finsh"><p class="td">配送完成</p><p class="td">2026/08/01 15:20</p></div>
        <div class="list"><p class="td">運送中</p><p class="td">2026/08/01 09:05</p></div>
      </div>
    </div></div></body></html>"""
    result = parse_history_page(html, number="900000000002")
    assert result.found is True
    assert len(result.events) == 2
    assert result.latest.status == "配送完成"
    assert result.latest.time == "2026/08/01 15:20"
