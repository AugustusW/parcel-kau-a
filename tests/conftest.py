"""測試一律隔離查詢紀錄，絕不碰使用者真實的 ~/.cache/parcel-kau-a/。

沒有這層隔離時，寫入紀錄的測試會污染真實檔案，後續測試又讀到它——本地全綠、
CI 全綠，卻在開發者機器上寫進真實單號（2026-08-02 實際踩到）。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import history  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_history(tmp_path, monkeypatch):
    monkeypatch.setenv(history.HOME_ENV, str(tmp_path / "parcel-home"))
