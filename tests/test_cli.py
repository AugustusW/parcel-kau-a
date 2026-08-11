"""CLI dispatch / 渲染行為（adapter 全替身，不打網路）。"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import track  # noqa: E402
from carriers.base import CarrierUnavailable, TrackEvent, TrackResult  # noqa: E402


class FakeAdapter:
    def __init__(self, code, detects=True, found=False, raises=None, status="送達"):
        self.code, self.name = code, f"假{code}"
        self._detects, self._found, self._raises = detects, found, raises
        self._status = status
        self.calls = 0

    def detect(self, number):
        return self._detects

    def track(self, number, carrier_code=None):
        self.calls += 1
        if self._raises:
            raise self._raises
        events = [TrackEvent(time="2026-08-01 10:00", status=self._status,
                             location="台北")] if self._found else []
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
    assert "假tcat" in capsys.readouterr().out, "應回報實際查到的那家"


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


# ── 查詢紀錄整合（spec 2026-08-02-parcel-history-record）────────────────

@pytest.fixture
def hist_home(tmp_path):
    """紀錄目錄已由 conftest 的 autouse fixture 隔離；此處僅供需要路徑的測試取用。"""
    return tmp_path


def test_known_number_queries_only_the_recorded_carrier(monkeypatch, hist_home):
    """紀錄命中＝只送一家，這正是本功能的隱私價值。"""
    import history
    history.record(TrackResult(carrier="ecan", number="123456789012", found=True,
                               events=[TrackEvent(time="t", status="配送中")]))
    a, b = FakeAdapter("tcat", found=True), FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    track.run(["123456789012"])
    assert (a.calls, b.calls) == (0, 1), "有紀錄就不該再問其他家"


def test_known_number_skips_the_multi_carrier_disclosure(monkeypatch, hist_home, capsys):
    """只送一家時就沒有「會送給多家」這回事，不該再印那段揭露。"""
    import history
    history.record(TrackResult(carrier="ecan", number="123456789012", found=True,
                               events=[TrackEvent(time="t", status="配送中")]))
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat"),
                                            "ecan": FakeAdapter("ecan", found=True)})
    track.run(["123456789012"])
    out = capsys.readouterr().out
    assert "將依序查詢" not in out
    assert "查詢紀錄" in out, "應告知使用者這次是依紀錄直達"


def test_stale_record_falls_back_to_polling(monkeypatch, hist_home, capsys):
    """紀錄過時（該家已查無）→ 退回輪巡，且退回前要重新揭露。"""
    import history
    history.record(TrackResult(carrier="tcat", number="123456789012", found=True,
                               events=[TrackEvent(time="t", status="配送中")]))
    a = FakeAdapter("tcat", found=False)          # 紀錄指向這家，但已查無
    b = FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    track.run(["123456789012"])
    assert (a.calls, b.calls) == (1, 1)
    out = capsys.readouterr().out
    # 先講了「只查這一家」，就不能默默多問別家
    assert "改試其餘" in out and "假ecan" in out


def test_found_lookup_writes_a_record(monkeypatch, hist_home):
    import history
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})
    track.run(["123456789012", "--carrier", "tcat"])
    assert history.lookup("123456789012") == "tcat"


def test_no_record_flag_suppresses_writing(monkeypatch, hist_home):
    import history
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})
    track.run(["123456789012", "--carrier", "tcat", "--no-record"])
    assert history.lookup("123456789012") is None


def test_completed_parcel_offers_the_delete_command(monkeypatch, hist_home, capsys):
    """需求 3：CLI 只標記可刪並給指令，不做互動提示（agent 環境會卡死）。"""
    monkeypatch.setattr(track, "CARRIERS",
                        {"tcat": FakeAdapter("tcat", found=True, status="順利送達")})
    track.run(["123456789012", "--carrier", "tcat"])
    out = capsys.readouterr().out
    assert "--forget 123456789012" in out


def test_in_transit_parcel_does_not_offer_deletion(monkeypatch, hist_home, capsys):
    monkeypatch.setattr(track, "CARRIERS",
                        {"tcat": FakeAdapter("tcat", found=True, status="配送中")})
    track.run(["123456789012", "--carrier", "tcat"])
    assert "--forget" not in capsys.readouterr().out


def test_forget_flag_deletes_without_querying(monkeypatch, hist_home, capsys):
    import history
    history.record(TrackResult(carrier="tcat", number="123456789012", found=True,
                               events=[TrackEvent(time="t", status="順利送達")]))
    a = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a})
    assert track.run(["--forget", "123456789012"]) == 0
    assert a.calls == 0, "刪紀錄不該順便發查詢"
    assert history.lookup("123456789012") is None


def test_history_flag_lists_records(monkeypatch, hist_home, capsys):
    import history
    history.record(TrackResult(carrier="tcat", number="123456789012", found=True,
                               events=[TrackEvent(time="t", status="順利送達")]))
    assert track.run(["--history"]) == 0
    out = capsys.readouterr().out
    assert "123456789012" in out and "順利送達" in out


def test_json_output_unaffected_by_history_notices(monkeypatch, hist_home, capsys):
    monkeypatch.setattr(track, "CARRIERS",
                        {"tcat": FakeAdapter("tcat", found=True, status="順利送達")})
    track.run(["123456789012", "--carrier", "tcat", "--json"])
    json.loads(capsys.readouterr().out)



# ── 未結案清單（spec 2026-08-07-parcel-pending-list）────────────────────

def _remember(number, status, event_time="2026-08-01 10:00", carrier="tcat"):
    import history
    history.record(TrackResult(carrier=carrier, number=number, found=True,
                               events=[TrackEvent(time=event_time, status=status)]))


def test_pending_flag_lists_only_unfinished_parcels(hist_home, capsys):
    _remember("111111111111", "配送中")
    _remember("222222222222", "順利送達")
    assert track.run(["--pending"]) == 0
    out = capsys.readouterr().out
    assert "111111111111" in out
    assert "222222222222" not in out, "已完成的不該出現在未結案清單"


def test_pending_flag_sends_no_network_request(monkeypatch, hist_home):
    """1A 決策：這個清單純讀本機紀錄，一個請求都不發。"""
    _remember("111111111111", "配送中")
    a = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a})
    track.run(["--pending"])
    assert a.calls == 0


def test_pending_flag_distinguishes_empty_history_from_all_complete(hist_home, capsys):
    """兩種「沒東西」講同一句話會讓使用者以為功能壞了，必須分開。"""
    assert track.run(["--pending"]) == 0
    assert "查詢紀錄是空的" in capsys.readouterr().out

    _remember("222222222222", "順利送達")
    assert track.run(["--pending"]) == 0
    out = capsys.readouterr().out
    assert "沒有未結案" in out
    assert "--forget" in out, "全部完成時要提示怎麼清掉紀錄"


def test_pending_flag_shows_days_since_the_last_event(hist_home, capsys):
    stale = (datetime.now() - timedelta(days=9)).strftime("%Y/%m/%d %H:%M")
    _remember("111111111111", "配送中", event_time=stale)
    track.run(["--pending"])
    assert "9 天沒更新" in capsys.readouterr().out


def test_pending_flag_says_today_instead_of_zero_days(hist_home, capsys):
    today = datetime.now().strftime("%Y/%m/%d %H:%M")
    _remember("111111111111", "配送中", event_time=today)
    track.run(["--pending"])
    out = capsys.readouterr().out
    assert "0 天" not in out and "今天" in out


def test_pending_flag_omits_the_age_when_time_is_unparseable(hist_home, capsys):
    _remember("111111111111", "配送中", event_time="時間不詳")
    assert track.run(["--pending"]) == 0
    out = capsys.readouterr().out
    assert "111111111111" in out
    assert "沒更新" not in out, "算不出天數就不要編一個出來"


def test_pending_flag_shows_carrier_name_and_status(hist_home, capsys):
    _remember("111111111111", "配送中", carrier="ecan")
    track.run(["--pending"])
    out = capsys.readouterr().out
    assert "台灣宅配通" in out and "配送中" in out


def test_missing_carrier_shows_a_visible_marker_in_both_listings(hist_home, capsys):
    """`carrier` 為空字串與整個缺鍵，兩者都顯示「?」。

    原本只有「缺鍵」會走到 "?"；欄位存在但是空字串時 `e.get("carrier", "?")` 回空字串，
    印出來是一段空白。那是 dict.get 預設值語意的副作用，不是設計決定——空白欄位看起來
    像對齊沒對好，「?」才講得出「這裡本來該有東西」。兩條路徑統一為後者
    （fast-code-refiner 2026-08-07 指出行為改變，實測確認後採用新行為並補上本測試）。
    """
    import history
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text(
        '{"111111111111": {"carrier": "", "last_status": "配送中"},'
        ' "222222222222": {"last_status": "配送中"}}', encoding="utf-8")
    for flag in ("--pending", "--history"):
        assert track.run([flag]) == 0
        out = capsys.readouterr().out
        for number in ("111111111111", "222222222222"):
            line = next(ln for ln in out.splitlines() if ln.startswith(number))
            assert "?" in line, f"{flag} 的 {number} 應顯示 ?：{line!r}"


def test_pending_flag_warns_once_about_a_corrupt_file(hist_home, capsys):
    """紀錄毀損時降級為空，但警告只該出現一次（讀兩次檔就會印兩次）。"""
    import history
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text("{ not json", encoding="utf-8")
    assert track.run(["--pending"]) == 0
    captured = capsys.readouterr()
    assert captured.err.count("查詢紀錄無法讀取") == 1
    assert "查詢紀錄是空的" in captured.out


def test_unavailable_carrier_does_not_abort_auto_mode(monkeypatch, capsys):
    """SPX 沒裝 Playwright 不該讓整趟自動查詢中止——其他家還能查。"""
    from carriers.base import CarrierUnavailable
    dead = FakeAdapter("spx", raises=CarrierUnavailable("SPX 需要 Playwright"))
    alive = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"spx": dead, "tcat": alive})
    assert track.run(["123456789012"]) == 0
    assert alive.calls == 1
    assert "Playwright" in capsys.readouterr().out


def test_unavailable_carrier_is_fatal_when_explicitly_requested(monkeypatch, capsys):
    """但使用者指名要查那家時，用不了就是用不了。"""
    from carriers.base import CarrierUnavailable
    dead = FakeAdapter("spx", raises=CarrierUnavailable("SPX 需要 Playwright"))
    monkeypatch.setattr(track, "CARRIERS", {"spx": dead})
    assert track.run(["TW254414081298F", "--carrier", "spx"]) == 3
    assert "Playwright" in capsys.readouterr().out


def test_history_write_failure_does_not_swallow_the_result(monkeypatch, capsys):
    """紀錄是輔助功能：寫不進去也必須先把查到的貨態給使用者。

    history.py 自述「絕不讓它擋住主功能」，但那只兌現了讀取毀損；寫入失敗
    （目錄唯讀／磁碟滿／檔案被佔用）原本會在輸出前就 raise（外部 review v0.2.0）。
    """
    import history
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})

    def boom(_result):
        raise OSError("Read-only file system")

    monkeypatch.setattr(history, "record", boom)
    assert track.run(["123456789012", "--carrier", "tcat"]) == 0
    out, err = capsys.readouterr()
    assert "假tcat" in out, "查詢結果必須照樣輸出"
    assert "Read-only" in err, "寫入失敗要講，但走 stderr 不干擾 stdout"


def test_history_write_failure_keeps_json_output_parseable(monkeypatch, capsys):
    import history
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})
    monkeypatch.setattr(history, "record", lambda _r: (_ for _ in ()).throw(OSError("disk full")))
    track.run(["123456789012", "--carrier", "tcat", "--json"])
    json.loads(capsys.readouterr().out)


# ── --refresh-pending：對未結案清單逐一即時查詢（spec 2026-08-11-parcel-refresh-pending）─

def test_refresh_pending_reports_empty_history(hist_home, capsys):
    """跟 --pending 一樣：兩種「沒東西」要分開講。"""
    assert track.run(["--refresh-pending"]) == 0
    assert "查詢紀錄是空的" in capsys.readouterr().out


def test_refresh_pending_reports_all_complete(hist_home, capsys):
    _remember("222222222222", "順利送達")
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "沒有未結案" in out
    assert "--forget" in out


def test_refresh_pending_sends_no_request_when_nothing_pending(monkeypatch, hist_home):
    _remember("222222222222", "順利送達", carrier="tcat")
    a = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a})
    track.run(["--refresh-pending"])
    assert a.calls == 0


def test_refresh_pending_marks_newly_delivered_as_new_completion(monkeypatch, hist_home, capsys):
    _remember("111111111111", "配送中", carrier="tcat", event_time="2026-07-01 09:00")
    fresh = FakeAdapter("tcat", found=True, status="順利送達")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": fresh})
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "新結案" in out
    assert "111111111111" in out and "順利送達" in out


def test_refresh_pending_marks_changed_status_as_progress(monkeypatch, hist_home, capsys):
    """狀態變了，但新狀態還不算完成——不是新結案，是有新進度。"""
    _remember("111111111111", "已集貨", carrier="tcat", event_time="2026-07-01 09:00")
    fresh = FakeAdapter("tcat", found=True, status="配送中")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": fresh})
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "有新進度" in out
    assert "無變化" not in out
    assert "新結案" not in out


def test_refresh_pending_marks_unchanged_status_as_no_change(monkeypatch, hist_home, capsys):
    """FakeAdapter 固定回 2026-08-01 10:00；紀錄用同一個時間+狀態才會判定無變化。"""
    _remember("111111111111", "配送中", carrier="tcat")
    fresh = FakeAdapter("tcat", found=True, status="配送中")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": fresh})
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "無變化" in out
    assert "111111111111" in out


def test_refresh_pending_marks_network_error_as_failure(monkeypatch, hist_home, capsys):
    import requests
    _remember("111111111111", "配送中", carrier="tcat")
    dead = FakeAdapter("tcat", raises=requests.exceptions.ConnectionError("boom"))
    monkeypatch.setattr(track, "CARRIERS", {"tcat": dead})
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "查詢失敗" in out
    assert "111111111111" in out


def test_refresh_pending_marks_not_found_as_failure(monkeypatch, hist_home, capsys):
    _remember("111111111111", "配送中", carrier="tcat")
    gone = FakeAdapter("tcat", found=False)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": gone})
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "查詢失敗" in out
    assert "查無資料" in out


def test_refresh_pending_continues_after_one_item_fails(monkeypatch, hist_home, capsys):
    """一家掛掉不該讓整批中止——換下一筆繼續（fail-fast per item, 不 fail-fast per batch）。"""
    import requests
    _remember("111111111111", "配送中", carrier="tcat", event_time="2026-07-01 09:00")
    _remember("222222222222", "配送中", carrier="ecan", event_time="2026-08-01 09:00")
    dead = FakeAdapter("tcat", raises=requests.exceptions.ConnectionError("boom"))
    alive = FakeAdapter("ecan", found=True, status="順利送達")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": dead, "ecan": alive})
    assert track.run(["--refresh-pending"]) == 0
    assert alive.calls == 1
    out = capsys.readouterr().out
    assert "查詢失敗" in out and "111111111111" in out
    assert "新結案" in out and "222222222222" in out


def test_refresh_pending_treats_other_carrier_unavailable_as_failure_not_skip(
        monkeypatch, hist_home, capsys):
    """CarrierUnavailable 不是每種都算「略過」——SPX 缺 Playwright 仍是查詢失敗。"""
    _remember("111111111111", "配送中", carrier="spx")
    dead = FakeAdapter("spx", raises=CarrierUnavailable("SPX 需要 Playwright"))
    monkeypatch.setattr(track, "CARRIERS", {"spx": dead})
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "查詢失敗" in out
    assert "Playwright" in out


def test_refresh_pending_handles_unrecognized_carrier_gracefully(hist_home, capsys):
    """手動編輯過的紀錄可能存了認不得的貨運代號——不可 raise，要列成查詢失敗。"""
    import history
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text(
        '{"111111111111": {"carrier": "not-a-real-carrier", "last_status": "配送中"}}',
        encoding="utf-8")
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "111111111111" in out
    assert "查詢失敗" in out


def test_refresh_pending_updates_the_stored_snapshot(monkeypatch, hist_home):
    """需求 3：更新後的結果要用 history.record 同一套機制寫回快照。"""
    import history
    _remember("111111111111", "配送中", carrier="tcat", event_time="2026-07-01 09:00")
    fresh = FakeAdapter("tcat", found=True, status="順利送達")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": fresh})
    track.run(["--refresh-pending"])
    entry = history.lookup_entry("111111111111")
    assert entry["last_status"] == "順利送達"
    assert entry["looks_complete"] is True


def test_refresh_pending_no_record_suppresses_snapshot_update(monkeypatch, hist_home):
    import history
    _remember("111111111111", "配送中", carrier="tcat", event_time="2026-07-01 09:00")
    fresh = FakeAdapter("tcat", found=True, status="順利送達")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": fresh})
    track.run(["--refresh-pending", "--no-record"])
    entry = history.lookup_entry("111111111111")
    assert entry["last_status"] == "配送中", "有 --no-record 就不該覆寫快照"


def test_refresh_pending_write_failure_still_shows_result(monkeypatch, hist_home, capsys):
    import history
    _remember("111111111111", "配送中", carrier="tcat", event_time="2026-07-01 09:00")
    fresh = FakeAdapter("tcat", found=True, status="順利送達")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": fresh})
    monkeypatch.setattr(history, "record", lambda _r: (_ for _ in ()).throw(OSError("disk full")))
    assert track.run(["--refresh-pending"]) == 0
    out, err = capsys.readouterr()
    assert "新結案" in out
    assert "disk full" in err


def test_refresh_pending_skips_17track_carrier_without_key(monkeypatch, hist_home, capsys):
    """spec 需求 5：17TRACK-only 貨運但沒設 key → 清楚略過，不是失敗、不是真的打出去。"""
    import history
    from carriers.seventeentrack import API_KEY_ENV
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text(
        '{"111111111111": {"carrier": "chunghwa-post", "last_status": "已收件"}}',
        encoding="utf-8")
    agg = FakeAdapter("17track")
    monkeypatch.setattr(track, "CARRIERS", {"17track": agg})
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "略過" in out
    assert "17TRACK" in out
    assert "111111111111" in out
    assert "查詢失敗" not in out
    assert agg.calls == 0, "沒 key 就不該真的打出去"


def test_refresh_pending_queries_17track_carrier_when_key_present(monkeypatch, hist_home, capsys):
    """有 key 時才真的呼叫，且要把 carrier 名稱翻成 17TRACK 數字碼。"""
    import history
    from carriers.seventeentrack import API_KEY_ENV
    monkeypatch.setenv(API_KEY_ENV, "test-key")
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text(
        '{"111111111111": {"carrier": "chunghwa-post", "last_status": "已收件"}}',
        encoding="utf-8")
    seen = {}

    class _Agg(FakeAdapter):
        def track(self, number, carrier_code=None):
            seen["code"] = carrier_code
            return super().track(number)

    agg = _Agg("17track", found=True, status="順利送達")
    monkeypatch.setattr(track, "CARRIERS", {"17track": agg})
    assert track.run(["--refresh-pending"]) == 0
    assert agg.calls == 1
    assert seen["code"] == 20011  # chunghwa-post 的 17TRACK 數字碼
    out = capsys.readouterr().out
    assert "新結案" in out


def test_refresh_pending_warns_once_about_a_corrupt_file(hist_home, capsys):
    """跟 --pending 同一份 entries()/pending() 路徑，毀損警告一樣只該印一次。"""
    import history
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text("{ not json", encoding="utf-8")
    assert track.run(["--refresh-pending"]) == 0
    captured = capsys.readouterr()
    assert captured.err.count("查詢紀錄無法讀取") == 1
    assert "查詢紀錄是空的" in captured.out


def test_refresh_pending_discloses_item_count_before_querying(monkeypatch, hist_home, capsys):
    _remember("111111111111", "配送中", carrier="tcat")
    fresh = FakeAdapter("tcat", found=True, status="配送中")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": fresh})
    track.run(["--refresh-pending"])
    out = capsys.readouterr().out
    assert "1 筆" in out
