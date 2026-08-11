"""共用資料模型與 adapter 介面。

單號屬個資鄰接資料。adapter 層本身不落地任何東西（無 cache、無 log），每次現查；
唯一的落地是 history.py 的查詢紀錄（單號→貨運對應，用來避免輪巡多家），
詳見該模組與 README 隱私段。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol

REQUEST_TIMEOUT = 10  # 秒；所有 adapter 共用，fail fast 不重試
# 版本只在這裡定義一次；USER_AGENT 由它推導，避免發版時忘了同步（外部 review v0.2.0
# 指出 v0.2.0 出貨後 UA 仍停在 0.1.0）。
VERSION = "0.4.0"
USER_AGENT = f"parcel-kau-a/{VERSION}"


class CarrierUnavailable(Exception):
    """環境缺依賴（如 SPX 未裝 Playwright）時拋出，訊息需含補救指令。"""


class ParseError(Exception):
    """網站頁面結構已變（scraping 專案的預期壽命問題），訊息引導使用者回報 issue。"""


# 各站時間格式不一：斜線/橫線、補零/不補零、有無秒、ISO 帶時區、宅配通還帶「上午」。
# 直接用字串比大小只在格式一致時才等於時間比大小——'2026/8/2' 的 '8' 字串上大於 '12'，
# 跨月時會靜靜挑錯「最新狀態」且不報錯（外部 review v0.2.0）。
_TIME_RE = re.compile(
    r"(?P<y>\d{4})[/-](?P<mo>\d{1,2})[/-](?P<d>\d{1,2})"
    r"(?:[ T]+(?P<ampm>上午|下午)?\s*(?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?)?")


def parse_event_time(text: str) -> Optional[datetime]:
    """把各站時間字串解析成 datetime；解析不了回 None（呼叫端退回字串比較）。

    刻意忽略時區位移：各站都是台灣時間，同一筆查詢內比較不受影響，
    引入 tzinfo 反而會讓 naive/aware 混用時 TypeError。
    """
    m = _TIME_RE.search(text or "")
    if not m:
        return None
    g = m.groupdict()
    hour = int(g["h"] or 0)
    if g["ampm"] == "下午" and hour < 12:
        hour += 12
    elif g["ampm"] == "上午" and hour == 12:
        hour = 0
    try:
        return datetime(int(g["y"]), int(g["mo"]), int(g["d"]),
                        hour, int(g["mi"] or 0), int(g["s"] or 0))
    except ValueError:
        return None


@dataclass
class TrackEvent:
    time: str  # 原站字串原樣保留——排序用 parse_event_time()，顯示用這個
    status: str
    location: Optional[str] = None

    @property
    def sort_key(self) -> tuple[int, object]:
        """可解析的時間優先且互相比較；解析不了的退到後面按字串排。"""
        parsed = parse_event_time(self.time)
        return (1, parsed) if parsed else (0, self.time)


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
        return max(self.events, key=lambda e: e.sort_key)


class CarrierAdapter(Protocol):
    code: str
    name: str

    def detect(self, number: str) -> bool: ...

    def track(self, number: str) -> TrackResult: ...
