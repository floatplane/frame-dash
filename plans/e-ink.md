# E-Ink Display Support (TRMNL X)

## Status: implemented (v0.2.0), pending on-device testing

Built an embedded BYOS server in the add-on. What's done:

- `frame_dash/byos.py` — HTTP server (threaded) implementing `/api/setup`,
  `/api/display`, `/api/log`, and `/images/<hash>.png`. Auto-registers devices,
  persists the MAC→api_key registry to `/data/byos-devices.json`, builds
  `image_url` from the request `Host` header, and serves a content-hashed
  filename so the device only re-downloads on change.
- `frame_dash/templates/eink.html.j2` + `static/eink.css` — landscape
  1872×1404, pure black-on-white, no clock, "Updated HH:MM" footer, text-only
  (no emoji, which dither poorly).
- `renderer.render_eink()` — renders the e-ink template and converts to 8-bit
  grayscale PNG via Pillow (firmware handles the 16-level quantize/dither).
- Config: `eink_enabled`, `eink_width`, `eink_height`, `eink_port` (2300),
  `eink_refresh_rate`. Port 2300 exposed via `ports:` in config.yaml.
- `preview.py --eink [--png]` to iterate on the layout without the device.

### Device-side setup (when configuring the physical TRMNL X)

1. Enable the add-on option `eink_enabled: true`, restart the add-on.
2. Find the HA host's LAN IP. The BYOS base URL is `http://<ha-ip>:2300`.
3. On the TRMNL X, set its server / "BYOS" URL to that base URL. (Exact UI
   path TBD — confirm on device; may require the TRMNL setup flow or a custom
   firmware build that points at a custom server.)
4. The device calls `/api/setup`, gets an api_key, then polls `/api/display`.

### Remaining / to verify on device

- Confirm how the TRMNL X is pointed at a custom server (app config vs flashing).
- Verify grayscale output looks good; tune dithering (server-side Floyd–Steinberg
  vs firmware) if it looks muddy.
- Confirm landscape is the right orientation on the stand; flip template if not.
- Confirm `refresh_rate` is honored and pick a sensible default vs battery life.

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

## Confirmed BYOS protocol (researched June 2026, device in hand)

The TRMNL does **not** simply fetch a static image URL. It polls a JSON API
(the "BYOS" / Terminus contract) and then downloads the image the JSON points to.

Reference implementations: `usetrmnl/byos_sinatra` (Ruby), `usetrmnl/terminus`.
Docs: https://docs.trmnl.com/go/diy/byos and the ImageMagick guide.

### Endpoints the device calls

1. **`GET /api/setup`** — first-time registration.
   - Request header: `ID: <device_mac_address>`
   - Response (200): `{status, api_key, friendly_id, image_url, message}`
   - Response (404): `{status: 404, ...null, message: "MAC Address not registered"}`
   - The device stores the returned `api_key` for subsequent `/api/display` calls.

2. **`GET /api/display`** — the polling endpoint, called every `refresh_rate` sec.
   - Request headers: `ID: <mac>`, `Access-Token: <api_key>`, `Content-Type: application/json`
   - Response (200):
     ```json
     {
       "status": 0,
       "image_url": "http://host/images/<filename>.png",
       "filename": "<filename>",
       "refresh_rate": 300,
       "reset_firmware": false,
       "update_firmware": false,
       "firmware_url": null,
       "special_function": "sleep"
     }
     ```
   - Auth failure → `{status: 404}`.
   - `filename` should change when the image changes (device skips download if
     filename is unchanged — use a content hash or timestamp).

3. **`POST /api/log`** — device posts its logs. A no-op returning 200 is fine.

4. **Image serving** — `image_url` must be reachable by the device and return the
   actual PNG/BMP.

### Image format for the TRMNL X

- 1872×1404, PNG or BMP3, supported since FW v1.5.2.
- Grayscale: `color-type=0`, up to 4-bit (16 levels). The X handles all 16 shades.
- Dithering can be server-side (Floyd–Steinberg) or left to firmware.
- ImageMagick example (adapt resolution for X):
  ```
  magick input.png -resize 1872x1404! -dither FloydSteinberg \
    -colorspace Gray -depth 4 -define png:color-type=0 output.png
  ```
- We use Playwright to screenshot → PNG, then convert. This needs Pillow
  (was removed earlier — re-add) or an ImageMagick call. Pillow is simpler to
  keep in-process and can do grayscale + dithering via `Image.convert("L")` /
  quantize.

### Implications for our plan

- Section 1 ("serve a static /dashboard.png") is replaced by the 3-endpoint BYOS
  contract above plus image serving.
- We need a tiny device registry (MAC → api_key). For a single household device,
  this can be a one-line file in `/data` or even a static configured token.
- `refresh_rate` should align with our render cadence; no point polling faster
  than we render.

### Still to confirm on the physical device

- Default poll interval / how `refresh_rate` is honored in practice.
- Whether the X stand holds it portrait or landscape (drives the template).
- Whether firmware dithers acceptably, or we should pre-dither server-side.
