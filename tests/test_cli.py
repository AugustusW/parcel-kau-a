"""CLI dispatch / 渲染行為（adapter 全替身，不打網路）。"""
import json
import sys
from datetime import datetime, timedelta, timezone
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
    track.run(["123456789012", "--auto"])
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
    code = track.run(["123456789012", "--auto"])
    assert code == 0
    assert alive.calls == 1
    assert "假tcat" in capsys.readouterr().out, "應回報實際查到的那家"


def test_parse_error_in_auto_mode_tries_next_carrier(monkeypatch, capsys):
    """撞號情境下，某家改版不該埋掉其他家的有效結果。"""
    from carriers.base import ParseError
    broken = FakeAdapter("tcat", raises=ParseError("頁面結構已變"))
    alive = FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": broken, "ecan": alive})
    assert track.run(["123456789012", "--auto"]) == 0
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
    track.run(["123456789012", "--auto"])

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
    track.run(["123456789012", "--auto", "--json"])
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
    track.run(["123456789012", "--auto"])
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
    # v0.5.0 起列表預設只顯示末四碼（spec 原則 8）
    assert "單號末四碼：9012" in out and "順利送達" in out
    assert "123456789012" not in out


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
    assert "單號末四碼：1111" in out
    assert "單號末四碼：2222" not in out, "已完成的不該出現在未結案清單"


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
    assert "9 天沒有新進度" in capsys.readouterr().out


def test_pending_flag_says_today_instead_of_zero_days(hist_home, capsys):
    today = datetime.now().strftime("%Y/%m/%d %H:%M")
    _remember("111111111111", "配送中", event_time=today)
    track.run(["--pending"])
    out = capsys.readouterr().out
    assert "0 天" not in out and "今天有新進度" in out


def test_pending_flag_omits_the_age_when_time_is_unparseable(hist_home, capsys):
    _remember("111111111111", "配送中", event_time="時間不詳")
    assert track.run(["--pending"]) == 0
    out = capsys.readouterr().out
    assert "單號末四碼：1111" in out
    assert "新進度" not in out, "算不出天數就不要編一個出來"


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
        # 每筆是一個區塊：第一行是標題（物流商名所在），第二行是單號
        blocks = [b.splitlines() for b in out.split("\n\n")]
        for last4 in ("1111", "2222"):
            block = next(b for b in blocks if len(b) > 1 and b[1] == f"單號末四碼：{last4}")
            assert "?" in block[0], f"{flag} 的 {last4} 應顯示 ?：{block[0]!r}"


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
    assert track.run(["123456789012", "--auto"]) == 0
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
    assert "單號末四碼：1111" in out and "順利送達" in out


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
    assert "單號末四碼：1111" in out


def test_refresh_pending_marks_network_error_as_failure(monkeypatch, hist_home, capsys):
    import requests
    _remember("111111111111", "配送中", carrier="tcat")
    dead = FakeAdapter("tcat", raises=requests.exceptions.ConnectionError("boom"))
    monkeypatch.setattr(track, "CARRIERS", {"tcat": dead})
    assert track.run(["--refresh-pending"]) == track.EXIT_PARTIAL_FAILURE
    out = capsys.readouterr().out
    assert "查詢失敗" in out
    assert "單號末四碼：1111" in out


def test_refresh_pending_marks_not_found_as_failure(monkeypatch, hist_home, capsys):
    _remember("111111111111", "配送中", carrier="tcat")
    gone = FakeAdapter("tcat", found=False)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": gone})
    assert track.run(["--refresh-pending"]) == track.EXIT_PARTIAL_FAILURE
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
    assert track.run(["--refresh-pending"]) == track.EXIT_PARTIAL_FAILURE
    assert alive.calls == 1
    out = capsys.readouterr().out
    assert "查詢失敗" in out and "單號末四碼：1111" in out
    assert "新結案" in out and "單號末四碼：2222" in out


def test_refresh_pending_treats_other_carrier_unavailable_as_failure_not_skip(
        monkeypatch, hist_home, capsys):
    """CarrierUnavailable 不是每種都算「略過」——SPX 缺 Playwright 仍是查詢失敗。"""
    _remember("111111111111", "配送中", carrier="spx")
    dead = FakeAdapter("spx", raises=CarrierUnavailable("SPX 需要 Playwright"))
    monkeypatch.setattr(track, "CARRIERS", {"spx": dead})
    assert track.run(["--refresh-pending"]) == track.EXIT_PARTIAL_FAILURE
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
    assert track.run(["--refresh-pending"]) == track.EXIT_PARTIAL_FAILURE
    out = capsys.readouterr().out
    assert "單號末四碼：1111" in out
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
    # 查到了但快照沒存成功也算部分失敗（v0.5.0 起 exit 6），原因寫在摘要裡
    assert track.run(["--refresh-pending"]) == track.EXIT_PARTIAL_FAILURE
    out = capsys.readouterr().out
    assert "新結案" in out
    assert "本機快照未更新" in out and "disk full" in out


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
    assert "單號末四碼：1111" in out and "111111111111" not in out
    assert "查詢失敗" not in out
    assert agg.calls == 0, "沒 key 就不該真的打出去"


