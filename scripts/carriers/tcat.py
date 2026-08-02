"""黑貓宅急便（統一速達）— https://www.t-cat.com.tw/Inquire/Trace.aspx

兩段式：
1. `Trace.aspx` ASP.NET postback（__VIEWSTATE 三件套 + txtQuery1..10）拿摘要，
   結果區塊是 `.orderlist-box` 的 col-1/col-2 定義列表（**不是** table）。
2. 摘要含 `TraceDetail.aspx?BillID=<單號>` 連結，該頁 `#resultTable` 是完整貨態歷程
   （每筆狀態 rowspan 分兩列，時間欄含 `<br>` 需正規化）。

抓取紀錄見 tests/fixtures/tcat_notes.md。
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from .base import (REQUEST_TIMEOUT, USER_AGENT, ParseError, TrackEvent,
                   TrackResult)

BASE = "https://www.t-cat.com.tw/Inquire/"
TRACE_URL = BASE + "Trace.aspx"
DETAIL_URL = BASE + "TraceDetail.aspx?BillID={number}"
# 宅急便包裹查詢號碼 12 碼數字（實測 2026-08-02 的真實單號與站方範例號皆 12 碼）
NUMBER_RE = re.compile(r"^\d{12}$")


def _clean(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def parse_summary_page(html: str, number: str) -> TrackResult:
    """Trace.aspx 摘要頁：目前狀態 + 資料登入時間 + 負責營業所（單筆）。"""
    result = TrackResult(carrier="tcat", number=number, found=False,
                         source_url=TRACE_URL)
    if "非有效單號" in html:
        return result

    soup = BeautifulSoup(html, "html.parser")
    boxes = soup.select(".orderlist-box")
    # 查詢頁有表單、結果頁有 orderlist-box；兩者皆無 = 站方改版
    if not boxes and not soup.find("input", {"name": lambda v: v and "txtQuery1" in v}):
        raise ParseError("T-cat 頁面結構已變，請回報 issue")

    for box in boxes:
        fields: dict[str, str] = {}
        for li in box.select("li"):
            k, v = li.select_one(".col-1"), li.select_one(".col-2")
            if k and v:
                fields[_clean(k)] = _clean(v)
        # 頁面內建一份隱藏樣板（站方範例號），以實際查詢號碼過濾
        if fields.get("包裹查詢號碼") != number:
            continue
        status = fields.get("目前狀態", "")
        if not status:
            continue
        result.events.append(TrackEvent(
            time=fields.get("資料登入時間", ""), status=status,
            location=fields.get("負責營業所") or None))
        result.found = True
        return result

    return result


def parse_detail_page(html: str, number: str) -> TrackResult:
    """TraceDetail.aspx `#resultTable`：完整歷程（表頭 貨態/資料登入時間/負責營業所）。"""
    result = TrackResult(carrier="tcat", number=number, found=False,
                         source_url=DETAIL_URL.format(number=number))
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="resultTable")
    if table is None:
        return result

    for tr in table.find_all("tr"):
        if "top" in (tr.get("class") or []):
            continue
        cells = [_clean(td) for td in tr.find_all("td")]
        # 首列多一格 rowspan 的單號欄；統一取末三格 = 貨態 / 時間 / 營業所
        if len(cells) < 3:
            continue
        status, when, where = cells[-3], cells[-2], cells[-1]
        if not status or status == number:
            continue
        result.events.append(TrackEvent(time=when, status=status,
                                        location=where or None))
    result.found = bool(result.events)
    return result


class TcatAdapter:
    code = "tcat"
    name = "黑貓宅急便"

    def detect(self, number: str) -> bool:
        return bool(NUMBER_RE.match(number))

    def track(self, number: str) -> TrackResult:
        s = requests.Session()
        s.headers["User-Agent"] = USER_AGENT
        form_html = s.get(TRACE_URL, timeout=REQUEST_TIMEOUT).text
        soup = BeautifulSoup(form_html, "html.parser")

        def hidden(name: str) -> str:
            el = soup.find("input", {"name": name})
            return el.get("value", "") if el else ""

        data = {n: hidden(n) for n in
                ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")}
        data["ctl00$ContentPlaceHolder1$txtQuery1"] = number
        for i in range(2, 11):
            data[f"ctl00$ContentPlaceHolder1$txtQuery{i}"] = ""
        data["ctl00$ContentPlaceHolder1$btnSend"] = "確認送出"
        summary = parse_summary_page(
            s.post(TRACE_URL, data=data, timeout=REQUEST_TIMEOUT,
                   headers={"Referer": TRACE_URL}).text, number)
        if not summary.found:
            return summary

        # 摘要只有最新一筆；詳細頁才有完整歷程，取得失敗時退回摘要
        try:
            detail = parse_detail_page(
                s.get(DETAIL_URL.format(number=number),
                      timeout=REQUEST_TIMEOUT).text, number)
        except requests.RequestException:
            return summary
        return detail if detail.found else summary
