#!/usr/bin/env python3
"""Local preview script for Frame Dash.

Renders the dashboard with fake data — no Home Assistant connection required.

Usage:
    python preview.py           # writes preview.html and opens in browser
    python preview.py --png     # renders preview.png via Playwright (TV resolution)
    python preview.py --dark    # dark theme
    python preview.py --png --dark --output my.png
"""

import argparse
import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make sure the package is importable from the repo root
sys.path.insert(0, str(Path(__file__).parent))

from frame_dash.config import Config, WatchedEntities
from frame_dash.ha_client import (
    CalendarEvent,
    DashboardData,
    EntityState,
    WeatherData,
)
from frame_dash.renderer import Renderer


def fake_data(now: datetime) -> DashboardData:
    """Build realistic fake dashboard data for previewing."""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    events_today = [
        CalendarEvent(
            summary="Dentist — Brian",
            start=today.replace(hour=9, minute=0),
            end=today.replace(hour=10, minute=0),
            all_day=False,
            calendar_name="Family",
        ),
        CalendarEvent(
            summary="School pickup",
            start=today.replace(hour=15, minute=15),
            end=today.replace(hour=15, minute=45),
            all_day=False,
            calendar_name="Family",
        ),
        CalendarEvent(
            summary="Garbage day",
            start=today,
            end=today + timedelta(days=1),
            all_day=True,
            calendar_name="Home",
        ),
    ]

    events_tomorrow = [
        CalendarEvent(
            summary="Yoga class",
            start=tomorrow.replace(hour=7, minute=30),
            end=tomorrow.replace(hour=8, minute=30),
            all_day=False,
            calendar_name="Family",
        ),
        CalendarEvent(
            summary="Groceries",
            start=tomorrow.replace(hour=11, minute=0),
            end=tomorrow.replace(hour=12, minute=0),
            all_day=False,
            calendar_name="Family",
        ),
        CalendarEvent(
            summary="Dinner with the Garcias",
            start=tomorrow.replace(hour=18, minute=30),
            end=tomorrow.replace(hour=21, minute=0),
            all_day=False,
            calendar_name="Family",
        ),
    ]

    # Attention items — things in a "problem" state
    attention_items = [
        EntityState(
            entity_id="lock.front_door",
            state="unlocked",
            friendly_name="Front Door",
            attributes={"device_class": "lock"},
        ),
        EntityState(
            entity_id="binary_sensor.garage_door",
            state="on",
            friendly_name="Garage Door",
            attributes={"device_class": "garage_door"},
        ),
        EntityState(
            entity_id="light.kitchen",
            state="on",
            friendly_name="Kitchen",
            attributes={},
        ),
        EntityState(
            entity_id="sensor.timeframe_laundry",
            state="🧺, Laundry done",
            friendly_name="Laundry",
            attributes={},
        ),
    ]

    # Climate — always shown
    climate_states = [
        EntityState(
            entity_id="climate.living_room",
            state="heat",
            friendly_name="Living Room",
            attributes={
                "current_temperature": 68,
                "temperature": 70,
                "hvac_action": "heating",
            },
        ),
        EntityState(
            entity_id="climate.bedroom",
            state="heat",
            friendly_name="Bedroom",
            attributes={
                "current_temperature": 65,
                "temperature": 67,
                "hvac_action": "idle",
            },
        ),
    ]

    weather = WeatherData(
        condition="partlycloudy",
        temperature=52.0,
        temperature_unit="°F",
        temp_high=64.0,
        temp_low=31.0,
    )

    all_states = {e.entity_id: e for e in attention_items + climate_states}

    return DashboardData(
        timestamp=now,
        events_today=events_today,
        events_tomorrow=events_tomorrow,
        attention_items=attention_items,
        climate_states=climate_states,
        weather=weather,
        all_states=all_states,
    )


def preview_config(theme: str) -> Config:
    """Minimal config for rendering."""
    return Config(
        tv_width=3840,
        tv_height=2160,
        calendars=["calendar.family", "calendar.home"],
        watched_entities=WatchedEntities(),
        theme=theme,
        show_clock=True,
        show_weather=True,
    )


def render_html(renderer: Renderer, data: DashboardData, config: Config, output: Path):
    """Write rendered HTML to a file (no Playwright needed)."""
    from jinja2 import Environment, FileSystemLoader
    from frame_dash.renderer import TEMPLATE_DIR

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    env.filters["time_fmt"] = renderer._time_fmt
    env.filters["temp_fmt"] = renderer._temp_fmt
    env.filters["weather_icon"] = renderer._weather_icon
    env.filters["status_icon"] = renderer._status_icon

    template = env.get_template("base.html.j2")
    html = template.render(
        data=data,
        config=config,
        now=datetime.now(),
        theme=config.theme,
    )
    output.write_text(html)


def main():
    parser = argparse.ArgumentParser(description="Preview Frame Dash locally")
    parser.add_argument("--png", action="store_true", help="Render PNG via Playwright")
    parser.add_argument("--dark", action="store_true", help="Use dark theme")
    parser.add_argument("--no-attention", action="store_true", help="Hide attention items (clean state)")
    parser.add_argument("--output", "-o", help="Output file path")
    args = parser.parse_args()

    theme = "dark" if args.dark else "light"
    config = preview_config(theme)
    now = datetime.now(timezone.utc)
    data = fake_data(now)

    if args.no_attention:
        data.attention_items = []

    renderer = Renderer(config)

    if args.png:
        output = Path(args.output or "preview.png")
        print(f"Rendering PNG ({config.tv_width}x{config.tv_height}) → {output}")
        renderer.start()
        try:
            renderer.render(data, str(output))
        finally:
            renderer.stop()
        print(f"Done. Open {output} to view.")
        # Try to open with default image viewer
        try:
            subprocess.run(["open", str(output)], check=False)
        except FileNotFoundError:
            pass
    else:
        output = Path(args.output or "preview.html")
        print(f"Rendering HTML → {output}")
        render_html(renderer, data, config, output)
        print(f"Done. Opening {output} in browser...")
        webbrowser.open(output.resolve().as_uri())


if __name__ == "__main__":
    main()
