#!/usr/bin/env python3
"""capture_fixture.py — 擷取一次真實查詢的原始回應，做成校準用的草稿 fixture。

**維護者／貢獻者專用工具，不是給終端使用者的功能**——所以獨立成一支腳本，
不掛在 track.py 的 CLI 介面上（track.py 的 flag 都是「查包裹」這個心智模型的
延伸；這支工具做的事完全不同：發一次真實請求、把原始回應存成測試 fixture，
讓 kerrytj/ecan/pchome 三家目前靠合成 payload 撐著的 found-path parser，日後
能對照真實資料校準）。也支援 17TRACK 橋接（全家/7-11 等）的回應擷取。

用法：
    python3 scripts/capture_fixture.py <真實單號> --carrier kerrytj
    python3 scripts/capture_fixture.py <真實單號> --carrier ecan
    python3 scripts/capture_fixture.py <真實單號> --carrier famiport --via-17track

會寫出兩個檔案到 tests/fixtures/（可用 --out-dir 覆寫）：
- `<carrier>_found_captured.<ext>`：原始回應（已做初步個資遮蔽）
- `<carrier>_found_captured_notes.md`：待人工補完的 notes 草稿

⚠️ 個資警告：寫入前只做了保守的正則遮蔽（單號本身／電話／身分證字號樣式／email／
常見地址樣式），**中文姓名完全沒有自動偵測**。這是輔助，不是保證——commit 這個
fixture 之前，一定要親自打開檔案看過一遍，notes 草稿裡也會重複這個提醒。

不支援蝦皮 SPX：SPX 走 headless 瀏覽器把 DOM 現場渲染出來，不是一個單純的 HTTP
回應可以存檔——這支工具攔截的是 requests.Session 的請求/回應，蝦皮的追蹤結果不會
經過那一層。要校準 SPX 得靠人工開瀏覽器開發者工具存頁面，這裡誠實地拒絕而不是
假裝擷取到東西。
"""
from __future__ import annotations

import argparse
import contextlib
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests

# 跟 scripts/ 目錄下其他模組同一套慣例（history.py、endpoints.py 皆同）：不自己
# 插 sys.path，仰賴執行方式本身把 scripts/ 放上去——`python3 scripts/capture_fixture.py`
# 時 Python 自動把腳本所在目錄放進 sys.path[0]；測試則由 conftest/test 檔自行插入。
import track  # 借用 describe_network_error，錯誤訊息不要有兩套說法
from carriers import CARRIERS
from carriers.base import CarrierUnavailable, ParseError, TrackResult
from carriers.seventeentrack import CARRIER_CODES

# 找不到規則對應時的預設副檔名／編碼／fixture 檔名前綴。
# fusheng 的 fixture 前綴沿用既有慣例 "fs"（既有檔案：fs_notes.md、fs_found.html），
# 其餘直接用 carrier code——新增檔名跟既有檔名對不上，人工校準時自己會發現、改掉即可。
_EXT = {"kerrytj": "json", "ecan": "html", "pchome": "html",
       "tcat": "html", "fusheng": "html", "17track": "json"}
_KNOWN_ENCODING = {"ecan": "big5"}  # 其餘走 requests 預設的 utf-8
_FIXTURE_PREFIX = {"fusheng": "fs"}

_SPX_UNSUPPORTED_MSG = (
    "蝦皮 SPX 走 headless 瀏覽器現場渲染 DOM，不是單純的 HTTP 回應——本工具攔截的是"
    "requests.Session，蝦皮的追蹤結果不會經過那一層，擷取不到東西。\n"
    "要校準 SPX 只能人工開瀏覽器開發者工具、手動存頁面內容，比照既有 fixture 慣例"
    "自行加進 tests/fixtures/。")


# ── 個資遮蔽 ────────────────────────────────────────────────────────────
#
# 「保守」的意思是：規則涵蓋常見樣式，但不宣稱完整——尤其中文姓名（2-4 個中文字，
# 跟一般狀態文字沒有可靠的正則區分法）完全不處理。這裡做的是降低風險，不是保證，
# 所以呼叫端一定要印出警告，不能讓沉默的「已遮蔽」給人一種可以不看內容就 commit 的錯覺。

