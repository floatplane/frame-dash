# Frame Dash

A Home Assistant add-on that renders a calm, minimal family dashboard and serves it to a [TRMNL X](https://shop.trmnl.com/products/trmnl-x) e-ink display.

Inspired by [Timeframe](https://github.com/joelhawksley/timeframe) by Joel Hawksley.

## Philosophy

The goal is **not** to replicate a Home Assistant dashboard. Instead, Frame Dash follows the principle of **ambient awareness**: show only what matters right now, and let silence mean everything is fine.

- **Calendar**: Today's events and tomorrow's events
- **Home status**: Only surfaces _problems_ — unlocked doors, lights left on, unusual energy usage
- **Climate**: Current indoor/outdoor conditions
- **Alerts**: Laundry done, garage open, anything that needs attention

If the status area is empty, your home is healthy.

## Architecture

```
┌─────────────────────────────────────────────┐
│  Home Assistant (Supervisor)                │
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │  Frame Dash Add-on (Docker)           │  │
│  │                                       │  │
│  │  1. Fetch data (HA REST API)          │  │
│  │     - Calendar events                 │  │
│  │     - Entity states (doors, lights,   │  │
│  │       climate, energy, sensors)       │  │
│  │                                       │  │
│  │  2. Render HTML → grayscale PNG       │  │
│  │     - Jinja2 template                 │  │
│  │     - Playwright/Chromium headless    │  │
│  │     - Output at device resolution     │  │
│  │                                       │  │
│  │  3. Serve via BYOS HTTP server        │  │
│  │     - /api/setup, /api/display, ...   │  │
│  │     - Device polls and displays it    │  │
│  └───────────────────────────────────────┘  │
│                        ▲                    │
│                        │ LAN poll           │
│                  TRMNL X (e-ink)            │
└─────────────────────────────────────────────┘
```

## Setup

### 1. Add the repository

In Home Assistant, go to **Settings → Apps → App store → ⋮ → Repositories** and add this repository URL. If the repository doesn't appear after adding, refresh your browser; if it still doesn't show, check **Settings → System → Logs → Supervisor** for errors.

### 2. Install and configure

Install "Frame Dash" from the app store, then configure it:

```yaml
# Home Assistant long-lived access token
# (Settings → People → [your user] → Security → Long-Lived Access Tokens)
# Note: When running as an add-on, SUPERVISOR_TOKEN is used automatically.
# This is only needed for standalone/development use.
ha_token: ""

# How often to re-render the dashboard, in seconds (300 = 5 minutes)
update_interval: 300

# Calendar entity IDs to display
calendars:
  - calendar.family
  - calendar.work

# Entities to monitor for "attention needed" status
# These are only shown when they're in a non-default state
watched_entities:
  doors:
    - lock.front_door
    - lock.back_door
    - binary_sensor.garage_door
  lights:
    - light.living_room
    - light.kitchen
  climate:
    - climate.main_floor
    - sensor.outdoor_temperature
  alerts:
    - binary_sensor.washer
    - binary_sensor.dryer

# Weather
show_weather: true
weather_entity: "weather.home"

# E-ink display (TRMNL X)
eink_width: 1872
eink_height: 1404
eink_port: 2300
eink_refresh_rate: 300  # how often the device polls, in seconds
```

### 3. TRMNL X setup

Frame Dash serves the dashboard to the TRMNL X over its "BYOS" (build-your-own-server) protocol.

1. Start the add-on. It serves the BYOS API at `http://<home-assistant-ip>:2300`.
2. Point the TRMNL X at that base URL as its server. The device registers
   itself (`/api/setup`), then polls `/api/display` every `eink_refresh_rate`
   seconds and displays the returned grayscale image.

The layout (`eink.html.j2`) is landscape, high-contrast black-on-white, with no clock and a small "Updated HH:MM" footer — an infrequently-refreshed e-ink panel showing a stale clock would be worse than none.

## Development

### Running standalone (outside HA)

```bash
# Clone and install
git clone https://github.com/floatplane/frame-dash.git
cd frame-dash

# Install dependencies
uv sync
uv run playwright install chromium

# Copy and edit config
cp local.example.yaml local.yaml
# Edit local.yaml with your HA URL and token

# Run once (renders and serves)
uv run python -m frame_dash.main --once

# Run as daemon
uv run python -m frame_dash.main
```

### Local preview (no HA or device needed)

```bash
uv run python preview.py          # renders preview.html, opens in browser
uv run python preview.py --png    # renders grayscale preview.png at device resolution
```

## Project Structure

```
frame-dash/
├── config.yaml          # HA add-on metadata
├── Dockerfile           # Add-on container build
├── run.sh               # Add-on entry point
├── frame_dash/
│   ├── __init__.py
│   ├── main.py          # Main loop: fetch → render → serve
│   ├── config.py        # Configuration loading
│   ├── ha_client.py     # Home Assistant REST API client
│   ├── renderer.py      # HTML → grayscale PNG rendering via Playwright
│   ├── byos.py          # BYOS server for the TRMNL X e-ink device
│   └── templates/
│       ├── eink.html.j2       # E-ink dashboard template
│       └── static/
│           └── eink.css       # E-ink grayscale styles
├── pyproject.toml
├── uv.lock
├── preview.py
├── local.example.yaml
└── README.md
```

## License

MIT
