"""查詢紀錄：記住「單號屬於哪家貨運」，讓後續查詢只送一家。

**這是隱私取捨，不是純粹的便利功能。** 沒有紀錄時，一個 12 碼數字單號會被依序送給
五家共用該格式的貨運公司，其中四家與這件包裹無關；有紀錄後只送一家。代價是單號會
落地本機。因此：
- 只在查到結果時寫（查無資料不寫，避免累積無意義單號）
- 檔案權限 600（單號屬個資鄰接，不讓同機其他帳號讀）
- 只存查詢必需的欄位，不存事件全文
- 提供 --forget / --forget-all，並在包裹看似完成時主動標記可刪

存放位置為 `~/.cache/parcel-kau-a/`（比照同作者的 audio-tldr）。注意 macOS 的
Time Machine 只自動排除 `~/Library/Caches`，**不會**排除 `~/.cache`——這個檔案會
進備份。README 有據實說明；不想留痕就用 --no-record 或查完 --forget。

紀錄毀損時一律降級為「無紀錄」繼續查詢，絕不讓它擋住主功能——「毀損」包含整檔
JSON 壞掉與單筆 entry 型別錯兩種。

並行限制：讀-改-寫沒有檔案鎖，兩個同時執行的查詢可能後寫覆蓋先寫。對「個人低頻
查詢」的定位可接受；若要並行大量查詢，這裡需要加鎖。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from carriers.base import TrackResult, parse_event_time

HOME_ENV = "PARCEL_KAU_A_HOME"
_DEFAULT_HOME = Path.home() / ".cache" / "parcel-kau-a"
_FILE_NAME = "history.json"

# 寬鬆比對（使用者 2026-08-02 選定）：誤判成本＝多問一句要不要刪；
# 漏判成本＝單號一直留在本機。各家用詞不統一，故涵蓋常見說法。
# 「投遞」單獨當關鍵字太短——「投遞中」「投遞失敗」都含它，必須用完整詞（外部 review v0.2.0）
COMPLETE_KEYWORDS = ("送達", "順利投遞", "投遞完成", "已投遞", "投遞成功",
                     "配送完成", "已完成", "結案", "取件完成")
# 但「送達」「投遞」都是短詞，會被前瞻性描述誤觸發（「預計送達」不是已完成）。
# 出現下列任一詞就一律不算完成——寧可漏判，也不要叫使用者刪掉還在路上的包裹。
_NOT_YET = ("預計", "預定", "預估", "尚未", "未能", "查無", "無法",
            "失敗", "退回", "異常", "不成功", "中")


def home() -> Path:
    return Path(os.environ.get(HOME_ENV) or _DEFAULT_HOME)


def path() -> Path:
    return home() / _FILE_NAME


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def entries() -> dict[str, dict]:
    """讀全部紀錄。檔案不存在或毀損一律回空 dict，不 raise、不改動檔案。"""
    p = path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(f"（查詢紀錄無法讀取，本次視為無紀錄：{e}）", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}
    # 「毀損」不只是整檔 JSON 壞掉——單筆 value 型別錯也算。在這裡一次擋掉，
    # 讓 record()/--history 等呼叫端都繼承「降級為無紀錄」的保證，
    # 而不是各自重新防禦（2026-08-02 code review Critical）。
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def lookup_entry(number: str) -> dict | None:
    return entries().get(number)


def lookup(number: str) -> str | None:
    """回傳該單號已知的 carrier code，沒有紀錄則 None。"""
    entry = lookup_entry(number)
    return entry.get("carrier") if isinstance(entry, dict) else None


def looks_complete(status: str) -> bool:
    text = status or ""
    if any(w in text for w in _NOT_YET):
        return False
    return any(kw in text for kw in COMPLETE_KEYWORDS)


def days_since_last_event(entry: dict, *, now: datetime | None = None) -> int | None:
    """最後一筆事件距今幾天；時間字串解析不了就回 None。

    回 None 而不是回 0 或改用 last_checked 墊檔：那兩者都是「我多久沒查」而非
    「包裹多久沒動」，拿來當停滯指標會讓使用者誤判。算不出來就不要說。

    比較全程用 naive 本地時間——各站時間都是台灣時間且不帶時區，
    parse_event_time() 也刻意回 naive，混入 aware 只會 TypeError。
    """
    parsed = parse_event_time(entry.get("last_event_time") or "")
    if parsed is None:
        return None
    # 站方時鐘比本機快（或本機時鐘慢）時 delta 會是負的，天數不該出現負值
    return max(0, ((now or datetime.now()) - parsed).days)


def _event_sort_key(entry: dict) -> tuple[int, object]:
    """比照 TrackEvent.sort_key：可解析的時間優先且互相比較，其餘退到後面按字串排。"""
    raw = entry.get("last_event_time") or ""
    parsed = parse_event_time(raw)
    return (1, parsed) if parsed else (0, raw)


def pending(data: dict[str, dict] | None = None) -> list[tuple[str, dict]]:
    """尚未結案的紀錄，依最後事件時間新→舊；時間解析不了的排最後。

    「未結案」＝ looks_complete 不為真。欄位缺漏（v0.2.0 之前的紀錄、或使用者
    手動編輯過）時算未結案——多列一行的代價，遠小於把還在路上的包裹藏起來。

    `data` 讓呼叫端傳入已讀好的 entries()：檔案毀損時 entries() 會印警告，
    同一次操作讀兩次就會印兩次。
    """
    items = entries() if data is None else data
    rows = [(num, e) for num, e in items.items() if not e.get("looks_complete")]
    rows.sort(key=lambda kv: _event_sort_key(kv[1]), reverse=True)
    return rows


def _write(data: dict[str, dict]) -> None:
    """原子寫入 + 600 權限：中斷不會留半截 JSON，暫存檔與正式檔同目錄才能 rename。"""
    d = home()
    d.mkdir(parents=True, exist_ok=True)
    # mkstemp 建檔即為 0600，權限在任何內容寫入之前就到位（無競態窗口）。
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".history-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def record(result: TrackResult) -> bool:
    """查到結果才寫。回傳是否真的寫入。"""
    if not result.found:
        return False
    latest = result.latest
    data = entries()
    existing = data.get(result.number) or {}
    now = _now()
    data[result.number] = {
        "carrier": result.carrier,
        "last_status": latest.status if latest else "",
        "last_event_time": latest.time if latest else "",
        "first_seen": existing.get("first_seen") or now,
        "last_checked": now,
        "looks_complete": looks_complete(latest.status if latest else ""),
    }
    _write(data)
    return True


def forget(number: str) -> bool:
    data = entries()
    if number not in data:
        return False
    del data[number]
    _write(data)
    return True


def forget_all() -> None:
    _write({})
