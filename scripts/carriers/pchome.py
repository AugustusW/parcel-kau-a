"""網家速配（PChome Express）— https://www.gopchome.com.tw/delivery/historyList/<單號>

PChome Online 100% 自營車隊。單號放在 URL path，純 GET 回 SSR HTML：
無 CAPTCHA、無登入、無 XHR、無簽章，robots.txt 全開放。

結果是 div 表格（非 <table>）：`.tr` 首個 `.td` 是單號，`.innerItem .list` 每個
是一筆貨態（`.td` 依序為狀態、時間）。抓取紀錄見 tests/fixtures/pchome_notes.md。
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from .base import (REQUEST_TIMEOUT, USER_AGENT, ParseError, TrackEvent,
                   TrackResult)

import endpoints

_EP = "pchome"


def _url() -> str:
    return endpoints.get(_EP)["query"]
# 12 碼數字（與黑貓/嘉里/宅配通撞號，自動判別需輪詢）
NUMBER_RE = re.compile(r"^\d{12}$")
NOT_FOUND_TEXT = "查無此單"


def parse_history_page(html: str, number: str) -> TrackResult:
    result = TrackResult(carrier="pchome", number=number, found=False,
                         source_url=_url().format(number=number))
    if NOT_FOUND_TEXT in html:
        return result

    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(".table")
    if table is None:
        raise ParseError("網家速配頁面結構已變，請回報 issue")

    for row in table.select(".tr"):
        if "top" in (row.get("class") or []):
            continue
        for item in row.select(".innerItem .list"):
            cells = [c.get_text(strip=True) for c in item.select(".td")]
            if not cells or not cells[0]:
                continue
            result.events.append(TrackEvent(
                time=cells[1] if len(cells) > 1 else "",
                status=cells[0], location=None))
    result.found = bool(result.events)
    return result


class PchomeAdapter:
    code = "pchome"
    name = "網家速配"

    def detect(self, number: str) -> bool:
        return bool(NUMBER_RE.match(number))

    def track(self, number: str) -> TrackResult:
        resp = requests.get(_url().format(number=number), timeout=REQUEST_TIMEOUT,
                            headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return parse_history_page(resp.text, number)