def test_refresh_pending_never_calls_17track_even_with_a_key(monkeypatch, hist_home, capsys):
    """環境裡有 key 不等於這次同意（spec 6.5）。v0.4.0 在此情境會自動呼叫 17TRACK。"""
    import history
    from carriers.seventeentrack import API_KEY_ENV
    monkeypatch.setenv(API_KEY_ENV, "test-key")
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text(
        '{"111111111111": {"carrier": "chunghwa-post", "last_status": "已收件"}}',
        encoding="utf-8")
    agg = FakeAdapter("17track", found=True, status="順利送達")
    monkeypatch.setattr(track, "CARRIERS", {"17track": agg})
    track.run(["--refresh-pending"])
    assert agg.calls == 0
    out = capsys.readouterr().out
    assert "已略過" in out and "track.py <單號> --carrier chunghwa-post --via-17track" in out


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


def test_forget_with_a_held_lock_exits_7_without_traceback(hist_home, capsys):
    import history
    import storage
    _remember("900000000001", "配送中")
    before = history.path().read_bytes()
    held = open(history.home() / storage.LOCK_NAME, "a+b")
    assert storage._try_lock(held)
    try:
        assert track.run(["--forget", "900000000001"]) == track.EXIT_PERSISTENCE
        assert track.run(["--forget-all"]) == track.EXIT_PERSISTENCE
    finally:
        storage._unlock(held)
        held.close()
    out = capsys.readouterr().out
    assert "另一個 parcel-kau-a 程序" in out
    assert history.path().read_bytes() == before



# ── v0.5.0 快照呈現（spec §5）──────────────────────────────────────────

TPE = timezone(timedelta(hours=8))


def _set_now(monkeypatch, dt):
    import snapshot
    monkeypatch.setattr(snapshot, "now", lambda: dt)


def _set_checked(number, iso):
    import history
    data = history.entries()
    data[number]["last_checked"] = iso
    history._write(data)


def test_pending_says_it_is_a_snapshot_and_shows_both_times(monkeypatch, hist_home, capsys):
    _remember("900000000001", "配送中", event_time="2026/10/16 14:20")
    _set_checked("900000000001", "2026-10-16T15:03:00+08:00")
    _set_now(monkeypatch, datetime(2026, 10, 17, 16, 0, tzinfo=TPE))
    assert track.run(["--pending"]) == 0
    out = capsys.readouterr().out
    assert "本機歷史快照；未連線" in out
    assert "物流事件：2026/10/16 14:20" in out
    expected = track._local_minutes("2026-10-16T15:03:00+08:00")
    assert f"上次查詢：{expected}（約 1 天前）" in out
    assert "--refresh-pending" in out


def test_stale_snapshot_is_flagged(monkeypatch, hist_home, capsys):
    _remember("900000000001", "配送中")
    _set_checked("900000000001", "2026-10-01T10:00:00+08:00")
    _set_now(monkeypatch, datetime(2026, 10, 17, 10, 0, tzinfo=TPE))
    track.run(["--pending"])
    assert "資料可能過期" in capsys.readouterr().out


def test_recent_snapshot_is_not_called_stale(monkeypatch, hist_home, capsys):
    _remember("900000000001", "配送中")
    _set_checked("900000000001", "2026-10-15T10:00:00+08:00")
    _set_now(monkeypatch, datetime(2026, 10, 17, 10, 0, tzinfo=TPE))
    track.run(["--pending"])
    out = capsys.readouterr().out
    assert "約 2 天前" in out and "資料可能過期" not in out


def test_missing_checked_time_is_said_not_invented(hist_home, capsys):
    import history
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text('{"900000000001": {"carrier": "tcat", "last_status": "配送中",'
                              ' "last_event_time": "2026/10/16 14:20"}}', encoding="utf-8")
    track.run(["--pending"])
    out = capsys.readouterr().out
    assert "上次查詢：時間未知" in out
    assert "物流事件：2026/10/16 14:20" in out


