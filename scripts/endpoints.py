"""各家查詢網址集中在這裡，並可用設定檔覆寫。

站方改版換網址時，使用者不必改程式：把新網址寫進
`~/.cache/parcel-kau-a/endpoints.json` 即可（只需列出要改的那幾個鍵，
其餘沿用預設）。`track.py --endpoints` 可看目前生效的值。

設定檔壞掉時一律退回預設並印 WARN——設定錯誤不該讓查詢整個失效。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOME_ENV = "PARCEL_KAU_A_HOME"
FILE_NAME = "endpoints.json"
_DEFAULT_HOME = Path.home() / ".cache" / "parcel-kau-a"

# `{number}` 為單號佔位符；沒有佔位符者為 POST 目標或表單頁。
DEFAULTS: dict[str, dict[str, str]] = {
    "tcat": {
        "trace": "https://www.t-cat.com.tw/Inquire/Trace.aspx",
        "detail": "https://www.t-cat.com.tw/Inquire/TraceDetail.aspx?BillID={number}",
    },
    "kerrytj": {
        "api": "https://www.kerrytj.com/api/Tracking/GetTracking",
        "source": "https://www.kerrytj.com/zh/checking",
    },
    "ecan": {
        # 中文檔名需 percent-encode，故此處直接存已編碼的完整網址
        "post": "https://query2.e-can.com.tw/%E5%A4%9A%E7%AD%86%E6%9F%A5%E4%BB%B6_oo4o.asp",
        "source": "https://query2.e-can.com.tw/%E5%A4%9A%E7%AD%86%E6%9F%A5%E4%BB%B6A.htm",
    },
    "pchome": {"query": "https://www.gopchome.com.tw/delivery/historyList/{number}"},
    "fusheng": {"query": "https://tmsvendor.fs.com.tw/search-result?ship_num1={number}"},
    "spx": {"source": "https://spx.tw/"},
    "17track": {
        "api_base": "https://api.17track.net/track/v2.4",
        "source": "https://t.17track.net/",
        "signup": "https://api.17track.net",   # 訊息中引導使用者申請 key 用
    },
}


def home() -> Path:
    return Path(os.environ.get(HOME_ENV) or _DEFAULT_HOME)


def path() -> Path:
    return home() / FILE_NAME


def _overrides() -> dict[str, dict[str, str]]:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(f"（endpoints 設定無法讀取，本次使用預設網址：{e}）", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def _accept(code: str, key: str, value, default: str | None) -> bool:
    """覆寫值必須可用才採納，否則退回預設並說明原因。

    靜默丟棄比報錯更糟：少了 {number} 的網址會讓每個單號都查到同一頁（假資料），
    佔位符拼錯則會在 .format() 拋 KeyError 裸拋給使用者。
    """
    if not isinstance(value, str):
        print(f"（endpoints 覆寫 {code}.{key} 不是字串，改用預設）", file=sys.stderr)
        return False
    if default and "{number}" in default and "{number}" not in value:
        print(f"（endpoints 覆寫 {code}.{key} 少了 {{number}} 佔位符，改用預設）",
              file=sys.stderr)
        return False
    return True


def all_endpoints() -> dict[str, dict[str, str]]:
    """預設值 + 使用者覆寫（逐鍵合併，未列出的鍵保持預設）。"""
    merged = {code: dict(urls) for code, urls in DEFAULTS.items()}
    for code, urls in _overrides().items():
        if not isinstance(urls, dict):
            print(f"（endpoints 覆寫 {code} 格式不正確，整組改用預設）", file=sys.stderr)
            continue
        target = merged.setdefault(code, {})
        for key, value in urls.items():
            if _accept(code, key, value, DEFAULTS.get(code, {}).get(key)):
                target[key] = value
    return merged


def get(code: str) -> dict[str, str]:
    return all_endpoints().get(code, {})
