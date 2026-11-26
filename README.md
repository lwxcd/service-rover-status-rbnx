# rover_status service

Read-only robonix service that reports the rover's GNSS/RTK, IMU and link
state. It is the in-stack successor to `scripts/rtk_imu/rover_status_ros.py`;
the standalone tool stays available as an out-of-stack fallback.

## Interfaces

- gRPC + MCP `robonix/service/rover_status/status`: request `section` (empty =
  full snapshot, or comma-separated top-level fields), response `ok`,
  `status_json`, `text`.
- ROS `{state_topic}` (default `/robonix/service/rover_status/state`):
  1 Hz `std_msgs/String` JSON snapshot for in-stack consumers.
- HTTP (default `127.0.0.1:50109`): `/` dashboard, `/status` JSON, `/text`
  one line. No authentication; it stays on loopback. In the standard
  deployment robonix-client runs on the same host and reads it directly;
  for a remote viewer, forward the port over SSH instead of binding it
  publicly.
- Records (default `~/.robonix/rover_status`): daily
  `rover_status_YYYYMMDD.csv` (23 columns, same as the standalone tool) and an
  atomic `rover_status.json`, pruned after `record_retention_days`.

The service opens no serial port, sends no NTRIP corrections and never
publishes a command topic.

## Provider resolution

Each of the six input roles is resolved independently through
`ATLAS.find_capability` (best-effort, never fatal):

| role | contract | default topic |
|---|---|---|
| rtk_status | `robonix/primitive/gnss/rtk_status` | `/gps/rtk_status` |
| fix | `robonix/primitive/gnss/fix` | `/gps/fix` |
| velocity | `robonix/primitive/gnss/velocity` | `/gps/velocity` |
| imu | `robonix/primitive/imu/imu` | `/wit_10axis/data` |
| imu_status | `robonix/primitive/imu/status` | `/wit_10axis/status` |
| magnetic_raw | `robonix/primitive/imu/magnetic_raw` | `/wit_10axis/magnetic_raw` |

Set `provider_ids.imu`/`imu_status`/`magnetic_raw` to `wit_imu`: the lidar
primitive also declares the standard IMU contract. `topic_remap` skips Atlas
for a role. Resolution outcome per role appears in the snapshot under
`service.topics`.

## Configuration

See `config.spec`. The manifest entry passes deployment-specific values
(origin config and provider ids). The origin keeps dashboard ENU aligned with
the outdoor map; without it the first valid fix becomes the datum and is
upgraded on the first RTK-fixed solution.

## Build and test

```bash
# On the robot (rbnx on PATH):
bash scripts/build.sh

# Pure-Python tests, no ROS needed:
uv run --no-project --with pytest pytest -q tests
```

## Deployment note

In the current single-stack deployment this service is the primary telemetry
path: robonix-client runs on the robot host and its Perception page reads the
loopback dashboard directly. The standalone `scripts/rtk_imu/rover_status_ros.py`
tool (HTTP 8080) still runs as an out-of-stack fallback and keeps its own
recordings under `~/rtk_imu_logs`; this service records under
`~/.robonix/rover_status`. Keep the two recorders distinct and revisit whether
the fallback should stay enabled once the service has run through the field
season.
