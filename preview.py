#!/usr/bin/env python3
"""Local preview script for Frame Dash.

Renders the e-ink dashboard with fake data — no Home Assistant connection
required.

Usage:
    python preview.py           # writes preview.html and opens in browser
    python preview.py --png     # renders grayscale preview.png at device resolution
    python preview.py --png --output my.png
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
    EnergyData,
    EntityState,
    HourlyForecast,
    VehicleData,
    WeatherData,
)
from frame_dash.renderer import Renderer


def fake_data(now: datetime) -> DashboardData:
    """Build realistic fake dashboard data for previewing."""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)

    # Multi-calendar, interleaved by time (all-day first, then ascending) —
    # mirrors what HAClient.fetch_dashboard_data now produces.
    events_today = [
        CalendarEvent(
            summary="Garbage day",
            start=today,
            end=today + timedelta(days=1),
            all_day=True,
            calendar_name="Home",
        ),
        CalendarEvent(
            summary="Standup",
            start=today.replace(hour=8, minute=30),
            end=today.replace(hour=9, minute=0),
            all_day=False,
            calendar_name="Work",
        ),
        CalendarEvent(
            summary="Dentist — Brian",
            start=today.replace(hour=9, minute=0),
            end=today.replace(hour=10, minute=0),
            all_day=False,
            calendar_name="Family",
        ),
        CalendarEvent(
            summary="Lunch with Sam",
            start=today.replace(hour=12, minute=0),
            end=today.replace(hour=13, minute=0),
            all_day=False,
            calendar_name="Work",
        ),
        CalendarEvent(
            summary="School pickup",
            start=today.replace(hour=15, minute=15),
            end=today.replace(hour=15, minute=45),
            all_day=False,
            calendar_name="Family",
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
            summary="1:1 with manager",
            start=tomorrow.replace(hour=9, minute=0),
            end=tomorrow.replace(hour=9, minute=30),
            all_day=False,
            calendar_name="Work",
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
            state="Laundry done",
            friendly_name="Laundry",
            attributes={},
        ),
        EntityState(
            entity_id="sensor.frame_dash_low_battery",
            state="Low battery: Front Lock 12% · Master Shade low",
            friendly_name="Low battery",
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

    # Every 2 hours across the day, with afternoon thunderstorms
    hourly_specs = [
        (8, 52, "partlycloudy", 0),
        (10, 60, "sunny", 0),
        (12, 64, "cloudy", 13),
        (14, 68, "lightning-rainy", 39),
        (16, 68, "lightning-rainy", 51),
        (18, 65, "lightning-rainy", 38),
        (20, 59, "rainy", 17),
        (22, 44, "clear-night", 0),
    ]
    hourly = [
        HourlyForecast(
            time=today.replace(hour=hr),
            temperature=float(temp),
            condition=cond,
            precip_probability=precip,
        )
        for hr, temp, cond, precip in hourly_specs
    ]

    weather = WeatherData(
        condition="partlycloudy",
        temperature=52.0,
        temperature_unit="°F",
        temp_high=64.0,
        temp_low=31.0,
        hourly=hourly,
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
        # Daytime demo: today's sunrise already passed, so the next rising is
        # tomorrow's — which makes today's sunset the proximate event.
        sunrise=tomorrow.replace(hour=5, minute=58),
        sunset=today.replace(hour=20, minute=21),
        vehicle=VehicleData(
            name="SKADI",
            range=268.0,
            range_unit="mi",
            battery=72.0,
            charging=True,
            plugged_in=True,
        ),
        energy=EnergyData(independence=98.0, source="solar"),
    )


def preview_config() -> Config:
    """Minimal config for rendering."""
    return Config(
        calendars=["calendar.family", "calendar.home"],
        watched_entities=WatchedEntities(),
        show_weather=True,
    )


def render_html(renderer: Renderer, data: DashboardData, config: Config, output: Path):
    """Write rendered HTML to a file (no Playwright needed)."""
    from jinja2 import Environment, FileSystemLoader
    from frame_dash.renderer import TEMPLATE_DIR

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    env.filters["temp_fmt"] = renderer._temp_fmt

    template = env.get_template("eink.html.j2")
    html = template.render(
        data=data,
        config=config,
        now=datetime.now(),
    )
    output.write_text(html)


def main():
    parser = argparse.ArgumentParser(description="Preview Frame Dash locally")
    parser.add_argument("--png", action="store_true", help="Render grayscale PNG via Playwright")
    parser.add_argument("--no-attention", action="store_true", help="Hide attention items (clean state)")
    parser.add_argument("--output", "-o", help="Output file path")
    args = parser.parse_args()

    config = preview_config()
    now = datetime.now(timezone.utc)
    data = fake_data(now)

    if args.no_attention:
        data.attention_items = []

    renderer = Renderer(config)

    if args.png:
        output = Path(args.output or "preview.png")
        print(f"Rendering e-ink PNG ({config.eink_width}x{config.eink_height}, grayscale) → {output}")
        renderer.start()
        try:
            output.write_bytes(renderer.render_eink(data))
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
