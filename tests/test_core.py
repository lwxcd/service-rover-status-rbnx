import json
import math

import pytest

from conftest import make_sample_state, sample_datum
from rover_status.core import (
    CSV_COLUMNS,
    Datum,
    RosState,
    build_status,
    csv_row,
    format_line,
    load_origin,
    parse_origin,
    quaternion_to_rpy,
    select_sections,
)


def test_full_snapshot_from_rtk():
    status = build_status(
        make_sample_state(1000.0), sample_datum(), 1, 0.0, t0=990.0,
        now=1000.5, wall=1700000000.0)
    assert status["uptime_s"] == 10.5
    assert status["mode"] == "ros"
    assert status["position"]["fix_quality"] == 4
    assert status["position"]["fix_name"] == "RTK fixed"
    assert status["position"]["sats"] == 18
    assert status["position"]["hdop"] == 0.6
    assert status["position"]["valid"] is True
    assert status["position"]["east_m"] == pytest.approx(0.96, abs=0.05)
    assert status["position"]["north_m"] == pytest.approx(1.11, abs=0.05)
    assert status["motion"]["speed_mps"] == 0.8
    assert status["motion"]["course_deg"] == 45.0
    assert status["imu"]["yaw_enu_deg"] == 30.0
    assert status["heading_deg"] == 60.0
    assert status["imu"]["status"] == "open"
    assert status["imu"]["mag_norm"] == 50.0
    assert status["ntrip"]["state"] == "up"
    assert status["ntrip"]["rtcm_bytes"] == 1234
    assert status["serial"]["rtk"] == "open"


def test_heading_sign_and_offset():
    state = make_sample_state(1000.0)
    state.on_imu(0.0, 0.0, 350.0, 0.0, 0.0, 0.0, 9.8, mono=1000.0)
    status = build_status(
        state, sample_datum(), 1, 10.0, t0=990.0, now=1000.1, wall=0.0)
    assert status["imu"]["yaw_enu_deg"] == 0.0
    assert status["heading_deg"] == 90.0


def test_stale_gnss_and_imu():
    state = make_sample_state(100.0)
    status = build_status(
        state, sample_datum(), 1, 0.0, t0=90.0, now=105.0, wall=0.0)
    assert status["position"]["lat"] is None
    assert status["position"]["valid"] is False
    assert status["heading_deg"] is None
    assert status["imu"]["status"] == "open (no data)"
    # serial.rtk mirrors the last RTK payload, as in the standalone tool.
    assert status["serial"]["rtk"] == "open"


def test_fix_fallback_when_rtk_stale():
    state = make_sample_state(100.0)
    state.on_fix(30.22360, 120.26000, 12.0, 2, mono=104.0)
    status = build_status(
        state, sample_datum(), 1, 0.0, t0=90.0, now=105.0, wall=0.0)
    assert status["position"]["fix_quality"] == 2
    assert status["position"]["fix_name"] == "DGPS"
    assert status["position"]["sats"] is None
    assert status["position"]["valid"] is True


def test_negative_fix_status_is_no_fix():
    state = RosState()
    state.on_fix(30.0, 120.0, 0.0, -1, mono=100.0)
    status = build_status(
        state, Datum(), 1, 0.0, t0=99.0, now=100.5, wall=0.0)
    assert status["position"]["fix_quality"] == 0
    assert status["position"]["fix_name"] == "no fix"
    assert status["position"]["valid"] is False


def test_velocity_fallback_and_low_speed_course():
    state = RosState()
    state.on_fix(30.0, 120.0, 0.0, 0, mono=100.0)
    state.on_velocity(0.3, 0.4, 0.0, "ENU", mono=100.0)
    status = build_status(
        state, Datum(), 1, 0.0, t0=99.0, now=100.2, wall=0.0)
    assert status["motion"]["speed_mps"] == 0.5
    assert status["motion"]["course_deg"] == pytest.approx(36.9, abs=0.05)

    state.on_velocity(0.1, 0.0, 0.0, "ENU", mono=100.2)
    status = build_status(
        state, Datum(), 1, 0.0, t0=99.0, now=100.3, wall=0.0)
    assert status["motion"]["speed_mps"] == 0.1
    assert status["motion"]["course_deg"] is None


def test_datum_first_fix_then_fixed_upgrade():
    datum = Datum()
    state = RosState()
    state.on_rtk_status({
        "lat": 30.2236, "lon": 120.26, "receiver_quality": 2, "valid": True,
    }, mono=100.0)
    build_status(state, datum, 1, 0.0, t0=99.0, now=100.1, wall=0.0)
    first = datum.as_dict()
    assert first["source"] == "first fix"
    assert first["quality"] == 2
    assert first["lat0"] == 30.2236

    state.on_rtk_status({
        "lat": 30.2237, "lon": 120.26, "receiver_quality": 4, "valid": True,
    }, mono=101.0)
    build_status(state, datum, 1, 0.0, t0=99.0, now=101.1, wall=0.0)
    upgraded = datum.as_dict()
    assert upgraded["source"] == "RTK fixed"
    assert upgraded["quality"] == 4
    assert upgraded["lat0"] == 30.2237


def test_fixed_datum_is_not_replaced():
    datum = Datum(lat0=1.0, lon0=2.0, fixed=True, source="config")
    datum.update(30.0, 120.0, 4)
    assert datum.as_dict()["lat0"] == 1.0
    assert datum.as_dict()["source"] == "config"


def test_quaternion_to_rpy():
    assert quaternion_to_rpy(0.0, 0.0, 0.0, 1.0) == pytest.approx((0, 0, 0))
    half = math.sqrt(0.5)
    roll, pitch, yaw = quaternion_to_rpy(0.0, 0.0, half, half)
    assert roll == pytest.approx(0.0)
    assert pitch == pytest.approx(0.0)
    assert yaw == pytest.approx(math.pi / 2)


def test_select_sections():
    status = {"t_wall": 1, "imu": {}, "position": {}}
    assert select_sections(status, "") is status
    assert select_sections(status, " , ") is status
    assert select_sections(status, "position, imu") == {
        "position": {}, "imu": {}}
    with pytest.raises(KeyError, match="available"):
        select_sections(status, "position,nope")


def test_format_line_and_csv_row():
    status = build_status(
        make_sample_state(1000.0), sample_datum(), 1, 0.0, t0=990.0,
        now=1000.5, wall=1700000000.0)
    line = format_line(status)
    assert "fix=4(RTK fixed)" in line
    assert "imu=open" in line
    row = csv_row(status, mono=1000.5)
    assert len(row) == len(CSV_COLUMNS) == 23
    assert row[1] == "1000.500"


def test_load_and_parse_origin(tmp_path):
    direct = tmp_path / "direct.json"
    direct.write_text(json.dumps({"origin": {"latitude": 1.5, "longitude": 2.5}}))
    assert load_origin(direct) == (1.5, 2.5)

    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps({
        "coordinate_reference": {
            "origin_wgs84": {"latitude": 30.1, "longitude": 120.2}}}))
    assert load_origin(reference) == (30.1, 120.2)

    assert load_origin(tmp_path / "missing.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert load_origin(bad) is None

    assert parse_origin("30.0,120.0") == (30.0, 120.0)
    assert parse_origin("30.0") is None
    assert parse_origin("nan,120") is None
