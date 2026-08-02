"""嘉里大榮 kerrytj adapter — JSON API 回應的離線解析。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from carriers.kerrytj import KerrytjAdapter, parse_tracking_response  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def test_detect_accepts_12_digit_numbers():
    a = KerrytjAdapter()
    assert a.detect("901234567890")
    assert not a.detect("TW254414081298F")


def test_notfound_response_parses_as_not_found():
    payload = json.loads((FIXTURES / "kerrytj_notfound.json").read_text(encoding="utf-8"))
    result = parse_tracking_response(payload, number="901234567890")
    assert result.found is False
    assert result.events == []


def test_found_response_parses_course_events():
    """合成 found payload（真實欄位名，值 UNVERIFIED 需真實單號校準）。"""
    payload = {
        "trackType": 0,
        "list": [{"bolNo": "900000000001", "course": [
            {"statusId": "OK1", "statusIdName": "順利送達",
             "processDepotIdName": "台北所",
             "processCargoCrtDate": 20260801, "processCargoCrtTime": 93000},
            {"statusId": "OK0", "statusIdName": "已集貨",
             "processDepotIdName": "新竹所",
             "processCargoCrtDate": 20260731, "processCargoCrtTime": 180000},
        ]}],
        "errTrackNo": [],
    }
    result = parse_tracking_response(payload, number="900000000001")
    assert result.found is True
    assert len(result.events) == 2
    assert result.latest.status == "順利送達"
    assert result.latest.location == "台北所"


def test_unexpected_json_shape_raises_parse_error():
    """API schema 改版（缺 list 與 errTrackNo）要能與「查無」區分。"""
    from carriers.base import ParseError

    import pytest
    with pytest.raises(ParseError):
        parse_tracking_response({"unexpected": "shape"}, number="900000000001")
