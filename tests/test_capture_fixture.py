"""capture_fixture.py — 擷取真實回應做校準用 fixture 草稿的離線測試。

一律用假的 requests.Session.request 替身，不打真實網路（spec 需求）。重點覆蓋：
個資遮蔽（單號代換、電話/身分證字號/email/地址正則）、fixture／notes 檔案寫入、
17TRACK 有無 key 兩條路、SPX 明確拒絕、批次遇到例外不崩潰。
"""
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import capture_fixture as cf  # noqa: E402
from carriers.seventeentrack import API_KEY_ENV  # noqa: E402


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200, json_data=None):
        self.content = content
        self.status_code = status_code
        self._json_data = json_data
        self.encoding = "utf-8"

    @property
    def text(self):
        return self.content.decode(self.encoding, errors="replace")

    def json(self):
        if self._json_data is not None:
            return self._json_data
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


def _fake_session_request(fn):
    """把 (method, url, **kwargs) -> _FakeResponse 的簡單函式包成 Session.request 替身。"""
    def _wrapped(self, *args, **kwargs):
        rest = dict(kwargs)
        method = rest.pop("method", None) or (args[0] if args else "GET")
        url = rest.pop("url", None) or (args[1] if len(args) > 1 else
                                        (args[0] if args else ""))
        return fn(method, url, **rest)
    return _wrapped


# ── 個資遮蔽：純函式，不碰網路 ────────────────────────────────────────

def test_fake_number_preserves_length_and_char_class():
    assert cf.fake_number("123456789012") == "9" * 12
    assert cf.fake_number("TW254414081298F") == "XX999999999999X"


def test_scrub_personal_data_replaces_the_real_number():
    text = "單號 123456789012 查詢結果"
    scrubbed, counts = cf.scrub_personal_data(text, "123456789012")
    assert "123456789012" not in scrubbed
    assert counts["單號"] == 1


def test_scrub_personal_data_masks_phone_numbers():
    scrubbed, counts = cf.scrub_personal_data("聯絡電話 0912-345-678 洽收件人", "x")
    assert "0912-345-678" not in scrubbed
    assert counts["電話"] == 1


def test_scrub_personal_data_masks_id_number_pattern():
    scrubbed, counts = cf.scrub_personal_data("身分證 A123456789 已核對", "x")
    assert "A123456789" not in scrubbed
    assert counts["身分證字號"] == 1


def test_scrub_personal_data_masks_email():
    scrubbed, counts = cf.scrub_personal_data("聯絡信箱 someone@example.com", "x")
    assert "someone@example.com" not in scrubbed
    assert counts["email"] == 1


def test_scrub_personal_data_masks_address_like_text():
    scrubbed, counts = cf.scrub_personal_data("配送地址 台北市中山區南京東路123號", "x")
    assert "南京東路123號" not in scrubbed
    assert counts["地址"] == 1


def test_scrub_personal_data_leaves_clean_status_text_untouched():
    scrubbed, counts = cf.scrub_personal_data("順利送達　台北營業所", "999999999999")
    assert scrubbed == "順利送達　台北營業所"
    assert all(v == 0 for v in counts.values())


# ── notes / summary 純字串產出 ─────────────────────────────────────────

def test_notes_skeleton_includes_manual_review_todo_and_privacy_warning():
    from carriers.kerrytj import parse_tracking_response
    result = parse_tracking_response({"list": [], "errTrackNo": ["900000000001"]},
                                     number="900000000001")
    text = cf._render_notes_skeleton(
        display_name="嘉里大榮", carrier_code="kerrytj", module="kerrytj",
        number="900000000001", calls=[cf._Call("POST", "https://x/api", 200, b"{}")],
        result=result, prefix="kerrytj", ext="json")
    assert "TODO" in text
    assert "個資" in text and "中文姓名" in text
    assert "kerrytj_notes.md" in text
    assert "carriers/kerrytj.py" in text


