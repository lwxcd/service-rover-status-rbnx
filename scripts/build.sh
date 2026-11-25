#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"
PY="${ROVER_STATUS_PYTHON:-/usr/bin/python3}"
command -v rbnx >/dev/null || { echo 'rbnx is required for contract generation' >&2; exit 2; }
rbnx validate "$PKG"
rbnx codegen -p "$PKG" --mcp --python "$PY"
"$PY" -m compileall -q rover_status
mkdir -p "$PKG/rbnx-build/data"
touch "$PKG/rbnx-build/.rbnx-built"
