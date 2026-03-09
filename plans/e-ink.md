# E-Ink Display Support (TRMNL X)

## Device

**TRMNL X** — ordered March 2026, shipping ~late March 2026

- 10.3" e-ink, 1872×1404, 16 grayscale shades
- ESP32-S3 + ESP32-C5, 2.4/5GHz WiFi
- 6000mAh battery (2-6 month runtime)
- Open source firmware; supports "bring your own server" mode — device polls a URL and displays the returned image

## Plan

### 1. Serve the rendered image over HTTP

Frame Dash already renders a PNG on disk. The simplest addition is a minimal HTTP server (one endpoint) that serves the latest image file.

Options:
- **Embedded in the main process** — spin up a `threading.Thread` running a simple `http.server.HTTPServer` alongside the render loop. No new dependencies.
- **Separate process / systemd socket** — overkill for this use case.

Endpoint: `GET /dashboard.png` → serves the most recently rendered file.

The TRMNL X just needs a URL to poll; it will fetch whatever is at that URL on its wake interval.

### 2. Add a second render target for e-ink

The TV render is 3840×2160 landscape. The TRMNL X is 1872×1404 — closer to portrait (4:3). A separate config option (or auto-detection) should drive a second render pass at the right resolution.

Config additions needed:
```yaml
eink_enabled: false
eink_width: 1872
eink_height: 1404
eink_serve_port: 8080
```

Or: just make width/height configurable per-output and let the user set them. The simpler path is a second optional render.

### 3. Rethink layout for grayscale + smaller size

The current template is landscape, color-aware, and sized for 10-foot viewing. For the dresser display:

- **Portrait layout** — clock top, calendar middle, weather/status bottom
- **Grayscale-safe** — the current palette is already mostly neutral; drop emoji or replace with SVG icons that work in grayscale
- **Denser text** — 1872×1404 at ~200dpi is much higher dpi than the TV, so font sizes need to scale down proportionally
- **No weather emoji** — replace `☀️ Sunny` with plain text or a simple Unicode symbol

Consider a separate Jinja2 template (`eink.html.j2`) rather than trying to make `base.html.j2` handle both cases. The layouts are different enough.

### 4. TRMNL X server configuration

In "bring your own server" mode, the TRMNL X firmware polls a URL at a configurable interval. The device expects a response with the image to display.

From the TRMNL developer docs, the self-hosted server should return:
- Content-Type: `image/bmp` or `image/png`
- The image at the device's native resolution

Confirm the exact protocol (BMP vs PNG, any headers, auth) when the device arrives. The open source firmware repo is the source of truth: https://github.com/usetrmnl/byos_sinatra (Ruby reference) and https://github.com/usetrmnl/firmware

### 5. Testing without the device

The existing `--render-only` flag + `preview.py` work fine for the TV layout. For e-ink:
- Add `python preview.py --eink` to render at e-ink resolution and open in browser
- The HTTP server can be tested with `curl http://localhost:8080/dashboard.png`

## What does NOT need to change

- The fetch loop (`ha_client.py`) — data is the same regardless of output device
- The Samsung push logic — runs independently of the e-ink path
- Config loading — just add new optional fields with safe defaults

## Open questions (answer when device arrives)

- Does TRMNL X firmware expect BMP or PNG? What bit depth?
- Is there any auth/token mechanism on the poll request?
- What wake interval is configurable? (Determines how often it fetches)
- Does the device do any dithering, or does it expect a pre-dithered image?
- Portrait vs landscape orientation — which way does the stand hold it?
