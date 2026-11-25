specVersion: 1
description: Read-only rover status from the running stack's ROS topics. Opens no serial port, sends no NTRIP corrections and publishes only state_topic.
properties:
  topic_remap:
    type: object
    description: Absolute ROS topics that skip Atlas resolution. Roles rtk_status, fix, velocity, imu, imu_status, magnetic_raw.
  topics:
    type: object
    description: Fallback absolute ROS topics used when Atlas resolution is disabled or fails. Same roles as topic_remap.
  provider_ids:
    type: object
    description: Provider instance per role for Atlas.find_capability. Set imu to wit_imu to avoid selecting the lidar's IMU stream.
  resolve_providers:
    type: boolean
    default: true
    description: Resolve the six input endpoints through Atlas; roles without a provider fall back to topics.
  origin:
    type: string
    default: ""
    description: Fixed local datum as LAT,LON. Overrides origin_config.
  origin_config:
    type: string
    default: ""
    description: JSON file with origin or coordinate_reference.origin_wgs84. Empty or none disables it; the first valid fix then becomes the datum.
  imu_yaw_sign:
    type: integer
    enum: [1, -1]
    default: 1
    description: Sign applied to WIT yaw, same convention as the standalone tools.
  imu_yaw_offset_deg:
    type: number
    default: 0.0
    description: Mounting offset added to ENU yaw.
  sample_hz:
    type: number
    default: 1.0
    description: Snapshot, state publication and CSV/JSON recording rate, (0,10].
  gnss_timeout_s:
    type: number
    default: 3.0
    description: GNSS sample and velocity freshness window.
  imu_timeout_s:
    type: number
    default: 1.5
    description: IMU freshness window for heading and link state.
  state_topic:
    type: string
    default: /robonix/service/rover_status/state
    description: 1 Hz std_msgs/String JSON snapshot published by the service.
  http_enabled:
    type: boolean
    default: true
    description: Serve the shared dashboard and /status, /text endpoints.
  http_bind:
    type: string
    default: 127.0.0.1
    description: Dashboard bind address; loopback by default because the endpoints have no authentication.
  http_port:
    type: integer
    default: 50109
    description: Dashboard port, 0 selects an ephemeral port.
  record_enabled:
    type: boolean
    default: true
    description: Write a daily CSV and an atomic JSON snapshot. Use only one recorder while the standalone tool still runs.
  record_dir:
    type: string
    default: ~/.robonix/rover_status
    description: Owned recording directory.
  record_retention_days:
    type: integer
    default: 14
    description: Delete rover_status_*.csv older than this many days; 0 keeps everything.
