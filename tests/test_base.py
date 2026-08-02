"""TrackResult / adapter registry 基礎行為（spec 2026-08-02-tw-parcel-track-skill）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers import CARRIERS  # noqa: E402
from carriers.base import TrackEvent, TrackResult  # noqa: E402


def _r(events):
    return TrackResult(carrier="tcat", number="9031234567", found=True,
                       events=events, source_url="https://example.test")


def test_latest_returns_chronologically_last_event():
    events = [
        TrackEvent(time="2026-08-01 10:00", status="已收件", location="台北"),
        TrackEvent(time="2026-08-02 09:30", status="配送中", location="新竹"),
        TrackEvent(time="2026-08-01 18:00", status="轉運中", location="桃園"),
    ]
    assert _r(events).latest.status == "配送中"


def test_latest_is_none_when_no_events():
    assert _r([]).latest is None


def test_registry_exposes_direct_carriers_plus_aggregator():
    assert set(CARRIERS) == {"tcat", "kerrytj", "ecan", "pchome", "fusheng", "spx", "17track"}


def test_only_direct_carriers_participate_in_auto_detection():
    """聚合服務要花使用者額度，detect() 必須永遠 False。"""
    detected = {c for c, a in CARRIERS.items() if a.detect("123456789012")}
    assert "17track" not in detected
    assert detected == {"tcat", "kerrytj", "ecan", "pchome", "fusheng"}


def test_registry_adapters_have_detect_and_track():
    for code, adapter in CARRIERS.items():
        assert callable(adapter.detect), code
        assert callable(adapter.track), code
        assert adapter.code == code