def test_clock_skew_is_reported_not_computed(monkeypatch, hist_home, capsys):
    _remember("900000000001", "配送中")
    _set_checked("900000000001", "2026-10-20T10:00:00+08:00")
    _set_now(monkeypatch, datetime(2026, 10, 17, 10, 0, tzinfo=TPE))
    track.run(["--pending"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("上次查詢："))
    assert "本機時間異常" in line and "前）" not in line, "不可出現負的經過時間"


def test_full_numbers_flag_reveals_the_number(hist_home, capsys):
    _remember("900000000001", "配送中")
    track.run(["--pending", "--full-numbers"])
    assert "單號：900000000001" in capsys.readouterr().out


def test_pending_json_is_one_snapshot_envelope(hist_home, capsys):
    _remember("900000000001", "配送中")
    assert track.run(["--pending", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["operation"] == "pending"
    assert payload["snapshot"] is True and payload["live_query"] is False
    item = payload["items"][0]
    assert item["number"] == "900000000001", "JSON 是機器介面，帶完整單號"
    assert {"event_time", "checked_at", "freshness", "checked_age_seconds"} <= item.keys()


def test_history_json_lists_completed_too(hist_home, capsys):
    _remember("900000000001", "順利送達")
    assert track.run(["--history", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "history"
    assert payload["items"][0]["looks_complete"] is True


def test_empty_history_json_still_parses(hist_home, capsys):
    assert track.run(["--history", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["items"] == []
    assert "查詢紀錄是空的" in captured.err


def test_snapshot_listings_leave_the_file_byte_identical(hist_home):
    import history
    _remember("900000000001", "配送中")
    before = history.path().read_bytes()
    for argv in (["--pending"], ["--history"], ["--pending", "--json"], ["--history", "--json"]):
        track.run(argv)
    assert history.path().read_bytes() == before


def test_live_result_says_it_was_just_queried(monkeypatch, capsys):
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})
    track.run(["123456789012", "--carrier", "tcat", "--no-record"])
    assert "剛剛即時查詢" in capsys.readouterr().out


# ── v0.5.0 單號送出前確認（spec §9；使用者 2026-10-17 決定本版即改）────────
#
# 舊版預設：物流商無法由格式判定時，把單號依序送給每一家格式相符的物流商。
# 新版預設：一筆都不送，列出候選；使用者選一家（--carrier）或同意全部（--auto）。

def test_ambiguous_number_sends_nothing_and_lists_candidates(monkeypatch, capsys):
    a, b = FakeAdapter("tcat", found=True), FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    assert track.run(["123456789012"]) == track.EXIT_SELECTION_REQUIRED
    assert (a.calls, b.calls) == (0, 0)
    out = capsys.readouterr().out
    assert "尚未送出任何查詢" in out
    assert "tcat" in out and "ecan" in out
    assert "--carrier" in out and "--auto" in out


def test_ambiguous_number_json_is_a_selection_envelope(monkeypatch, capsys):
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat"), "ecan": FakeAdapter("ecan")})
    assert track.run(["123456789012", "--json"]) == 8
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["operation"] == "detect" and payload["selection_required"] is True
    assert [c["carrier"] for c in payload["candidates"]] == ["tcat", "ecan"]
    assert "--auto" in captured.err


def test_unique_format_needs_no_confirmation(monkeypatch):
    spx = FakeAdapter("spx", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", detects=False), "spx": spx})
    assert track.run(["TW254414081298F"]) == 0
    assert spx.calls == 1


def test_known_number_with_stale_record_asks_before_polling_others(monkeypatch, hist_home, capsys):
    import history
    history.record(TrackResult(carrier="tcat", number="123456789012", found=True,
                               events=[TrackEvent(time="t", status="配送中")]))
    a, b = FakeAdapter("tcat", found=False), FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    assert track.run(["123456789012"]) == 8
    assert (a.calls, b.calls) == (1, 0)
    assert "紀錄中那家查無資料" in capsys.readouterr().out


def test_recorded_carrier_timeout_is_reported_not_broadcast(monkeypatch, hist_home, capsys):
    """紀錄那家只是逾時，不代表紀錄過時；即使有 --auto 也不改問別家。"""
    import history
    import requests
    history.record(TrackResult(carrier="tcat", number="123456789012", found=True,
                               events=[TrackEvent(time="t", status="配送中")]))
    a = FakeAdapter("tcat", raises=requests.exceptions.ReadTimeout("t"))
    b = FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    assert track.run(["123456789012", "--auto"]) == 5
    assert b.calls == 0
    assert "逾時" in capsys.readouterr().out


@pytest.mark.parametrize("meta", [None, {"auto_detect_allowed": False}])
def test_unregistered_or_disallowed_carrier_is_never_a_candidate(monkeypatch, meta):
    """沒寫 metadata 與明確 False 都不可參與自動判別。"""
    import carriers
    newbie = FakeAdapter("newbie", found=True)
    tcat = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"newbie": newbie, "tcat": tcat})  # newbie 排前面：舊行為會先問它
    if meta is not None:
        monkeypatch.setitem(carriers.CARRIER_META, "newbie", meta)
    assert track.run(["123456789012"]) == 0   # 只剩 tcat 一家候選 → 直接查
    assert newbie.calls == 0


def test_unsupported_carrier_name_sends_nothing(monkeypatch):
    """使用者指定的物流商不在支援清單：直接回錯誤，不改送其他家（2026-10-17 使用者要求）。"""
    a, b = FakeAdapter("tcat", found=True), FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    assert track.run(["123456789012", "--carrier", "hct"]) == 2
    assert (a.calls, b.calls) == (0, 0)


def test_no_candidate_sends_nothing(monkeypatch):
    """格式判斷不出任何一家：零請求（不退回輪巡、不自動改走 17TRACK）。"""
    a = FakeAdapter("tcat", detects=False)
    agg = FakeAdapter("17track", detects=False)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "17track": agg})
    assert track.run(["83546610320956"]) == 2
    assert (a.calls, agg.calls) == (0, 0)


@pytest.mark.parametrize("extra", [["--carrier", "tcat"], ["--via-17track"]])
def test_auto_conflicts_are_rejected_before_any_request(monkeypatch, extra):
    a = FakeAdapter("tcat", found=True)
    agg = FakeAdapter("17track", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "17track": agg})
    assert track.run(["123456789012", "--auto", *extra]) == 2
    assert (a.calls, agg.calls) == (0, 0)


# ── v0.5.0 包裹名稱（spec §4）──────────────────────────────────────────

def test_label_is_saved_only_after_a_found_result(monkeypatch, hist_home):
    import labels
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True, status="配送中")})
    assert track.run(["900000000001", "--carrier", "tcat", "--label", "momo 耳機"]) == 0
    assert labels.load_for_read() == {"900000000001": "momo 耳機"}


