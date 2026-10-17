"""使用者自訂的包裹名稱（labels.json）。

刻意不放進 history.json：history.record() 每次查到結果都會重建整筆 entry，舊版程式
不認得 label 欄位，降版後再查一次就會把名稱洗掉（spec §4.5）。

名稱可能比單號更有語意（「媽媽的藥」），屬個資擴張，所以：
- 只由使用者明確提供，不從物流頁或商品頁推測
- 限長並以白名單驗證字元，避免 terminal injection、bidi 欺騙與藏在 Agent context
  裡看不見的文字
- 檔案權限與 history 相同（0600、原子寫入、mutation lock）；毀損時讀取降級為沒有名稱，
  寫入一律 fail closed——名稱的每次寫入都是使用者明確的操作，靜默換新檔會讓所有
  名稱看似消失
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable

import history
import storage

MAX_LEN = 100
_FILE_NAME = "labels.json"
# 允許：文字（L）、組合記號（M，含 emoji 的 variation selector）、數字（N）、標點（P）、
# 符號（S，含 emoji）、一般空白（Zs），加上 emoji 序列需要的 ZWJ／ZWNJ。
# 其餘一律拒絕：Cc 控制字元（換行、NUL、ESC）、Cf 格式字元（bidi 控制、tag 字元）、
# Cs 孤立 surrogate（POSIX argv 含非 UTF-8 位元組時會出現，寫 JSON 時會炸）、
# Zl／Zp 行段分隔符、Co／Cn。
_ALLOWED_MAJOR = ("L", "M", "N", "P", "S")
_ALLOWED_EXTRA = {"‌", "‍"}
_VISIBLE_MAJOR = ("L", "N", "P", "S")
_SPACES = re.compile(r"\s+")


class InvalidLabel(ValueError):
    pass


def path() -> Path:
    return history.home() / _FILE_NAME


def validate(text: str) -> str:
    """回傳正規化（NFC、去頭尾空白）後可儲存的名稱；不合法時 raise InvalidLabel。"""
    name = unicodedata.normalize("NFC", (text or "").strip())
    if not name:
        raise InvalidLabel("名稱不能是空白")
    if len(name) > MAX_LEN:
        raise InvalidLabel(f"名稱最多 {MAX_LEN} 個字（目前 {len(name)}）")
    for ch in name:
        cat = unicodedata.category(ch)
        if not (cat[0] in _ALLOWED_MAJOR or cat == "Zs" or ch in _ALLOWED_EXTRA):
            raise InvalidLabel(f"名稱含有不允許的字元（U+{ord(ch):04X}）")
    if not any(unicodedata.category(ch)[0] in _VISIBLE_MAJOR for ch in name):
        raise InvalidLabel("名稱至少要有一個可見字元")
    return name


def normalize(text: str) -> str:
    """比對用：NFC、去頭尾空白、連續空白合一、只轉 ASCII 大小寫——不動會改變中文語意的字元。"""
    collapsed = _SPACES.sub(" ", unicodedata.normalize("NFC", text).strip())
    return "".join(c.lower() if c.isascii() else c for c in collapsed)


def _read_strict() -> dict[str, str]:
    data = storage.read_json_object(path()) or {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


def check_writable() -> None:
    """寫入前的預檢：檔案毀損就 raise storage.Corrupt，讓呼叫端在送出任何查詢前就停下。"""
    _read_strict()


def load_for_read() -> dict[str, str]:
    """不存在回空；毀損時警告並回空，不改動檔案。"""
    try:
        return _read_strict()
    except storage.Corrupt as e:
        print(f"（名稱檔 {e}；本次不顯示名稱。修正或改名該檔後即可恢復，"
              f"--forget-all 會刪除它）", file=sys.stderr)
        return {}


def _write(data: dict[str, str]) -> None:
    storage.atomic_write_json(history.home(), path(), data, prefix=".labels-")


def set_label(number: str, label: str) -> None:
    with storage.mutation_lock(history.home()):
        data = _read_strict()
        data[number] = label
        _write(data)


def remove(number: str) -> bool:
    with storage.mutation_lock(history.home()):
        data = _read_strict()
        if number not in data:
            return False
        del data[number]
        _write(data)
        return True


def remove_all() -> bool:
    """使用者要求全部清除：檔案毀損也直接刪，回傳是否真的有刪到檔案。"""
    with storage.mutation_lock(history.home()):
        try:
            path().unlink()
        except FileNotFoundError:
            return False
        return True


def find(query: str, numbers: Iterable[str], names: dict[str, str]) -> list[str]:
    """依序比對：完整單號 → 名稱完全相符 → 名稱包含；回傳第一個有命中的層級的全部結果。

    不做模糊比對（spec §4.3 首版範圍），也絕不替使用者從多筆裡挑一筆。
    """
    nums = list(numbers)
    raw = query.strip()
    q = normalize(query)
    if not q:
        return []
    exact_number = [n for n in nums if n == raw]
    if exact_number:
        return exact_number
    exact = [n for n in nums if n in names and normalize(names[n]) == q]
    if exact:
        return exact
    return [n for n in nums if n in names and q in normalize(names[n])]
