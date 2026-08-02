"""事件排序必須按真實時間，不是按字串。

各家時間格式不一（斜線/橫線、補零/不補零、有無秒、ISO 含時區、宅配通還有「上午」），
字串比大小只在格式完全一致時才等於時間比大小。跨月時會靜靜給出錯的「最新狀態」，
而且不報錯——外部 review v0.2.0 指出，實測宅配通確實用 2026/8/2 這種不補零格式。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers.base import TrackEvent, TrackResult  # noqa: E402


def _r(times):
    return TrackResult(carrier="x", number="n", found=True,
                       events=[TrackEvent(time=t, status=f"s{i}")
                               for i, t in enumerate(times)])


def test_latest_is_correct_with_unpadded_month_and_day():
    """宅配通格式：'2026/8/2' 的 '8' 字串上大於 '12'——跨月時 max() 會挑錯。"""
    r = _r(["2026/8/2 13:28", "2026/12/1 09:00"])
    assert r.latest.time == "2026/12/1 09:00"


def test_latest_is_correct_across_month_boundary():
    r = _r(["2026/08/28 10:00", "2026/09/02 09:00"])
    assert r.latest.time == "2026/09/02 09:00"


def test_latest_handles_mixed_separators():
    r = _r(["2026/08/02 13:28", "2026-08-03 09:00"])
    assert r.latest.time == "2026-08-03 09:00"


def test_latest_handles_iso_with_timezone():
    r = _r(["2026-08-01T09:00:00+08:00", "2026-08-01T14:30:00+08:00"])
    assert r.latest.time == "2026-08-01T14:30:00+08:00"


def test_latest_handles_ecan_am_pm_marker():
    """宅配通頁面帶「上午/下午」：下午 1 點要大於上午 10 點。"""
    r = _r(["2026/8/2 上午 10:54:06", "2026/8/2 下午 01:20:00"])
    assert r.latest.time == "2026/8/2 下午 01:20:00"


def test_display_string_is_preserved_untouched():
    """排序用解析後的時間，顯示仍用原站字串——不改變使用者看到的內容。"""
    r = _r(["2026/8/2 13:28"])
    assert r.events[0].time == "2026/8/2 13:28"


def test_unparseable_times_do_not_crash():
    """解析不了就退回字串比較，絕不能因為格式意外而炸掉查詢。"""
    r = _r(["還沒有資料", "2026/08/02 13:28"])
    assert r.latest is not None


def test_empty_events_still_none():
    assert TrackResult(carrier="x", number="n", found=False).latest is None


def test_cli_render_order_matches_latest(monkeypatch, capsys):
    """渲染順序與 latest 必須用同一把鑰匙，否則首行跟「最新」會兜不起來。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import track

    class _A:
        code, name = "x", "假x"

        def detect(self, n):
            return True

        def track(self, n, carrier_code=None):
            return _r(["2026/8/28 10:00", "2026/9/2 09:00", "2026/8/30 12:00"])

    monkeypatch.setattr(track, "CARRIERS", {"x": _A()})
    track.run(["123456789012", "--carrier", "x", "--no-record"])
    lines = [l for l in capsys.readouterr().out.splitlines() if "2026" in l and "來源" not in l]
    assert lines[0].startswith("2026/9/2"), f"首行應為最新，實際：{lines}"