def test_relabelling_says_what_it_replaced(monkeypatch, hist_home, capsys):
    import labels
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True, status="配送中")})
    track.run(["900000000001", "--carrier", "tcat", "--label", "耳機"])
    track.run(["900000000001", "--carrier", "tcat", "--label", "工作用耳機"])
    assert labels.load_for_read()["900000000001"] == "工作用耳機"
    assert "從「耳機」改為「工作用耳機」" in capsys.readouterr().out


def test_not_found_creates_no_orphan_label(monkeypatch, hist_home, capsys):
    import labels
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=False)})
    assert track.run(["900000000001", "--carrier", "tcat", "--label", "耳機"]) == 0
    assert labels.load_for_read() == {}
    assert "名稱未儲存" in capsys.readouterr().out


def test_invalid_label_sends_no_request(monkeypatch):
    a = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a})
    assert track.run(["900000000001", "--carrier", "tcat", "--label", "\x1b[31mx"]) == 2
    assert a.calls == 0


@pytest.mark.parametrize("extra", [["--no-record"], ["--via-17track"]])
def test_label_needs_a_recorded_direct_query(monkeypatch, extra):
    a = FakeAdapter("tcat", found=True)
    agg = FakeAdapter("17track", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "17track": agg})
    assert track.run(["900000000001", "--carrier", "tcat", "--label", "x", *extra]) == 2
    assert (a.calls, agg.calls) == (0, 0)


def test_label_without_a_number_is_an_error(hist_home):
    assert track.run(["--label", "x"]) == 2


def test_history_write_failure_leaves_no_label(monkeypatch, hist_home):
    import history
    import labels
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})

    def boom(_):
        raise OSError("disk full")

    monkeypatch.setattr(history, "record", boom)
    assert track.run(["900000000001", "--carrier", "tcat", "--label", "x"]) == track.EXIT_PERSISTENCE
    assert labels.load_for_read() == {}


def test_corrupt_labels_file_blocks_labelling_before_any_request(monkeypatch, hist_home):
    import labels
    labels.path().parent.mkdir(parents=True, exist_ok=True)
    labels.path().write_text("{ broken", encoding="utf-8")
    a = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a})
    assert track.run(["900000000001", "--carrier", "tcat", "--label", "x"]) == 7
    assert a.calls == 0


def test_rename_and_clear_label_touch_no_network(monkeypatch, hist_home):
    import labels
    _remember("900000000001", "配送中")
    a = FakeAdapter("tcat")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a})
    assert track.run(["--rename", "900000000001", "工作用耳機"]) == 0
    assert labels.load_for_read()["900000000001"] == "工作用耳機"
    assert track.run(["--clear-label", "900000000001"]) == 0
    assert labels.load_for_read() == {}
    assert a.calls == 0


def test_rename_unknown_number_is_an_error(hist_home):
    assert track.run(["--rename", "900000000009", "x"]) == 2


def test_rename_json_reports_the_saved_label(hist_home, capsys):
    _remember("900000000001", "配送中")
    assert track.run(["--rename", "900000000001", "耳機", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "rename" and payload["saved"] is True
    assert payload["label"] == "耳機"


def test_find_single_match(hist_home, capsys):
    import labels
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "momo 耳機")
    assert track.run(["--find", "耳機"]) == 0
    out = capsys.readouterr().out
    assert "momo 耳機" in out and "本機歷史快照" in out and "900000000001" not in out


def test_find_without_match_says_so(hist_home, capsys):
    _remember("900000000001", "配送中")
    assert track.run(["--find", "耳機"]) == 0
    assert "找不到" in capsys.readouterr().out


def test_find_multiple_matches_requires_selection_and_sends_nothing(monkeypatch, hist_home, capsys):
    import labels
    _remember("900000000001", "配送中")
    _remember("900000000002", "已到轉運站", carrier="ecan")
    labels.set_label("900000000001", "momo 耳機保護殼")
    labels.set_label("900000000002", "momo 藍牙耳機")
    a, b = FakeAdapter("tcat"), FakeAdapter("ecan")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": a, "ecan": b})
    assert track.run(["--find", "耳機"]) == 8
    out = capsys.readouterr().out
    assert "找到 2 個名稱相近的包裹" in out and "不是即時貨態" in out
    assert "1. momo 耳機保護殼" in out and "2. momo 藍牙耳機" in out
    assert (a.calls, b.calls) == (0, 0)


def test_find_json_reports_selection_required(hist_home, capsys):
    import labels
    _remember("900000000001", "配送中")
    _remember("900000000002", "配送中")
    labels.set_label("900000000001", "耳機 A")
    labels.set_label("900000000002", "耳機 B")
    assert track.run(["--find", "耳機", "--json"]) == 8
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "find" and payload["selection_required"] is True
    assert len(payload["matches"]) == 2


def test_find_and_failed_writes_leave_files_byte_identical(hist_home):
    import history
    import labels
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "耳機")
    before = (history.path().read_bytes(), labels.path().read_bytes())
    track.run(["--find", "耳機"])
    track.run(["--find", "不存在"])
    track.run(["--rename", "900000000009", "x"])
    track.run(["--rename", "900000000001", "\x00"])
    assert (history.path().read_bytes(), labels.path().read_bytes()) == before


