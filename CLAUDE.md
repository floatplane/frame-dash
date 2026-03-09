# CLAUDE.md — Frame Dash

## What is this?

Frame Dash is a Home Assistant add-on that renders a calm, minimal family dashboard as a PNG and pushes it to a Samsung The Frame TV via the art mode API. It runs as a Docker container inside HA OS.

Inspired by [Timeframe](https://github.com/joelhawksley/timeframe) by Joel Hawksley ([blog post](https://hawksley.org/2026/02/17/timeframe.html)). The core philosophy borrowed from that project: **only show what needs attention right now; silence means the house is healthy.**

## Architecture

The main loop in `frame_dash/main.py` runs a cycle every N seconds (default 300):

1. **Fetch** — `ha_client.py` calls the HA REST API for calendar events, entity states, and weather
2. **Render** — `renderer.py` uses Jinja2 to fill an HTML template, then Playwright (headless Chromium) screenshots it to a PNG at the TV's native resolution
3. **Push** — `samsung.py` uploads the PNG to the Frame TV via the `samsungtvws` library's art mode API, selects it as current art, and deletes the previous image to avoid filling TV storage

When running as an HA add-on, the `SUPERVISOR_TOKEN` env var provides API access automatically. For standalone dev, a long-lived access token is configured in `config.yaml`.

## Project structure

```
frame-dash/
├── config.yaml              # HA add-on metadata (name, slug, options schema)
├── build.yaml               # Base images per architecture (Debian bookworm)
├── Dockerfile               # Add-on container — Debian-based for Playwright compat
├── run.sh                   # Add-on entry point (bashio wrapper → Python)
├── requirements.txt         # Python deps: playwright, samsungtvws, jinja2, httpx, pyyaml, pillow
├── config.example.yaml      # Standalone dev config template
├── repository.yaml          # HA add-on repo metadata
├── translations/en.yaml     # Config option descriptions for HA UI
├── frame_dash/
│   ├── __init__.py
│   ├── main.py              # CLI entry point + main loop
│   ├── config.py            # Config loading (HA add-on JSON or standalone YAML)
│   ├── ha_client.py         # HA REST API client (calendars, states, weather)
│   ├── renderer.py          # Jinja2 + Playwright HTML→PNG rendering
│   ├── samsung.py           # Samsung Frame TV art mode push via samsungtvws
│   └── templates/
│       ├── base.html.j2     # Main dashboard template
│       └── static/
│           └── style.css    # Dashboard styles (light/dark themes)
└── README.md
```

## Key dependencies

- **playwright** — headless Chromium for HTML→PNG. Requires Debian (not Alpine) due to glibc. The Dockerfile installs it with `playwright install --with-deps chromium`.
- **samsungtvws** — Python wrapper for Samsung TV WebSocket API. Art mode methods: `upload()`, `select_image()`, `delete()`, `get_artmode()`, `set_artmode()`. Auth token persisted to `/data/samsung-tv-token.txt`.
- **httpx** — HTTP client for HA REST API calls.
- **jinja2** — HTML template rendering with custom filters for time formatting, weather icons, status icons.

## Running locally for development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp config.example.yaml config.yaml
# Edit config.yaml with your HA URL, token, TV IP

# Render only (no TV push) — saves dashboard.png locally
python -m frame_dash.main --render-only --once --output dashboard.png

# Full cycle
python -m frame_dash.main --once
```

## Design decisions to know about

- **HTML rendering, not canvas/SVG** — we render a full HTML page to PNG via Playwright. This means the dashboard layout is just CSS. Heavyweight but extremely flexible.
- **Single-image slot on TV** — each push cycle uploads a new image, selects it, deletes the old one. This prevents the TV's ~4GB internal storage from filling up. The `_previous_image_id` is tracked in memory (lost on restart, but cleanup logic handles orphans).
- **Attention-only status** — doors/locks/lights are only shown when they're in a "problem" state (unlocked, open, on). The `EntityState.is_problem` property in `ha_client.py` defines this logic per domain.
- **Climate always shown** — entities in the `climate` watched list are always displayed, not just when problematic.
- **Timeframe-style sensors** — supports HA template sensors using the `"icon,Label"` CSV format from Timeframe. Any `sensor.timeframe_*` entity with this format gets rendered as a status item.

## Open tasks and known gaps

### Must do before first real use
- [ ] **Determine Brian's Samsung Frame model year** — art mode API works reliably on 2020-2021 models. 2022+ may have restrictions. Test with `tv.art().supported()`.
- [ ] **Fill in actual HA entity IDs** — the config.example.yaml has placeholder entities. Need real lock, light, climate, calendar entity IDs from Brian's HA instance.
- [ ] **Test the samsungtvws upload→select→delete cycle** — the `samsung.py` cleanup logic needs real-device testing. The `upload()` return value (image ID) format may vary by TV model.
- [ ] **Font loading in Playwright** — the Dockerfile installs `fonts-inter` but the CSS falls back to system-ui. Verify Inter actually renders in the headless Chromium screenshot. May need to embed fonts via @font-face with base64.

### Should do
- [ ] **HA webhook for instant updates** — instead of only polling every N seconds, register an HA automation that hits a webhook when watched entity states change (door unlocks, laundry finishes). The add-on would need to expose an HTTP endpoint.
- [ ] **Graceful degradation** — if HA API is unreachable, render a cached version with a stale-data indicator. If the TV is off/unreachable, skip push and don't error.
- [ ] **Image diffing** — don't push to TV if the rendered PNG is identical to the last one (hash comparison). Reduces unnecessary TV API calls.
- [ ] **Multi-day calendar view** — current template shows today + tomorrow. Could show the next 3-5 days in a more compact format.
- [ ] **Energy usage display** — Brian has solar (Enphase) and tracks energy. Could add a simple energy production/consumption indicator to the status area.
- [ ] **Sonos now-playing** — Timeframe shows current Sonos track. Brian has a Sonos setup. Could add a `media_player.*` entity watcher.

### Nice to have
- [ ] **Web preview endpoint** — serve the dashboard HTML on a local port so you can preview it in a browser during development without running Playwright.
- [ ] **Template hot-reload** — watch the templates directory and re-render on change during development.
- [ ] **Alternative to Playwright** — Playwright + Chromium adds ~500MB to the Docker image. Could explore `wkhtmltoimage` or `weasyprint` for lighter-weight HTML→PNG, but they have worse CSS support.
- [ ] **Multiple display support** — different layouts for different TVs/displays (e.g., a bedroom Frame showing just tomorrow's early events and weather).
- [ ] **Dark mode auto-switch** — switch between light/dark theme based on time of day or HA sun entity.

## Brian's home context

- Lives in Santa Fe, NM
- Runs Home Assistant with Lutron Caséta (Smart Bridge 2), Navien hydronic heating, Enphase solar
- Has a Sonos audio system
- Has a `~/projects/casadeloso` directory for HA-related projects (Python, uv-managed)
- The Frame TV model year is unknown — needs to be checked

## Style and conventions

- Python 3.11+ (type hints, `X | Y` union syntax)
- Dataclasses over dicts for structured data
- `httpx` over `requests` (async-ready, better API)
- Logging via stdlib `logging`, not print statements
- HTML templates in Jinja2 with `.html.j2` extension
- CSS uses custom properties (`--bg`, `--fg`, etc.) for theming
