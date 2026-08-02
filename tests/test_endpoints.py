"""查詢網址集中管理：站方改版時只要改設定，不必動程式碼。

也驗「網址錯了會怎麼通知使用者」——實測顯示原本一律顯示「連線失敗」，
但 404 不是連線問題，那個訊息會把使用者送去查網路而不是查設定。
"""
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import endpoints  # noqa: E402


def test_every_carrier_has_a_default_endpoint():
    for code in ("tcat", "kerrytj", "ecan", "pchome", "fusheng", "spx", "17track"):
        assert endpoints.get(code), f"{code} 缺預設網址"


def test_defaults_need_no_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv(endpoints.HOME_ENV, str(tmp_path))
    assert "t-cat.com.tw" in endpoints.get("tcat")["trace"]


def test_override_file_replaces_only_named_keys(tmp_path, monkeypatch):
    monkeypatch.setenv(endpoints.HOME_ENV, str(tmp_path))
    cfg = tmp_path / endpoints.FILE_NAME
    cfg.write_text(json.dumps({"tcat": {"trace": "https://example.test/new"}}),
                   encoding="utf-8")
    assert endpoints.get("tcat")["trace"] == "https://example.test/new"
    # 沒被覆寫的鍵維持預設，不會因為部分覆寫就整組消失
    assert "TraceDetail" in endpoints.get("tcat")["detail"]
    assert "kerrytj" in endpoints.all_endpoints()


def test_corrupt_override_falls_back_to_defaults(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(endpoints.HOME_ENV, str(tmp_path))
    (tmp_path / endpoints.FILE_NAME).write_text("{ not json", encoding="utf-8")
    assert "t-cat.com.tw" in endpoints.get("tcat")["trace"], "設定壞掉不可讓查詢死掉"
    assert "endpoints" in capsys.readouterr().err, "設定壞掉要有警告，否則使用者不知道覆寫沒生效"


def test_unknown_carrier_returns_empty():
    assert endpoints.get("no-such-carrier") == {}


# ── 網址錯誤時的使用者訊息（實測原本顯示「連線失敗」，具誤導性）──────────

def _http_error(status: int) -> requests.HTTPError:
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(f"{status} Client Error", response=resp)


@pytest.mark.parametrize("status,expect", [
    (404, "網址"),      # 端點不存在 → 指向設定，不是網路
    (410, "網址"),
    (500, "站方"),      # 對方伺服器問題 → 稍後再試
    (503, "站方"),
])
def test_http_status_maps_to_actionable_message(status, expect):
    import track
    assert expect in track.describe_network_error(_http_error(status))


def test_timeout_and_connection_error_stay_distinguishable():
    import track
    assert "逾時" in track.describe_network_error(requests.exceptions.Timeout())
    assert "連線" in track.describe_network_error(requests.exceptions.ConnectionError())


def test_404_message_points_at_the_endpoint_config():
    """使用者要知道「去哪裡改」，否則訊息等於沒說。"""
    import track
    msg = track.describe_network_error(_http_error(404))
    assert "--endpoints" in msg or "endpoints.json" in msg


def test_override_missing_placeholder_is_rejected(tmp_path, monkeypatch, capsys):
    """少了 {number} 的覆寫會讓每個單號都查同一個網址——靜默給錯資料比報錯更糟。"""
    monkeypatch.setenv(endpoints.HOME_ENV, str(tmp_path))
    (tmp_path / endpoints.FILE_NAME).write_text(
        json.dumps({"pchome": {"query": "https://example.test/no-placeholder"}}),
        encoding="utf-8")
    assert "{number}" in endpoints.get("pchome")["query"], "應退回預設"
    assert "number" in capsys.readouterr().err


def test_override_with_wrong_placeholder_name_is_rejected(tmp_path, monkeypatch, capsys):
    """{Number} 大小寫錯會讓 .format() 拋 KeyError，而 CLI 沒接這個例外。"""
    monkeypatch.setenv(endpoints.HOME_ENV, str(tmp_path))
    (tmp_path / endpoints.FILE_NAME).write_text(
        json.dumps({"fusheng": {"query": "https://example.test/{Number}"}}),
        encoding="utf-8")
    assert endpoints.get("fusheng")["query"] == endpoints.DEFAULTS["fusheng"]["query"]


def test_non_string_override_value_warns_instead_of_vanishing(tmp_path, monkeypatch, capsys):
    """文件說「壞掉會退回預設並印警告」——原本只有整檔壞才警告，單鍵錯是靜默丟棄。"""
    monkeypatch.setenv(endpoints.HOME_ENV, str(tmp_path))
    (tmp_path / endpoints.FILE_NAME).write_text(
        json.dumps({"tcat": {"trace": 12345}}), encoding="utf-8")
    assert endpoints.get("tcat")["trace"] == endpoints.DEFAULTS["tcat"]["trace"]
    assert "tcat" in capsys.readouterr().err


def test_requirements_file_is_ascii_only():
    """pip 以系統 locale 編碼讀 requirements.txt：非 ASCII 註解會讓繁中 Windows
    （cp950）安裝直接 UnicodeDecodeError。用測試守住，別靠人眼看（我自己就漏了一行）。
    """
    raw = (Path(__file__).resolve().parent.parent / "requirements.txt").read_bytes()
    try:
        raw.decode("ascii")
    except UnicodeDecodeError as e:
        bad = raw[e.start:e.end].decode("utf-8", "replace")
        raise AssertionError(f"requirements.txt 含非 ASCII 字元 {bad!r}（offset {e.start}）")


def test_no_file_read_or_write_relies_on_the_platform_default_encoding():
    """未指定 encoding 的檔案讀寫在 Windows 會用 cp1252/cp950 → UnicodeDecodeError。

    產品程式碼一直是對的；掛掉的是測試自己（2026-08-02 Windows CI 首跑抓到）。
    用測試守住整個 repo，因為這種疏漏靠 review 看不出來——少寫一個參數而已。

    用 AST 而非正則：`p.write_text(json.dumps(x), encoding="utf-8")` 的第一個 `)`
    屬於 json.dumps，正則會在那裡斷掉而誤報（第一版就是這樣自己絆倒）。
    """
    import ast

    root = Path(__file__).resolve().parent.parent
    offenders = []
    for py in sorted(list((root / "scripts").rglob("*.py")) + list((root / "tests").glob("*.py"))):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", ""))
            if name not in ("read_text", "write_text", "open"):
                continue
            kwargs = {k.arg for k in node.keywords}
            if "encoding" in kwargs:
                continue
            if name == "open":
                mode = next((a.value for a in node.args[1:2]
                             if isinstance(a, ast.Constant)), "r")
                if "b" in str(mode):      # 二進位模式沒有編碼問題
                    continue
            offenders.append(f"{py.relative_to(root)}:{node.lineno} {name}()")
    assert not offenders, ("以下檔案操作未指定 encoding（Windows 會用系統 locale）：\n"
                           + "\n".join(offenders))
