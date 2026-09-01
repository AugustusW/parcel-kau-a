"""Docs numbers, enforced against the repository.

The Status section of README.md states a version and a test count. Nothing
made them move when the code moved, and numbers like these drift exactly one
release at a time, silently. These tests read them out of the README and
compare them against the CHANGELOG and against what pytest actually collects,
so a stale claim is a red suite instead of a wrong page.

The zh-TW README carries no Status numbers, so only the English one is read.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CHANGELOG = ROOT / "CHANGELOG.md"

# Anchored on the CHANGELOG link so that version mentions elsewhere in the
# README (feature history, examples) can never be mistaken for the Status one.
STATUS_VERSION_RE = re.compile(r"v(\d+\.\d+\.\d+)\s*[（(]\[CHANGELOG\]")
TEST_COUNT_RE = re.compile(r"(\d+) offline unit tests")
CHANGELOG_ENTRY_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.M)


def _read(path):
    return path.read_text(encoding="utf-8")


def _collected_count():
    """Ask pytest, rather than trusting a written number. --collect-only runs
    nothing, so this cannot recurse; pointing it at the tests directory makes
    the answer the same however the suite was started."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(ROOT / "tests")],
        capture_output=True, text=True, cwd=ROOT,
    )
    match = re.search(r"(\d+) tests? collected", proc.stdout)
    assert match, f"could not read a collected count from pytest:\n{proc.stdout}\n{proc.stderr}"
    return int(match.group(1))


def test_readme_status_version_matches_the_newest_changelog_entry():
    stated = STATUS_VERSION_RE.findall(_read(README))
    assert len(stated) == 1, (
        f"README.md has {len(stated)} Status version lines; a stale duplicate "
        "survives first-wins reading, keep exactly one"
    )
    entries = CHANGELOG_ENTRY_RE.findall(_read(CHANGELOG))
    assert entries, "CHANGELOG.md has no '## [x.y.z]' entries"
    assert stated[0] == entries[0], (
        f"README Status says v{stated[0]} but the newest CHANGELOG entry "
        f"is {entries[0]}"
    )


def test_readme_test_count_matches_what_pytest_collects():
    stated = TEST_COUNT_RE.findall(_read(README))
    assert stated, "README.md states no test count"
    collected = _collected_count()
    wrong = sorted({int(n) for n in stated if int(n) != collected})
    assert not wrong, (
        f"README.md states {wrong} test(s) but the suite collects {collected}; "
        "update every count in the file"
    )
