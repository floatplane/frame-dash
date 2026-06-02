# Frame Dash

A Home Assistant add-on that renders a calm, minimal family dashboard and pushes it to a [TRMNL X](https://shop.trmnl.com/products/trmnl-x) e-ink display via a TRMNL [Webhook Image](https://help.trmnl.com/en/articles/13213669-webhook-image) plugin.

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
│  │  3. POST PNG to TRMNL Webhook Image   │  │
│  └───────────────────────────────────────┘  │
│                        │                    │
└────────────────────────┼────────────────────┘
                         ▼
              TRMNL cloud (Webhook Image plugin)
                         │  device pulls on its
                         ▼  playlist schedule
                  TRMNL X (e-ink)
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

# How often to re-render and push, in seconds. TRMNL caps uploads at
# 12/hour, so keep this >= 300 (600 = 10 minutes).
update_interval: 600

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

# Private URL from your TRMNL "Webhook Image" plugin (see step 3)
eink_webhook_url: ""
```

### 3. TRMNL setup

Frame Dash pushes its rendered image to a TRMNL **Webhook Image** plugin, so it appears as one screen in your device's playlist.

1. In the TRMNL web app, go to **Plugins → Webhook Image → Add**. Copy the private webhook URL it generates.
2. Paste that URL into the add-on's `eink_webhook_url` option and start the add-on.
3. Add the Webhook Image plugin to your device's playlist. Frame Dash will POST a fresh image every `update_interval` seconds; the device shows it on its own refresh schedule.

The layout (`eink.html.j2`) is landscape, high-contrast black-on-white, with no clock and a small "Updated HH:MM" footer — an infrequently-refreshed e-ink panel showing a stale clock would be worse than none.

Because delivery is an outbound POST to TRMNL's cloud, the add-on needs no inbound ports and the device doesn't have to be on the same network.

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

# Run once (renders and pushes)
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
│   ├── main.py          # Main loop: fetch → render → push
│   ├── config.py        # Configuration loading
│   ├── ha_client.py     # Home Assistant REST API client
│   ├── renderer.py      # HTML → grayscale PNG rendering via Playwright
│   ├── webhook.py       # Pushes the PNG to the TRMNL Webhook Image plugin
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