_PHONE_RE = re.compile(r"\b09\d{2}-?\d{3}-?\d{3}\b|\b0\d{1,2}-?\d{6,8}\b")
_ID_NUMBER_RE = re.compile(r"\b[A-Za-z][12]\d{8}\b")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
# 縣市可省略（很多站只印到路名），但至少要有路/街/巷/弄其中之一加上門牌號碼「號」，
# 避免隨便一串中文字被誤判成地址。
_ADDRESS_RE = re.compile(
    r"(?:[一-鿿]{2,3}(?:縣|市)[一-鿿]{0,4}(?:區|鄉|鎮|市)?)?"
    r"[一-鿿0-9]{1,10}(?:路|街|巷|弄)[一-鿿0-9]{0,6}\d{1,4}號")

_SCRUB_LABELS = ("單號", "電話", "身分證字號", "email", "地址")


def fake_number(real: str) -> str:
    """產生跟原始單號等長、字元類型相同的假單號。

    保留長度與「數字/大寫字母/小寫字母」的類型，是為了不要破壞頁面欄位寬度或格式
    驗證（有些頁面拿單號長度當合法性判斷）；不是要讓假單號看起來像真的。數字一律
    代換成 9，跟既有 fixture（900000000001 之類）用的假單號風格一致。
    """
    out = []
    for ch in real:
        if ch.isdigit():
            out.append("9")
        elif ch.isupper():
            out.append("X")
        elif ch.islower():
            out.append("x")
        else:
            out.append(ch)
    return "".join(out)


def scrub_personal_data(text: str, number: str) -> tuple[str, dict[str, int]]:
    """回傳 (遮蔽後文字, 各類別遮蔽次數)。真實單號一律先代換，其餘走正則。"""
    counts = dict.fromkeys(_SCRUB_LABELS, 0)
    if number and number in text:
        counts["單號"] = text.count(number)
        text = text.replace(number, fake_number(number))
    text, counts["電話"] = _PHONE_RE.subn("[電話已遮蔽]", text)
    text, counts["身分證字號"] = _ID_NUMBER_RE.subn("[身分證字號已遮蔽]", text)
    text, counts["email"] = _EMAIL_RE.subn("[email已遮蔽]", text)
    text, counts["地址"] = _ADDRESS_RE.subn("[地址已遮蔽]", text)
    return text, counts


# ── 攔截 HTTP 回應 ──────────────────────────────────────────────────────
#
# 包在 requests.Session.request 這一層，不是 requests.get/requests.post：
# T-cat 用自己的 requests.Session() 管 cookie（見 carriers/tcat.py），頂層的
# requests.get/post 攔不到它；Session.request 是兩種呼叫方式共同的底層（連
# requests.get() 內部也是建一個 Session 再呼叫 .request()），一次攔截兩種情境。
#
# 只在單次擷取呼叫期間短暫替換、finally 一定還原——這是個一次性 CLI 工具，不是
# 常駐服務，沒有多執行緒同時打的疑慮。

@dataclass
class _Call:
    method: str
    url: str
    status_code: int | None
    content: bytes = field(repr=False)


class _ResponseRecorder:
    def __init__(self) -> None:
        self.calls: list[_Call] = []

    def wrap(self, real_request):
        def _wrapped(session_self, *args, **kwargs):
            resp = real_request(session_self, *args, **kwargs)
            method, url = _extract_method_url(args, kwargs)
            self.calls.append(_Call(method=method, url=url,
                                    status_code=getattr(resp, "status_code", None),
                                    content=getattr(resp, "content", b"") or b""))
            return resp
        return _wrapped


def _extract_method_url(args: tuple, kwargs: dict) -> tuple[str, str]:
    """Session.request 可能收位置參數（Session.get/post 的路徑）或 method=/url=
    關鍵字（requests.get/post 等頂層便利函式的路徑）；兩種都要接得住。抓不準也
    只影響顯示用的訊息，不影響擷取到的回應內容本身。
    """
    method, url = kwargs.get("method"), kwargs.get("url")
    remaining = list(args)
    if method is None and remaining:
        method = remaining.pop(0)
    if url is None and remaining:
        url = remaining.pop(0)
    return str(method or "?").upper(), str(url or "?")


@contextlib.contextmanager
def _recording():
    recorder = _ResponseRecorder()
    orig = requests.Session.request
    requests.Session.request = recorder.wrap(orig)
    try:
        yield recorder
    finally:
        requests.Session.request = orig


# ── 主流程 ──────────────────────────────────────────────────────────────

def _module_name(carrier_code: str, via_17track: bool) -> str:
    return "seventeentrack" if via_17track else carrier_code


