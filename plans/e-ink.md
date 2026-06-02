# E-Ink Display (TRMNL X)

## Status: implemented (v0.4.0), pending on-device testing

The project renders a grayscale dashboard and pushes it to a TRMNL **Webhook
Image** plugin, so Frame Dash shows up as one screen in the device's playlist
(rotating with any other plugins). What's built:

- `frame_dash/webhook.py` — POSTs the rendered PNG to the configured
  `eink_webhook_url` (`Content-Type: image/png`). Best-effort: rate limits
  (429) and network errors are logged but don't fail the render cycle.
- `frame_dash/templates/eink.html.j2` + `static/eink.css` — landscape
  1872×1404, pure black-on-white, no clock, "Updated HH:MM" footer, text-only
  (no emoji, which dither poorly).
- `renderer.render_eink()` — renders the template and converts to 8-bit
  grayscale PNG via Pillow.
- Config: `eink_width`, `eink_height`, `eink_webhook_url`, and `update_interval`
  (= push cadence). No inbound ports — delivery is outbound to TRMNL's cloud.
- `preview.py [--png]` to iterate on the layout without the device.

### Device-side setup

1. In the TRMNL web app: **Plugins → Webhook Image → Add**. Copy the private
   webhook URL.
2. Put that URL in the add-on's `eink_webhook_url` option; start the add-on.
3. Add the Webhook Image plugin to the device's playlist.

### Remaining / to verify on device

- Confirm the X displays the pushed image at native 1872×1404 (the webhook docs
  cite 800×480 for the OG as optimal — make sure the X isn't upscaling a smaller
  image). Adjust `eink_width/height` if needed.
- Verify grayscale output looks crisp; pre-dither server-side (Floyd–Steinberg)
  if the firmware's own conversion looks muddy.
- Confirm landscape is the right orientation on the stand; flip the template if not.
- Tune `update_interval` vs the 12 uploads/hour cap and battery life.

## Webhook Image notes

- Push model: `POST <webhook_url>` with the binary PNG. The device pulls the
  updated image from TRMNL's cloud on its own playlist/refresh schedule.
- Requires a TRMNL cloud account + the Webhook Image plugin (generates the URL).
- Formats: PNG / JPEG / BMP, max 5 MB. Rate limit: 12 uploads/hour (→ keep
  `update_interval` ≥ 300; default 600).
- Docs: https://help.trmnl.com/en/articles/13213669-webhook-image

## Device

**TRMNL X**

- 10.3" e-ink, 1872×1404, 16 grayscale shades
- ESP32-S3 + ESP32-C5, 2.4/5GHz WiFi
- 6000mAh battery (2-6 month runtime)

## History: BYOS approach (explored, dropped)

Before webhook image, this used a self-hosted BYOS (build-your-own-server) HTTP
server (`/api/setup`, `/api/display`, `/api/log`, image serving) that the device
polled directly over the LAN. It was fully private (image never left the house)
but made the device a single-purpose Frame Dash panel — no playlist rotation
with other TRMNL plugins. Dropped in favor of webhook image for **plugin
rotation** and to keep **full layout control** of our own render, accepting that
the image transits TRMNL's cloud. (For reference, the BYOS contract: device
sends `ID: <mac>` to `/api/setup` to get an `api_key`, then polls `/api/display`
with `ID` + `Access-Token`; the server returns a JSON envelope with `image_url`
+ `refresh_rate`. See git history for the `byos.py` implementation.)
