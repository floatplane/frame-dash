#!/usr/bin/with-contenv bashio

bashio::log.info "Starting Frame Dash..."

# Export config as JSON for the Python process
CONFIG_PATH=/data/options.json

# The supervisor token is automatically available in this env var
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"
export FRAME_DASH_CONFIG="${CONFIG_PATH}"
export FRAME_DASH_DATA="/data"

# Run the main application
exec /opt/frame-dash/.venv/bin/python -m frame_dash.main