def capture(number: str, carrier_code: str, *, via_17track: bool, out_dir: Path) -> int:
    if not via_17track and carrier_code == "spx":
        print(_SPX_UNSUPPORTED_MSG)
        return 2

    if via_17track:
        if carrier_code not in CARRIER_CODES:
            print(f"17TRACK 不認得的貨運代號：{carrier_code}\n"
                  f"可用：{'/'.join(sorted(CARRIER_CODES))}")
            return 2
        adapter = CARRIERS["17track"]
        display_name = f"17TRACK（{carrier_code}）"
        prefix, ext = f"17track_{carrier_code}", _EXT["17track"]
        numeric_code = CARRIER_CODES[carrier_code]

        def _do_query():
            return adapter.track(number, carrier_code=numeric_code)
    else:
        direct = [c for c in CARRIERS if c != "17track"]
        if carrier_code not in direct:
            print(f"未知的貨運代號：{carrier_code}\n可用：{'/'.join(sorted(direct))}"
                  f"（中華郵政/全家/7-11/新竹請加 --via-17track）")
            return 2
        adapter = CARRIERS[carrier_code]
        display_name = adapter.name
        prefix = _FIXTURE_PREFIX.get(carrier_code, carrier_code)
        ext = _EXT.get(carrier_code, "html")

        def _do_query():
            return adapter.track(number)

    with _recording() as recorder:
        try:
            result = _do_query()
        except (CarrierUnavailable, ParseError) as e:
            print(f"擷取失敗（{display_name}　單號 {number}）：{e}")
            _print_calls_made(recorder.calls)
            return 3
        except requests.RequestException as e:
            print(f"擷取失敗（{display_name}　單號 {number}）："
                  f"{track.describe_network_error(e)}")
            _print_calls_made(recorder.calls)
            return 3

    if not recorder.calls:
        print(f"沒有攔截到任何 HTTP 請求——{display_name} 可能不是走 requests 套件"
              f"（例如需要瀏覽器），本工具無法擷取原始回應。")
        return 4

    last = recorder.calls[-1]
    encoding = _KNOWN_ENCODING.get(carrier_code, "utf-8")
    raw_text = last.content.decode(encoding, errors="replace")
    scrubbed_text, scrub_counts = scrub_personal_data(raw_text, number)
    try:
        scrubbed_bytes = scrubbed_text.encode(encoding)
    except UnicodeEncodeError:
        print(f"（警告：遮蔽後的文字用原編碼 {encoding} 寫不回去，改用 UTF-8——"
              f"如果這家原本就該是別的編碼，請人工確認擷取檔）")
        encoding = "utf-8"
        scrubbed_bytes = scrubbed_text.encode(encoding, errors="replace")

    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = out_dir / f"{prefix}_found_captured.{ext}"
    notes_path = out_dir / f"{prefix}_found_captured_notes.md"
    fixture_path.write_bytes(scrubbed_bytes)
    notes_path.write_text(
        _render_notes_skeleton(display_name=display_name, carrier_code=carrier_code,
                               module=_module_name(carrier_code, via_17track),
                               number=number, calls=recorder.calls, result=result,
                               prefix=prefix, ext=ext),
        encoding="utf-8")

    print(_render_capture_summary(display_name=display_name, calls=recorder.calls,
                                  fixture_path=fixture_path, notes_path=notes_path,
                                  result=result, scrub_counts=scrub_counts,
                                  content_length=len(scrubbed_bytes)))
    return 0


def _print_calls_made(calls: list[_Call]) -> None:
    if not calls:
        return
    print("（擷取失敗前已送出的請求：）")
    for c in calls:
        print(f"  {c.method} {c.url} → {c.status_code}")


