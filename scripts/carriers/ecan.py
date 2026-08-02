"""台灣宅配通 e-can — POST query2.e-can.com.tw/多筆查件_oo4o.asp

經典 ASP + **Big5 編碼**（表單 urlencode 與回應解碼都須指定 big5）。
入口與欄位名見 tests/fixtures/ecan_notes.md。
"""
from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup

from .base import (REQUEST_TIMEOUT, USER_AGENT, ParseError, TrackEvent,
                   TrackResult)

import endpoints

_EP = "ecan"


def _url(key: str) -> str:
    return endpoints.get(_EP)[key]
# 宅配單號 12 碼數字（表單 maxLength=12）
NUMBER_RE = re.compile(r"^\d{12}$")


def parse_result_page(html: str, number: str) -> TrackResult:
    result = TrackResult(carrier="ecan", number=number, found=False,
                         source_url=_url("source"))
    if "查無資料" in html:
        return result

    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [c.get_text(strip=True) for c in rows[0].find_all(["td", "th"])]
        if "最新狀態" not in header:
            continue
        idx = {name: i for i, name in enumerate(header)}
        for tr in rows[1:]:
            cells = [c.get_text(strip=True) for c in tr.find_all("td")]
            if len(cells) < len(header):
                continue
            result.events.append(TrackEvent(
                time=cells[idx.get("處理日期", -2)],
                status=cells[idx["最新狀態"]],
                location=cells[idx.get("營業所", -1)] or None))
        if result.events:
            result.found = True
            return result

    # 走到這裡代表：沒有「查無資料」字樣，也沒有含「最新狀態」表頭的結果表。
    # 「宅配」是站方自有品牌字樣、任何頁面都有，不能當判準（2026-08-02 code review）。
    raise ParseError("宅配通頁面結構已變，請回報 issue")


class EcanAdapter:
    code = "ecan"
    name = "台灣宅配通"

    def detect(self, number: str) -> bool:
        return bool(NUMBER_RE.match(number))

    def track(self, number: str) -> TrackResult:
        data = {f"txtMainID_{i}": "" for i in range(1, 11)}
        data["txtMainID_1"] = number
        data["B1"] = " 查詢 "
        resp = requests.post(
            _url("post"), data=data, timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Referer": _url("source")})
        resp.encoding = "big5"  # 站方不送 charset，requests 會猜錯
        return parse_result_page(resp.text, number)