def test_capture_summary_lists_requests_and_extracted_fields():
    from carriers.base import TrackEvent, TrackResult
    result = TrackResult(carrier="tcat", number="x", found=True,
                         events=[TrackEvent(time="2026/08/01 10:00", status="順利送達",
                                            location="台北所")])
    text = cf._render_capture_summary(
        display_name="黑貓宅急便",
        calls=[cf._Call("GET", "https://x/trace", 200, b"abc")],
        fixture_path=Path("/tmp/x.html"), notes_path=Path("/tmp/x_notes.md"),
        result=result, scrub_counts={"單號": 1, "電話": 0, "身分證字號": 0, "email": 0, "地址": 0},
        content_length=3)
    assert "GET https://x/trace" in text
    assert "found: True" in text
    assert "順利送達" in text
    assert "單號 1 處" in text
    assert "個資警告" in text


# ── capture()：假 Session.request，驗證檔案寫入與內容 ──────────────────

@pytest.fixture
def isolated(monkeypatch):
    """capture_fixture 借用 track.CARRIERS 這條路一律用真實 registry，只假 HTTP 層。"""
    yield


def test_capture_writes_deidentified_json_fixture_for_kerrytj(monkeypatch, tmp_path):
    payload = {"list": [{"bolNo": "900000000001", "course": [
        {"statusId": "OK1", "statusIdName": "順利送達",
         "processDepotIdName": "台北所",
         "processCargoCrtDate": 20260801, "processCargoCrtTime": 93000}]}],
              "errTrackNo": []}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def _fake(method, url, **kwargs):
        assert method.upper() == "POST"
        return _FakeResponse(body, 200, json_data=payload)

    monkeypatch.setattr(requests.Session, "request", _fake_session_request(_fake))

    code = cf.capture("900000000001", "kerrytj", via_17track=False, out_dir=tmp_path)
    assert code == 0

    fixture = tmp_path / "kerrytj_found_captured.json"
    notes = tmp_path / "kerrytj_found_captured_notes.md"
    assert fixture.exists() and notes.exists()
    written = fixture.read_text(encoding="utf-8")
    assert "900000000001" not in written, "真實單號不該留在擷取檔裡"
    assert "999999999999" in written
    assert "順利送達" in written  # 站方狀態文字本身不是個資，原樣保留


def test_capture_writes_big5_html_fixture_for_ecan(monkeypatch, tmp_path):
    html = ("<html><body><table><tr><td>項次</td><td>宅配單號</td><td>出貨單號</td>"
           "<td>結案</td><td>最新狀態</td><td>細節說明</td><td>處理日期</td>"
           "<td>營業所</td></tr><tr><td>1</td><td>123456789012</td><td></td>"
           "<td>Y</td><td>順利送達</td><td>已簽收</td><td>2026/08/01 14:30</td>"
           "<td>台北營業所</td></tr></table></body></html>")
    body = html.encode("big5")

    def _fake(method, url, **kwargs):
        return _FakeResponse(body, 200)

    monkeypatch.setattr(requests.Session, "request", _fake_session_request(_fake))

    code = cf.capture("123456789012", "ecan", via_17track=False, out_dir=tmp_path)
    assert code == 0

    fixture = tmp_path / "ecan_found_captured.html"
    raw = fixture.read_bytes().decode("big5")
    assert "123456789012" not in raw
    assert "順利送達" in raw


def test_capture_uses_fs_prefix_for_fusheng_to_match_existing_convention(monkeypatch, tmp_path):
    """既有 fixture 是 fs_notes.md / fs_found.html，不是 fusheng_*——新檔名要對得上。"""
    html = "<html><body><div class='panel-body'><ul></ul></div></body></html>"

    def _fake(method, url, **kwargs):
        return _FakeResponse(html.encode("utf-8"), 200)

    monkeypatch.setattr(requests.Session, "request", _fake_session_request(_fake))
    code = cf.capture("123456789012", "fusheng", via_17track=False, out_dir=tmp_path)
    assert code == 0
    assert (tmp_path / "fs_found_captured.html").exists()


def test_capture_continues_gracefully_when_carrier_raises_network_error(monkeypatch, tmp_path,
                                                                        capsys):
    def _fake(method, url, **kwargs):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "request", _fake_session_request(_fake))
    code = cf.capture("123456789012", "pchome", via_17track=False, out_dir=tmp_path)
    assert code != 0
    assert not list(tmp_path.iterdir()), "失敗時不該留下半成品檔案"
    out = capsys.readouterr().out
    assert "Traceback" not in out
    assert "擷取失敗" in out