def test_management_flags_are_mutually_exclusive(hist_home):
    with pytest.raises(SystemExit) as exc:
        track.run(["--find", "x", "--pending"])
    assert exc.value.code == 2


def test_label_with_a_held_lock_still_shows_the_result(monkeypatch, hist_home, capsys):
    """拿不到鎖時名稱存不了，但查到的貨態仍要交給使用者。"""
    import history
    import labels
    import storage
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True, status="配送中")})
    history.home().mkdir(parents=True, exist_ok=True)
    held = open(history.home() / storage.LOCK_NAME, "a+b")
    assert storage._try_lock(held)
    try:
        code = track.run(["900000000001", "--carrier", "tcat", "--label", "x", "--json"])
    finally:
        storage._unlock(held)
        held.close()
    captured = capsys.readouterr()
    assert code == track.EXIT_PERSISTENCE
    assert json.loads(captured.out)["found"] is True
    assert "名稱未儲存" in captured.err
    assert labels.load_for_read() == {}


# ── v0.5.0 名稱與刪除（spec §4.5 privacy-first 順序）───────────────────

def test_listings_show_labels(hist_home, capsys):
    import labels
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "momo 耳機")
    track.run(["--pending"])
    assert "momo 耳機" in capsys.readouterr().out
    track.run(["--history", "--json"])
    assert json.loads(capsys.readouterr().out)["items"][0]["label"] == "momo 耳機"


def test_forget_removes_the_label_too(hist_home, capsys):
    import history
    import labels
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "耳機")
    assert track.run(["--forget", "900000000001"]) == 0
    assert labels.load_for_read() == {} and history.lookup_entry("900000000001") is None
    assert "與名稱" in capsys.readouterr().out


def test_forget_stops_before_history_when_label_removal_fails(hist_home, capsys):
    import history
    import labels
    _remember("900000000001", "配送中")
    labels.path().write_text("{ broken", encoding="utf-8")
    before = history.path().read_bytes()
    assert track.run(["--forget", "900000000001"]) == track.EXIT_PERSISTENCE
    assert history.path().read_bytes() == before, "名稱刪不掉就不能接著刪紀錄"
    assert "未刪除任何資料" in capsys.readouterr().out


def test_forget_reports_partial_success_when_history_fails(monkeypatch, hist_home, capsys):
    import history
    import labels
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "耳機")

    def boom(_):
        raise OSError("read-only")

    monkeypatch.setattr(history, "forget", boom)
    assert track.run(["--forget", "900000000001"]) == 7
    out = capsys.readouterr().out
    assert "名稱已刪除" in out and "可重試" in out
    assert labels.load_for_read() == {}


def test_forget_all_clears_a_corrupt_labels_file(hist_home, capsys):
    import history
    import labels
    _remember("900000000001", "配送中")
    labels.path().write_text("{ broken", encoding="utf-8")
    assert track.run(["--forget-all"]) == 0
    assert not labels.path().exists() and history.entries() == {}
    assert "與名稱" in capsys.readouterr().out


def test_forget_with_a_held_lock_changes_nothing(hist_home, capsys):
    import history
    import labels
    import storage
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "耳機")
    held = open(history.home() / storage.LOCK_NAME, "a+b")
    assert storage._try_lock(held)
    before = (history.path().read_bytes(), labels.path().read_bytes())
    try:
        assert track.run(["--forget", "900000000001", "--json"]) == 7
    finally:
        storage._unlock(held)
        held.close()
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and payload["exit_code"] == 7
    assert (history.path().read_bytes(), labels.path().read_bytes()) == before


