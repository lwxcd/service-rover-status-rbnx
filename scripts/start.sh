#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"
mkdir -p "$PKG/rbnx-build/ros_logs" "$PKG/rbnx-build/ros_home"
export ROS_LOG_DIR="$PKG/rbnx-build/ros_logs" ROS_HOME="$PKG/rbnx-build/ros_home"
export ROBONIX_CAPABILITY_ID="${ROBONIX_CAPABILITY_ID:-rover_status}"
# The stack runs zenoh; defaults keep a manual start working too.
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
set +u
if [[ -n "${ROS_SETUP:-}" ]]; then
    source "$ROS_SETUP"
elif [[ -f "/opt/ros/${ROS_DISTRO:-humble}/setup.bash" ]]; then
    source "/opt/ros/${ROS_DISTRO:-humble}/setup.bash"
elif [[ -z "${AMENT_PREFIX_PATH:-}" ]]; then
    echo "Source ROS 2 or set ROS_SETUP to its setup.bash" >&2
    exit 1
fi
set -u
export PYTHONPATH="$PKG:$PKG/rbnx-build/codegen/proto_gen:$PKG/rbnx-build/codegen/robonix_mcp_types:$(rbnx path robonix-api):${PYTHONPATH:-}"
exec "${ROVER_STATUS_PYTHON:-/usr/bin/python3}" -u -m rover_status.main
