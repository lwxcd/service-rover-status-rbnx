# SPDX-License-Identifier: MulanPSL-2.0
"""Robonix service lifecycle and RPC/MCP facade for rover status."""

from __future__ import annotations

import json
import logging
import os

from robonix_api import Err, Ok, Service
from rover_status_api_mcp import Status_Request, Status_Response
from rover_status_api_pb2 import Status_Response as StatusPB

from .config import parse_config
from .core import format_line, select_sections
from .node import RoverStatusService
from .providers import resolve

log = logging.getLogger(__name__)

service = Service(
    id=os.environ.get("ROBONIX_CAPABILITY_ID", "rover_status"),
    namespace="robonix/service/rover_status",
)
config = parse_config({})
active: RoverStatusService | None = None
channels: list = []


def _close_channels() -> None:
    for channel in channels:
        try:
            channel.close()
        except Exception:  # noqa: BLE001
            pass
    channels.clear()


@service.on_init
def init(cfg):
    global config
    if active is not None:
        return Err("Deactivate before changing rover status configuration")
    try:
        parsed = parse_config(cfg)
    except ValueError as exc:
        return Err(str(exc))
    config = parsed
    return Ok()


@service.on_activate
def activate():
    global active
    if active is None:
        opened: list = []
        try:
            topics, sources, opened = resolve(config, service)
            log.info("rover status endpoints: %s", sources)
            active = RoverStatusService(
                config, topics, sources, service_id=service.id)
            channels.extend(opened)
        except Exception as exc:  # noqa: BLE001
            log.exception("rover status failed to start")
            for channel in opened:
                try:
                    channel.close()
                except Exception:  # noqa: BLE001
                    pass
            active = None
            return Err(f"Failed to start rover status: {exc}")
    return Ok()


@service.on_deactivate
def deactivate():
    global active
    if active is not None:
        active.stop()
        active = None
    _close_channels()
    return Ok()


@service.on_shutdown
def shutdown():
    global active
    if active is not None:
        active.stop()
        active = None
    _close_channels()
    return Ok()


def status(req: Status_Request) -> Status_Response:
    """Read-only rover telemetry: GNSS/RTK fix quality, local position, IMU
    heading, motion and NTRIP/IMU link state. ``section`` optionally selects
    comma-separated top-level fields (e.g. "position,imu"); empty returns the
    full snapshot including per-topic provider resolution."""
    if active is None:
        return Status_Response(
            ok=False, status_json="{}", text="rover status service is not active")
    full = active.status()
    try:
        payload = select_sections(full, req.section)
    except KeyError as exc:
        return Status_Response(ok=False, status_json="{}", text=str(exc))
    return Status_Response(
        ok=True,
        status_json=json.dumps(payload, ensure_ascii=False),
        text=format_line(full),
    )


def grpc_handler(handler, response):
    def invoke(req):
        return response(**handler(req).to_dict())

    return invoke


CONTRACT = "robonix/service/rover_status/status"
service.mcp(CONTRACT)(status)
service.grpc(CONTRACT)(grpc_handler(status, StatusPB))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service.run()
