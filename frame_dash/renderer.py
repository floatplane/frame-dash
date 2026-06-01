"""Render the dashboard HTML template to a grayscale PNG for the e-ink display.

Uses Playwright (headless Chromium) to render the Jinja2-templated HTML at the
TRMNL X's native resolution, screenshots it, then converts to grayscale.
"""

import io
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from PIL import Image
from playwright.sync_api import sync_playwright

from .config import Config
from .ha_client import DashboardData

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class Renderer:
    """Renders dashboard data to a grayscale PNG image for the e-ink panel."""

    def __init__(self, config: Config):
        self.config = config
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True,
        )
        # Register custom filters
        self.env.filters["temp_fmt"] = self._temp_fmt

        self._playwright = None
        self._browser = None

    def start(self):
        """Start the Playwright browser (call once, reuse across renders)."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"],
        )
        logger.info("Playwright browser started")

    def stop(self):
        """Shut down the browser."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        logger.info("Playwright browser stopped")

    def render_eink(self, data: DashboardData) -> bytes:
        """Render the e-ink dashboard and return grayscale PNG bytes.

        Renders the e-ink template at the device's resolution, then converts to
        8-bit grayscale. The TRMNL firmware handles quantization to its 16 gray
        levels (and dithering) on-device.
        """
        template = self.env.get_template("eink.html.j2")
        html = template.render(
            data=data,
            config=self.config,
            now=datetime.now(),
        )

        png = self._screenshot(html, self.config.eink_width, self.config.eink_height)

        # Convert to grayscale for the e-ink panel
        with Image.open(io.BytesIO(png)) as img:
            gray = img.convert("L")
            out = io.BytesIO()
            gray.save(out, format="PNG")
            return out.getvalue()

    def _screenshot(self, html: str, width: int, height: int) -> bytes:
        """Screenshot rendered HTML at the given viewport, returning PNG bytes."""
        if not self._browser:
            self.start()

        page = self._browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        try:
            page.set_content(html, wait_until="networkidle")
            # Brief pause to let any CSS transitions/fonts settle
            page.wait_for_timeout(500)
            return page.screenshot(type="png", full_page=False)
        finally:
            page.close()

    # --- Template filters ---

    @staticmethod
    def _temp_fmt(temp: float, unit: str = "°F") -> str:
        """Format a temperature value."""
        return f"{temp:.0f}{unit}"
