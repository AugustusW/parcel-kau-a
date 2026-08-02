"""蝦皮店到店 SPX — headless 瀏覽器（Playwright，選配依賴）。

為什麼不走純 HTTP：SPX 的 tracking API
`GET spx.tw/api/v2/fleet_order/tracking/search?sls_tracking_number=<單號>|<token>`
其中 token 是前端 JS 計算的簽章（timestamp + 64 hex）。逆向該演算法會在站方改版
時立刻失效，維護成本高（見 spec ADR），因此改用 Playwright 載入站方頁面、由站方
自己的 JS 產生簽章。

導航界線：只使用首頁 `spx.tw/` 的公開查詢框；不觸碰 robots.txt disallow 的
`/detail/` 路徑。
"""
from __future__ import annotations

import re

from .base import (REQUEST_TIMEOUT, CarrierUnavailable, ParseError,
                   TrackEvent, TrackResult)

import endpoints


def _source() -> str:
    return endpoints.get("spx")["source"]
# SPX 單號：TW 開頭（UNVERIFIED: 長度以 2026-08-02 觀察的 15 碼為準，需真實單號校準）
NUMBER_RE = re.compile(r"^TW[0-9A-Z]{10,20}$", re.IGNORECASE)

_PKG_HINT = ("SPX 需要 Playwright："
             "pip install playwright && playwright install chromium")
_BROWSER_HINT = ("SPX 需要 Chromium：請執行 playwright install chromium")


def _load_playwright():
    """回傳 (sync_playwright, PlaywrightError)；測試以 monkeypatch 替換。"""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    return sync_playwright, PlaywrightError


def build_result(rows: list[dict], number: str) -> TrackResult:
    events = [TrackEvent(time=r.get("time", ""), status=r.get("status", ""),
                         location=r.get("location")) for r in rows]
    return TrackResult(carrier="spx", number=number, found=bool(events),
                       events=events, source_url=_source())


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
        rows: list[dict] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                # 與其他 adapter 共用同一個 10s 上限（plan Global Constraints）
                page.set_default_timeout(REQUEST_TIMEOUT * 1000)
                page.set_default_navigation_timeout(REQUEST_TIMEOUT * 1000)
                page.goto(_source(), wait_until="domcontentloaded")
                box = page.get_by_role("textbox").first
                box.fill(number)
                page.get_by_role("button", name="追蹤").click()
                # 站方以 XHR 回填；等結果或錯誤訊息任一出現
                page.wait_for_timeout(2000)
                # UNVERIFIED: 結果 DOM 結構需真實單號校準；先以「含時間戳格式的列」廣義抓
                for el in page.locator("li, tr, div").all():
                    text = (el.text_content() or "").strip()
                    m = re.match(r"(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2})\s*(.+)",
                                 text)
                    if m and len(text) < 200:
                        rows.append({"time": m.group(1), "status": m.group(2)})
            finally:
                browser.close()
        return build_result(rows, number)
