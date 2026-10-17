"""本機檔案的寫入共用層：原子寫入、跨程序 mutation lock、毀損檔隔離。

history.json 與 labels.json 可能被同時執行的兩個 Agent／終端改動。lock 只防止
「讀-改-寫」交錯造成 lost update，**不會**讓兩次 os.replace() 變成同一個 transaction——
跨檔刪除的部分失敗契約見 track.py 的 forget 路徑。

鎖用 OS 的檔案鎖（POSIX flock、Windows msvcrt.locking）鎖住一個常駐的空檔，而不是
「建立／刪除 lock 檔」：後者在程序被 SIGKILL 或 timeout 殺掉時會留下永久的 lock，
之後每一次寫入都被擋，而且無法可靠分辨「另一個程序正在寫」與「上次當掉」。
OS 檔案鎖在程序結束時由系統釋放，這個問題不存在。

取不到鎖立即失敗，不等待。重入計數是模組層級的：CLI 單執行緒、一次只操作一個
home，所以這裡不是 thread-safe，也不支援同一程序內交錯操作兩個 home。
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

LOCK_NAME = ".mutation.lock"
_depth = 0
_handle = None


class StorageError(OSError):
    """本模組所有例外的基底。繼承 OSError，讓既有 `except OSError` 的保證
    （紀錄寫不進去也要先交出查詢結果）延續到新的失敗型態。"""


class LockBusy(StorageError):
    def __init__(self, path: Path):
        super().__init__(f"另一個 parcel-kau-a 程序正在修改本機紀錄，請等它結束後再試（{path}）")
        self.path = path


class Corrupt(StorageError):
    def __init__(self, path: Path, reason: str):
        super().__init__(f"{path} 無法解析（{reason}）")
        self.path = path


def _try_lock(f) -> bool:
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(f) -> None:
    if os.name == "nt":
        import msvcrt
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextmanager
def mutation_lock(home: Path):
    global _depth, _handle
    if _depth == 0:
        home.mkdir(parents=True, exist_ok=True)
        lock = home / LOCK_NAME
        f = open(lock, "a+b")
        try:
            if not _try_lock(f):
                raise LockBusy(lock)
        except BaseException:
            f.close()
            raise
        _handle = f
    _depth += 1
    try:
        yield
    finally:
        _depth -= 1
        if _depth == 0:
            f, _handle = _handle, None
            try:
                _unlock(f)
            finally:
                f.close()


def read_json_object(p: Path) -> dict | None:
    """檔案不存在回 None；讀不了、不是 JSON、root 不是 object 一律 raise Corrupt。"""
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        raise Corrupt(p, str(e)) from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise Corrupt(p, str(e)) from e
    if not isinstance(data, dict):
        raise Corrupt(p, "內容不是 JSON object")
    return data


def quarantine(p: Path) -> Path:
    """把毀損檔改名保留在同目錄，回傳新路徑。原內容一個位元組都不動。"""
    kept = p.with_name(f"{p.name}.corrupt-{datetime.now():%Y%m%dT%H%M%S}")
    os.replace(p, kept)
    return kept


def _replace(src: str, dst: Path) -> None:
    # Windows 上目標檔正被別的程序開著讀取時 os.replace 會 PermissionError；
    # 讀取端不取鎖，所以給一點時間讓對方讀完。POSIX 的 rename 不受影響。
    attempts = 3 if os.name == "nt" else 1
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.1)


def atomic_write_json(home: Path, final: Path, data, *, prefix: str) -> None:
    """mkstemp 建檔即為 0600，權限在任何內容寫入之前就到位；暫存檔與正式檔同目錄才能 rename。"""
    home.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=home, prefix=prefix, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, final)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
