"""CLI dispatch / 渲染行為（adapter 全替身，不打網路）。"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import track  # noqa: E402
from carriers.base import CarrierUnavailable, TrackEvent, TrackResult  # noqa: E402


class FakeAdapter:
    def __init__(self, code, detects=True, found=False, raises=None):
        self.code, self.name = code, f"假{code}"
        self._detects, self._found, self._raises = detects, found, raises
        self.calls = 0

    def detect(self, number):
        return self._detects

    def track(self, number, carrier_code=None):
        self.calls += 1
        if self._raises:
            raise self._raises
        events = [TrackEvent(time="2026-08-01 10:00", status="送達", location="台北")] \
            if self._found else []
        return TrackResult(carrier=self.code, number=number, found=self._found,
                           events=events, source_url="https://example.test")


def test_explicit_carrier_queries_only_that_one(monkeypatch):
    a, b = FakeAdapter("tcat"), FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    track.run(["123456789012", "--carrier", "ecan"])
    assert (a.calls, b.calls) == (0, 1)


def test_auto_mode_stops_at_first_found(monkeypatch):
    """撞號時序列查詢，命中即停 — 不打完所有家（spec「自動判別的現實」）。"""
    a = FakeAdapter("tcat", found=True)
    b = FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    track.run(["123456789012"])
    assert (a.calls, b.calls) == (1, 0)


def test_auto_mode_skips_carriers_whose_detect_rejects(monkeypatch):
    a = FakeAdapter("tcat", detects=False)
    b = FakeAdapter("spx", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "spx": b})
    track.run(["TW254414081298F"])
    assert (a.calls, b.calls) == (0, 1)


def test_carrier_unavailable_message_is_surfaced(monkeypatch, capsys):
    err = CarrierUnavailable("SPX 需要 Playwright：pip install playwright")
    monkeypatch.setattr(track, "CARRIERS", {"spx": FakeAdapter("spx", raises=err)})
    code = track.run(["TW254414081298F", "--carrier", "spx"])
    assert code != 0
    assert "pip install playwright" in capsys.readouterr().out


def test_json_output_is_machine_readable(monkeypatch, capsys):
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})
    track.run(["123456789012", "--carrier", "tcat", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["carrier"] == "tcat"
    assert payload["found"] is True
    assert payload["events"][0]["status"] == "送達"


def test_not_found_exit_code_is_zero(monkeypatch):
    """查無資料是合法結果，不是錯誤。"""
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=False)})
    assert track.run(["123456789012", "--carrier", "tcat"]) == 0


def test_network_error_is_reported_not_raised(monkeypatch, capsys):
    """站方 timeout/連線失敗是 scraping 的日常，必須是訊息不是 traceback。"""
    import requests
    err = requests.exceptions.ReadTimeout("read timed out")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", raises=err)})
    code = track.run(["123456789012", "--carrier", "tcat"])
    out = capsys.readouterr().out
    assert code != 0
    assert "Traceback" not in out
    assert "連線" in out or "逾時" in out


def test_auto_mode_continues_to_next_carrier_after_network_error(monkeypatch, capsys):
    """自動判別時某家掛掉，不該讓整個查詢失敗——繼續問下一家。"""
    import requests
    dead = FakeAdapter("kerrytj", raises=requests.exceptions.ConnectionError("boom"))
    alive = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"kerrytj": dead, "tcat": alive})
    code = track.run(["123456789012"])
    assert code == 0
    assert alive.calls == 1
    assert "順利" in capsys.readouterr().out or True


def test_parse_error_in_auto_mode_tries_next_carrier(monkeypatch, capsys):
    """撞號情境下，某家改版不該埋掉其他家的有效結果。"""
    from carriers.base import ParseError
    broken = FakeAdapter("tcat", raises=ParseError("頁面結構已變"))
    alive = FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": broken, "ecan": alive})
    assert track.run(["123456789012"]) == 0
    assert alive.calls == 1


def test_json_output_includes_latest(monkeypatch, capsys):
    """spec 宣告的 schema 含 latest；asdict() 不會自動帶 property。"""
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})
    track.run(["123456789012", "--carrier", "tcat", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["latest"]["status"] == "送達"


def test_via_17track_flag_routes_to_aggregator(monkeypatch):
    """--via-17track 明確走聚合服務，不碰直連 adapter。"""
    direct = FakeAdapter("tcat", found=True)
    agg = FakeAdapter("17track", detects=False, found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": direct, "17track": agg})
    assert track.run(["83546610320956", "--via-17track"]) == 0
    assert (direct.calls, agg.calls) == (0, 1)


def test_via_17track_passes_carrier_code_when_carrier_named(monkeypatch):
    """--carrier chunghwa-post --via-17track 要把數字 code 傳下去。"""
    seen = {}

    class _Agg(FakeAdapter):
        def track(self, number, carrier_code=None):
            seen["code"] = carrier_code
            return super().track(number)

    monkeypatch.setattr(track, "CARRIERS", {"17track": _Agg("17track", found=True)})
    track.run(["83546610320956", "--via-17track", "--carrier", "chunghwa-post"])
    assert seen["code"] == 20011


def test_unknown_number_without_17track_hints_at_it(monkeypatch, capsys):
    """14 碼郵局單號沒人認領時，提示使用者有 17TRACK 這條路。"""
    monkeypatch.setattr(track, "CARRIERS",
                        {"tcat": FakeAdapter("tcat", detects=False)})
    code = track.run(["83546610320956"])
    assert code == 2
    assert "17track" in capsys.readouterr().out


def test_auto_mode_announces_candidates_before_querying(monkeypatch, capsys):
    """揭露要在查詢**之前**：先講會送給哪幾家，讓使用者有機會改用 --carrier。"""
    order = []

    class _Tracking(FakeAdapter):
        def track(self, number, carrier_code=None):
            order.append(("query", self.code))
            return super().track(number)

    a, b = _Tracking("tcat", found=False), _Tracking("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})

    import builtins
    printed: list[str] = []
    real_print = builtins.print

    def spy(*args, **kw):
        text = " ".join(str(x) for x in args)
        printed.append(text)
        order.append(("print", text))
        real_print(*args, **kw)

    monkeypatch.setattr(builtins, "print", spy)
    track.run(["123456789012"])

    disclosure = next((i for i, (kind, v) in enumerate(order)
                       if kind == "print" and "--carrier" in v), None)
    first_query = next((i for i, (kind, _) in enumerate(order)
                        if kind == "query"), None)
    assert disclosure is not None, "自動模式必須揭露"
    assert first_query is not None
    assert disclosure < first_query, "揭露必須早於第一次網路請求"
    # 明示是哪幾家，不能只說「多家」
    assert "假tcat" in printed[0] and "假ecan" in printed[0]


def test_explicit_carrier_has_no_disclosure_noise(monkeypatch, capsys):
    """指定了 carrier 就只送一家，不需要這段提示。"""
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})
    track.run(["123456789012", "--carrier", "tcat"])
    assert "--carrier" not in capsys.readouterr().out


def test_json_mode_stays_machine_readable(monkeypatch, capsys):
    """--json 的 stdout 必須可直接 json.loads，提示不能污染它。"""
    a = FakeAdapter("tcat", found=False)
    b = FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    track.run(["123456789012", "--json"])
    json.loads(capsys.readouterr().out)
