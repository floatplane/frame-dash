# E-Ink Display (TRMNL X)

## Status: implemented (v0.3.0), pending on-device testing

The whole project now targets the TRMNL X. An embedded BYOS server in the
add-on serves a grayscale dashboard the device polls for. What's built:

- `frame_dash/byos.py` — HTTP server (threaded) implementing `/api/setup`,
  `/api/display`, `/api/log`, and `/images/<hash>.png`. Auto-registers devices,
  persists the MAC→api_key registry to `/data/byos-devices.json`, builds
  `image_url` from the request `Host` header, and serves a content-hashed
  filename so the device only re-downloads on change.
- `frame_dash/templates/eink.html.j2` + `static/eink.css` — landscape
  1872×1404, pure black-on-white, no clock, "Updated HH:MM" footer, text-only
  (no emoji, which dither poorly).
- `renderer.render_eink()` — renders the template and converts to 8-bit
  grayscale PNG via Pillow (firmware handles the 16-level quantize/dither).
- Config: `eink_width`, `eink_height`, `eink_port` (2300), `eink_refresh_rate`.
  Port 2300 exposed via `ports:` in config.yaml.
- `preview.py [--png]` to iterate on the layout without the device.

### Device-side setup (when configuring the physical TRMNL X)

1. Start the add-on. Find the HA host's LAN IP — the BYOS base URL is
   `http://<ha-ip>:2300`.
2. On the TRMNL X, set its server / "BYOS" URL to that base URL. (Exact UI
   path TBD — confirm on device; may require the TRMNL setup flow or a custom
   firmware build that points at a custom server.)
3. The device calls `/api/setup`, gets an api_key, then polls `/api/display`.

### Remaining / to verify on device

- Confirm how the TRMNL X is pointed at a custom server (app config vs flashing).
- Verify grayscale output looks good; tune dithering (server-side Floyd–Steinberg
  vs firmware) if it looks muddy.
- Confirm landscape is the right orientation on the stand; flip template if not.
- Confirm `refresh_rate` is honored and pick a sensible default vs battery life.

## Device

**TRMNL X**

- 10.3" e-ink, 1872×1404, 16 grayscale shades
- ESP32-S3 + ESP32-C5, 2.4/5GHz WiFi
- 6000mAh battery (2-6 month runtime)
- Open source firmware; supports "bring your own server" mode

## BYOS protocol reference (researched June 2026)

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
     filename is unchanged — we use a content hash).

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
- We use Playwright to screenshot → PNG, then convert to grayscale with Pillow
  (`Image.convert("L")`). If the firmware's own dither looks muddy, switch to a
  server-side quantize/dither.
