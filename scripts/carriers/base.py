"""共用資料模型與 adapter 介面。

單號屬個資鄰接資料。adapter 層本身不落地任何東西（無 cache、無 log），每次現查；
唯一的落地是 history.py 的查詢紀錄（單號→貨運對應，用來避免輪巡多家），
詳見該模組與 README 隱私段。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

REQUEST_TIMEOUT = 10  # 秒；所有 adapter 共用，fail fast 不重試
USER_AGENT = "parcel-kau-a/0.1.0"


class CarrierUnavailable(Exception):
    """環境缺依賴（如 SPX 未裝 Playwright）時拋出，訊息需含補救指令。"""


class ParseError(Exception):
    """網站頁面結構已變（scraping 專案的預期壽命問題），訊息引導使用者回報 issue。"""


@dataclass
class TrackEvent:
    time: str  # 原站字串格式，不轉 timezone（各站皆台灣時間）
    status: str
    location: Optional[str] = None


@dataclass
class TrackResult:
    carrier: str
    number: str
    found: bool
    events: list[TrackEvent] = field(default_factory=list)
    source_url: str = ""

    @property
    def latest(self) -> Optional[TrackEvent]:
        if not self.events:
            return None
        return max(self.events, key=lambda e: e.time)


class CarrierAdapter(Protocol):
    code: str
    name: str

    def detect(self, number: str) -> bool: ...

    def track(self, number: str) -> TrackResult: ...