def test_forget_json_reports_what_was_removed(hist_home, capsys):
    import labels
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "耳機")
    assert track.run(["--forget", "900000000001", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "forget"
    assert payload["label_removed"] is True and payload["history_removed"] is True


# ── v0.5.0 批次更新範圍（spec §6.2）──────────────────────────────────────

def _three_pending():
    import labels
    _remember("900000000001", "配送中", event_time="2026/10/16 10:00", carrier="tcat")
    _remember("900000000002", "配送中", event_time="2026/10/15 10:00", carrier="ecan")
    _remember("900000000003", "配送中", event_time="2026/10/14 10:00", carrier="tcat")
    labels.set_label("900000000001", "momo 耳機")
    labels.set_label("900000000002", "藍牙耳機")
    labels.set_label("900000000003", "書")


def test_match_with_multiple_hits_needs_all_matches(monkeypatch, hist_home, capsys):
    _three_pending()
    t, e = FakeAdapter("tcat", found=True, status="配送中"), FakeAdapter("ecan", found=True, status="配送中")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": t, "ecan": e})
    assert track.run(["--refresh-pending", "--match", "耳機"]) == 8
    assert (t.calls, e.calls) == (0, 0)
    out = capsys.readouterr().out
    assert "尚未送出任何查詢" in out and "--all-matches" in out
    assert track.run(["--refresh-pending", "--match", "耳機", "--all-matches"]) == 0
    assert (t.calls, e.calls) == (1, 1)


def test_match_with_one_hit_refreshes_only_it(monkeypatch, hist_home):
    _three_pending()
    t = FakeAdapter("tcat", found=True, status="配送中")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": t, "ecan": FakeAdapter("ecan")})
    assert track.run(["--refresh-pending", "--match", "書"]) == 0
    assert t.calls == 1


def test_match_with_no_hit_sends_nothing(monkeypatch, hist_home, capsys):
    _three_pending()
    t = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": t, "ecan": FakeAdapter("ecan")})
    assert track.run(["--refresh-pending", "--match", "相機"]) == 0
    assert t.calls == 0
    assert "沒有名稱符合「相機」" in capsys.readouterr().out


def test_carrier_filter_and_limit(monkeypatch, hist_home):
    _three_pending()
    seen = []

    class _T(FakeAdapter):
        def track(self, number, carrier_code=None):
            seen.append(number)
            return super().track(number)

    monkeypatch.setattr(track, "CARRIERS", {"tcat": _T("tcat", found=True, status="配送中"),
                                            "ecan": _T("ecan", found=True, status="配送中")})
    track.run(["--refresh-pending", "--carrier", "tcat", "--limit", "1"])
    assert seen == ["900000000001"], "先篩物流商、再依事件時間新到舊、最後截斷"


def test_limit_does_not_bypass_the_multi_match_gate(monkeypatch, hist_home):
    _three_pending()
    t = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": t, "ecan": FakeAdapter("ecan")})
    assert track.run(["--refresh-pending", "--match", "耳機", "--limit", "1"]) == 8
    assert t.calls == 0


def test_dry_run_sends_and_writes_nothing(monkeypatch, hist_home, capsys):
    import history
    import labels
    _three_pending()
    before = (history.path().read_bytes(), labels.path().read_bytes())
    t = FakeAdapter("tcat", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": t, "ecan": FakeAdapter("ecan")})
    assert track.run(["--refresh-pending", "--dry-run"]) == 0
    assert t.calls == 0
    assert "將查詢 3 筆" in capsys.readouterr().out
    assert (history.path().read_bytes(), labels.path().read_bytes()) == before


# 旗標互斥矩陣（README 有同一張表）：每一列都必須 exit 2 且一筆查詢都不送
FLAG_CONFLICTS = [
    ["--find", "x", "--pending"],
    ["--rename", "1", "x", "--clear-label", "1"],
    ["--forget", "1", "--history"],
    ["--refresh-pending", "--endpoints"],
    ["--label", "x"],
    ["--pending", "--label", "x"],
    ["123456789012", "--auto", "--carrier", "tcat"],
    ["123456789012", "--auto", "--via-17track"],
    ["123456789012", "--carrier", "tcat", "--label", "x", "--no-record"],
    ["123456789012", "--carrier", "tcat", "--label", "x", "--via-17track"],
    ["--pending", "--match", "x"],
    ["--history", "--all-matches"],
    ["--pending", "--limit", "3"],
    ["--history", "--dry-run"],
    ["123456789012", "--carrier", "tcat", "--dry-run"],
    ["--refresh-pending", "--all-matches"],
    ["--refresh-pending", "--limit", "0"],
    ["--refresh-pending", "--carrier", "17track"],
    ["--refresh-pending", "--carrier", "hct"],
]


@pytest.mark.parametrize("argv", FLAG_CONFLICTS)
def test_flag_conflicts_are_errors_that_send_nothing(monkeypatch, hist_home, argv):
    _remember("900000000001", "配送中")
    t = FakeAdapter("tcat", found=True)
    agg = FakeAdapter("17track", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": t, "17track": agg})
    try:
        code = track.run(argv)
    except SystemExit as e:
        code = e.code
    assert code == 2
    assert (t.calls, agg.calls) == (0, 0)


# ── v0.5.0 批次摘要與 JSON（spec §6.3、6.4、6.7）──────────────────────────

def test_digest_shows_transition_and_says_it_is_live(monkeypatch, hist_home, capsys):
    import labels
    _remember("900000000002", "轉運中", carrier="ecan")
    labels.set_label("900000000002", "生活用品")
    monkeypatch.setattr(track, "CARRIERS", {"ecan": FakeAdapter("ecan", found=True, status="配送中")})
    assert track.run(["--refresh-pending"]) == 0
    out = capsys.readouterr().out
    assert "剛剛即時查詢" in out
    assert "生活用品　假ecan　轉運中 → 配送中" in out
    assert "900000000002" not in out and "單號末四碼：0002" in out
    assert "查詢時間：" in out


def test_failure_keeps_last_snapshot_and_says_so(monkeypatch, hist_home, capsys):
    import history
    import requests
    _remember("900000000003", "配送中", carrier="kerrytj")
    _set_checked("900000000003", "2026-10-16T20:10:00+08:00")
    before = history.path().read_bytes()
    dead = FakeAdapter("kerrytj", raises=requests.exceptions.ReadTimeout("t"))
    monkeypatch.setattr(track, "CARRIERS", {"kerrytj": dead})
    assert track.run(["--refresh-pending"]) == track.EXIT_PARTIAL_FAILURE
    out = capsys.readouterr().out
    expected = track._local_minutes("2026-10-16T20:10:00+08:00")
    assert f"仍保留上次成功快照：{expected} 查詢" in out
    assert history.path().read_bytes() == before


def test_snapshot_save_failure_is_partial_failure_in_json(monkeypatch, hist_home, capsys):
    import history
    _remember("900000000001", "配送中")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True, status="順利送達")})

    def boom(_):
        raise OSError("disk full")

    monkeypatch.setattr(history, "record", boom)
    assert track.run(["--refresh-pending", "--json"]) == 6
    payload = json.loads(capsys.readouterr().out)
    o = payload["outcomes"][0]
    assert o["query_succeeded"] is True and o["snapshot_saved"] is False
    assert payload["partial_failure"] is True


def test_no_record_is_not_a_partial_failure(monkeypatch, hist_home, capsys):
    _remember("900000000001", "配送中")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True, status="順利送達")})
    assert track.run(["--refresh-pending", "--no-record", "--json"]) == 0
    o = json.loads(capsys.readouterr().out)["outcomes"][0]
    assert o["query_succeeded"] is True and o["snapshot_saved"] is False


