"""使用者自訂的包裹名稱：只存本機、只由使用者明確提供（spec §4）。

名稱會出現在終端機與 Agent 的 context 裡，所以驗證採白名單：一般文字、標點、符號
（含 emoji）與空白可以；控制字元、bidi 控制、零寬以外的格式字元、孤立 surrogate、
行／段分隔符一律拒絕。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import labels  # noqa: E402
import storage  # noqa: E402


@pytest.mark.parametrize("ok", [
    "momo 耳機", "媽媽的包裹", "\U0001F469‍\U0001F467 禮物", "AirPods Pro　第二代",
    "\U0001F3F4 英格蘭", "x" * 100, "書（上）", "#3 包裹"])
def test_valid_labels_are_accepted(ok):
    assert labels.validate(ok) == ok.strip()


def test_labels_are_nfc_normalised():
    assert labels.validate("é") == "é"


@pytest.mark.parametrize("bad", [
    "", "   ", "a\nb", "a\x00b", "\x1b[31m紅字", "a‮b", "a⁦b", "a؜b",
    "a\x85b", "a b", "a b", "a\U000E0041b", "‍‍", "a\udc80b", "x" * 101])
def test_invalid_labels_are_rejected(bad):
    with pytest.raises(labels.InvalidLabel):
        labels.validate(bad)


def test_normalize_collapses_spaces_and_ascii_case_only():
    assert labels.normalize("  Momo   AirPods ") == "momo airpods"
    assert labels.normalize("ＡＢＣ") == "ＡＢＣ", "全形字不在 ASCII 範圍，不改"


def test_find_prefers_exact_number_then_exact_name_then_contains():
    names = {"111": "耳機", "222": "momo 耳機保護殼", "333": "工作用耳機"}
    nums = ["111", "222", "333"]
    assert labels.find("222", nums, names) == ["222"]
    assert labels.find("耳機", nums, names) == ["111"], "名稱完全相符優先於包含"
    assert labels.find("保護殼", nums, names) == ["222"]
    assert labels.find("用耳", nums, names) == ["333"]
    assert labels.find("MOMO", nums, names) == ["222"]
    assert labels.find("不存在", nums, names) == []
    assert labels.find("   ", nums, names) == []


def test_find_returns_every_contains_match_in_input_order():
    names = {"2": "momo 藍牙耳機", "1": "momo 耳機保護殼"}
    assert labels.find("momo", ["1", "2"], names) == ["1", "2"]


def test_set_and_remove_roundtrip():
    labels.set_label("900000000001", "momo 耳機")
    assert labels.load_for_read() == {"900000000001": "momo 耳機"}
    assert labels.remove("900000000001") is True
    assert labels.remove("900000000001") is False
    assert labels.load_for_read() == {}


def test_reading_without_a_file_creates_nothing():
    assert labels.load_for_read() == {}
    labels.check_writable()
    assert not labels.path().exists()


def test_corrupt_file_degrades_on_read_and_fails_closed_on_write(capsys):
    labels.path().parent.mkdir(parents=True, exist_ok=True)
    labels.path().write_text("{ broken", encoding="utf-8")
    before = labels.path().read_bytes()
    assert labels.load_for_read() == {}
    assert "labels.json" in capsys.readouterr().err
    for op in (labels.check_writable, lambda: labels.set_label("1", "x"),
               lambda: labels.remove("1")):
        with pytest.raises(storage.Corrupt):
            op()
    assert labels.path().read_bytes() == before


def test_remove_all_deletes_even_a_corrupt_file():
    labels.path().parent.mkdir(parents=True, exist_ok=True)
    labels.path().write_text("{ broken", encoding="utf-8")
    assert labels.remove_all() is True
    assert not labels.path().exists()
    assert labels.remove_all() is False


def test_non_string_values_are_ignored_on_read():
    labels.path().parent.mkdir(parents=True, exist_ok=True)
    labels.path().write_text('{"1": "ok", "2": 5, "3": null}', encoding="utf-8")
    assert labels.load_for_read() == {"1": "ok"}


def test_find_matches_a_number_suffix_after_exact_number_and_before_names():
    names = {"900000000001": "書", "900000000002": "0001 號包裹"}
    nums = ["900000000001", "900000000002"]
    assert labels.find("0001", nums, names) == ["900000000001"], "尾碼優先於名稱"
    assert labels.find("900000000001", nums, names) == ["900000000001"]


def test_find_suffix_can_match_several_numbers():
    nums = ["900000000001", "800000000001"]
    assert labels.find("0001", nums, {}) == nums


def test_short_queries_are_not_treated_as_suffixes():
    assert labels.find("01", ["900000000001"], {}) == []


def test_non_string_values_block_writes_instead_of_being_dropped():
    labels.path().parent.mkdir(parents=True, exist_ok=True)
    labels.path().write_text('{"1": "ok", "2": 5}', encoding="utf-8")
    before = labels.path().read_bytes()
    with pytest.raises(storage.Corrupt):
        labels.set_label("3", "x")
    with pytest.raises(storage.Corrupt):
        labels.remove("1")
    assert labels.path().read_bytes() == before
    assert labels.load_for_read() == {"1": "ok"}
