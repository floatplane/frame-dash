# Frame Dash

A Home Assistant add-on that renders a calm, minimal family dashboard and pushes it to a Samsung The Frame TV via Art Mode.

Inspired by [Timeframe](https://github.com/joelhawksley/timeframe) by Joel Hawksley.

## Philosophy

The goal is **not** to replicate a Home Assistant dashboard on your TV. Instead, Frame Dash follows the principle of **ambient awareness**: show only what matters right now, and let silence mean everything is fine.

- **Calendar**: Today's events and tomorrow's early events
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
│  │  2. Render HTML → PNG                 │  │
│  │     - Jinja2 templates               │  │
│  │     - Playwright/Chromium headless    │  │
│  │     - Output at TV native resolution  │  │
│  │                                       │  │
│  │  3. Push to Samsung Frame             │  │
│  │     - samsungtvws art mode API        │  │
│  │     - Upload PNG, select, cleanup     │  │
│  └───────────────────────────────────────┘  │
│                        │                    │
│                        ▼                    │
│              Samsung The Frame TV           │
│              (Art Mode / LAN)               │
└─────────────────────────────────────────────┘
```

## Setup

### 1. Add the repository

In Home Assistant, go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add this repository URL.

### 2. Install and configure

Install "Frame Dash" from the add-on store, then configure it:

```yaml
# Samsung Frame TV IP (set a static IP on your TV first)
samsung_tv_ip: "192.168.1.100"

# Home Assistant long-lived access token
# (Settings → People → [your user] → Security → Long-Lived Access Tokens)
# Note: When running as an add-on, SUPERVISOR_TOKEN is used automatically.
# This is only needed for standalone/development use.
ha_token: ""

# Update interval in seconds (300 = 5 minutes)
update_interval: 300

# TV resolution
tv_width: 3840
tv_height: 2160

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

# Display settings
theme: "light"  # "light" or "dark"
show_clock: true
show_weather: true
weather_entity: "weather.home"
```

### 3. Samsung Frame TV setup

1. Set a **static IP** for your Frame TV in your router
2. On first run, the TV will show a permission prompt — **accept it**
3. The add-on will upload a dashboard image and set it as the current art

### 4. Verify your TV model

The art mode API works reliably with 2020-2021 Frame TVs. Support for 2022+ models varies. Test with:

```bash
pip install samsungtvws
python -c "
from samsungtvws import SamsungTVWS
tv = SamsungTVWS('YOUR_TV_IP')
print(tv.art().supported())
"
```

## Development

### Running standalone (outside HA)

```bash
# Clone and install
git clone https://github.com/YOUR_USER/frame-dash.git
cd frame-dash/frame-dash

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Copy and edit config
cp config.example.yaml config.yaml
# Edit config.yaml with your settings

# Run once (renders and pushes)
python -m frame_dash.main --once

# Run as daemon
python -m frame_dash.main
```

### Running the renderer only (no TV push)

Useful for designing the dashboard layout:

```bash
python -m frame_dash.main --render-only --output dashboard.png
```

This saves the rendered PNG locally so you can iterate on the template.

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
│   ├── renderer.py      # HTML → PNG rendering via Playwright
│   ├── samsung.py       # Samsung Frame art mode push
│   └── templates/
│       ├── base.html.j2       # Main dashboard template
│       ├── components/
│       │   ├── clock.html.j2
│       │   ├── calendar.html.j2
│       │   ├── status.html.j2
│       │   └── weather.html.j2
│       └── static/
│           ├── style.css
│           └── fonts/
├── requirements.txt
├── config.example.yaml
└── README.md
```

## License

MIT
