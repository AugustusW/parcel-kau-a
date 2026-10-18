"""蝦皮店到店 SPX — headless 瀏覽器（Playwright，選配依賴）。

為什麼不走純 HTTP：SPX 的 tracking API
`GET spx.tw/api/v2/fleet_order/tracking/search?sls_tracking_number=<單號>|<token>`
其中 token 是前端 JS 計算的簽章（timestamp + 64 hex）。逆向該演算法會在站方改版
時立刻失效，維護成本高（見 spec ADR），因此改用 Playwright 載入站方頁面、由站方
自己的 JS 產生簽章。

資料來源：按下「追蹤」後，站方頁面自己發出上面那個 API 請求；本 adapter 只在旁邊讀取
它的 JSON 回應（`tracking_list[].timestamp` 為 Unix 秒），不解析畫面文字——v0.5.1 以前
用正則找畫面上的日期，真實頁面的日期格式不同，每一件都被判成查無資料。

導航界線：只使用首頁 `spx.tw/` 的公開查詢框。查到資料後網址列會變成 `/detail/<單號>`，
那是頁面內的前端路由，不會向伺服器請求 robots.txt disallow 的 `/detail/`
（2026-10-18 擷取時記錄全部請求確認過）。

風控：站方會對無頭瀏覽器回 403（`action_type: 2`）。本專案不繞過風控，被擋時明確
回報並建議改走 17TRACK，絕不把它當成查無資料。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .base import (REQUEST_TIMEOUT, CarrierUnavailable, ParseError,
                   TrackEvent, TrackResult)

import endpoints


def _source() -> str:
    return endpoints.get("spx")["source"]
# SPX 單號：TW 開頭。2026-10-18 兩筆真實單號皆為 15 碼（TW＋13 碼，末碼可能是英文字母）
NUMBER_RE = re.compile(r"^TW[0-9A-Z]{10,20}$", re.IGNORECASE)

_PKG_HINT = ("SPX 需要 Playwright："
             "pip install playwright && playwright install chromium")
_BROWSER_HINT = ("SPX 需要 Chromium：請執行 playwright install chromium")
_BLOCKED_HINT = ("蝦皮擋下了這次自動查詢（站方風控對自動化瀏覽器回 403），本工具不繞過風控。"
                 "可以用瀏覽器開 https://spx.tw/ 自己查，或自備 17TRACK key 改用："
                 "track.py <單號> --carrier spx --via-17track")
_API_PATH = "/api/v2/fleet_order/tracking/search"
_TW = timezone(timedelta(hours=8))
# 站方對不存在的單號回 HTTP 200、retcode -1000、訊息「Server error」、data 為空
# （2026-10-18 以假單號實測）。字面像伺服器錯誤，但這是查無資料的實際回應。
_NOT_FOUND_RETCODE = -1000


def _load_playwright():
    """回傳 (sync_playwright, PlaywrightError)；測試以 monkeypatch 替換。"""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    return sync_playwright, PlaywrightError


def _is_blocked(status: int, body) -> bool:
    return status == 403 or (isinstance(body, dict) and (
        body.get("redirect_to_error_page") is True or "action_type" in body))


def parse_api(status: int, body, number: str) -> TrackResult:
    """把 tracking/search 的回應轉成 TrackResult。被擋 raise CarrierUnavailable，
    看不懂的回應 raise ParseError——兩者都不可以被當成查無資料。"""
    if _is_blocked(status, body):
        raise CarrierUnavailable(_BLOCKED_HINT)
    if status != 200 or not isinstance(body, dict):
        raise ParseError(f"蝦皮查詢回應不如預期（HTTP {status}），請回報 issue")
    retcode, data = body.get("retcode"), body.get("data")
    if retcode == _NOT_FOUND_RETCODE and not data:
        return TrackResult(carrier="spx", number=number, found=False, source_url=_source())
    if retcode != 0 or not isinstance(data, dict):
        raise ParseError(f"蝦皮查詢回應不如預期（retcode {retcode}），請回報 issue")
    rows = data.get("tracking_list") or []
    if not isinstance(rows, list):
        raise ParseError("蝦皮查詢回應的 tracking_list 格式已變，請回報 issue")
    events = []
    for row in rows:
        try:
            when = datetime.fromtimestamp(int(row["timestamp"]), _TW)
            events.append(TrackEvent(time=when.strftime("%Y/%m/%d %H:%M"),
                                     status=str(row.get("message") or row.get("status") or "")))
        except (KeyError, TypeError, ValueError, OSError) as e:
            raise ParseError(f"蝦皮查詢回應的事件格式已變，請回報 issue（{e}）") from e
    return TrackResult(carrier="spx", number=number, found=bool(events), events=events,
                       source_url=_source())


class SpxAdapter:
    code = "spx"
    name = "蝦皮店到店"

    def detect(self, number: str) -> bool:
        return bool(NUMBER_RE.match(number))

    def track(self, number: str) -> TrackResult:
        try:
            sync_playwright, playwright_error = _load_playwright()
        except ImportError as e:
            raise CarrierUnavailable(_PKG_HINT) from e

        try:
            return self._scrape(sync_playwright, number)
        except playwright_error as e:
            # 套件在但 chromium 沒下載過，Playwright 拋 Error("Executable doesn't exist")
            if "xecutable" in str(e) or "install" in str(e).lower():
                raise CarrierUnavailable(_BROWSER_HINT) from e
            # 其餘（含 selector 逾時 = DOM 改版的主要徵兆）比照其他 adapter 走 ParseError，
            # 讓 CLI 有明確訊息可印，而不是把 Playwright 例外裸拋給使用者
            raise ParseError(f"蝦皮頁面結構已變或載入逾時，請回報 issue（{e}）") from e

    def _scrape(self, sync_playwright, number: str) -> TrackResult:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                # 與其他 adapter 共用同一個 10s 上限（plan Global Constraints）
                page.set_default_timeout(REQUEST_TIMEOUT * 1000)
                page.set_default_navigation_timeout(REQUEST_TIMEOUT * 1000)
                page.goto(_source(), wait_until="domcontentloaded")
                page.get_by_role("textbox").first.fill(number)
                with page.expect_response(lambda r: _API_PATH in r.url) as info:
                    page.get_by_role("button", name="追蹤").click()
                response = info.value
                try:
                    body = response.json()
                except Exception:  # 非 JSON（例如錯誤頁）：交給 parse_api 依狀態碼判斷
                    body = None
                return parse_api(response.status, body, number)
            finally:
                browser.close()
