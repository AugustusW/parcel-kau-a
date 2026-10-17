"""Carrier adapter registry。

新增貨運公司：實作 CarrierAdapter（base.py Protocol）後在此註冊。
"""
from .base import CarrierAdapter
from .ecan import EcanAdapter
from .fusheng import FushengAdapter
from .kerrytj import KerrytjAdapter
from .pchome import PchomeAdapter
from .seventeentrack import SeventeenTrackAdapter
from .spx import SpxAdapter
from .tcat import TcatAdapter


CARRIERS: dict[str, CarrierAdapter] = {
    "tcat": TcatAdapter(),
    "kerrytj": KerrytjAdapter(),
    "ecan": EcanAdapter(),
    "pchome": PchomeAdapter(),
    "fusheng": FushengAdapter(),
    "spx": SpxAdapter(),
    # 聚合服務：需使用者自備 API key，detect() 永遠 False（不進自動判別）
    "17track": SeventeenTrackAdapter(),
}


# 物流商的靜態屬性集中在這裡，renderer、自動判別與 README 都從這裡讀，不在各處重複
# 硬編碼（spec §8）。auto_detect_allowed 是單號能不能在使用者沒指定物流商時被送去
# 試查；不在本表的 code 一律視為不允許（track._candidate_codes）。保留期取自各站公告：
# 黑貓 3 個月、宅配通 2 個月；其餘未公告為 None。verification_date 是維護者最後
# 確認 adapter 或官方查詢流程的年月，不是包裹狀態時間。
_TW = "+08:00"
CARRIER_META: dict[str, dict] = {
    "tcat": {"source_type": "official-http", "retention_days": 90,
             "auto_detect_allowed": True, "event_timezone": _TW, "verification_date": "2026-08"},
    "kerrytj": {"source_type": "official-http", "retention_days": None,
                "auto_detect_allowed": True, "event_timezone": _TW, "verification_date": "2026-08"},
    "ecan": {"source_type": "official-http", "retention_days": 60,
             "auto_detect_allowed": True, "event_timezone": _TW, "verification_date": "2026-08"},
    "pchome": {"source_type": "official-http", "retention_days": None,
               "auto_detect_allowed": True, "event_timezone": _TW, "verification_date": "2026-08"},
    "fusheng": {"source_type": "official-http", "retention_days": None,
                "auto_detect_allowed": True, "event_timezone": _TW, "verification_date": "2026-08"},
    "spx": {"source_type": "official-browser", "retention_days": None,
            "auto_detect_allowed": True, "event_timezone": _TW, "verification_date": "2026-08"},
    "17track": {"source_type": "third-party-17track", "retention_days": None,
                "auto_detect_allowed": False, "event_timezone": None, "verification_date": "2026-08"},
}
