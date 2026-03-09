#!/bin/bash
set -e

export FRAME_DASH_CONFIG="/data/options.json"
export FRAME_DASH_DATA="/data"

exec /opt/frame-dash/.venv/bin/python -m frame_dash.main
