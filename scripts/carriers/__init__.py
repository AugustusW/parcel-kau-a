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
