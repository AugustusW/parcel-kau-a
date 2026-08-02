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

from carriers import CARRIERS
from carriers.base import CarrierUnavailable, ParseError, TrackResult
from carriers.seventeentrack import CARRIER_CODES


def _render(result: TrackResult, carrier_name: str) -> str:
    head = f"{carrier_name}　{result.number}"
    if not result.found:
        return f"{head}\n查無資料（單號未登錄、輸入錯誤，或已超過該站保留期限）"
    lines = [head, ""]
    for e in sorted(result.events, key=lambda x: x.time, reverse=True):
        where = f"　{e.location}" if e.location else ""
        lines.append(f"{e.time}　{e.status}{where}")
    lines += ["", f"來源：{result.source_url}"]
    return "\n".join(lines)


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
    p.add_argument("number", help="包裹單號")
    p.add_argument("--carrier", help="指定貨運公司（省略則自動判別）。直連："
                   + "/".join(c for c in sorted(CARRIERS) if c != "17track")
                   + "；搭配 --via-17track 時可用 " + "/".join(sorted(CARRIER_CODES)))
    p.add_argument("--via-17track", action="store_true", dest="via_17track",
                   help="改走 17TRACK 聚合服務（需自備 API key；會消耗你的額度）")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="輸出 JSON")
    args = p.parse_args(argv)

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
        except requests.RequestException:
            print("17TRACK：連線失敗")
            return 5
        _emit(result, adapter.name, args.as_json)
        return 0

    direct = [c for c in CARRIERS if c != "17track"]
    if args.carrier:
        if args.carrier not in direct:
            print(f"未知的貨運代號：{args.carrier}\n可用：{'/'.join(sorted(direct))}"
                  f"（中華郵政/全家/7-11/新竹請加 --via-17track）")
            return 2
        codes = [args.carrier]
    else:
        codes = [c for c in direct if CARRIERS[c].detect(args.number)]
    if not codes:
        print(f"無法判別貨運公司：{args.number}\n"
              f"直連支援：{'/'.join(sorted(direct))}\n"
              f"若為中華郵政/全家/7-11/新竹，請加 --via-17track（需自備 API key）")
        return 2

    last: tuple[TrackResult, str] | None = None
    errors: list[str] = []
    for code in codes:
        adapter = CARRIERS[code]
        try:
            result = adapter.track(args.number)
        except CarrierUnavailable as e:
            print(str(e))
            return 3
        except ParseError as e:
            # 撞號情境下，某家改版不該埋掉其他家的有效結果；單家指定時才視為錯誤
            if args.carrier:
                print(f"{adapter.name}：{e}")
                return 4
            errors.append(f"{adapter.name}：{e}")
            continue
        except requests.RequestException as e:
            # 站方逾時/斷線是 scraping 的日常：自動模式下換下一家，別中斷整趟查詢
            kind = "連線逾時" if isinstance(
                e, requests.exceptions.Timeout) else "連線失敗"
            errors.append(f"{adapter.name}：{kind}")
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
    _emit(result, name, args.as_json)
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
