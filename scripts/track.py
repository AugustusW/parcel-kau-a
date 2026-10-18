#!/usr/bin/env python3
"""parcel-kau-a — 台灣包裹追蹤 CLI。

用法：
    track.py <單號> [--carrier tcat|kerrytj|ecan|spx] [--auto] [--json]

不指定 --carrier 時，只有物流商可以唯一判定（格式唯一，或查詢紀錄已知）才會送出
查詢。黑貓／嘉里／宅配通等單號同為 12 碼數字無法由格式區分：這時一筆都不送，列出
候選並以 exit 8 結束，由使用者選一家（--carrier）或同意依序詢問全部（--auto）。
單號是個資鄰接資料，送給無關的物流商要先經過使用者同意（v0.5.0 起）。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

import requests

import carriers
import endpoints
import history
import labels
import snapshot
import storage
from carriers import CARRIERS
from carriers.base import CarrierUnavailable, ParseError, TrackResult
from carriers.seventeentrack import CARRIER_CODES


# 結束碼：0/2/3/4/5 沿用 v0.4.0 單筆查詢語意；以下為管理型命令新增
EXIT_PARTIAL_FAILURE = 6  # 批次完成，但至少一筆查詢或保存失敗
EXIT_PERSISTENCE = 7  # 本機紀錄／名稱未能完整保存或刪除
EXIT_SELECTION_REQUIRED = 8  # 需要使用者選擇（物流商或多個名稱候選）；未送出任何查詢


def _render(result: TrackResult, carrier_name: str) -> str:
    head = f"{carrier_name}　{result.number}"
    if not result.found:
        return f"{head}\n查無資料（單號未登錄、輸入錯誤，或已超過該站保留期限）"
    lines = [head, ""]
    # 與 TrackResult.latest 用同一把排序鑰匙，否則「最新」與列表首行可能不一致
    for e in sorted(result.events, key=lambda x: x.sort_key, reverse=True):
        where = f"　{e.location}" if e.location else ""
        lines.append(f"{e.time}　{e.status}{where}")
    lines += ["", f"來源：{result.source_url}",
              f"查詢時間：{snapshot.now():%Y/%m/%d %H:%M}（剛剛即時查詢）"]
    return "\n".join(lines)


def _carrier_name(entry: dict) -> str:
    """紀錄裡的 carrier code 翻成中文名；認不得就原樣顯示（手動編輯過的檔案也不該爆）。"""
    code = entry.get("carrier")
    if not isinstance(code, str):
        return "?"
    return CARRIERS[code].name if code in CARRIERS else (code or "?")


# ── 本機快照的呈現（spec §5）────────────────────────────────────────────
#
# 快照不是即時貨態。每個列出快照的畫面都要講明兩件事：這是本機紀錄、沒有連線；
# 以及兩種時間——物流事件時間（包裹最後一次動）與上次查詢時間（資料多舊）。

SNAPSHOT_NOTE = "本機歷史快照；未連線"


def _display_number(number: str, full: bool) -> str:
    """列表預設只顯示末四碼（spec 原則 8）；JSON 不經過這裡，一律帶完整單號。"""
    return f"單號：{number}" if full else f"單號末四碼：{number[-4:]}"


def _local_minutes(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone().strftime("%Y/%m/%d %H:%M")


def _stall_days(entry: dict) -> int | None:
    """包裹多久沒有新事件。各站時間是不帶時區的台灣時間，所以拿本機 naive 時間比。"""
    return history.days_since_last_event(
        entry, now=snapshot.now().astimezone().replace(tzinfo=None))


def _checked_line(v: dict) -> str:
    if v["checked_problem"] == "unparseable":
        return f"上次查詢：{v['checked_at'] or '?'}（時間格式無法判讀）"
    if v["checked_at"] is None:
        return "上次查詢：時間未知"
    if v["checked_problem"] == "future":
        return f"上次查詢：{v['checked_at']}（晚於現在，本機時間異常，無法計算經過時間）"
    tail = "，資料可能過期" if v["freshness"] == "stale" else ""
    return (f"上次查詢：{_local_minutes(v['checked_at'])}"
            f"（{snapshot.relative(v['checked_age_seconds'])}{tail}）")


def _render_snapshot_item(v: dict, *, full: bool, stall_days: int | None,
                          complete_mark: bool = False) -> list[str]:
    code = v["carrier"]
    name = CARRIERS[code].name if code in CARRIERS else (code or "?")
    if v["record_missing"]:
        return [v["label"] or "?", _display_number(v["number"], full),
                "（只剩名稱，查詢紀錄已不存在；可用 --clear-label 清除這個名稱）"]
    head = "　".join(x for x in (v["label"], name, v["latest_status"]) if x)
    if complete_mark and v["looks_complete"]:
        head += "　✓可刪（看似已完成）"
    if v["event_time"]:
        stall = ("" if stall_days is None else
                 "（今天有新進度）" if stall_days == 0 else f"（{stall_days} 天沒有新進度）")
        event = f"物流事件：{v['event_time']}{stall}"
    else:
        event = "物流事件：未知"
    lines = [head, _display_number(v["number"], full), event, _checked_line(v)]
    if v["past_retention"]:
        who = v["number"] if full else f"末四碼 {v['number'][-4:]}"
        how = "" if full else "；加 --full-numbers 可看完整單號"
        lines.append(f"物流事件已超過物流商查詢保留期（{who}），可用 --forget <單號> 刪除這筆紀錄{how}")
    return lines


def _views(rows: list[tuple[str, dict]], names: dict[str, str],
           missing: frozenset = frozenset()) -> list[dict]:
    now = snapshot.now()
    return [snapshot.view(n, e, label=names.get(n), now=now, record_missing=n in missing)
            for n, e in rows]


def _emit_envelope(operation: str, **fields) -> None:
    """管理型命令的 JSON：stdout 只有這一份 document，提示一律走 stderr（spec §5.6）。"""
    print(json.dumps({"schema_version": 1, "operation": operation, **fields},
                     ensure_ascii=False))


def _fail(args, code: int, message: str, *, operation: str = "error", **fields) -> int:
    """新增的錯誤路徑共用：JSON 模式下錯誤也是一份 envelope，訊息另走 stderr。"""
    if getattr(args, "as_json", False):
        _emit_envelope(operation, ok=False, exit_code=code, message=message, **fields)
        print(message, file=sys.stderr)
    else:
        print(message)
    return code


# ── 單號送出前確認（spec §9）──────────────────────────────────────────────

def _candidate_codes(number: str, *, exclude: str | None = None) -> list[str]:
    """格式相符、且允許參與自動判別的直連物流商。

    不在 CARRIER_META 的 code 一律不允許：新 adapter 忘了寫 metadata 時，失敗方向是
    「單號不會被自動送出」，而不是悄悄加入輪巡。
    """
    return [c for c, a in CARRIERS.items()
            if c != "17track" and c != exclude
            and carriers.CARRIER_META.get(c, {}).get("auto_detect_allowed", False)
            and a.detect(number)]


def _selection_required(number: str, codes: list[str], args, *, reason: str) -> int:
    hint = ("知道是哪一家：加 --carrier <code> 只送那一家\n"
            "同意依序詢問以上全部：加 --auto（單號會被送到其中多家，命中即停）")
    if args.as_json:
        _emit_envelope("detect", selection_required=True, number=number, reason=reason,
                       candidates=[{"carrier": c, "name": CARRIERS[c].name} for c in codes])
        print(f"{reason}，尚未送出任何查詢。\n{hint}", file=sys.stderr)
    else:
        print(f"{reason}，尚未送出任何查詢。\n可能的物流商：")
        for c in codes:
            print(f"  {c}　{CARRIERS[c].name}")
        print(hint)
    return EXIT_SELECTION_REQUIRED


def _run_rename(args) -> int:
    number, raw = args.rename
    if history.lookup_entry(number) is None:
        return _fail(args, 2, f"查詢紀錄中沒有 {number}，只能為查詢過的包裹命名",
                     operation="rename")
    try:
        name = labels.validate(raw)
        labels.set_label(number, name)
    except labels.InvalidLabel as e:
        return _fail(args, 2, f"名稱不合法：{e}", operation="rename")
    except OSError as e:
        return _fail(args, EXIT_PERSISTENCE, f"名稱未儲存：{e}", operation="rename")
    if args.as_json:
        _emit_envelope("rename", number=number, label=name, saved=True)
    else:
        print(f"已改名為「{name}」")
    return 0


def _run_clear_label(args) -> int:
    number = args.clear_label
    try:
        removed = labels.remove(number)
    except OSError as e:
        return _fail(args, EXIT_PERSISTENCE, f"名稱未清除：{e}", operation="clear_label")
    if args.as_json:
        _emit_envelope("clear_label", number=number, removed=removed)
    else:
        print("已清除名稱" if removed else "這個單號沒有設定名稱")
    return 0


def _print_candidates(rows, views, *, full: bool) -> None:
    for i, ((_, entry), v) in enumerate(zip(rows, views), 1):
        print()
        item = _render_snapshot_item(v, full=full, stall_days=_stall_days(entry))
        item[0] = f"{i}. {item[0]}"
        print("\n".join(item))


def _run_find(args) -> int:
    """只讀本機。找到多筆時列出全部並以 exit 8 結束——由使用者選，絕不替他挑一筆。"""
    data = history.entries()
    names = labels.load_for_read()
    # 只剩名稱的單號（紀錄檔曾毀損被另存）也要找得到，否則那些名稱就再也看不到了
    orphans = frozenset(n for n in names if n not in data)
    hits = labels.find(args.find, [*data.keys(), *sorted(orphans)], names)
    rows = [(n, data.get(n, {})) for n in hits]
    views = _views(rows, names, orphans)
    need_pick = len(views) > 1
    code = EXIT_SELECTION_REQUIRED if need_pick else 0
    if args.as_json:
        _emit_envelope("find", snapshot=True, live_query=False,
                       selection_required=need_pick, matches=views)
        return code
    if not views:
        print(f"找不到名稱或單號符合「{args.find}」的包裹（本機紀錄，未連線）")
        return 0
    if need_pick:
        print(f"找到 {len(views)} 個名稱相近的包裹（{SNAPSHOT_NOTE}）")
        _print_candidates(rows, views, full=args.full_numbers)
        print("\n這些不是即時貨態。請指定編號或完整名稱；若要全部更新，請明確說「全部更新」。")
    else:
        print(f"找到 1 個包裹（{SNAPSHOT_NOTE}）\n")
        print("\n".join(_render_snapshot_item(views[0], full=args.full_numbers,
                                              stall_days=_stall_days(rows[0][1]))))
        print("\n這不是即時貨態；需要目前貨態請重新查詢這一筆。")
    return code


# ── 刪除：先刪名稱、再刪紀錄（spec §4.5 privacy-first）─────────────────
#
# 兩個檔案無法形成同一個 transaction。名稱比單號更有語意，所以先刪名稱；名稱刪不掉
# 就整個停下、紀錄不動；名稱刪了但紀錄寫不進去，回報部分成功並可安全重試。
# 任何一步失敗都是 exit 7，不得回報完整成功。

def _run_forget(args) -> int:
    n = args.forget
    try:
        with storage.mutation_lock(history.home()):
            try:
                label_removed = labels.remove(n)
            except OSError as e:
                return _fail(args, EXIT_PERSISTENCE,
                             f"未刪除任何資料：名稱檔無法處理（{e}）。"
                             f"修正或改名該檔後重試；--forget-all 會連同它一起刪除",
                             operation="forget", label_removed=False, history_removed=False)
            try:
                history_removed = history.forget(n)
            except OSError as e:
                done = "名稱已刪除，" if label_removed else ""
                return _fail(args, EXIT_PERSISTENCE,
                             f"{done}查詢紀錄刪除失敗（{e}），可重試 --forget {n}",
                             operation="forget", label_removed=label_removed,
                             history_removed=False)
    except storage.LockBusy as e:
        return _fail(args, EXIT_PERSISTENCE, str(e), operation="forget",
                     label_removed=False, history_removed=False)
    if args.as_json:
        _emit_envelope("forget", number=n, label_removed=label_removed,
                       history_removed=history_removed, complete=True)
    elif history_removed or label_removed:
        print(f"已刪除 {n} 的查詢紀錄" + ("與名稱" if label_removed else ""))
    else:
        print(f"查詢紀錄中沒有 {n}")
    return 0


def _run_forget_all(args) -> int:
    try:
        with storage.mutation_lock(history.home()):
            try:
                labels_removed = labels.remove_all()
            except OSError as e:
                return _fail(args, EXIT_PERSISTENCE, f"未刪除任何資料：名稱檔無法刪除（{e}）",
                             operation="forget_all", label_removed=False, history_removed=False)
            try:
                history.forget_all()
            except OSError as e:
                return _fail(args, EXIT_PERSISTENCE,
                             f"名稱已全部刪除，查詢紀錄清空失敗（{e}），可重試 --forget-all",
                             operation="forget_all", label_removed=True, history_removed=False)
    except storage.LockBusy as e:
        return _fail(args, EXIT_PERSISTENCE, str(e), operation="forget_all",
                     label_removed=False, history_removed=False)
    if args.as_json:
        _emit_envelope("forget_all", label_removed=labels_removed, history_removed=True,
                       complete=True)
    else:
        print("已清空所有查詢紀錄" + ("與名稱" if labels_removed else ""))
    return 0


def _run_snapshot_listing(args) -> int:
    data = history.entries()
    if args.show_pending:
        rows = history.pending(data)
    else:
        rows = sorted(data.items(), key=lambda kv: str(kv[1].get("last_checked", "")),
                      reverse=True)
    names = labels.load_for_read()
    views = _views(rows, names)
    orphan_count = sum(1 for n in names if n not in data)
    op = "pending" if args.show_pending else "history"
    if args.as_json:
        if not data:
            print("查詢紀錄是空的", file=sys.stderr)
        _emit_envelope(op, snapshot=True, live_query=False, items=views,
                       orphan_labels=orphan_count)
        return 0
    if not data:
        print("查詢紀錄是空的")
        return 0
    if args.show_pending and not rows:
        # 「沒紀錄」與「全都到了」是兩件事，講同一句話會讓使用者以為功能壞了
        print(f"沒有未結案的包裹（{len(data)} 筆全部已完成，可用 --forget-all 清掉）")
        return 0
    title = "未結案包裹" if args.show_pending else "查詢紀錄"
    print(f"{title}（{len(rows)} 筆，{SNAPSHOT_NOTE}）")
    if args.show_history:
        print(f"檔案：{history.path()}")
    for (_, entry), v in zip(rows, views):
        print()
        stall = None if v["looks_complete"] else _stall_days(entry)
        print("\n".join(_render_snapshot_item(v, full=args.full_numbers, stall_days=stall,
                                              complete_mark=args.show_history)))
    if args.show_pending:
        print("\n需要目前貨態時，請使用 --refresh-pending 或指定其中一筆重新查詢。")
    if args.show_history and orphan_count:
        print(f"\n另有 {orphan_count} 個名稱沒有對應的查詢紀錄（可能是紀錄檔曾毀損）："
              f"--find 找得到它們，可用 --clear-label <單號> 逐一清除，或 --forget-all 全部清除")
    return 0


def describe_network_error(e: Exception) -> str:
    """把網路層例外翻成使用者能據以行動的訊息。

    實測（2026-08-02）：查詢網址若失效，原本一律顯示「連線失敗」——但 404 不是
    連線問題，那個字會把使用者送去查網路，而不是去查網址設定。改為分類處理。
    """
    resp = getattr(e, "response", None)
    status = getattr(resp, "status_code", None)
    if status in (404, 410):
        return (f"查詢網址回 {status}，該網址可能已失效（站方改版）。"
                f"可用 --endpoints 查看目前設定，或在 {endpoints.path()} 覆寫新網址")
    if status == 429:
        return "站方回報請求過於頻繁（429），請稍後再試"
    if status is not None and 500 <= status < 600:
        return f"站方伺服器錯誤（{status}），請稍後再試"
    if status is not None and 400 <= status < 500:
        return (f"站方拒絕這個請求（{status}）——查詢網址或參數可能已變動，"
                f"可用 --endpoints 檢查")
    if isinstance(e, requests.exceptions.Timeout):
        return "連線逾時"
    return "連線失敗"


def _finish(result: TrackResult, carrier_name: str, args) -> bool:
    """輸出結果，並依 spec 處理查詢紀錄的寫入與「可刪」標記。

    回傳查詢紀錄裡現在是否有這筆（本次寫入成功，或原本就在）——名稱只能掛在有紀錄的單號上。
    """
    recorded = False
    if not args.no_record:
        try:
            recorded = history.record(result)
        except OSError as e:
            # 紀錄是輔助功能：寫不進去（目錄唯讀／磁碟滿／檔案被佔用）也必須先把
            # 查到的貨態交給使用者。走 stderr 才不會污染 --json 的 stdout。
            print(f"（查詢紀錄寫入失敗，本次結果未記住：{e}）", file=sys.stderr)
    _emit(result, carrier_name, args.as_json)
    # 需求 3：CLI 不做互動提示（非互動硬規則 + agent 環境會卡死），
    # 只標記並給指令；真正詢問使用者的是 agent。
    if (not args.as_json and recorded
            and history.looks_complete(result.latest.status if result.latest else "")):
        print(f"\n（這筆看起來已完成，可用 --forget {result.number} 刪除紀錄）")
    return recorded or (result.found and history.lookup_entry(result.number) is not None)


def _complete(result: TrackResult, carrier_name: str, args) -> int:
    """單號查詢的收尾：輸出、寫紀錄，有 --label 時在同一個鎖內接著存名稱。

    record 與 set_label 放在同一個臨界區，避免中間被另一個程序的 --forget 插入，
    留下指向已刪除紀錄的名稱。拿不到鎖時仍要先交出查詢結果（紀錄是輔助功能）。
    """
    if args.label is None:
        _finish(result, carrier_name, args)
        return 0
    try:
        with storage.mutation_lock(history.home()):
            return _finish_with_label(result, carrier_name, args)
    except storage.LockBusy as e:
        _finish(result, carrier_name, args)
        return _label_error(e)


def _label_error(e: Exception) -> int:
    # 查詢結果已經印在 stdout（JSON 模式下就是那一份 document），錯誤只能走 stderr
    print(f"名稱未儲存：{e}", file=sys.stderr)
    return EXIT_PERSISTENCE


def _finish_with_label(result: TrackResult, carrier_name: str, args) -> int:
    kept = _finish(result, carrier_name, args)
    out = sys.stderr if args.as_json else sys.stdout
    if not result.found:
        print("查無資料，名稱未儲存", file=out)
        return 0
    if not kept:
        print("查詢紀錄未保存，名稱未儲存", file=sys.stderr)
        return EXIT_PERSISTENCE
    try:
        old = labels.load_for_read().get(result.number)
        labels.set_label(result.number, args.label)
    except OSError as e:
        return _label_error(e)
    if old and old != args.label:
        print(f"已將名稱從「{old}」改為「{args.label}」", file=out)
    else:
        print(f"已將這筆命名為「{args.label}」", file=out)
    return 0


def _emit(result: TrackResult, carrier_name: str, as_json: bool) -> None:
    if as_json:
        # latest 是 property，asdict() 不會帶——但它在 spec 宣告的 schema 裡
        payload = asdict(result)
        payload["latest"] = asdict(result.latest) if result.latest else None
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(_render(result, carrier_name))


# ── --refresh-pending：對未結案清單逐一即時查詢 ─────────────────────────
#
# 沿用單號查詢的既有路徑（同一個 adapter.track()），差別只在「批次」：逐筆 fail-fast、
# 一筆失敗不中止整批（spec 需求 1）。不加重試、不加並行——README 的 Limitations 段
# 講得很白：「個人低頻查詢，無重試迴圈、無並行」，這裡沒有理由破例。

@dataclass
class RefreshOutcome:
    number: str
    carrier_code: str
    carrier_name: str
    category: str  # 新結案 / 有新進度 / 無變化 / 已略過 / 查詢失敗
    status: str = ""
    event_time: str = ""
    detail: str = ""  # 已略過／查詢失敗時的原因；其餘分類不使用
    label: str | None = None
    previous_status: str = ""
    previous_checked: str | None = None  # 查詢失敗時「仍保留的快照」是哪次查的
    query_succeeded: bool = False
    snapshot_saved: bool = False
    save_error: str = ""  # 查到了但快照沒存成功：部分失敗，不是完整成功


_REFRESH_CATEGORIES = ("新結案", "有新進度", "無變化", "已略過", "查詢失敗")
# JSON 用穩定的英文鍵，中文分類名只給人看（spec 6.7）
_CATEGORY_KEYS = {"新結案": "completed", "有新進度": "progressed", "無變化": "unchanged",
                  "已略過": "skipped", "查詢失敗": "failed"}


def _refresh_query_plan(carrier_code: str) -> tuple[str, object]:
    """判斷某筆紀錄的貨運代號要怎麼查。

    回傳 ("direct", adapter) | ("17track", 數字碼或 None) | ("unknown", None)。

    正常流程下 history 裡永遠不會出現 17TRACK 相關的 carrier（--via-17track 的結果
    刻意不記錄，見 history.py 與 CHANGELOG v0.2.1）；這裡處理的是手動編輯過的紀錄檔——
    「毀損」不只是整檔 JSON 壞掉，也包含塞進去一個現在查不到的貨運代號。
    """
    if carrier_code in CARRIERS and carrier_code != "17track":
        return "direct", CARRIERS[carrier_code]
    if carrier_code == "17track":
        return "17track", None
    if carrier_code in CARRIER_CODES:
        return "17track", CARRIER_CODES[carrier_code]
    return "unknown", None


def _try_query(fn) -> tuple[TrackResult | None, str]:
    """統一單筆查詢的例外分類；回傳 (result, error_detail)，成功時 error_detail 為空字串。

    對齊主查詢路徑（run() 自動模式）用的三種例外，差別是這裡的呼叫端是逐筆迴圈，
    永遠不會讓一筆的例外中止整批。
    """
    try:
        return fn(), ""
    except CarrierUnavailable as e:
        return None, str(e)
    except ParseError as e:
        return None, str(e)
    except requests.RequestException as e:
        return None, describe_network_error(e)


def _classify_refresh(entry: dict, result: TrackResult) -> tuple[str, str, str]:
    """比對新查到的最新事件與紀錄快照，回傳 (category, status, event_time)。

    entry 一律來自 history.pending()，保證 looks_complete 不為真——因此「新結案」
    不必比較新舊，新狀態現在算完成就成立；不算完成時才需要比對是否與快照不同。
    """
    latest = result.latest
    status = latest.status if latest else ""
    event_time = latest.time if latest else ""
    if history.looks_complete(status):
        return "新結案", status, event_time
    changed = (status != (entry.get("last_status") or "")
              or event_time != (entry.get("last_event_time") or ""))
    return ("有新進度" if changed else "無變化"), status, event_time


def _refresh_entry(number: str, entry: dict, *, no_record: bool, full: bool = False,
                   label: str | None = None) -> RefreshOutcome:
    """對一筆未結案紀錄做即時查詢。不 raise——任何例外都收斂成一個 RefreshOutcome。"""
    carrier_code = entry.get("carrier") if isinstance(entry.get("carrier"), str) else ""
    carrier_name = _carrier_name(entry)
    base = dict(label=label, previous_status=entry.get("last_status") or "",
                previous_checked=entry.get("last_checked") or None)
    # payload 依 plan 而異："direct" 時是 adapter 物件，"17track" 時是數字碼（或 None，
    # 讓 17TRACK 自己判別）；分岐後各自取用，變數名不共用才不會混淆兩種意義。
    plan, payload = _refresh_query_plan(carrier_code)

    if plan == "unknown":
        return RefreshOutcome(number, carrier_code, carrier_name, "查詢失敗",
                              detail=f"無法辨識的貨運代號：{carrier_code or '（空白）'}"
                                     f"（可能是手動編輯過的紀錄）", **base)

    if plan == "17track":
        # 批次更新永不呼叫 17TRACK（spec 6.5）：額度是使用者自己的錢，而環境裡設了 key
        # 不等於這一次同意。正常流程下 17TRACK 的結果不寫入紀錄，會走到這裡的只有
        # 手動編輯過的紀錄檔。
        via = f" --carrier {carrier_code}" if carrier_code != "17track" else ""
        shown = number if full else "<單號>"
        return RefreshOutcome(
            number, carrier_code, carrier_name, "已略過",
            detail=("批次更新不使用 17TRACK（會消耗你的額度，需要逐次同意）；"
                    f"要查這筆請執行：track.py {shown}{via} --via-17track"), **base)
    adapter = payload
    result, err = _try_query(lambda: adapter.track(number))

    if result is None:
        return RefreshOutcome(number, carrier_code, carrier_name, "查詢失敗", detail=err, **base)
    if not result.found:
        return RefreshOutcome(number, carrier_code, carrier_name, "查詢失敗",
                              detail="查無資料（單號未登錄、輸入錯誤，或已超過該站保留期限）",
                              **base)

    category, status, event_time = _classify_refresh(entry, result)
    saved, save_error = False, ""
    if not no_record:
        # 與單號查詢路徑同一個保證：紀錄寫不進去也不能讓這筆查到的結果消失，
        # 只是這筆要算部分失敗，不能包裝成完整成功。
        try:
            saved = history.record(result)
        except OSError as e:
            save_error = str(e)
    return RefreshOutcome(number, carrier_code, carrier_name, category, status, event_time,
                          query_succeeded=True, snapshot_saved=saved, save_error=save_error,
                          **base)


def _safe_local_minutes(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return _local_minutes(iso)
    except (TypeError, ValueError):
        return iso


def _render_refresh_digest(outcomes: list[RefreshOutcome], *, attempted_at: str,
                           full: bool) -> str:
    counts = {c: 0 for c in _REFRESH_CATEGORIES}
    for o in outcomes:
        counts[o.category] += 1
    checked = _local_minutes(attempted_at)
    lines = [f"未結案包裹更新完成（{len(outcomes)} 筆，剛剛即時查詢）", "",
             "　".join(f"{c} {counts[c]}" for c in _REFRESH_CATEGORIES if counts[c])]
    for cat in _REFRESH_CATEGORIES:
        rows = [o for o in outcomes if o.category == cat]
        if not rows:
            continue
        lines += ["", f"── {cat} ──"]
        for i, o in enumerate(rows):
            if i:
                lines.append("")
            if cat in ("已略過", "查詢失敗"):
                what = o.detail
            elif cat == "有新進度" and o.previous_status and o.previous_status != o.status:
                what = f"{o.previous_status} → {o.status}"
            else:
                what = o.status
            lines.append("　".join(x for x in (o.label, o.carrier_name, what) if x))
            lines.append(_display_number(o.number, full))
            if cat == "查詢失敗":
                kept = _safe_local_minutes(o.previous_checked)
                lines.append(f"仍保留上次成功快照：{kept} 查詢" if kept
                             else "仍保留上次成功快照（查詢時間未知）")
            elif cat != "已略過":
                if o.event_time:
                    lines.append(f"物流事件：{o.event_time}")
                lines.append(f"查詢時間：{checked}")
                if o.save_error:
                    lines.append(f"（查到了，但本機快照未更新：{o.save_error}）")
    return "\n".join(lines)


def _select_refresh_rows(data: dict, names: dict[str, str], args):
    """決定這次要更新哪些包裹，回傳 (rows, 提前結束的 exit code 或 None)。

    順序固定（spec 6.2）：未結案 → --match／--carrier → 多候選 gate → 排序 → --limit。
    先截斷再比對的話，不同次執行會得到不同的候選；--limit 也不代表同意更新多個候選。
    """
    rows = history.pending(data)  # 已依最新物流事件新到舊排序
    if args.match is not None:
        keep = set(labels.find(args.match, [n for n, _ in rows], names))
        rows = [(n, e) for n, e in rows if n in keep]
    if args.carrier:
        rows = [(n, e) for n, e in rows if e.get("carrier") == args.carrier]
    if not rows:
        if args.carrier:
            message = f"沒有符合條件的未結案包裹（--carrier {args.carrier}" + (
                f"、名稱「{args.match}」）" if args.match is not None else "）")
        else:
            message = f"沒有名稱符合「{args.match}」的未結案包裹"
        if args.as_json:
            _emit_envelope("refresh_pending", live_query=False, selection_required=False,
                           matches=[])
            print(message, file=sys.stderr)
        else:
            print(message)
        return [], 0
    if args.match is not None and len(rows) > 1 and not args.all_matches:
        views = _views(rows, names)
        head = f"找到 {len(rows)} 個名稱相近的未結案包裹（{SNAPSHOT_NOTE}），尚未送出任何查詢。"
        hint = "請改用更完整的名稱或單號；若要全部更新，加 --all-matches。"
        if args.as_json:
            _emit_envelope("refresh_pending", live_query=False, selection_required=True,
                           matches=views)
            print(f"{head}\n{hint}", file=sys.stderr)
        else:
            print(head)
            _print_candidates(rows, views, full=args.full_numbers)
            print(f"\n{hint}")
        return [], EXIT_SELECTION_REQUIRED
    if args.limit is not None:
        rows = rows[: args.limit]
    return rows, None


def _run_refresh_pending(args) -> int:
    data = history.entries()
    empty_note = None
    if not data:
        empty_note = "查詢紀錄是空的"
    elif not history.pending(data):
        # 跟 --pending 同一個區分：「沒紀錄」與「全都到了」不是同一句話。
        empty_note = f"沒有未結案的包裹（{len(data)} 筆全部已完成，可用 --forget-all 清掉）"
    if empty_note:
        if args.as_json:
            _emit_envelope("refresh_pending", live_query=False, partial_failure=False,
                           counts={k: 0 for k in _CATEGORY_KEYS.values()}, outcomes=[])
            print(empty_note, file=sys.stderr)
        else:
            print(empty_note)
        return 0
    names = labels.load_for_read()
    rows, early = _select_refresh_rows(data, names, args)
    if early is not None:
        return early
    if args.dry_run:
        views = _views(rows, names)
        if args.as_json:
            _emit_envelope("refresh_pending", live_query=False, dry_run=True, items=views)
            return 0
        print(f"將查詢 {len(rows)} 筆（未連線、未寫入）")
        for (_, entry), v in zip(rows, views):
            print()
            print("\n".join(_render_snapshot_item(v, full=args.full_numbers,
                                                  stall_days=_stall_days(entry))))
        return 0
    # 序列、非並行——揭露在查詢之前，讓使用者知道這可能要花一點時間（無重試、無並行
    # 是專案既定立場，見 README Limitations）。
    attempted_at = snapshot.now().isoformat(timespec="seconds")
    print(f"（即將對 {len(rows)} 筆未結案包裹逐一即時查詢，依序不並行——需要一點時間）\n",
          file=sys.stderr if args.as_json else sys.stdout)
    outcomes = [_refresh_entry(n, e, no_record=args.no_record, full=args.full_numbers,
                               label=names.get(n)) for n, e in rows]
    partial = any(o.category == "查詢失敗" or o.save_error for o in outcomes)
    if args.as_json:
        counts = {k: 0 for k in _CATEGORY_KEYS.values()}
        for o in outcomes:
            counts[_CATEGORY_KEYS[o.category]] += 1
        _emit_envelope("refresh_pending", live_query=True, attempted_at=attempted_at,
                       counts=counts, partial_failure=partial, outcomes=[{
                           "number": o.number, "label": o.label, "carrier": o.carrier_code,
                           "category": _CATEGORY_KEYS[o.category], "status": o.status,
                           "previous_status": o.previous_status, "event_time": o.event_time,
                           "query_succeeded": o.query_succeeded,
                           "snapshot_saved": o.snapshot_saved,
                           "detail": o.detail or o.save_error} for o in outcomes])
    else:
        print(_render_refresh_digest(outcomes, attempted_at=attempted_at,
                                     full=args.full_numbers))
    return EXIT_PARTIAL_FAILURE if partial else 0


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("必須是整數") from None
    if value < 1:
        raise argparse.ArgumentTypeError("必須是 1 以上的整數")
    return value


def run(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="parcel-kau-a", description="台灣包裹追蹤")
    p.add_argument("number", nargs="?", help="包裹單號")
    p.add_argument("--carrier", help="指定貨運公司（省略則自動判別）。直連："
                   + "/".join(c for c in sorted(CARRIERS) if c != "17track")
                   + "；搭配 --via-17track 時可用 " + "/".join(sorted(CARRIER_CODES)))
    p.add_argument("--via-17track", action="store_true", dest="via_17track",
                   help="改走 17TRACK 聚合服務（需自備 API key；會消耗你的額度）")
    p.add_argument("--auto", action="store_true",
                   help="同意把單號依序送給所有格式相符的物流商（命中即停）")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="輸出 JSON")
    p.add_argument("--no-record", action="store_true", dest="no_record",
                   help="本次查詢不寫入查詢紀錄")
    # 管理型旗標兩兩互斥；argparse 衝突時以 exit 2 結束（spec §4.2）
    group = p.add_mutually_exclusive_group()
    group.add_argument("--forget", metavar="單號",
                   help="刪除該單號的查詢紀錄（不查詢）")
    group.add_argument("--forget-all", action="store_true", dest="forget_all",
                   help="清空所有查詢紀錄")
    group.add_argument("--history", action="store_true", dest="show_history",
                   help="列出查詢紀錄")
    group.add_argument("--pending", action="store_true", dest="show_pending",
                   help="只列出尚未結案的包裹（純讀本機紀錄，不發任何查詢請求）")
    group.add_argument("--refresh-pending", action="store_true", dest="refresh_pending",
                   help="對每筆未結案紀錄逐一即時查詢，回報彙整摘要並更新本機紀錄快照")
    group.add_argument("--endpoints", action="store_true", dest="show_endpoints",
                   help="列出目前生效的各家查詢網址（可在設定檔覆寫）")
    group.add_argument("--find", metavar="名稱或單號",
                       help="用自訂名稱或單號找包裹（純讀本機紀錄，不發任何查詢請求）")
    group.add_argument("--rename", nargs=2, metavar=("單號", "新名稱"),
                       help="修改已查詢過的包裹名稱")
    group.add_argument("--clear-label", metavar="單號", dest="clear_label",
                       help="清除包裹名稱")
    p.add_argument("--label", metavar="名稱",
                   help="查到結果後為這個單號取名稱（只存在本機）")
    p.add_argument("--match", metavar="名稱",
                   help="搭配 --refresh-pending：只更新名稱符合的未結案包裹")
    p.add_argument("--all-matches", action="store_true", dest="all_matches",
                   help="搭配 --match：命中多筆時同意全部更新")
    p.add_argument("--limit", type=_positive_int, metavar="N",
                   help="搭配 --refresh-pending：只更新前 N 筆（依最新物流事件新到舊）")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="搭配 --refresh-pending：只列出將查詢的項目，不連線、不寫入")
    p.add_argument("--full-numbers", action="store_true", dest="full_numbers",
                   help="列表顯示完整單號（預設只顯示末四碼）")
    args = p.parse_args(argv)

    refresh_only = [flag for flag, on in (("--match", args.match is not None),
                                          ("--all-matches", args.all_matches),
                                          ("--limit", args.limit is not None),
                                          ("--dry-run", args.dry_run)) if on]
    if refresh_only and not args.refresh_pending:
        return _fail(args, 2, f"{'、'.join(refresh_only)} 只能搭配 --refresh-pending 使用")
    if args.all_matches and args.match is None:
        return _fail(args, 2, "--all-matches 需要搭配 --match")
    direct_codes = sorted(c for c in CARRIERS if c != "17track")
    if args.refresh_pending and args.carrier and args.carrier not in direct_codes:
        return _fail(args, 2, f"--refresh-pending 的 --carrier 只接受直連物流商："
                              f"{'/'.join(direct_codes)}")
    if args.label is not None and not args.number:
        return _fail(args, 2, "--label 只能搭配單號查詢使用", operation="label")

    # 管理型旗標：只動本機紀錄，不發任何網路請求
    if args.rename:
        return _run_rename(args)
    if args.clear_label:
        return _run_clear_label(args)
    if args.find is not None:
        return _run_find(args)
    if args.forget:
        return _run_forget(args)
    if args.forget_all:
        return _run_forget_all(args)
    if args.show_endpoints:
        print(f"目前生效的查詢網址（覆寫檔：{endpoints.path()}）\n")
        for code, urls in endpoints.all_endpoints().items():
            name = CARRIERS[code].name if code in CARRIERS else code
            print(f"{name}（{code}）")
            for key, url in urls.items():
                print(f"　{key}: {url}")
        print("\n只需在覆寫檔列出要改的鍵，其餘沿用預設。")
        return 0
    if args.show_history or args.show_pending:
        return _run_snapshot_listing(args)
    if args.refresh_pending:
        return _run_refresh_pending(args)

    if not args.number:
        p.error("需要包裹單號（或使用 --history / --forget / --forget-all）")

    if args.label is not None:
        # 這些檢查都在送出任何查詢之前：名稱不合法或存不進去，就不該先把單號送出去
        if args.no_record or args.via_17track:
            return _fail(args, 2, "--label 需要寫入查詢紀錄，不能和 --no-record 或 --via-17track"
                                  "（17TRACK 的結果不寫入紀錄）同時使用", operation="label")
        try:
            args.label = labels.validate(args.label)
            labels.check_writable()
        except labels.InvalidLabel as e:
            return _fail(args, 2, f"名稱不合法：{e}", operation="label")
        except storage.Corrupt as e:
            return _fail(args, EXIT_PERSISTENCE,
                         f"名稱檔 {e}，本次不查詢。修正或改名該檔後重試；--forget-all 會刪除它",
                         operation="label")

    if args.auto and (args.carrier or args.via_17track):
        return _fail(args, 2, "--auto 不能和 --carrier 或 --via-17track 同時使用"
                              "（--auto 是同意依序詢問所有格式相符的直連物流商）")

    if args.via_17track:
        adapter = CARRIERS["17track"]
        carrier_code = CARRIER_CODES.get(args.carrier) if args.carrier else None
        if args.carrier and carrier_code is None:
            print(f"17TRACK 不認得的貨運代號：{args.carrier}\n"
                  f"可用：{'/'.join(sorted(CARRIER_CODES))}")
            return 2
        try:
            result = adapter.track(args.number, carrier_code=carrier_code)
        except CarrierUnavailable as e:
            print(str(e))
            return 3
        except ParseError as e:
            print(f"{adapter.name}：{e}")
            return 4
        except requests.RequestException as e:
            print(f"17TRACK：{describe_network_error(e)}")
            return 5
        _emit(result, adapter.name, args.as_json)
        return 0

    direct = [c for c in CARRIERS if c != "17track"]
    tried_from_record: str | None = None
    remembered = None if args.carrier else history.lookup(args.number)
    # 舊紀錄可能與現行格式判別不符（單號規則變更／紀錄手動編輯過），
    # 先過 detect() 再發請求，與其他路徑一致。
    if remembered and remembered in direct and CARRIERS[remembered].detect(args.number):
        # 有紀錄＝知道是哪家＝只送一家，這正是紀錄功能的隱私價值
        if not args.as_json:
            print(f"（依查詢紀錄：這個單號屬於 {CARRIERS[remembered].name}，只查這一家）\n")
        name = CARRIERS[remembered].name
        # 查詢本身失敗（逾時、缺 Playwright、站方改版）不代表紀錄過時：直接回報，
        # 不改問別家——否則一次逾時就會把單號廣播給其餘各家（architect 2026-10-17）。
        try:
            result = CARRIERS[remembered].track(args.number)
        except CarrierUnavailable as e:
            print(f"{name}：{e}")
            return 3
        except (ParseError, KeyError) as e:
            print(f"{name}：{e}")
            return 4
        except requests.RequestException as e:
            print(f"{name}：{describe_network_error(e)}")
            return 5
        if result.found:
            return _complete(result, name, args)
        # 站方明確回「查無」→ 紀錄可能過時或單號被重用。改問其他家要再經過同意。
        tried_from_record = remembered
        remembered = None
        rest = _candidate_codes(args.number, exclude=tried_from_record)
        if rest and not args.auto:
            return _selection_required(args.number, rest, args,
                                       reason="紀錄中那家查無資料（紀錄可能過時）")
        # 前面已對使用者說「只查這一家」，這裡多問別家就必須講明，否則等於說一套做一套。
        if rest and not args.as_json:
            names = "、".join(CARRIERS[c].name for c in rest)
            print(f"（紀錄中那家查無資料——紀錄可能過時，依 --auto 改試其餘 {len(rest)} 家：{names}）\n")

    if args.carrier:
        if args.carrier not in direct:
            print(f"未知的貨運代號：{args.carrier}\n可用：{'/'.join(sorted(direct))}"
                  f"（中華郵政/全家/7-11/新竹請加 --via-17track）")
            return 2
        codes = [args.carrier]
    else:
        codes = _candidate_codes(args.number, exclude=tried_from_record)
        if len(codes) > 1 and not args.auto and tried_from_record is None:
            return _selection_required(args.number, codes, args,
                                       reason="單號格式符合多家物流商")
    if not codes:
        print(f"無法判別貨運公司：{args.number}\n"
              f"直連支援：{'/'.join(sorted(direct))}\n"
              f"若為中華郵政/全家/7-11/新竹，請加 --via-17track（需自備 API key）")
        return 2

    # 揭露在查詢之前：這些單號格式共用，不指定 carrier 時單號會依序送給下列各家
    # （命中即停，所以實際家數可能較少）。使用者要有機會在請求發出前改用 --carrier。
    if (args.auto and not args.as_json and len(codes) > 1
            and tried_from_record is None):
        names = "、".join(CARRIERS[c].name for c in codes)
        print(f"（未指定貨運公司：單號格式符合 {len(codes)} 家，將依序查詢 {names}，"
              f"命中即停——單號因此可能送到不只一家。\n"
              f"　指定 --carrier 可只送一家：{'/'.join(codes)}）\n")

    last: tuple[TrackResult, str] | None = None
    errors: list[str] = []
    asked: list[str] = []
    # 只有一家可問（指定了 --carrier，或格式只符合一家）時，這家的錯誤就是整次查詢的錯誤
    single = bool(args.carrier) or len(codes) == 1
    for code in codes:
        adapter = CARRIERS[code]
        asked.append(adapter.name)
        try:
            result = adapter.track(args.number)
        except CarrierUnavailable as e:
            # 指定單一貨運時這是致命錯（使用者就是要查那家）；自動／退回模式下
            # 只是「這家用不了」，該繼續問其他家——否則會違背剛印出的「改試其餘 N 家」。
            if single:
                print(f"{adapter.name}：{e}")
                return 3
            errors.append(f"{adapter.name}：{e}")
            continue
        except ParseError as e:
            # 撞號情境下，某家改版不該埋掉其他家的有效結果；單家指定時才視為錯誤
            if single:
                print(f"{adapter.name}：{e}")
                return 4
            errors.append(f"{adapter.name}：{e}")
            continue
        except requests.RequestException as e:
            # 站方逾時/斷線是 scraping 的日常：自動模式下換下一家，別中斷整趟查詢
            errors.append(f"{adapter.name}：{describe_network_error(e)}")
            continue
        last = (result, adapter.name)
        if result.found:
            break

    if last is None:
        print("查詢未完成\n" + "\n".join(errors))
        return 5

    for msg in errors:  # 有結果但部分站台失敗時，仍讓使用者知道漏查了誰
        print(f"（{msg}，已略過）", file=sys.stderr if args.as_json else sys.stdout)
    result, name = last
    return _complete(result, name, args)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
