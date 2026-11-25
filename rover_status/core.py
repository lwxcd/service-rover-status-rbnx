# SPDX-License-Identifier: MulanPSL-2.0
"""Pure rover status model: samples, datum projection and the JSON snapshot.

The ROS node, HTTP server and recorder are deliberately kept out of this
module so the status contract can be tested without ROS. The snapshot schema
matches scripts/rtk_imu/rover_status_ros.py: the standalone tool stays an
emergency fallback and the web dashboard is shared verbatim.
"""

from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path
from typing import Optional

FIX_NAMES = {
    0: "no fix",
    1: "single",
    2: "DGPS",
    4: "RTK fixed",
    5: "RTK float",
    6: "dead reckoning",
}
DEFAULT_GNSS_TIMEOUT_S = 3.0
DEFAULT_IMU_TIMEOUT_S = 1.5

# CSV columns written by the standalone tool; kept identical so a day of
# service records can be diffed against the fallback recorder.
CSV_COLUMNS = [
    "t_wall", "t_mono", "heading_deg", "imu_yaw_enu_deg", "roll_deg", "pitch_deg",
    "mag_norm", "gz_dps", "lat", "lon", "alt_m", "east_m", "north_m",
    "speed_mps", "course_deg", "fix_quality", "sats", "hdop", "diff_age_s",
    "ntrip", "rtcm_bytes", "gga_up", "imu_status",
]

# Top-level keys exposed to the optional MCP section filter.
STATUS_FIELDS = (
    "t_wall", "uptime_s", "mode", "heading_deg", "heading_source", "imu",
    "position", "motion", "ntrip", "serial", "datum", "topics", "service",
)


