"""BYOS (Build Your Own Server) HTTP server for TRMNL e-ink devices.

Implements the minimal TRMNL device API so a TRMNL X (or compatible device)
can poll this add-on directly for a grayscale dashboard image:

  GET  /api/setup    — first-time registration (device sends `ID: <mac>`)
  GET  /api/display  — polling endpoint, returns JSON pointing at the image
  POST /api/log      — device log sink (accepted and logged)
  GET  /images/<f>   — serves the current rendered image

Device flow: on first boot the device calls /api/setup with its MAC in the
`ID` header and receives an `api_key`. Thereafter it polls /api/display every
`refresh_rate` seconds with `ID` + `Access-Token` headers; we return a JSON
envelope whose `image_url` points back at /images/<hash>.png on this server.

The contract is intentionally permissive: this serves a local dashboard image
on the home LAN, so an unknown device is auto-registered rather than rejected
(robust against a lost registry or a device that skipped setup).
"""

import hashlib
import json
import logging
import random
import secrets
import string
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger(__name__)


class EinkImageState:
    """Thread-safe holder for the latest rendered e-ink PNG.

    The render loop calls update() with fresh PNG bytes; the HTTP handler reads
    the current filename/bytes. The filename is a content hash so the device
    only re-downloads when the image actually changes.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._png: bytes | None = None
        self._filename: str = "frame"

    def update(self, png: bytes) -> None:
        digest = hashlib.sha256(png).hexdigest()[:16]
        with self._lock:
            self._png = png
            self._filename = digest

    def get(self) -> tuple[str, bytes | None]:
        with self._lock:
            return self._filename, self._png


class DeviceRegistry:
    """Persistent MAC → api_key/friendly_id map, stored as JSON in data_dir."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._devices: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                self._devices = json.loads(self._path.read_text())
        except Exception as e:
            logger.warning(f"Could not load BYOS device registry: {e}")
            self._devices = {}

    def _save(self) -> None:
        try:
            self._path.write_text(json.dumps(self._devices, indent=2))
        except Exception as e:
            logger.warning(f"Could not save BYOS device registry: {e}")

    def get_or_register(self, mac: str) -> dict:
        """Return the device record for `mac`, registering it if unseen."""
        mac = mac.lower()
        with self._lock:
            if mac not in self._devices:
                friendly_id = "".join(
                    random.choices(string.ascii_uppercase + string.digits, k=6)
                )
                self._devices[mac] = {
                    "api_key": secrets.token_hex(16),
                    "friendly_id": friendly_id,
                }
                self._save()
                logger.info(f"Registered new e-ink device {mac} as {friendly_id}")
            return dict(self._devices[mac])


class _Handler(BaseHTTPRequestHandler):
    # Silence the default noisy per-request stderr logging
    def log_message(self, fmt, *args):
        logger.debug("BYOS %s - %s", self.address_string(), fmt % args)

    @property
    def _image_state(self) -> EinkImageState:
        return self.server.image_state

    @property
    def _registry(self) -> DeviceRegistry:
        return self.server.registry

    @property
    def _refresh_rate(self) -> int:
        return self.server.refresh_rate

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _image_url(self, filename: str) -> str:
        # The device reached us via this Host header, so it's reachable back here.
        host = self.headers.get("Host") or f"localhost:{self.server.server_address[1]}"
        return f"http://{host}/images/{filename}.png"

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/api/setup":
            self._handle_setup()
        elif path == "/api/display":
            self._handle_display()
        elif path.startswith("/images/"):
            self._handle_image()
        elif path in ("/", "/health"):
            self._send_json({"status": "ok", "service": "frame-dash-byos"})
        else:
            self._send_json({"status": 404, "message": "not found"}, status=404)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/log":
            self._handle_log()
        else:
            self._send_json({"status": 404, "message": "not found"}, status=404)

    def _handle_setup(self):
        mac = self.headers.get("ID", "")
        if not mac:
            self._send_json(
                {"status": 404, "message": "Missing ID (MAC) header"}, status=404
            )
            return
        device = self._registry.get_or_register(mac)
        filename, _ = self._image_state.get()
        self._send_json(
            {
                "status": 200,
                "api_key": device["api_key"],
                "friendly_id": device["friendly_id"],
                "image_url": self._image_url(filename),
                "message": "Welcome to Frame Dash",
            }
        )

    def _handle_display(self):
        mac = self.headers.get("ID", "")
        if not mac:
            self._send_json({"status": 404, "message": "Missing ID header"}, status=404)
            return

        # Permissive: register unknown devices on the fly so a lost registry or a
        # device that skipped setup still gets served.
        device = self._registry.get_or_register(mac)
        token = self.headers.get("Access-Token", "")
        if token and token != device["api_key"]:
            logger.debug(f"Device {mac} presented a stale token; serving anyway")

        filename, _ = self._image_state.get()
        self._send_json(
            {
                "status": 0,
                "image_url": self._image_url(filename),
                "filename": filename,
                "refresh_rate": self._refresh_rate,
                "reset_firmware": False,
                "update_firmware": False,
                "firmware_url": None,
                "special_function": "sleep",
            }
        )

    def _handle_image(self):
        filename, png = self._image_state.get()
        if png is None:
            self._send_json(
                {"status": 503, "message": "No image rendered yet"}, status=503
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(png)

    def _handle_log(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        logger.debug("BYOS device log: %s", body.decode(errors="replace"))
        self._send_json({"status": 200})


class BYOSServer:
    """Runs the BYOS HTTP API in a background daemon thread."""

    def __init__(self, port: int, refresh_rate: int, data_dir: str):
        self.image_state = EinkImageState()
        self._registry = DeviceRegistry(Path(data_dir) / "byos-devices.json")
        self._port = port
        self._refresh_rate = refresh_rate
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._httpd = ThreadingHTTPServer(("0.0.0.0", self._port), _Handler)
        # Stash shared state on the server so the handler can reach it
        self._httpd.image_state = self.image_state
        self._httpd.registry = self._registry
        self._httpd.refresh_rate = self._refresh_rate
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="byos-server", daemon=True
        )
        self._thread.start()
        logger.info(f"BYOS e-ink server listening on :{self._port}")

    def update_image(self, png: bytes) -> None:
        self.image_state.update(png)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            logger.info("BYOS e-ink server stopped")
