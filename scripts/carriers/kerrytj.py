"""嘉里大榮 Kerry TJ — POST https://www.kerrytj.com/api/Tracking/GetTracking

前端 Vue 頁背後是乾淨 JSON API（無 CAPTCHA、無簽章）。
payload 形狀與查無判準見 tests/fixtures/kerrytj_notes.md。
"""
from __future__ import annotations

import re

import requests

from .base import (REQUEST_TIMEOUT, USER_AGENT, ParseError, TrackEvent,
                   TrackResult)

API_URL = "https://www.kerrytj.com/api/Tracking/GetTracking"
SOURCE_URL = "https://www.kerrytj.com/zh/checking"
# 託運單號 12 碼數字（官網表單提示；UNVERIFIED: 需真實單號校準是否有其他長度）
NUMBER_RE = re.compile(r"^\d{12}$")


def _fmt(date_val, time_val) -> str:
    """processCargoCrtDate/Time 疑為 YYYYMMDD/HHMMSS int（UNVERIFIED: 需真實單號校準）。"""
    d, t = str(date_val), str(time_val).rjust(6, "0")
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:4]}"
    return f"{d} {t}"


def parse_tracking_response(payload: dict, number: str) -> TrackResult:
    result = TrackResult(carrier="kerrytj", number=number, found=False,
                         source_url=SOURCE_URL)
    # 「查無」時站方仍回 list + errTrackNo；兩個 key 都不在 = schema 變了
    if "list" not in payload and "errTrackNo" not in payload:
        raise ParseError("嘉里大榮 API 回應格式已變，請回報 issue")
    if number in (payload.get("errTrackNo") or []):
        return result
    for item in payload.get("list") or []:
        for c in item.get("course") or []:
            if c.get("statusId") == "ERROR":
                return result
            result.events.append(TrackEvent(
                time=_fmt(c.get("processCargoCrtDate", 0),
                          c.get("processCargoCrtTime", 0)),
                status=c.get("statusIdName") or "",
                location=c.get("processDepotIdName")))
    result.found = bool(result.events)
    return result


class KerrytjAdapter:
    code = "kerrytj"
    name = "嘉里大榮"

    def detect(self, number: str) -> bool:
        return bool(NUMBER_RE.match(number))

    def track(self, number: str) -> TrackResult:
        blanks = [{"idxTxt": t, "value": ""} for t in ("二", "三", "四", "五")]
        payload = {"trackType": "0",
                   "trackNo": [{"idxTxt": "一", "value": number}] + blanks}
        resp = requests.post(API_URL, json=payload, timeout=REQUEST_TIMEOUT,
                             headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return parse_tracking_response(resp.json(), number)