def _num(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _wrap360(degrees: float) -> float:
    return degrees % 360.0


def quaternion_to_rpy(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    """Roll, pitch, yaw in radians from a unit-ish quaternion."""
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    pitch = math.asin(max(-1.0, min(1.0, sinp)))

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return roll, pitch, yaw


class Datum:
    """WGS84 datum for the local east/north display.

    A fixed origin (from the localization config or the ``origin`` option)
    keeps dashboard coordinates aligned with the map. Otherwise the first
    valid fix becomes the origin and is upgraded once an RTK-fixed solution
    arrives.
    """

    def __init__(self, lat0: Optional[float] = None, lon0: Optional[float] = None,
                 fixed: bool = False, source: str = "first fix") -> None:
        self.lock = threading.Lock()
        self.lat0 = lat0
        self.lon0 = lon0
        self.quality: Optional[int] = None
        self.fixed = fixed and lat0 is not None and lon0 is not None
        self.source = source if self.fixed else "first fix"

    def update(self, lat: Optional[float], lon: Optional[float],
               quality: Optional[int]) -> None:
        if lat is None or lon is None or quality in (None, 0):
            return
        with self.lock:
            if self.fixed:
                return
            if self.lat0 is None or (quality >= 4 and (self.quality or 0) < 4):
                self.lat0 = lat
                self.lon0 = lon
                self.quality = quality
                self.source = "RTK fixed" if quality >= 4 else "first fix"

    def to_enu(self, lat: Optional[float],
               lon: Optional[float]) -> Optional[tuple[float, float]]:
        with self.lock:
            lat0, lon0 = self.lat0, self.lon0
        if lat is None or lon is None or lat0 is None or lon0 is None:
            return None
        # Local tangent plane on the WGS84 ellipsoid.
        a = 6378137.0
        f = 1.0 / 298.257223563
        e2 = f * (2.0 - f)
        sin_lat = math.sin(math.radians(lat0))
        w = math.sqrt(1.0 - e2 * sin_lat * sin_lat)
        meridional = a * (1.0 - e2) / (w ** 3)
        prime_vertical = a / w
        east = math.radians(lon - lon0) * prime_vertical * math.cos(math.radians(lat0))
        north = math.radians(lat - lat0) * meridional
        return east, north

    def as_dict(self) -> dict:
        with self.lock:
            return {
                "lat0": self.lat0,
                "lon0": self.lon0,
                "quality": self.quality,
                "source": self.source,
            }


class RosState:
    """Latest samples from the stack; callbacks only touch this object."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.rtk: dict = {}
        self.rtk_mono: Optional[float] = None
        self.fix: dict = {}
        self.fix_mono: Optional[float] = None
        self.velocity: dict = {}
        self.velocity_mono: Optional[float] = None
        self.imu: dict = {}
        self.imu_mono: Optional[float] = None
        self.imu_status: dict = {}
        self.imu_status_mono: Optional[float] = None
        self.mag: Optional[tuple[float, float, float]] = None
        self.mag_mono: Optional[float] = None
        self.counts = {
            "rtk": 0, "fix": 0, "velocity": 0, "imu": 0, "imu_status": 0, "mag": 0,
        }

    @staticmethod
    def _age(now: float, stamp: Optional[float]) -> Optional[float]:
        return None if stamp is None else now - stamp

    def on_rtk_status(self, data: dict, mono: Optional[float] = None) -> None:
        if not isinstance(data, dict):
            return
        with self.lock:
            self.rtk = data
            self.rtk_mono = time.monotonic() if mono is None else mono
            self.counts["rtk"] += 1

    def on_fix(self, lat, lon, alt, status, mono: Optional[float] = None) -> None:
        with self.lock:
            self.fix = {
                "lat": _num(lat),
                "lon": _num(lon),
                "alt": _num(alt),
                "status": _int(status),
            }
            self.fix_mono = time.monotonic() if mono is None else mono
            self.counts["fix"] += 1

    def on_velocity(self, east, north, up, frame="",
                    mono: Optional[float] = None) -> None:
        with self.lock:
            self.velocity = {
                "east": _num(east),
                "north": _num(north),
                "up": _num(up),
                "frame": frame,
            }
            self.velocity_mono = time.monotonic() if mono is None else mono
            self.counts["velocity"] += 1

    def on_imu(self, roll_deg, pitch_deg, yaw_deg, gz_dps, ax, ay, az,
               mono: Optional[float] = None) -> None:
        with self.lock:
            self.imu = {
                "roll_deg": _num(roll_deg),
                "pitch_deg": _num(pitch_deg),
                "yaw_deg": _num(yaw_deg),
                "gz_dps": _num(gz_dps),
                "ax": _num(ax),
                "ay": _num(ay),
                "az": _num(az),
            }
            self.imu_mono = time.monotonic() if mono is None else mono
            self.counts["imu"] += 1

    def on_imu_status(self, data: dict, mono: Optional[float] = None) -> None:
        if not isinstance(data, dict):
            return
        with self.lock:
            self.imu_status = data
            self.imu_status_mono = time.monotonic() if mono is None else mono
            self.counts["imu_status"] += 1

    def on_mag(self, x, y, z, mono: Optional[float] = None) -> None:
        x, y, z = _num(x), _num(y), _num(z)
        if x is None or y is None or z is None:
            return
        with self.lock:
            self.mag = (x, y, z)
            self.mag_mono = time.monotonic() if mono is None else mono
            self.counts["mag"] += 1

    def snapshot(self, now: Optional[float] = None) -> dict:
        now = time.monotonic() if now is None else now
        with self.lock:
            return {
                "rtk": dict(self.rtk),
                "rtk_age": self._age(now, self.rtk_mono),
                "fix": dict(self.fix),
                "fix_age": self._age(now, self.fix_mono),
                "velocity": dict(self.velocity),
                "velocity_age": self._age(now, self.velocity_mono),
                "imu": dict(self.imu),
                "imu_age": self._age(now, self.imu_mono),
                "imu_status": dict(self.imu_status),
                "imu_status_age": self._age(now, self.imu_status_mono),
                "mag": self.mag,
                "mag_age": self._age(now, self.mag_mono),
                "counts": dict(self.counts),
            }


def build_status(state: RosState, datum: Datum, yaw_sign: float, yaw_offset: float,
                 t0: float, *, gnss_timeout_s: float = DEFAULT_GNSS_TIMEOUT_S,
                 imu_timeout_s: float = DEFAULT_IMU_TIMEOUT_S,
                 now: Optional[float] = None,
                 wall: Optional[float] = None) -> dict:
    now = time.monotonic() if now is None else now
    wall = time.time() if wall is None else wall
    snap = state.snapshot(now=now)
    rtk = snap["rtk"]
    fix = snap["fix"]
    velocity = snap["velocity"]
    imu = snap["imu"]
    imu_status = snap["imu_status"]

    rtk_host_age = snap["rtk_age"]
    rtk_usable = bool(rtk) and (
        rtk_host_age is None or rtk_host_age < gnss_timeout_s)
    fix_usable = bool(fix) and snap["fix_age"] is not None and \
        snap["fix_age"] < gnss_timeout_s

    lat = _num(rtk.get("lat")) if rtk_usable else None
    lon = _num(rtk.get("lon")) if rtk_usable else None
    alt = _num(rtk.get("alt_m")) if rtk_usable else None
    if lat is None or lon is None:
        lat = fix.get("lat") if fix_usable else None
        lon = fix.get("lon") if fix_usable else None
        alt = fix.get("alt") if fix_usable else None

    if rtk_usable:
        quality = _int(rtk.get("receiver_quality"))
        sats = _int(rtk.get("sats")) or _int(rtk.get("satellites"))
        hdop = _num(rtk.get("hdop"))
        diff_age = _num(rtk.get("diff_age_s"))
        receiver_age = _num(rtk.get("fix_age_s"))
        valid = bool(rtk.get("valid", quality not in (None, 0)))
        age = max(value for value in (receiver_age or 0.0, rtk_host_age or 0.0))
    else:
        quality = _int(fix.get("status")) if fix_usable else None
        if quality is not None and quality < 0:
            quality = 0
        sats, hdop, diff_age = None, None, None
        receiver_age = None
        valid = bool(fix_usable and quality not in (None, 0))
        age = snap["fix_age"] if fix_usable else None

    datum.update(lat if valid else None, lon if valid else None, quality)
    enu = datum.to_enu(lat, lon) if valid else None

    speed = _num(rtk.get("speed_mps")) if rtk_usable else None
    course = _num(rtk.get("course_deg")) if rtk_usable else None
    if speed is None and snap["velocity_age"] is not None and \
            snap["velocity_age"] < gnss_timeout_s:
        east, north = _num(velocity.get("east")), _num(velocity.get("north"))
        if east is not None and north is not None:
            speed = math.hypot(east, north)
            course = _wrap360(math.degrees(math.atan2(east, north)))
    if speed is not None and speed <= 0.2:
        course = None

    imu_age = snap["imu_age"]
    heading = None
    yaw_enu = _num(imu.get("yaw_deg"))
    if yaw_enu is not None and imu_age is not None and imu_age <= imu_timeout_s:
        yaw_enu = _wrap360(yaw_sign * yaw_enu + yaw_offset)
        heading = _wrap360(90.0 - yaw_enu)

    connected = imu_status.get("serial_connected")
    if connected is False:
        imu_state = "closed"
    elif imu_age is not None and imu_age <= imu_timeout_s:
        imu_state = "open"
    elif connected is True:
        imu_state = "open (no data)"
    else:
        imu_state = "no data"

    mag_norm = None
    if snap["mag"] is not None:
        mag_norm = math.sqrt(sum(component * component for component in snap["mag"]))

    ntrip = rtk.get("ntrip") if isinstance(rtk.get("ntrip"), dict) else {}

    return {
        "t_wall": round(wall, 3),
        "uptime_s": round(now - t0, 1),
        "mode": "ros",
        "heading_deg": None if heading is None else round(heading, 1),
        "heading_source": "imu_mag",
        "imu": {
            "status": imu_state,
            "frames": _int((imu_status.get("counts") or {}).get("imu")),
            "roll_deg": None if imu.get("roll_deg") is None else round(imu["roll_deg"], 2),
            "pitch_deg": None if imu.get("pitch_deg") is None else round(imu["pitch_deg"], 2),
            "yaw_enu_deg": None if yaw_enu is None else round(yaw_enu, 2),
            "gz_dps": None if imu.get("gz_dps") is None else round(imu["gz_dps"], 2),
            "mag_norm": None if mag_norm is None else round(mag_norm, 1),
            "age_s": None if imu_age is None else round(imu_age, 2),
        },
        "position": {
            "lat": lat,
            "lon": lon,
            "alt_m": alt,
            "east_m": None if enu is None else round(enu[0], 2),
            "north_m": None if enu is None else round(enu[1], 2),
            "fix_quality": quality,
            "fix_name": FIX_NAMES.get(quality, "unknown") if quality is not None else None,
            "sats": sats,
            "hdop": hdop,
            "diff_age_s": diff_age,
            "age_s": None if age is None else round(age, 2),
            "valid": valid,
            "state": rtk.get("state"),
            "rtk_fixed": rtk.get("rtk_fixed"),
        },
        "motion": {
            "speed_mps": None if speed is None else round(speed, 3),
            "course_deg": None if course is None else round(course, 1),
        },
        "ntrip": {
            "state": ntrip.get("state", "unknown"),
            "rtcm_bytes": _int(ntrip.get("rtcm_bytes")) or 0,
            "gga_uploaded": _int(ntrip.get("gga_uploaded")) or 0,
            "connects": _int(ntrip.get("connects")) or 0,
            "last_error": ntrip.get("last_error", ""),
        },
        "serial": {
            "rtk": rtk.get("serial_status") or ("open" if rtk_usable else "no data"),
            "imu": imu_state,
        },
        "datum": datum.as_dict(),
        "topics": {
            "counts": snap["counts"],
            "rtk_age_s": None if rtk_host_age is None else round(rtk_host_age, 2),
            "imu_status_age_s": None
            if snap["imu_status_age"] is None
            else round(snap["imu_status_age"], 2),
        },
    }


def select_sections(status: dict, section: str) -> dict:
    """Return the requested comma-separated top-level fields.

    Empty returns the full snapshot. Unknown fields raise KeyError so an MCP
    caller gets an explicit error instead of a silently reduced snapshot.
    """
    if not isinstance(section, str):
        raise KeyError("section must be a string")
    names = [name.strip() for name in section.split(",") if name.strip()]
    if not names:
        return status
    unknown = [name for name in names if name not in status]
    if unknown:
        raise KeyError(
            "unknown section field(s): " + ", ".join(unknown)
            + "; available: " + ", ".join(status.keys())
        )
    return {name: status[name] for name in names}


def format_line(status: dict) -> str:
    heading = status["heading_deg"]
    pos = status["position"]
    motion = status["motion"]
    imu = status["imu"]
    heading_text = "--" if heading is None else f"{heading:5.1f}"
    if pos["lat"] is None:
        pos_text = "--"
        alt_text = "--"
    else:
        pos_text = f"{pos['lat']:.7f},{pos['lon']:.7f}"
        alt_text = "--" if pos["alt_m"] is None else f"{pos['alt_m']:.1f}"
    local_text = (
        "--"
        if pos["east_m"] is None
        else f"{pos['east_m']:+.1f},{pos['north_m']:+.1f}"
    )
    speed_text = "--" if motion["speed_mps"] is None else f"{motion['speed_mps']:.2f}"
    course_text = "--" if motion["course_deg"] is None else f"{motion['course_deg']:.1f}"
    fix_text = "--" if pos["fix_quality"] is None else f"{pos['fix_quality']}({pos['fix_name']})"
    sats = "--" if pos["sats"] is None else str(pos["sats"])
    hdop = "--" if pos["hdop"] is None else f"{pos['hdop']:.1f}"
    mag = "--" if imu["mag_norm"] is None else f"{imu['mag_norm']:.0f}"
    return (
        f"t={status['uptime_s']:7.1f}s heading={heading_text}° pos={pos_text} alt={alt_text}m "
        f"local=({local_text})m speed={speed_text}m/s course={course_text}° "
        f"fix={fix_text} sats={sats} hdop={hdop} ntrip={status['ntrip']['state']} "
        f"mag={mag} imu={imu['status']}"
    )


def csv_row(status: dict, mono: Optional[float] = None) -> list:
    mono = time.monotonic() if mono is None else mono
    return [
        status["t_wall"], f"{mono:.3f}", status["heading_deg"],
        status["imu"]["yaw_enu_deg"], status["imu"]["roll_deg"],
        status["imu"]["pitch_deg"],
        status["imu"]["mag_norm"], status["imu"]["gz_dps"],
        status["position"]["lat"], status["position"]["lon"],
        status["position"]["alt_m"],
        status["position"]["east_m"], status["position"]["north_m"],
        status["motion"]["speed_mps"], status["motion"]["course_deg"],
        status["position"]["fix_quality"], status["position"]["sats"],
        status["position"]["hdop"], status["position"]["diff_age_s"],
        status["ntrip"]["state"], status["ntrip"]["rtcm_bytes"],
        status["ntrip"]["gga_uploaded"], status["imu"]["status"],
    ]


def load_origin(path: Optional[Path]) -> Optional[tuple[float, float]]:
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    origin = data.get("origin") if isinstance(data, dict) else None
    if not isinstance(origin, dict):
        reference = data.get("coordinate_reference") if isinstance(data, dict) else None
        origin = reference.get("origin_wgs84") if isinstance(reference, dict) else None
    if not isinstance(origin, dict):
        return None
    lat = _num(origin.get("latitude"))
    lon = _num(origin.get("longitude"))
    if lat is None or lon is None:
        return None
    return lat, lon


def parse_origin(text: str) -> Optional[tuple[float, float]]:
    try:
        lat_text, lon_text = text.split(",", 1)
        lat, lon = float(lat_text), float(lon_text)
    except (ValueError, AttributeError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    return lat, lon
