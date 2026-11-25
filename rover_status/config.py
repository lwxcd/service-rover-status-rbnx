# SPDX-License-Identifier: MulanPSL-2.0
"""Configuration for the read-only rover status service."""

from __future__ import annotations

import math
import re

from .core import parse_origin

TOPIC_PATTERN = r"/[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*"

# Subscription roles and the primitive contracts that own them.
CONTRACTS = {
    "rtk_status": "robonix/primitive/gnss/rtk_status",
    "fix": "robonix/primitive/gnss/fix",
    "velocity": "robonix/primitive/gnss/velocity",
    "imu": "robonix/primitive/imu/imu",
    "imu_status": "robonix/primitive/imu/status",
    "magnetic_raw": "robonix/primitive/imu/magnetic_raw",
}
ROLES = tuple(CONTRACTS)

# Endpoints used when no Atlas provider is resolved. They match the stack's
# deployment defaults, so the service still monitors a running stack when
# Atlas is temporarily unavailable.
DEFAULT_TOPICS = {
    "rtk_status": "/gps/rtk_status",
    "fix": "/gps/fix",
    "velocity": "/gps/velocity",
    "imu": "/wit_10axis/data",
    "imu_status": "/wit_10axis/status",
    "magnetic_raw": "/wit_10axis/magnetic_raw",
}

DEFAULTS = {
    "topic_remap": {},
    "topics": dict(DEFAULT_TOPICS),
    "provider_ids": {},
    "resolve_providers": True,
    "origin": "",
    "origin_config": "",
    "imu_yaw_sign": 1,
    "imu_yaw_offset_deg": 0.0,
    "sample_hz": 1.0,
    "gnss_timeout_s": 3.0,
    "imu_timeout_s": 1.5,
    "state_topic": "/robonix/service/rover_status/state",
    "http_enabled": True,
    "http_bind": "127.0.0.1",
    "http_port": 50109,
    "record_enabled": True,
    "record_dir": "~/.robonix/rover_status",
    "record_retention_days": 14,
}


def _topic(value, field):
    if not isinstance(value, str) or re.fullmatch(TOPIC_PATTERN, value) is None:
        raise ValueError(f"{field} must be an absolute ROS topic name")
    return value


def _number(value, field, upper, lower=0.0):
    if type(value) not in (int, float) or not math.isfinite(value) \
            or not lower < value <= upper:
        raise ValueError(f"{field} must be in ({lower},{upper}]")
    return float(value)


def _mapping(value, field):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    unknown = set(value) - set(ROLES)
    if unknown:
        raise ValueError(f"Unknown {field} roles: {sorted(unknown)}")
    return dict(value)


def parse_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError("Configuration must be an object")
    unknown = set(cfg) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown config keys: {sorted(unknown)}")
    parsed = {**DEFAULTS, **cfg}
    parsed["topics"] = {**DEFAULT_TOPICS, **_mapping(parsed["topics"], "topics")}
    parsed["topic_remap"] = _mapping(parsed["topic_remap"], "topic_remap")
    parsed["provider_ids"] = _mapping(parsed["provider_ids"], "provider_ids")

    for field in ("topics", "topic_remap"):
        for role, value in parsed[field].items():
            parsed[field][role] = _topic(value, f"{field}.{role}")
    for role, provider in parsed["provider_ids"].items():
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError(f"provider_ids.{role} must be a non-empty string")
        parsed["provider_ids"][role] = provider.strip()

    parsed["state_topic"] = _topic(parsed["state_topic"], "state_topic")
    if parsed["state_topic"] in set(parsed["topics"].values()) | \
            set(parsed["topic_remap"].values()):
        raise ValueError("state_topic must differ from every subscription topic")

    effective = {
        role: parsed["topic_remap"].get(role, parsed["topics"][role])
        for role in ROLES
    }
    if len(set(effective.values())) != len(effective):
        raise ValueError("subscription topics must be distinct")

    if not isinstance(parsed["resolve_providers"], bool):
        raise ValueError("resolve_providers must be a boolean")

    origin = parsed["origin"]
    if not isinstance(origin, str):
        raise ValueError("origin must be a LAT,LON string")
    if origin.strip() and parse_origin(origin.strip()) is None:
        raise ValueError("origin must be LAT,LON")

    sign = parsed["imu_yaw_sign"]
    if type(sign) is not int or sign not in (1, -1):
        raise ValueError("imu_yaw_sign must be 1 or -1")
    parsed["imu_yaw_offset_deg"] = _number(
        parsed["imu_yaw_offset_deg"], "imu_yaw_offset_deg", 360.0, -360.0)
    parsed["sample_hz"] = _number(parsed["sample_hz"], "sample_hz", 10.0)
    parsed["gnss_timeout_s"] = _number(
        parsed["gnss_timeout_s"], "gnss_timeout_s", 60.0)
    parsed["imu_timeout_s"] = _number(
        parsed["imu_timeout_s"], "imu_timeout_s", 60.0)

    if not isinstance(parsed["origin_config"], str):
        raise ValueError("origin_config must be a path string")

    if not isinstance(parsed["http_enabled"], bool):
        raise ValueError("http_enabled must be a boolean")
    bind = parsed["http_bind"]
    if not isinstance(bind, str) or not bind.strip() or any(c.isspace() for c in bind):
        raise ValueError("http_bind must be a non-empty bind address")
    port = parsed["http_port"]
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("http_port must be an integer in [0,65535]")

    if not isinstance(parsed["record_enabled"], bool):
        raise ValueError("record_enabled must be a boolean")
    if not isinstance(parsed["record_dir"], str) or not parsed["record_dir"].strip():
        raise ValueError("record_dir must be a non-empty path")
    retention = parsed["record_retention_days"]
    if type(retention) is not int or not 0 <= retention <= 3650:
        raise ValueError("record_retention_days must be an integer in [0,3650]")
    return parsed
