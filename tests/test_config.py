import pytest

from rover_status.config import DEFAULT_TOPICS, DEFAULTS, parse_config


def test_defaults():
    cfg = parse_config({})
    assert cfg["http_port"] == 50109
    assert cfg["http_bind"] == "127.0.0.1"
    assert cfg["topics"] == DEFAULT_TOPICS
    assert cfg["record_dir"] == "~/.robonix/rover_status"
    assert set(cfg) == set(DEFAULTS)


def test_explicit_defaults_are_not_shared():
    first = parse_config({})
    second = parse_config({})
    first["topics"]["imu"] = "/mutated"
    assert second["topics"]["imu"] == "/wit_10axis/data"


def test_unknown_key():
    with pytest.raises(ValueError, match="Unknown config keys"):
        parse_config({"nope": 1})


@pytest.mark.parametrize("patch", [
    {"topics": {"imu": "relative"}},
    {"topics": {"bogus": "/x"}},
    {"topic_remap": {"bogus": "/x"}},
    {"topic_remap": {"imu": "/one", "fix": "/one"}},
    {"provider_ids": {"imu": ""}},
    {"provider_ids": {"bogus": "x"}},
    {"state_topic": "/gps/fix"},
    {"imu_yaw_sign": 2},
    {"sample_hz": 0},
    {"sample_hz": 11},
    {"gnss_timeout_s": 0},
    {"imu_timeout_s": 0},
    {"http_port": -1},
    {"http_port": 70000},
    {"http_port": True},
    {"http_bind": " "},
    {"record_retention_days": -1},
    {"record_retention_days": 1.5},
    {"origin": "30.0"},
    {"origin": "nan,1"},
    {"resolve_providers": "yes"},
])
def test_invalid(patch):
    with pytest.raises(ValueError):
        parse_config(patch)


def test_topic_and_provider_overrides():
    cfg = parse_config({
        "topics": {"imu": "/custom/imu"},
        "provider_ids": {"imu": "wit_imu", "rtk_status": "bt982g1_gnss"},
        "topic_remap": {"magnetic_raw": "/custom/mag"},
    })
    assert cfg["topics"]["imu"] == "/custom/imu"
    assert cfg["topics"]["fix"] == "/gps/fix"
    assert cfg["provider_ids"] == {
        "imu": "wit_imu", "rtk_status": "bt982g1_gnss"}
    assert cfg["topic_remap"]["magnetic_raw"] == "/custom/mag"


def test_origin_string_accepted():
    cfg = parse_config({"origin": "30.2236,120.2600"})
    assert cfg["origin"] == "30.2236,120.2600"


def test_default_state_topic_is_not_an_input():
    cfg = parse_config({})
    assert cfg["state_topic"] not in cfg["topics"].values()


def test_record_can_be_disabled():
    cfg = parse_config({"record_enabled": False, "http_enabled": False})
    assert cfg["record_enabled"] is False
    assert cfg["http_enabled"] is False
