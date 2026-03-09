"""Render the dashboard HTML template to a PNG image.

Uses Playwright (headless Chromium) to render Jinja2-templated HTML
at the TV's native resolution, then captures a screenshot as PNG.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

from .config import Config
from .ha_client import DashboardData

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class Renderer:
    """Renders dashboard data to a PNG image."""

    def __init__(self, config: Config):
        self.config = config
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True,
        )
        # Register custom filters
        self.env.filters["time_fmt"] = self._time_fmt
        self.env.filters["temp_fmt"] = self._temp_fmt
        self.env.filters["weather_icon"] = self._weather_icon
        self.env.filters["status_icon"] = self._status_icon

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

    def render(self, data: DashboardData, output_path: str) -> str:
        """Render dashboard data to a PNG file. Returns the output path."""
        if not self._browser:
            self.start()

        # Render HTML from template
        template = self.env.get_template("base.html.j2")
        html = template.render(
            data=data,
            config=self.config,
            now=datetime.now(),
            theme=self.config.theme,
        )

        # Use Playwright to screenshot the HTML
        page = self._browser.new_page(
            viewport={
                "width": self.config.tv_width,
                "height": self.config.tv_height,
            },
            device_scale_factor=1,
        )

        try:
            page.set_content(html, wait_until="networkidle")
            # Brief pause to let any CSS transitions/fonts settle
            page.wait_for_timeout(500)
            page.screenshot(path=output_path, type="png", full_page=False)
            logger.info(f"Rendered dashboard to {output_path}")
        finally:
            page.close()

        return output_path

    # --- Template filters ---

    @staticmethod
    def _time_fmt(dt: datetime) -> str:
        """Format a datetime as a human-readable time string."""
        if not isinstance(dt, datetime):
            return str(dt)
        return dt.strftime("%-I:%M %p").lower().replace(" ", "\u2009")

    @staticmethod
    def _temp_fmt(temp: float, unit: str = "°F") -> str:
        """Format a temperature value."""
        return f"{temp:.0f}{unit}"

    @staticmethod
    def _weather_icon(condition: str) -> str:
        """Map HA weather condition to an emoji/icon."""
        icons = {
            "clear-night": "🌙",
            "cloudy": "☁️",
            "fog": "🌫️",
            "hail": "🌨️",
            "lightning": "⚡",
            "lightning-rainy": "⛈️",
            "partlycloudy": "⛅",
            "pouring": "🌧️",
            "rainy": "🌦️",
            "snowy": "❄️",
            "snowy-rainy": "🌨️",
            "sunny": "☀️",
            "windy": "💨",
            "windy-variant": "💨",
            "exceptional": "⚠️",
        }
        return icons.get(condition, "🌡️")

    @staticmethod
    def _status_icon(entity_state) -> str:
        """Return an appropriate icon for an attention item."""
        domain = entity_state.domain
        state = entity_state.state

        if domain == "lock":
            return "🔓" if state == "unlocked" else "🔒"
        if domain == "binary_sensor":
            device_class = entity_state.attributes.get("device_class", "")
            if device_class == "garage_door":
                return "🏠"  # garage
            if device_class in ("door", "opening"):
                return "🚪"
            if device_class in ("moisture", "water"):
                return "💧"
            return "⚠️"
        if domain == "light":
            return "💡"
        if domain == "sensor":
            # Timeframe-style CSV: "icon_name,Label"
            parts = state.split(",", 1)
            if len(parts) == 2:
                return parts[0].strip()
            return "📊"

        return "⚠️"