def _render_capture_summary(*, display_name: str, calls: list[_Call], fixture_path: Path,
                            notes_path: Path, result: TrackResult, scrub_counts: dict[str, int],
                            content_length: int) -> str:
    lines = [f"擷取完成：{display_name}", "", "送出的請求："]
    for c in calls:
        lines.append(f"  {c.method} {c.url} → {c.status_code}")
    lines += ["",
             f"原始回應已寫入：{fixture_path}（{content_length} bytes，已套用個資初步遮蔽）",
             f"notes 草稿已寫入：{notes_path}",
             "",
             "── Parser 目前解讀出的欄位（供校準比對）──",
             f"found: {result.found}"]
    if result.found:
        lines.append(f"events: {len(result.events)} 筆")
        for i, e in enumerate(result.events):
            where = f"　{e.location}" if e.location else ""
            lines.append(f"  [{i}] {e.time}　{e.status}{where}")
        if result.latest:
            lines.append(f"latest: {result.latest.status} @ {result.latest.time}")
    lines += ["", "個資初步遮蔽統計：" +
             "、".join(f"{k} {v} 處" for k, v in scrub_counts.items())]
    lines += ["",
             "⚠️⚠️⚠️ 個資警告 ⚠️⚠️⚠️",
             "自動遮蔽只是輔助，不是保證——尤其中文姓名完全沒有自動偵測，需要你自己看過",
             "整份擷取檔內容。commit 前務必人工確認乾淨，細節見 notes 草稿裡的 TODO 清單。"]
    return "\n".join(lines)


def _render_notes_skeleton(*, display_name: str, carrier_code: str, module: str,
                           number: str, calls: list[_Call], result: TrackResult, prefix: str,
                           ext: str) -> str:
    calls_block = "\n".join(f"  - {c.method} {c.url} → {c.status_code}" for c in calls)
    return f"""# {display_name} 抓取紀錄（{date.today().isoformat()} 擷取，待人工校準）— 草稿

**這是 `capture_fixture.py` 自動產生的草稿，不是最終 notes。** 請人工檢視擷取檔與
下方欄位後，視情況併入既有的 `{prefix}_notes.md`，或整份取代原本標示 UNVERIFIED 的
合成 fixture。

## 擷取資訊

- 貨運：{display_name}（{carrier_code}）
- 擷取日期：{date.today().isoformat()}
- 單號：已於擷取檔中代換為 `{fake_number(number)}`（真實單號沒有寫進任何檔案）
- 送出的請求：
{calls_block}
- Parser 目前判讀：found={result.found}，events={len(result.events) if result.found else 0} 筆

## TODO（人工補完才能收工）

- [ ] 對照擷取檔，確認 parser 目前抓到的欄位跟頁面／回應實際內容一致
- [ ] 若欄位結構跟原本 UNVERIFIED 的假設不同，回頭改 `scripts/carriers/{module}.py`
      的 parser，並移除或更新對應的 UNVERIFIED 註解
- [ ] 決定最終檔名（例如 `{prefix}_found.{ext}`），把這份草稿內容併進正式的
      `{prefix}_notes.md`，並用真實 fixture 換掉對應測試檔裡目前的合成 payload
- [ ] **個資複查**（見下方警告）——尤其中文姓名，本工具完全不會自動偵測
- [ ] 校準完成後刪掉這份 `_found_captured.*` 草稿檔

⚠️ 個資警告：自動遮蔽（單號本身／電話樣式／身分證字號樣式／email／常見地址樣式）
只是輔助，不保證乾淨，尤其中文姓名完全沒有自動偵測。commit 前務必親自看過整份
擷取檔內容。
"""


def _default_out_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def run(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="capture_fixture",
        description=("擷取一次真實查詢的原始回應，寫成待人工校準的草稿 fixture "
                     "（維護者／貢獻者工具，不是給終端使用者的功能）。"),
        epilog=("⚠️ 個資警告：寫入前只做了保守的正則遮蔽（單號／電話／身分證字號樣式／"
               "email／常見地址樣式），中文姓名完全沒有自動偵測。這是輔助，不是保證——"
               "產生的 fixture 在 git add／commit 之前，一定要親自打開檔案看過一遍。"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("number", help="真實包裹單號（只用來發這一次請求，不會被寫進任何檔案——"
                                  "檔案裡一律是代換過的假單號）")
    p.add_argument("--carrier", required=True,
                   help="直連：" + "/".join(sorted(c for c in CARRIERS if c != "17track"))
                   + "；搭配 --via-17track 時可用：" + "/".join(sorted(CARRIER_CODES)))
    p.add_argument("--via-17track", action="store_true", dest="via_17track",
                   help="走 17TRACK 橋接擷取（需先設定 PARCEL_KAU_A_17TRACK_KEY）")
    p.add_argument("--out-dir", default=None,
                   help="輸出目錄，預設 tests/fixtures（測試或臨時擷取可覆寫）")
    args = p.parse_args(argv)

    out_dir = Path(args.out_dir) if args.out_dir else _default_out_dir()
    return capture(args.number, args.carrier, via_17track=args.via_17track, out_dir=out_dir)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
