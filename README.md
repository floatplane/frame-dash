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

In Home Assistant, go to **Settings → Apps → App store → ⋮ → Repositories** and add this repository URL. If the repository doesn't appear after adding, refresh your browser; if it still doesn't show, check **Settings → System → Logs → Supervisor** for errors.

### 2. Install and configure

Install "Frame Dash" from the app store, then configure it:

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

# E-ink display (TRMNL X) — optional
eink_enabled: false
eink_width: 1872
eink_height: 1404
eink_port: 2300
eink_refresh_rate: 300  # how often the device polls, in seconds
```

### 3. Samsung Frame TV setup

1. Set a **static IP** for your Frame TV in your router
2. On first run, the TV will show a permission prompt — **accept it**
3. The add-on will upload a dashboard image and set it as the current art

### 4. Verify your TV model

The art mode API works reliably with 2020-2021 Frame TVs. Support for 2022+ models varies. Test with:

```bash
uvx --from samsungtvws python -c "
from samsungtvws import SamsungTVWS
tv = SamsungTVWS('YOUR_TV_IP')
print(tv.art().supported())
"
```

### 5. E-ink display (TRMNL X) — optional

Frame Dash can also serve a grayscale version of the dashboard to a
[TRMNL X](https://shop.trmnl.com/products/trmnl-x) (or compatible) e-ink panel
over its "BYOS" (build-your-own-server) protocol — useful for a calmer,
always-on display on a dresser or desk.

1. Set `eink_enabled: true` and restart the add-on.
2. The add-on serves the BYOS API at `http://<home-assistant-ip>:2300`.
3. Point the TRMNL X at that base URL as its server. The device registers
   itself (`/api/setup`), then polls `/api/display` every `eink_refresh_rate`
   seconds and displays the returned grayscale image.

The e-ink layout is a separate, simplified template (`eink.html.j2`): landscape,
high-contrast black-on-white, no clock, with a small "Updated HH:MM" footer.

## Development

### Running standalone (outside HA)

```bash
# Clone and install
git clone https://github.com/YOUR_USER/frame-dash.git
cd frame-dash

# Install dependencies
uv sync
uv run playwright install chromium

# Copy and edit config
cp local.example.yaml local.yaml
# Edit local.yaml with your HA URL, token, TV IP

# Run once (renders and pushes)
uv run python -m frame_dash.main --once

# Run as daemon
uv run python -m frame_dash.main
```

### Local preview (no HA or TV needed)

```bash
uv run python preview.py            # renders preview.html, opens in browser
uv run python preview.py --png      # renders preview.png at TV resolution via Playwright
uv run python preview.py --dark     # dark theme
uv run python preview.py --eink         # renders the e-ink layout (HTML)
uv run python preview.py --eink --png   # renders grayscale e-ink PNG at device resolution
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
│   ├── renderer.py      # HTML → PNG rendering via Playwright
│   ├── samsung.py       # Samsung Frame art mode push
│   ├── byos.py          # BYOS server for TRMNL X e-ink devices
│   └── templates/
│       ├── base.html.j2       # Main TV dashboard template
│       ├── eink.html.j2       # E-ink (TRMNL X) dashboard template
│       └── static/
│           ├── style.css      # TV styles
│           └── eink.css       # E-ink grayscale styles
├── pyproject.toml
├── uv.lock
├── preview.py
├── local.example.yaml
└── README.md
```

## License

MIT
