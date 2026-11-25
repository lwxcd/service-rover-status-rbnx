# SPDX-License-Identifier: MulanPSL-2.0
"""Runtime side of the rover status service: ROS subscriptions, 1 Hz sampler,
CSV/JSON recording and the read-only dashboard.

Everything here is read-only. The service opens no serial port, sends no NTRIP
corrections and publishes only its own status topic.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import ROLES
from .core import (
    CSV_COLUMNS,
    Datum,
    RosState,
    _wrap360 as wrap360,
    build_status,
    csv_row,
    load_origin,
    parse_origin,
    quaternion_to_rpy,
)
from .web import StatusHTTPServer, local_ips, make_handler

log = logging.getLogger(__name__)

STATUS_JSON_NAME = "rover_status.json"


class Recorder:
    """Daily CSV plus an atomic JSON snapshot.

    Files are named rover_status_YYYYMMDD.csv and appended across restarts so
    a service restart does not lose the day. Retention pruning runs at startup
    and on day rotation.
    """

    def __init__(self, directory: str, retention_days: int) -> None:
        self.directory = Path(directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.status_path = self.directory / STATUS_JSON_NAME
        self._day: Optional[str] = None
        self._handle = None
        self._writer = None
        self._prune()

    @property
    def current_path(self) -> Optional[Path]:
        return None if self._day is None else \
            self.directory / f"rover_status_{self._day}.csv"

    def _prune(self) -> None:
        if self.retention_days <= 0:
            return
        cutoff = time.time() - self.retention_days * 86400.0
        for path in self.directory.glob("rover_status_*.csv"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    log.info("pruned old record %s", path)
            except OSError:
                pass

    def _close_file(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
        self._handle = None
        self._writer = None
        self._day = None

    def _ensure_file(self) -> None:
        day = datetime.now().strftime("%Y%m%d")
        if day == self._day:
            return
        self._close_file()
        path = self.directory / f"rover_status_{day}.csv"
        is_new = not path.exists()
        handle = path.open("a", newline="", encoding="utf-8")
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(CSV_COLUMNS)
        self._day = day
        self._handle = handle
        self._writer = writer
        log.info("recording to %s", path)
        self._prune()

    def write(self, status: dict) -> None:
        self._ensure_file()
        self._writer.writerow(csv_row(status))
        self._handle.flush()
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.status_path)

    def close(self) -> None:
        self._close_file()


class RoverStatusService:
    """Owns the rclpy context, sampler thread, recorder and HTTP server."""

    def __init__(self, config, topics, sources, service_id: str = "rover_status"):
        self.config = config
        self.topics = dict(topics)
        self.sources = dict(sources)
        self.service_id = service_id
        self.state = RosState()
        self.stopped = False
        self.latest: Optional[dict] = None
        self.t0 = time.monotonic()
        self._stop = threading.Event()
        self.context = None
        self.node = None
        self.executor = None
        self.spin_thread = None
        self.sampler = None
        self.state_publisher = None
        self.http_server = None
        self.http_thread = None
        self.recorder: Optional[Recorder] = None
        self._String = None

        try:
            self.datum = self._make_datum()
            self._start_ros()
            self._start_http()
            self._start_recorder()
            self.sampler = threading.Thread(
                target=self._sample_loop, name="rover-status-sampler", daemon=True)
            self.sampler.start()
            log.info("rover status sampling at %.1f Hz from %s",
                     config["sample_hz"], self.topics)
        except Exception:
            self.stop()
            raise

    # -- construction helpers ---------------------------------------------

    def _make_datum(self) -> Datum:
        origin = None
        source = "first fix"
        configured = self.config["origin"].strip()
        if configured:
            origin = parse_origin(configured)
            source = "origin"
        elif self.config["origin_config"].strip().lower() not in ("", "none"):
            path = Path(self.config["origin_config"]).expanduser()
            origin = load_origin(path)
            if origin is not None:
                source = str(path)
            else:
                log.warning("origin config %s has no usable origin; using first fix", path)
        datum = Datum(
            lat0=None if origin is None else origin[0],
            lon0=None if origin is None else origin[1],
            fixed=origin is not None,
            source=source,
        )
        log.info("datum source %s -> %s", datum.source, datum.as_dict())
        return datum

    def _start_ros(self) -> None:
        import rclpy
        from rclpy.context import Context
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import QoSProfile, ReliabilityPolicy
        from geometry_msgs.msg import TwistStamped, Vector3Stamped
        from sensor_msgs.msg import Imu, NavSatFix
        from std_msgs.msg import String

        self._String = String
        self.context = Context()
        rclpy.init(context=self.context)
        node = self.node = rclpy.create_node(
            "rover_status", context=self.context)
        try:
            # Best-effort subscribers are compatible with both reliable and
            # best-effort publishers, keeping the monitor independent of the
            # stack's QoS choices.
            qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
            node.create_subscription(
                String, self.topics["rtk_status"], self._on_rtk_status, qos)
            node.create_subscription(
                NavSatFix, self.topics["fix"], self._on_fix, qos)
            node.create_subscription(
                TwistStamped, self.topics["velocity"], self._on_velocity, qos)
            node.create_subscription(
                Imu, self.topics["imu"], self._on_imu, qos)
            node.create_subscription(
                String, self.topics["imu_status"], self._on_imu_status, qos)
            node.create_subscription(
                Vector3Stamped, self.topics["magnetic_raw"], self._on_mag, qos)
            self.state_publisher = node.create_publisher(
                String, self.config["state_topic"], 10)
            self.executor = SingleThreadedExecutor(context=self.context)
            self.executor.add_node(node)
            self.spin_thread = threading.Thread(
                target=self.executor.spin, name="rover-status-ros", daemon=True)
            self.spin_thread.start()
        except Exception:
            node.destroy_node()
            if self.context.ok():
                self.context.shutdown()
            raise

    def _start_http(self) -> None:
        if not self.config["http_enabled"]:
            return
        bind = self.config["http_bind"]
        port = self.config["http_port"]
        try:
            server = StatusHTTPServer((bind, port), make_handler(self.status))
        except OSError as exc:
            log.warning("dashboard disabled: %s", exc)
            return
        self.http_server = server
        self.http_thread = threading.Thread(
            target=server.serve_forever, name="rover-status-http", daemon=True)
        self.http_thread.start()
        bound = server.server_address[1]
        if bind in ("0.0.0.0", "::"):
            for ip in local_ips() or ["<orin-ip>"]:
                log.info("dashboard http://%s:%s/", ip, bound)
        log.info("dashboard http://%s:%s/ (JSON /status, text /text)", bind, bound)

    def _start_recorder(self) -> None:
        if not self.config["record_enabled"]:
            return
        try:
            self.recorder = Recorder(
                self.config["record_dir"], self.config["record_retention_days"])
        except OSError as exc:
            log.warning("recording disabled: %s", exc)

    # -- subscriptions -----------------------------------------------------

    def _on_rtk_status(self, msg) -> None:
        try:
            data = json.loads(msg.data)
        except (TypeError, ValueError):
            return
        self.state.on_rtk_status(data)

    def _on_fix(self, msg) -> None:
        self.state.on_fix(
            msg.latitude, msg.longitude, msg.altitude, msg.status.status)

    def _on_velocity(self, msg) -> None:
        self.state.on_velocity(
            msg.twist.linear.x, msg.twist.linear.y, msg.twist.linear.z,
            msg.header.frame_id)

    def _on_imu(self, msg) -> None:
        q = msg.orientation
        roll, pitch, yaw = quaternion_to_rpy(q.x, q.y, q.z, q.w)
        self.state.on_imu(
            math.degrees(roll), math.degrees(pitch),
            wrap360(math.degrees(yaw)), math.degrees(msg.angular_velocity.z),
            msg.linear_acceleration.x, msg.linear_acceleration.y,
            msg.linear_acceleration.z)

    def _on_imu_status(self, msg) -> None:
        try:
            data = json.loads(msg.data)
        except (TypeError, ValueError):
            return
        self.state.on_imu_status(data)

    def _on_mag(self, msg) -> None:
        self.state.on_mag(msg.vector.x, msg.vector.y, msg.vector.z)

    # -- sampling ----------------------------------------------------------

    def status(self) -> dict:
        data = build_status(
            self.state, self.datum,
            self.config["imu_yaw_sign"], self.config["imu_yaw_offset_deg"],
            self.t0,
            gnss_timeout_s=self.config["gnss_timeout_s"],
            imu_timeout_s=self.config["imu_timeout_s"],
        )
        data["service"] = self._service_info()
        return data

    def _service_info(self) -> dict:
        if self.http_server is not None:
            http = {
                "enabled": True,
                "bind": self.config["http_bind"],
                "port": self.http_server.server_address[1],
            }
        else:
            http = {"enabled": False}
        record = {"enabled": self.recorder is not None}
        if self.recorder is not None:
            record["dir"] = str(self.recorder.directory)
            record["file"] = (
                None if self.recorder.current_path is None
                else str(self.recorder.current_path)
            )
        return {
            "id": self.service_id,
            "http": http,
            "record": record,
            "topics": {
                role: {"topic": self.topics[role], "source": self.sources[role]}
                for role in ROLES
            },
        }

    def _sample_loop(self) -> None:
        period = 1.0 / self.config["sample_hz"]
        while not self._stop.wait(period):
            try:
                data = self.status()
                self.latest = data
                if self.recorder is not None:
                    self.recorder.write(data)
                if self.state_publisher is not None:
                    self.state_publisher.publish(self._String(
                        data=json.dumps(data, ensure_ascii=False,
                                        separators=(",", ":"))))
            except Exception:  # noqa: BLE001
                log.exception("rover status sample failed")

    # -- teardown ----------------------------------------------------------

    def stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        self._stop.set()
        if self.sampler is not None:
            self.sampler.join(timeout=2.0)
        if self.http_server is not None:
            self.http_server.shutdown()
            self.http_server.server_close()
            if self.http_thread is not None:
                self.http_thread.join(timeout=2.0)
            self.http_server = None
        if self.recorder is not None:
            self.recorder.close()
        if self.executor is not None:
            self.executor.shutdown(timeout_sec=2.0)
        if self.spin_thread is not None:
            self.spin_thread.join(timeout=3.0)
        if self.node is not None:
            try:
                self.node.destroy_node()
            except Exception:  # noqa: BLE001
                pass
            self.node = None
        if self.context is not None and self.context.ok():
            self.context.shutdown()
