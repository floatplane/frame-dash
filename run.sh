#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Frame Dash..."

# Export config as JSON for the Python process
CONFIG_PATH=/data/options.json

# The supervisor token is automatically available in this env var
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"
export FRAME_DASH_CONFIG="${CONFIG_PATH}"
export FRAME_DASH_DATA="/data"

# Activate venv
source /opt/frame-dash-venv/bin/activate

# Run the main application
python -m frame_dash.main