def test_capture_picks_the_gettrackinfo_response_not_the_register_response(monkeypatch,
                                                                           tmp_path):
    """17TRACK 兩段式：register 只是登錄，真正的貨態在 gettrackinfo，擷取檔要是後者。"""
    tracking_payload = {"code": 0, "data": {"accepted": [
        {"number": "83546610320956", "track_info": {"tracking": {"providers": [
            {"events": [{"time_iso": "2026-08-01T10:00:00+08:00",
                        "description": "順利投遞"}]}]}}}]}}

    def _fake(method, url, **kwargs):
        if url.endswith("/register"):
            return _FakeResponse(b'{"code":0,"data":{}}', 200, json_data={"code": 0, "data": {}})
        body = json.dumps(tracking_payload, ensure_ascii=False).encode("utf-8")
        return _FakeResponse(body, 200, json_data=tracking_payload)

    monkeypatch.setenv(API_KEY_ENV, "test-key")
    monkeypatch.setattr(requests.Session, "request", _fake_session_request(_fake))

    code = cf.capture("83546610320956", "famiport", via_17track=True, out_dir=tmp_path)
    assert code == 0
    fixture = tmp_path / "17track_famiport_found_captured.json"
    assert fixture.exists()
    written = json.loads(fixture.read_text(encoding="utf-8"))
    assert "順利投遞" in json.dumps(written, ensure_ascii=False)
    assert "83546610320956" not in fixture.read_text(encoding="utf-8")


def test_capture_reports_missing_17track_key_without_writing_files(monkeypatch, tmp_path,
                                                                    capsys):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    code = cf.capture("83546610320956", "famiport", via_17track=True, out_dir=tmp_path)
    assert code != 0
    assert not list(tmp_path.iterdir())
    out = capsys.readouterr().out
    assert API_KEY_ENV in out


def test_capture_rejects_spx_without_touching_the_network(monkeypatch, tmp_path, capsys):
    def _boom(self, *a, **kw):
        raise AssertionError("SPX 不該真的發請求")

    monkeypatch.setattr(requests.Session, "request", _boom)
    code = cf.capture("TW254414081298F", "spx", via_17track=False, out_dir=tmp_path)
    assert code != 0
    assert not list(tmp_path.iterdir())
    assert "headless" in capsys.readouterr().out or "瀏覽器" in capsys.readouterr().out


def test_capture_rejects_unknown_direct_carrier(tmp_path, capsys):
    code = cf.capture("123456789012", "not-a-carrier", via_17track=False, out_dir=tmp_path)
    assert code != 0
    assert not list(tmp_path.iterdir())


def test_capture_rejects_unknown_17track_carrier(tmp_path, capsys):
    code = cf.capture("123456789012", "not-a-carrier", via_17track=True, out_dir=tmp_path)
    assert code != 0
    assert not list(tmp_path.iterdir())


def test_capture_reports_when_no_http_call_is_intercepted(monkeypatch, tmp_path, capsys):
    """理論上的防呆：如果哪天某個 direct carrier 改用別的傳輸層，不該假裝擷取到東西。"""
    class _NoNetworkAdapter:
        code = "kerrytj"
        name = "假嘉里大榮"

        def detect(self, number):
            return True

        def track(self, number):
            from carriers.base import TrackResult
            return TrackResult(carrier="kerrytj", number=number, found=False)

    monkeypatch.setitem(cf.CARRIERS, "kerrytj", _NoNetworkAdapter())
    code = cf.capture("123456789012", "kerrytj", via_17track=False, out_dir=tmp_path)
    assert code != 0
    assert not list(tmp_path.iterdir())
    assert "沒有攔截到" in capsys.readouterr().out


# ── run()：CLI 進入點 ───────────────────────────────────────────────────

def test_run_parses_argv_and_writes_into_out_dir(monkeypatch, tmp_path):
    payload = {"list": [], "errTrackNo": ["123456789012"]}

    def _fake(method, url, **kwargs):
        return _FakeResponse(json.dumps(payload).encode("utf-8"), 200, json_data=payload)

    monkeypatch.setattr(requests.Session, "request", _fake_session_request(_fake))
    code = cf.run(["123456789012", "--carrier", "kerrytj", "--out-dir", str(tmp_path)])
    assert code == 0
    assert (tmp_path / "kerrytj_found_captured.json").exists()


def test_run_rejects_missing_carrier_argument():
    with pytest.raises(SystemExit):
        cf.run(["123456789012"])
