# CLAUDE.md — Frame Dash

## What is this?

Frame Dash is a Home Assistant add-on that renders a calm, minimal family dashboard as a grayscale PNG and serves it to a TRMNL X e-ink display over the TRMNL "BYOS" (build-your-own-server) protocol. It runs as a Docker container inside HA OS.

Inspired by [Timeframe](https://github.com/joelhawksley/timeframe) by Joel Hawksley ([blog post](https://hawksley.org/2026/02/17/timeframe.html)). The core philosophy borrowed from that project: **only show what needs attention right now; silence means the house is healthy.**

## Architecture

The main loop in `frame_dash/main.py` runs a cycle every N seconds (default 300):

1. **Fetch** — `ha_client.py` calls the HA REST API for calendar events, entity states, and weather
2. **Render** — `renderer.py` uses Jinja2 to fill the HTML template, then Playwright (headless Chromium) screenshots it and Pillow converts it to a grayscale PNG at the device's native resolution
3. **Serve** — `byos.py` runs an HTTP server implementing the TRMNL BYOS device API. The device polls `/api/display` on its own schedule and downloads the latest image

When running as an HA add-on, the `SUPERVISOR_TOKEN` env var provides API access automatically. For standalone dev, a long-lived access token is configured in `local.yaml`.

## Project structure

```
frame-dash/
├── config.yaml              # HA add-on metadata (name, slug, options schema, port)
├── build.yaml               # Base images per architecture (Debian bookworm)
├── Dockerfile               # Add-on container — Debian-based for Playwright compat
├── run.sh                   # Add-on entry point (bashio wrapper → Python)
├── pyproject.toml           # Python deps: playwright, jinja2, httpx, pyyaml, pillow
├── uv.lock                  # Locked dependency versions
├── preview.py               # Local preview script (fake data, no HA/device needed)
├── local.example.yaml       # Standalone dev config template
├── repository.yaml          # HA add-on repo metadata
├── translations/en.yaml     # Config option descriptions for HA UI
├── frame_dash/
│   ├── __init__.py
│   ├── main.py              # CLI entry point + main loop
│   ├── config.py            # Config loading (HA add-on JSON or standalone YAML)
│   ├── ha_client.py         # HA REST API client (calendars, states, weather)
│   ├── renderer.py          # Jinja2 + Playwright HTML→grayscale PNG rendering
│   ├── byos.py              # BYOS HTTP server for the TRMNL X e-ink device
│   └── templates/
│       ├── eink.html.j2     # E-ink dashboard template
│       └── static/
│           └── eink.css     # E-ink grayscale styles (black-on-white)
└── README.md
```

## Key dependencies

- **playwright** — headless Chromium for HTML→PNG. Requires Debian (not Alpine) due to glibc. The Dockerfile installs it with `playwright install --with-deps chromium`.
- **pillow** — converts the screenshot to 8-bit grayscale for the e-ink panel.
- **httpx** — HTTP client for HA REST API calls.
- **jinja2** — HTML template rendering with a `temp_fmt` custom filter.

## Running locally for development

```bash
uv sync
uv run playwright install chromium

# Preview with fake data — no HA or device needed
python preview.py           # HTML, opens in browser
python preview.py --png     # grayscale PNG at device resolution

# Full cycle against real HA (needs local.yaml)
cp local.example.yaml local.yaml
# Edit local.yaml with your HA URL and token
uv run python -m frame_dash.main --once
```

## Design decisions to know about

- **HTML rendering, not canvas/SVG** — we render a full HTML page to PNG via Playwright. This means the dashboard layout is just CSS. Heavyweight but extremely flexible.
- **Embedded BYOS server** — `byos.py` is a small threaded HTTP server implementing TRMNL's BYOS device API (`/api/setup`, `/api/display`, `/api/log`, `/images/<hash>.png`). It auto-registers devices, persists the MAC→api_key registry to `/data/byos-devices.json`, builds `image_url` from the request `Host` header, and serves a content-hashed filename so the device only re-downloads when the image actually changes.
- **Grayscale render** — `render_eink()` screenshots the template and converts to 8-bit grayscale via Pillow; the TRMNL firmware handles the 16-level quantize/dither on-device.
- **No clock on the panel** — an e-ink display refreshes infrequently, so a clock showing a stale time would be worse than none. The template instead shows a small "Updated HH:MM" footer.
- **Attention-only status** — doors/locks/lights are only shown when they're in a "problem" state (unlocked, open, on). The `EntityState.is_problem` property in `ha_client.py` defines this logic per domain.
- **Climate always shown** — entities in the `climate` watched list are always displayed, not just when problematic.
- **Timeframe-style sensors** — supports HA template sensors using the `"icon,Label"` CSV format from Timeframe. Any `sensor.timeframe_*` entity with this format gets rendered as a status item.

## Open tasks and known gaps

### Must do before first real use
- [ ] **Confirm how the TRMNL X is pointed at a custom server** — app config vs. flashing custom firmware. This is the main on-device unknown.
- [ ] **Verify grayscale output on the physical device** — tune dithering (server-side Floyd–Steinberg vs. letting the firmware do it) if it looks muddy.
- [ ] **Fill in actual HA entity IDs** — the local.example.yaml has placeholder entities. Need real lock, light, climate, calendar entity IDs from Brian's HA instance.
- [ ] **Font loading in Playwright** — the Dockerfile installs `fonts-inter` but the CSS falls back to system-ui. Verify Inter actually renders in the headless Chromium screenshot. May need to embed fonts via @font-face with base64.

### Should do
- [ ] **HA webhook for instant updates** — instead of only polling every N seconds, register an HA automation that hits a webhook when watched entity states change (door unlocks, laundry finishes).
- [ ] **Graceful degradation** — if HA API is unreachable, keep serving the last good image rather than erroring.
- [ ] **Multi-day calendar view** — current template shows today + tomorrow. Could show the next 3-5 days in a more compact format.
- [ ] **Energy usage display** — Brian has solar (Enphase) and tracks energy. Could add a simple energy production/consumption indicator to the status area.
- [ ] **Sonos now-playing** — Timeframe shows current Sonos track. Brian has a Sonos setup. Could add a `media_player.*` entity watcher.
- [ ] **Portrait orientation option** — currently landscape; the template/CSS are structured to flip if the device sits portrait on the stand.

### Nice to have
- [ ] **Template hot-reload** — watch the templates directory and re-render on change during development.
- [ ] **Alternative to Playwright** — Playwright + Chromium adds ~500MB to the Docker image. Could explore `wkhtmltoimage` or `weasyprint` for lighter-weight HTML→PNG, but they have worse CSS support.
- [ ] **Multiple display support** — different layouts for different e-ink panels.

## Brian's home context

- Lives in Santa Fe, NM
- Runs Home Assistant with Lutron Caséta (Smart Bridge 2), Navien hydronic heating, Enphase solar
- Has a Sonos audio system
- Has a `~/projects/casadeloso` directory for HA-related projects (Python, uv-managed)

## Style and conventions

- Python 3.11+ (type hints, `X | Y` union syntax)
- Dataclasses over dicts for structured data
- `httpx` over `requests` (async-ready, better API)
- Logging via stdlib `logging`, not print statements
- HTML templates in Jinja2 with `.html.j2` extension
- CSS uses custom properties (`--bg`, `--fg`, etc.) for theming