def test_refresh_json_envelope(monkeypatch, hist_home, capsys):
    import labels
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "耳機")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True, status="順利送達")})
    assert track.run(["--refresh-pending", "--json"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema_version"] == 1 and payload["operation"] == "refresh_pending"
    assert payload["live_query"] is True and payload["partial_failure"] is False
    assert payload["counts"] == {"completed": 1, "progressed": 0, "unchanged": 0,
                                 "skipped": 0, "failed": 0}
    o = payload["outcomes"][0]
    assert o["number"] == "900000000001" and o["label"] == "耳機"
    assert o["category"] == "completed" and o["previous_status"] == "配送中"
    assert o["snapshot_saved"] is True
    assert "attempted_at" in payload
    assert "1 筆" in captured.err, "筆數揭露在 JSON 模式走 stderr"


@pytest.mark.parametrize("argv,key", [
    (["--refresh-pending", "--match", "耳機", "--json"], "matches"),
    (["--refresh-pending", "--dry-run", "--json"], "items"),
])
def test_refresh_selection_and_dry_run_json_are_one_document(monkeypatch, hist_home, capsys,
                                                             argv, key):
    _three_pending()
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat"), "ecan": FakeAdapter("ecan")})
    track.run(argv)
    payload = json.loads(capsys.readouterr().out)
    assert payload["operation"] == "refresh_pending" and payload["live_query"] is False
    assert len(payload[key]) >= 2


def test_refresh_empty_history_json_parses(hist_home, capsys):
    assert track.run(["--refresh-pending", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["outcomes"] == []
    assert "查詢紀錄是空的" in captured.err


# 每一條新的 --json 錯誤路徑：stdout 恰好一份 JSON，帶 ok=false 與 exit_code
JSON_ERROR_CASES = [
    (["900000000001", "--carrier", "tcat", "--label", "\x07", "--json"], 2),
    (["--rename", "900000000009", "x", "--json"], 2),
    (["--rename", "900000000001", "\x00", "--json"], 2),
    (["--refresh-pending", "--all-matches", "--json"], 2),
    (["--pending", "--match", "x", "--json"], 2),
    (["900000000001", "--carrier", "tcat", "--label", "x", "--no-record", "--json"], 2),
    (["--label", "x", "--json"], 2),
    (["123456789012", "--auto", "--carrier", "tcat", "--json"], 2),
    (["--refresh-pending", "--carrier", "hct", "--json"], 2),
]


@pytest.mark.parametrize("argv,code", JSON_ERROR_CASES)
def test_every_new_json_error_path_prints_exactly_one_document(monkeypatch, hist_home, capsys,
                                                               argv, code):
    _remember("900000000001", "配送中")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", found=True)})
    assert track.run(argv) == code
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False and payload["exit_code"] == code


# ── 最終審查修正（2026-10-18）──────────────────────────────────────────

def test_forget_on_a_corrupt_history_does_not_claim_success(hist_home, capsys):
    """要求刪除時，不可把含有該單號的檔案改名搬走，再回報「已刪除」。"""
    import history
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text('{ "123456789012": broken', encoding="utf-8")
    before = history.path().read_bytes()
    assert track.run(["--forget", "123456789012"]) == track.EXIT_PERSISTENCE
    assert history.path().read_bytes() == before
    assert list(history.home().glob("history.json.corrupt-*")) == []
    assert str(history.path()) in capsys.readouterr().out


def test_auto_json_keeps_stdout_parseable_when_one_courier_fails(monkeypatch, capsys):
    import requests
    dead = FakeAdapter("tcat", raises=requests.exceptions.ReadTimeout("t"))
    alive = FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": dead, "ecan": alive})
    assert track.run(["123456789012", "--auto", "--json", "--no-record"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["found"] is True
    assert "逾時" in captured.err


@pytest.mark.parametrize("argv", [["--pending"], ["--history"], ["--pending", "--json"],
                                  ["--refresh-pending", "--dry-run"], ["--find", "1"]])
def test_hand_edited_wrong_types_degrade_instead_of_crashing(hist_home, argv):
    import history
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text(
        '{"111111111111": {"carrier": ["tcat"], "last_status": 5, "last_event_time": 3,'
        ' "last_checked": 7},'
        ' "222222222222": {"carrier": "tcat", "last_status": "配送中",'
        ' "last_event_time": "2026/10/16 14:20"}}', encoding="utf-8")
    assert track.run(argv) in (0, 8)


def test_refresh_with_wrong_carrier_type_reports_failure_not_crash(hist_home, capsys):
    import history
    history.path().parent.mkdir(parents=True, exist_ok=True)
    history.path().write_text('{"111111111111": {"carrier": ["tcat"], "last_status": "配送中"}}',
                              encoding="utf-8")
    assert track.run(["--refresh-pending"]) == track.EXIT_PARTIAL_FAILURE
    assert "無法辨識的貨運代號" in capsys.readouterr().out


def test_refresh_carrier_filter_with_nothing_left_says_so(monkeypatch, hist_home, capsys):
    _remember("900000000001", "配送中", carrier="tcat")
    t, e = FakeAdapter("tcat", found=True), FakeAdapter("ecan", found=True)
    monkeypatch.setattr(track, "CARRIERS", {"tcat": t, "ecan": e})
    assert track.run(["--refresh-pending", "--carrier", "ecan"]) == 0
    out = capsys.readouterr().out
    assert "沒有符合條件的未結案包裹" in out and "即將對" not in out
    assert (t.calls, e.calls) == (0, 0)


def test_match_plus_carrier_mismatch_does_not_blame_the_name(monkeypatch, hist_home, capsys):
    import labels
    _remember("900000000001", "配送中", carrier="tcat")
    labels.set_label("900000000001", "耳機")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat"), "ecan": FakeAdapter("ecan")})
    assert track.run(["--refresh-pending", "--match", "耳機", "--carrier", "ecan"]) == 0
    out = capsys.readouterr().out
    assert "沒有符合條件的未結案包裹" in out and "--carrier ecan" in out



# ── v0.5.1 延後項目 ────────────────────────────────────────────────────

def test_find_accepts_the_last_four_digits(hist_home, capsys):
    _remember("900000000001", "配送中")
    _remember("900000000002", "配送中")
    assert track.run(["--find", "0001"]) == 0
    out = capsys.readouterr().out
    assert "單號末四碼：0001" in out and "單號末四碼：0002" not in out


def test_find_by_last_four_digits_lists_every_collision(hist_home):
    _remember("900000000001", "配送中")
    _remember("800000000001", "配送中")
    assert track.run(["--find", "0001"]) == 8


def test_retention_hint_names_the_parcel_and_how_to_see_its_number(monkeypatch, hist_home, capsys):
    import carriers
    monkeypatch.setitem(carriers.CARRIER_META["tcat"], "retention_days", 10)
    _remember("900000000001", "配送中", event_time="2026/01/01 10:00")
    track.run(["--pending"])
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "保留期" in ln)
    assert "末四碼 0001" in line and "--full-numbers" in line


def _orphan_name():
    import labels
    _remember("900000000001", "配送中")
    labels.set_label("900000000001", "耳機")
    labels.set_label("900000000009", "孤兒耳機")   # 紀錄已不存在，只剩名稱


def test_find_still_finds_names_whose_record_is_gone(hist_home, capsys):
    _orphan_name()
    assert track.run(["--find", "孤兒"]) == 0
    out = capsys.readouterr().out
    assert "孤兒耳機" in out and "只剩名稱，查詢紀錄已不存在" in out


def test_find_json_marks_orphan_names(hist_home, capsys):
    _orphan_name()
    track.run(["--find", "孤兒", "--json"])
    match = json.loads(capsys.readouterr().out)["matches"][0]
    assert match["record_missing"] is True and match["number"] == "900000000009"


def test_history_mentions_orphan_names_and_how_to_clear_them(hist_home, capsys):
    _orphan_name()
    track.run(["--history"])
    out = capsys.readouterr().out
    assert "另有 1 個名稱沒有對應的查詢紀錄" in out
    assert "--clear-label" in out and "--forget-all" in out


def test_history_has_no_orphan_note_when_there_are_none(hist_home, capsys):
    _remember("900000000001", "配送中")
    track.run(["--history"])
    assert "沒有對應的查詢紀錄" not in capsys.readouterr().out


def test_unparseable_checked_time_is_not_blamed_on_the_clock(monkeypatch, hist_home, capsys):
    _remember("900000000001", "配送中")
    _set_checked("900000000001", "2026-10-16T15:03:00")   # 少了時區
    track.run(["--pending"])
    line = next(ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("上次查詢："))
    assert "時間格式無法判讀" in line and "本機時間異常" not in line


def test_far_future_event_does_not_say_today(monkeypatch, hist_home, capsys):
    future = (datetime.now() + timedelta(days=3)).strftime("%Y/%m/%d %H:%M")
    _remember("900000000001", "配送中", event_time=future)
    track.run(["--pending"])
    out = capsys.readouterr().out
    assert "今天有新進度" not in out and f"物流事件：{future}" in out


def test_a_single_format_candidate_reports_errors_like_an_explicit_carrier(monkeypatch, capsys):
    """格式只符合一家（例如蝦皮 TW 開頭）＝實際上就是指定了那一家：用不了是 exit 3，
    不是「查詢未完成」的 exit 5（v0.5.1 以前蝦皮被風控擋下時就是這樣誤導）。"""
    err = CarrierUnavailable("蝦皮擋下了這次自動查詢")
    monkeypatch.setattr(track, "CARRIERS", {"tcat": FakeAdapter("tcat", detects=False),
                                            "spx": FakeAdapter("spx", raises=err)})
    assert track.run(["TW0000000000002"]) == 3
    assert "蝦皮擋下了這次自動查詢" in capsys.readouterr().out
