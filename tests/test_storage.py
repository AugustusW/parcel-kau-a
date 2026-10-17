"""寫入共用層：原子寫入、跨程序 mutation lock。

鎖用 OS 的檔案鎖（flock／msvcrt.locking）而不是「建立／刪除 lock 檔」：後者在程序被
SIGKILL 或 timeout 殺掉時會留下永久的 lock，之後每一次寫入都被擋（architect 2026-10-17）。
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import storage  # noqa: E402


def _hold_externally(home):
    """另一個 open file description 取得同一把鎖，模擬另一個程序。"""
    home.mkdir(parents=True, exist_ok=True)
    f = open(home / storage.LOCK_NAME, "a+b")
    assert storage._try_lock(f)
    return f


def _release(f):
    storage._unlock(f)
    f.close()


def test_lock_is_exclusive_across_holders(tmp_path):
    held = _hold_externally(tmp_path)
    try:
        with pytest.raises(storage.LockBusy) as exc:
            with storage.mutation_lock(tmp_path):
                pass
        assert exc.value.path == tmp_path / storage.LOCK_NAME
    finally:
        _release(held)


def test_lock_is_free_again_after_the_holder_releases(tmp_path):
    _release(_hold_externally(tmp_path))
    with storage.mutation_lock(tmp_path):
        pass


def test_failed_acquire_leaves_no_state_behind(tmp_path):
    held = _hold_externally(tmp_path)
    try:
        with pytest.raises(storage.LockBusy):
            with storage.mutation_lock(tmp_path):
                pass
    finally:
        _release(held)
    assert storage._depth == 0 and storage._handle is None
    with storage.mutation_lock(tmp_path):
        pass


def test_reentrant_and_released_after_nested_exception(tmp_path):
    with pytest.raises(RuntimeError):
        with storage.mutation_lock(tmp_path):
            with storage.mutation_lock(tmp_path):
                raise RuntimeError("boom")
    assert storage._depth == 0 and storage._handle is None
    _release(_hold_externally(tmp_path))  # 真的釋放了：外部可以再取得


def test_inner_exit_does_not_release_the_outer_hold(tmp_path):
    with storage.mutation_lock(tmp_path):
        with storage.mutation_lock(tmp_path):
            pass
        f = open(tmp_path / storage.LOCK_NAME, "a+b")
        try:
            assert storage._try_lock(f) is False, "內層結束不可提早釋放"
        finally:
            f.close()


def test_lock_released_when_the_holding_process_is_killed(tmp_path):
    code = textwrap.dedent(f"""
        import sys, time, pathlib
        sys.path.insert(0, {str(Path(storage.__file__).parent)!r})
        import storage
        with storage.mutation_lock(pathlib.Path({str(tmp_path)!r})):
            print("locked", flush=True)
            time.sleep(30)
    """)
    p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "locked"
        with pytest.raises(storage.LockBusy):
            with storage.mutation_lock(tmp_path):
                pass
    finally:
        p.kill()
        p.wait()
        p.stdout.close()
    with storage.mutation_lock(tmp_path):
        pass


def test_read_json_object_distinguishes_missing_from_corrupt(tmp_path):
    assert storage.read_json_object(tmp_path / "none.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(storage.Corrupt):
        storage.read_json_object(bad)
    arr = tmp_path / "arr.json"
    arr.write_text("[]", encoding="utf-8")
    with pytest.raises(storage.Corrupt):
        storage.read_json_object(arr)


def test_storage_errors_are_oserrors():
    """既有呼叫端靠 `except OSError` 保證「紀錄寫不進去也要交出查詢結果」。"""
    assert issubclass(storage.LockBusy, OSError)
    assert issubclass(storage.Corrupt, OSError)


def test_quarantine_keeps_the_original_bytes(tmp_path):
    bad = tmp_path / "history.json"
    bad.write_text("{ not json", encoding="utf-8")
    kept = storage.quarantine(bad)
    assert not bad.exists()
    assert kept.parent == tmp_path and kept.name.startswith("history.json.corrupt-")
    assert kept.read_text(encoding="utf-8") == "{ not json"


@pytest.mark.skipif(os.name != "posix", reason="POSIX 權限")
def test_atomic_write_creates_owner_only_file(tmp_path):
    target = tmp_path / "x.json"
    storage.atomic_write_json(tmp_path, target, {"a": 1}, prefix=".x-")
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]
