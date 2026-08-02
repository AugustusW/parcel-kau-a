"""富昇物流（momo 自營）adapter — 對真實 fixtures 的離線解析。

fixtures 取自 2026-08-02 真實查詢：單號代換為 900000000004、站名代換為甲/乙。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers.fusheng import FushengAdapter, parse_result_page  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
NUM = "900000000004"


def test_detect_accepts_12_digit_numbers():
    a = FushengAdapter()
    assert a.detect(NUM)
    assert not a.detect("TW254414081298F")


def test_notfound_page_parses_as_not_found():
    html = (FIXTURES / "fs_notfound.html").read_text()
    result = parse_result_page(html, number=NUM)
    assert result.found is False
    assert result.events == []


def test_real_found_page_parses_full_history():
    """真實回應：4 筆歷程，每筆為「時間 狀態 站點」以 &nbsp 分隔的 <li>。"""
    html = (FIXTURES / "fs_found.html").read_text()
    result = parse_result_page(html, number=NUM)
    assert result.found is True
    assert len(result.events) == 4
    assert result.latest.status == "已送達"
    assert result.latest.time == "2026-07-31 18:16:13"
    assert result.latest.location == "甲配送站"
    assert result.events[0].status == "分理作業中"
    assert result.events[0].location == "乙分轉中心"
