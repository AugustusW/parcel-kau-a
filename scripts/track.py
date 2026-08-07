#!/usr/bin/env python3
"""parcel-kau-a — 台灣包裹追蹤 CLI。

用法：
    track.py <單號> [--carrier tcat|kerrytj|ecan|spx] [--json]

不指定 --carrier 時依 detect() 逐家序列查詢、命中即停。黑貓/嘉里/宅配通單號
同為 12 碼數字無法由格式區分，知道貨運公司時請指定 --carrier 以省下無謂請求。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

import requests

import endpoints
import history
from carriers import CARRIERS
from carriers.base import CarrierUnavailable, ParseError, TrackResult
from carriers.seventeentrack import CARRIER_CODES


def _render(result: TrackResult, carrier_name: str) -> str:
    head = f"{carrier_name}　{result.number}"
    if not result.found:
        return f"{head}\n查無資料（單號未登錄、輸入錯誤，或已超過該站保留期限）"
    lines = [head, ""]
    # 與 TrackResult.latest 用同一把排序鑰匙，否則「最新」與列表首行可能不一致
    for e in sorted(result.events, key=lambda x: x.sort_key, reverse=True):
        where = f"　{e.location}" if e.location else ""
        lines.append(f"{e.time}　{e.status}{where}")
    lines += ["", f"來源：{result.source_url}"]
    return "\n".join(lines)


def _carrier_name(entry: dict) -> str:
    """紀錄裡的 carrier code 翻成中文名；認不得就原樣顯示（手動編輯過的檔案也不該爆）。"""
    code = entry.get("carrier")
    return CARRIERS[code].name if code in CARRIERS else (code or "?")


def _age_note(entry: dict) -> str:
    """「多久沒更新」——算不出來就不顯示，不編一個天數出來誤導判斷。"""
    days = history.days_since_last_event(entry)
    if days is None:
        return ""
    return "　（今天更新）" if days == 0 else f"　（{days} 天沒更新）"


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


def _finish(result: TrackResult, carrier_name: str, args) -> None:
    """輸出結果，並依 spec 處理查詢紀錄的寫入與「可刪」標記。"""
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


def _emit(result: TrackResult, carrier_name: str, as_json: bool) -> None:
    if as_json:
        # latest 是 property，asdict() 不會帶——但它在 spec 宣告的 schema 裡
        payload = asdict(result)
        payload["latest"] = asdict(result.latest) if result.latest else None
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(_render(result, carrier_name))


def run(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="parcel-kau-a", description="台灣包裹追蹤")
    p.add_argument("number", nargs="?", help="包裹單號")
    p.add_argument("--carrier", help="指定貨運公司（省略則自動判別）。直連："
                   + "/".join(c for c in sorted(CARRIERS) if c != "17track")
                   + "；搭配 --via-17track 時可用 " + "/".join(sorted(CARRIER_CODES)))
    p.add_argument("--via-17track", action="store_true", dest="via_17track",
                   help="改走 17TRACK 聚合服務（需自備 API key；會消耗你的額度）")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="輸出 JSON")
    p.add_argument("--no-record", action="store_true", dest="no_record",
                   help="本次查詢不寫入查詢紀錄")
    p.add_argument("--forget", metavar="單號",
                   help="刪除該單號的查詢紀錄（不查詢）")
    p.add_argument("--forget-all", action="store_true", dest="forget_all",
                   help="清空所有查詢紀錄")
    p.add_argument("--history", action="store_true", dest="show_history",
                   help="列出查詢紀錄")
    p.add_argument("--pending", action="store_true", dest="show_pending",
                   help="只列出尚未結案的包裹（純讀本機紀錄，不發任何查詢請求）")
    p.add_argument("--endpoints", action="store_true", dest="show_endpoints",
                   help="列出目前生效的各家查詢網址（可在設定檔覆寫）")
    args = p.parse_args(argv)

    # 管理型旗標：只動本機紀錄，不發任何網路請求
    if args.forget:
        removed = history.forget(args.forget)
        print(f"已刪除 {args.forget} 的查詢紀錄" if removed
              else f"查詢紀錄中沒有 {args.forget}")
        return 0
    if args.forget_all:
        history.forget_all()
        print("已清空所有查詢紀錄")
        return 0
    if args.show_endpoints:
        print(f"目前生效的查詢網址（覆寫檔：{endpoints.path()}）\n")
        for code, urls in endpoints.all_endpoints().items():
            name = CARRIERS[code].name if code in CARRIERS else code
            print(f"{name}（{code}）")
            for key, url in urls.items():
                print(f"　{key}: {url}")
        print("\n只需在覆寫檔列出要改的鍵，其餘沿用預設。")
        return 0
    if args.show_history:
        data = history.entries()
        if not data:
            print("查詢紀錄是空的")
            return 0
        print(f"查詢紀錄（{history.path()}）\n")
        for num, e in sorted(data.items(), key=lambda kv: kv[1].get("last_checked", ""),
                             reverse=True):
            mark = "　✓可刪（看似已完成）" if e.get("looks_complete") else ""
            print(f"{num}　{_carrier_name(e)}　{e.get('last_status', '')}"
                  f"　{e.get('last_event_time', '')}{mark}")
        return 0
    if args.show_pending:
        # 純讀本機紀錄：一個網路請求都不發。要最新貨態就查單號，這裡是「還有哪些在路上」。
        data = history.entries()
        if not data:
            print("查詢紀錄是空的")
            return 0
        rows = history.pending(data)
        if not rows:
            # 「沒紀錄」與「全都到了」是兩件事，講同一句話會讓使用者以為功能壞了
            print(f"沒有未結案的包裹（{len(data)} 筆全部已完成，可用 --forget-all 清掉）")
            return 0
        print(f"未結案包裹（{len(rows)} 筆）\n")
        for num, e in rows:
            print(f"{num}　{_carrier_name(e)}　{e.get('last_status', '')}"
                  f"　{e.get('last_event_time', '')}{_age_note(e)}")
        return 0

    if not args.number:
        p.error("需要包裹單號（或使用 --history / --forget / --forget-all）")

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
        try:
            result = CARRIERS[remembered].track(args.number)
        except (CarrierUnavailable, ParseError, requests.RequestException, KeyError) as e:
            # 靜默吞掉會讓「站方改版」「缺 Playwright」這類訊號消失，使用者只看到
            # 最後的「查無資料」，比 v0.1.1 的自動判別更難診斷。講出來再退回。
            result = None
            if not args.as_json:
                detail = (describe_network_error(e)
                          if isinstance(e, requests.RequestException) else str(e))
                print(f"（{CARRIERS[remembered].name}：{detail}）")
        if result is not None and result.found:
            _finish(result, CARRIERS[remembered].name, args)
            return 0
        # 紀錄過時或單號被重用 → 退回輪巡其餘各家（已問過的那家不再重問）。
        # 前面已對使用者說「只查這一家」，這裡多問別家就必須講明，否則等於說一套做一套。
        tried_from_record = remembered
        remembered = None
        rest = [c for c in direct
                if c != tried_from_record and CARRIERS[c].detect(args.number)]
        if rest and not args.as_json:
            names = "、".join(CARRIERS[c].name for c in rest)
            print(f"（紀錄中那家查無資料——紀錄可能過時，改試其餘 {len(rest)} 家：{names}）\n")

    if args.carrier:
        if args.carrier not in direct:
            print(f"未知的貨運代號：{args.carrier}\n可用：{'/'.join(sorted(direct))}"
                  f"（中華郵政/全家/7-11/新竹請加 --via-17track）")
            return 2
        codes = [args.carrier]
    else:
        codes = [c for c in direct
                 if CARRIERS[c].detect(args.number) and c != tried_from_record]
    if not codes:
        print(f"無法判別貨運公司：{args.number}\n"
              f"直連支援：{'/'.join(sorted(direct))}\n"
              f"若為中華郵政/全家/7-11/新竹，請加 --via-17track（需自備 API key）")
        return 2

    # 揭露在查詢之前：這些單號格式共用，不指定 carrier 時單號會依序送給下列各家
    # （命中即停，所以實際家數可能較少）。使用者要有機會在請求發出前改用 --carrier。
    if (not args.carrier and not args.as_json and len(codes) > 1
            and tried_from_record is None):
        names = "、".join(CARRIERS[c].name for c in codes)
        print(f"（未指定貨運公司：單號格式符合 {len(codes)} 家，將依序查詢 {names}，"
              f"命中即停——單號因此可能送到不只一家。\n"
              f"　指定 --carrier 可只送一家：{'/'.join(codes)}）\n")

    last: tuple[TrackResult, str] | None = None
    errors: list[str] = []
    asked: list[str] = []
    for code in codes:
        adapter = CARRIERS[code]
        asked.append(adapter.name)
        try:
            result = adapter.track(args.number)
        except CarrierUnavailable as e:
            # 指定單一貨運時這是致命錯（使用者就是要查那家）；自動／退回模式下
            # 只是「這家用不了」，該繼續問其他家——否則會違背剛印出的「改試其餘 N 家」。
            if args.carrier:
                print(str(e))
                return 3
            errors.append(f"{adapter.name}：{e}")
            continue
        except ParseError as e:
            # 撞號情境下，某家改版不該埋掉其他家的有效結果；單家指定時才視為錯誤
            if args.carrier:
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
        print(f"（{msg}，已略過）")
    result, name = last
    _finish(result, name, args)
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
