import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rover_status.core import Datum, RosState, build_status  # noqa: E402


def make_sample_state(mono=1000.0):
    state = RosState()
    state.on_rtk_status({
        "lat": 30.22361,
        "lon": 120.26001,
        "alt_m": 12.3,
        "receiver_quality": 4,
        "sats": 18,
        "hdop": 0.6,
        "diff_age_s": 2.0,
        "fix_age_s": 0.5,
        "valid": True,
        "speed_mps": 0.8,
        "course_deg": 45.0,
        "state": "fixed",
        "rtk_fixed": True,
        "serial_status": "open",
        "ntrip": {
            "state": "up",
            "rtcm_bytes": 1234,
            "gga_uploaded": 9,
            "connects": 2,
            "last_error": "",
        },
    }, mono=mono)
    state.on_fix(30.22361, 120.26001, 12.3, 0, mono=mono)
    state.on_velocity(0.0, 0.0, 0.0, "ENU", mono=mono)
    state.on_imu(1.0, 2.0, 30.0, 0.5, 0.1, 0.2, 9.8, mono=mono)
    state.on_imu_status(
        {"serial_connected": True, "counts": {"imu": 42}}, mono=mono)
    state.on_mag(30.0, 40.0, 0.0, mono=mono)
    return state


def sample_datum():
    return Datum(
        lat0=30.2236, lon0=120.2600, fixed=True, source="test")


def make_sample_status(mono=1000.0):
    return build_status(
        make_sample_state(mono), sample_datum(), 1, 0.0, t0=990.0,
        now=mono + 0.5, wall=1700000000.0)


@pytest.fixture
def sample_status():
    return make_sample_status()
