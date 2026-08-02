"""查詢紀錄：記住單號屬於哪家，讓後續查詢只送一家（spec 2026-08-02-parcel-history-record）。

隱私取捨：本機多存一筆，換第三方揭露面從最多五家降為一家。因此這裡的測試不只驗
功能，也驗「不該存的不存」與「刪得掉」。
"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers.base import TrackEvent, TrackResult  # noqa: E402
import history  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv(history.HOME_ENV, str(tmp_path))
    return tmp_path


def _found(number="135079340105", carrier="tcat", status="順利送達", time="2026/08/02 13:28"):
    return TrackResult(carrier=carrier, number=number, found=True,
                       events=[TrackEvent(time=time, status=status, location="甲營業所")],
                       source_url="https://example.test")


def test_found_result_is_recorded(home):
    history.record(_found())
    assert history.lookup("135079340105") == "tcat"


def test_not_found_result_is_never_recorded(home):
    history.record(TrackResult(carrier="tcat", number="999", found=False))
    assert history.lookup("999") is None
    assert not history.path().exists(), "查無資料不該憑空建立紀錄檔"


def test_lookup_misses_are_silent(home):
    assert history.lookup("000000000000") is None


def test_record_file_is_owner_only(home):
    history.record(_found())
    mode = stat.S_IMODE(os.stat(history.path()).st_mode)
    assert mode == 0o600, f"單號屬個資鄰接，不可讓同機他人讀取（實際 {oct(mode)}）"


def test_record_stores_only_expected_fields(home):
    history.record(_found())
    entry = json.loads(history.path().read_text())["135079340105"]
    assert set(entry) == {"carrier", "last_status", "last_event_time",
                          "first_seen", "last_checked", "looks_complete"}


def test_first_seen_survives_recheck_but_last_checked_moves(home):
    history.record(_found(status="配送中"))
    first = json.loads(history.path().read_text())["135079340105"]
    history.record(_found(status="順利送達"))
    second = json.loads(history.path().read_text())["135079340105"]
    assert second["first_seen"] == first["first_seen"]
    assert second["last_checked"] >= first["last_checked"]
    assert second["last_status"] == "順利送達"


@pytest.mark.parametrize("status,expected", [
    ("順利送達", True), ("已送達", True), ("配送完成", True), ("順利投遞", True),
    ("已集貨", False), ("配送中", False), ("超商代收", False), ("分理作業中", False),
])
def test_completion_detection(home, status, expected):
    history.record(_found(status=status))
    assert history.lookup_entry("135079340105")["looks_complete"] is expected


def test_forget_removes_one_entry(home):
    history.record(_found(number="111111111111"))
    history.record(_found(number="222222222222", carrier="ecan"))
    assert history.forget("111111111111") is True
    assert history.lookup("111111111111") is None
    assert history.lookup("222222222222") == "ecan"


def test_forget_unknown_number_reports_false(home):
    assert history.forget("000000000000") is False


def test_forget_all_clears_everything(home):
    history.record(_found(number="111111111111"))
    history.record(_found(number="222222222222"))
    history.forget_all()
    assert history.entries() == {}


def test_corrupt_file_degrades_to_no_history(home, capsys):
    """紀錄毀損不可讓查詢失敗——視為無紀錄繼續。"""
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text("{ this is not json")
    assert history.lookup("135079340105") is None
    assert history.entries() == {}


def test_corrupt_file_is_not_silently_overwritten_on_read(home):
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text("{ broken")
    history.lookup("x")
    assert history.path().read_text() == "{ broken", "唯讀操作不該動使用者的檔案"


def test_write_is_atomic_leaving_no_temp_files(home):
    history.record(_found())
    leftovers = [p.name for p in history.path().parent.iterdir()
                 if p.name != history.path().name]
    assert leftovers == [], f"寫入後不該留暫存檔：{leftovers}"


def test_completion_keywords_reject_forward_looking_phrases(home):
    """「預計送達」不是已完成——短關鍵字容易被這類片語誤觸發（architect MEDIUM）。"""
    for status in ("預計送達", "預定投遞", "預估送達時間", "尚未送達"):
        history.forget_all()
        history.record(_found(status=status))
        assert history.lookup_entry("135079340105")["looks_complete"] is False, status


def test_temp_file_is_owner_only_before_content_is_written(home, monkeypatch):
    """權限要在寫入內容前就設好，否則有一段時間單號是他人可讀的（architect MEDIUM）。"""
    seen: list[int] = []
    real_fdopen = os.fdopen

    def spy(fd, *a, **kw):
        # 內容尚未寫入時，先確認該 fd 對應的檔案已是 600
        seen.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return real_fdopen(fd, *a, **kw)

    monkeypatch.setattr(os, "fdopen", spy)
    history.record(_found())
    assert seen and seen[0] == 0o600, f"寫入前權限應已是 600，實際 {[oct(m) for m in seen]}"


def test_single_malformed_entry_does_not_crash_callers(home):
    """毀損的定義包含「單筆 entry 型別錯」，不只整檔 JSON 壞掉。

    模組宣稱「紀錄毀損時一律降級為無紀錄」，但 record() 與 --history 原本都假設
    每個 value 是 dict，遇到字串就 AttributeError 裸拋（2026-08-02 code review）。
    在 entries() 一次擋掉，讓所有呼叫端繼承這個保證。
    """
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text('{"123456789012": "not-a-dict", "999999999999": {"carrier": "tcat"}}',
                              encoding="utf-8")
    assert history.entries() == {"999999999999": {"carrier": "tcat"}}
    assert history.lookup("123456789012") is None
    history.record(_found(number="123456789012"))          # 不可 raise
    assert history.lookup("123456789012") == "tcat"


@pytest.mark.parametrize("status,expected", [
    ("投遞中", False),      # 含「投遞」但還在路上——原本會被標成可刪
    ("投遞失敗", False),
    ("配送異常", False),
    ("退回中", False),
    ("順利投遞", True),
    ("投遞完成", True),
    ("已投遞", True),
])
def test_completion_rejects_in_progress_and_failed_states(home, status, expected):
    """「投遞」是短詞，投遞中／投遞失敗都含它（外部 review v0.2.0）。"""
    assert history.looks_complete(status) is expected
