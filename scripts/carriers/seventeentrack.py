"""17TRACK 聚合查詢 — https://api.17track.net/track/v2.4

用途：補上四家因圖形驗證碼而無法直接查的貨運（中華郵政 / 全家 / 7-11 / 新竹）。

**API key 由使用者自備**（環境變數 `PARCEL_KAU_A_17TRACK_KEY`），本專案不內建、
不代管。額度是使用者的錢，因此這個 adapter：
- `detect()` 永遠回 False —— 絕不進自動判別
- 必須以 `--carrier 17track` 明確指定才會呼叫

流程：POST /register（把單號登錄進帳號）→ POST /gettrackinfo（取貨態）。

扣量規則（官方文件 2026-08-02 查證）：**只有 register 扣 1 quota**，gettrackinfo
與 webhook 推送不扣。所以同一單號重複查詢是免費的，200 筆免費額度 = 200 個
不同單號。刻意不使用 getRealTimeTrackInfo —— 那支的 cacheLevel=Instant 一次
扣 10 quota，是最容易燒光額度的路徑。
carrier code 取自 https://res.17track.net/asset/carrier/info/apicarrier.all.json
（2026-08-02 擷取；完整清單見該檔，此處只固定台灣相關幾家）。
"""
from __future__ import annotations

import os

import requests

from .base import (REQUEST_TIMEOUT, CarrierUnavailable, ParseError, TrackEvent,
                   TrackResult)

API_BASE = "https://api.17track.net/track/v2.4"
API_KEY_ENV = "PARCEL_KAU_A_17TRACK_KEY"
SOURCE_URL = "https://t.17track.net/"

# 17TRACK 數字 carrier code（2026-08-02 自官方 apicarrier.all.json 擷取）
CARRIER_CODES: dict[str, int] = {
    "chunghwa-post": 20011,      # 中華郵政
    "chunghwa-post-domestic": 20012,
    "famiport": 100227,          # 全家店到店
    "seven-eleven": 190456,      # 7-ELEVEN 交貨便
    "hct": 190466,               # 新竹物流
    # 以下五家本專案已可直接查，列出僅供使用者需要時明確指定
    "tcat": 100215,
    "kerrytj": 100704,
    "ecan": 100459,              # Pelican（宅配通）
    "pchome": 100875,
    "spx": 100863,
    # 富昇（momo 自營）17TRACK 未收錄，只能直連 --carrier fusheng
}

# 官方錯誤碼（doc v2.4）：額度耗盡 / 超出日限 / 已登錄 / 尚未登錄
QUOTA_ERROR_CODES = {-18019908, -18019907}
NOT_REGISTERED_CODE = -18019902

_KEY_HINT = (
    f"17TRACK 需要 API key：於 https://api.17track.net 註冊後，"
    f"把 key 設進環境變數 {API_KEY_ENV}（免費額度 200 筆，用量計在你自己的帳號）")


def _event_time(e: dict) -> str:
    """官方 schema：time_iso / time_utc 是字串，time_raw 是 {date,time,timezone} 物件。

    先前直接取 time_raw（dict 為 truthy）會把物件塞進宣告為 str 的欄位，
    到 CLI 依 time 排序時才炸 TypeError。
    """
    for key in ("time_iso", "time_utc"):
        v = e.get(key)
        if isinstance(v, str) and v:
            return v
    raw = e.get("time_raw")
    if isinstance(raw, dict):
        return " ".join(x for x in (raw.get("date"), raw.get("time")) if x).strip()
    return raw if isinstance(raw, str) else ""


def _quota_message(payload: dict) -> str | None:
    """額度錯誤有兩種出現位置：頂層 code，或（真實情況）data.rejected[].error。"""
    code, msg = payload.get("code"), str(payload.get("message", ""))
    if code and code != 0 and ("quota" in msg.lower() or "insufficient" in msg.lower()):
        return f"17TRACK 額度不足或已用盡（{msg}）"
    for item in (payload.get("data") or {}).get("rejected") or []:
        err = item.get("error") or {}
        if err.get("code") in QUOTA_ERROR_CODES:
            return (f"17TRACK 額度不足或已用盡（{err.get('message', '')}）—— "
                    f"請至 https://api.17track.net 查看你的帳號用量")
    return None


def parse_response(payload: dict, number: str) -> TrackResult:
    quota = _quota_message(payload)
    if quota:
        raise CarrierUnavailable(quota)

    data = payload.get("data")
    if not isinstance(data, dict) or ("accepted" not in data and "rejected" not in data):
        raise ParseError("17TRACK 回應格式非預期，請回報 issue")

    result = TrackResult(carrier="17track", number=number, found=False,
                         source_url=SOURCE_URL)
    for item in data.get("accepted") or []:
        if str(item.get("number")) != number:
            continue
        tracking = (item.get("track_info") or {}).get("tracking") or {}
        for provider in tracking.get("providers") or []:
            for e in provider.get("events") or []:
                loc = e.get("location")
                if isinstance(loc, dict):  # 文件標為字串，防禦性處理巢狀變體
                    loc = loc.get("city") or loc.get("state") or None
                result.events.append(TrackEvent(
                    time=_event_time(e),
                    status=e.get("description") or e.get("stage") or "",
                    location=loc or None))
    result.found = bool(result.events)
    return result


class SeventeenTrackAdapter:
    code = "17track"
    name = "17TRACK"

    def detect(self, number: str) -> bool:
        # 永不自動選用：呼叫要花使用者的額度，必須由使用者明確指定
        return False

    def track(self, number: str, carrier_code: int | None = None) -> TrackResult:
        key = os.environ.get(API_KEY_ENV, "").strip()
        if not key:
            raise CarrierUnavailable(_KEY_HINT)

        headers = {"17token": key, "Content-Type": "application/json"}
        body: list[dict] = [{"number": number}]
        if carrier_code:
            body[0]["carrier"] = carrier_code

        # register 對已登錄過的單號回 rejected(-18019901)，不額外扣額度；
        # 但 HTTP 層錯誤（key 失效 401/403、限流 429）必須當場講清楚，
        # 否則會被第二支呼叫的 RequestException 蓋成籠統的「連線失敗」。
        reg = requests.post(f"{API_BASE}/register", json=body, headers=headers,
                            timeout=REQUEST_TIMEOUT)
        self._raise_for_auth(reg)
        quota = _quota_message(reg.json() if reg.content else {})
        if quota:
            raise CarrierUnavailable(quota)

        resp = requests.post(f"{API_BASE}/gettrackinfo", json=body,
                             headers=headers, timeout=REQUEST_TIMEOUT)
        self._raise_for_auth(resp)
        resp.raise_for_status()
        return parse_response(resp.json(), number)

    @staticmethod
    def _raise_for_auth(resp) -> None:
        status = getattr(resp, "status_code", 200)
        if status in (401, 403):
            raise CarrierUnavailable(
                f"17TRACK 拒絕這把 API key（HTTP {status}）——"
                f"請確認 {API_KEY_ENV} 設定正確且帳號仍有效")
        if status == 429:
            raise CarrierUnavailable("17TRACK 請求過於頻繁（HTTP 429），請稍後再試")
