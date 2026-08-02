"""富昇物流（momo 自營配送）— https://tmsvendor.fs.com.tw/search-result?ship_num1=<單號>

momo（富邦媒體）100% 持股的自營車隊。momo 訂單走雙軌：六都內多為富昇自營，
運能不足或偏遠地區則委外給黑貓／宅配通／新竹（那些用各自的 adapter 即可，
因為 momo 顯示的配送單號就是承運商自己的託運單號）。

純 GET、SSR 回完整 HTML：無 CAPTCHA、無登入、無 XHR。
歷程在 `.panel-body ul li`，每個 li 為「時間 &nbsp&nbsp&nbsp 狀態 &nbsp&nbsp&nbsp 站點」。
抓取紀錄見 tests/fixtures/fs_notes.md。
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from .base import (REQUEST_TIMEOUT, USER_AGENT, ParseError, TrackEvent,
                   TrackResult)

import endpoints

_EP = "fusheng"


def _url() -> str:
    return endpoints.get(_EP)["query"]
# 官方表單接受 10-32 碼數字，但實務上 momo 配送單號為 12 碼；限縮以降低與其他家的撞號
# （官方正則 \d{10,32} 過寬，會讓自動判別多打無謂請求）
NUMBER_RE = re.compile(r"^\d{12}$")
NOT_FOUND_TEXT = "尚未能查詢"


def parse_result_page(html: str, number: str) -> TrackResult:
    result = TrackResult(carrier="fusheng", number=number, found=False,
                         source_url=_url().format(number=number))
    if NOT_FOUND_TEXT in html:
        return result

    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".panel-body")
    if body is None:
        raise ParseError("富昇物流頁面結構已變，請回報 issue")

    for li in body.select("li"):
        # 「2026-07-31 18:16:13   已送達   甲配送站」——原始以 &nbsp 分隔
        parts = [p for p in re.split(r"[\s ]{2,}",
                                     li.get_text(" ", strip=True)) if p]
        if len(parts) < 2:
            continue
        result.events.append(TrackEvent(
            time=parts[0], status=parts[1],
            location=parts[2] if len(parts) > 2 else None))
    result.found = bool(result.events)
    return result


class FushengAdapter:
    code = "fusheng"
    name = "富昇物流（momo）"

    def detect(self, number: str) -> bool:
        return bool(NUMBER_RE.match(number))

    def track(self, number: str) -> TrackResult:
        resp = requests.get(_url().format(number=number), timeout=REQUEST_TIMEOUT,
                            headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return parse_result_page(resp.text, number)
