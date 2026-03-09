"""Home Assistant REST API client.

Fetches calendar events, entity states, and weather data from the HA API.
When running as an add-on, uses the Supervisor API proxy automatically.
"""

import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

import httpx

from .config import Config

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    summary: str
    start: datetime
    end: datetime
    all_day: bool = False
    calendar_name: str = ""

    @property
    def time_str(self) -> str:
        if self.all_day:
            return "All day"
        return self.start.strftime("%-I:%M %p").lower()


@dataclass
class EntityState:
    entity_id: str
    state: str
    friendly_name: str = ""
    attributes: dict = field(default_factory=dict)
    icon: str = ""

    @property
    def domain(self) -> str:
        return self.entity_id.split(".")[0]

    @property
    def is_problem(self) -> bool:
        """Determine if this entity is in a state that needs attention."""
        domain = self.domain

        if domain == "lock":
            return self.state == "unlocked"
        if domain == "binary_sensor":
            # For doors/windows, "on" typically means open
            device_class = self.attributes.get("device_class", "")
            if device_class in ("door", "garage_door", "window", "opening"):
                return self.state == "on"
            # For appliance sensors (washer/dryer), "on" means running
            # We'd surface "off" after it was recently "on" via a separate mechanism
            return False
        if domain == "light":
            return self.state == "on"
        if domain == "climate":
            # Not really a "problem" — always show climate info
            return True
        if domain == "sensor":
            # Sensors with timeframe-style CSV format: "icon,Label"
            return bool(self.state and self.state != "unknown" and "," in self.state)

        return False


@dataclass
class WeatherData:
    condition: str  # e.g., "sunny", "cloudy", "rainy"
    temperature: float
    temperature_unit: str  # "°F" or "°C"
    humidity: float | None = None
    forecast_today: dict | None = None


@dataclass
class DashboardData:
    """All data needed to render a single frame of the dashboard."""
    timestamp: datetime
    events_today: list[CalendarEvent]
    events_tomorrow: list[CalendarEvent]
    attention_items: list[EntityState]
    climate_states: list[EntityState]
    weather: WeatherData | None
    all_states: dict[str, EntityState]


class HAClient:
    """Client for the Home Assistant REST API."""

    def __init__(self, config: Config):
        self.config = config
        self.client = httpx.Client(
            base_url=config.ha_url,
            headers={
                "Authorization": f"Bearer {config.ha_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def _get(self, path: str, **kwargs) -> dict | list:
        """Make a GET request to the HA API."""
        try:
            resp = self.client.get(path, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error(f"HA API error on {path}: {e}")
            return []

    def get_calendar_events(
        self, calendar_id: str, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Fetch events from a calendar entity."""
        params = {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        data = self._get(f"/api/calendars/{calendar_id}", params=params)
        if not isinstance(data, list):
            return []

        events = []
        for item in data:
            start_raw = item.get("start", {})
            end_raw = item.get("end", {})

            # All-day events have "date", timed events have "dateTime"
            all_day = "date" in start_raw
            if all_day:
                evt_start = datetime.fromisoformat(start_raw["date"]).replace(tzinfo=timezone.utc)
                evt_end = datetime.fromisoformat(end_raw["date"]).replace(tzinfo=timezone.utc)
            else:
                evt_start = datetime.fromisoformat(start_raw["dateTime"])
                evt_end = datetime.fromisoformat(end_raw["dateTime"])
                if evt_start.tzinfo is None:
                    evt_start = evt_start.replace(tzinfo=timezone.utc)
                if evt_end.tzinfo is None:
                    evt_end = evt_end.replace(tzinfo=timezone.utc)

            # Get a friendly name for the calendar
            cal_name = calendar_id.replace("calendar.", "").replace("_", " ").title()

            events.append(CalendarEvent(
                summary=item.get("summary", ""),
                start=evt_start,
                end=evt_end,
                all_day=all_day,
                calendar_name=cal_name,
            ))

        return sorted(events, key=lambda e: (not e.all_day, e.start))

    def get_entity_state(self, entity_id: str) -> EntityState | None:
        """Fetch the current state of a single entity."""
        data = self._get(f"/api/states/{entity_id}")
        if not isinstance(data, dict) or "state" not in data:
            return None

        attrs = data.get("attributes", {})
        return EntityState(
            entity_id=entity_id,
            state=data["state"],
            friendly_name=attrs.get("friendly_name", entity_id),
            attributes=attrs,
            icon=attrs.get("icon", ""),
        )

    def get_weather(self, entity_id: str) -> WeatherData | None:
        """Fetch weather data from a weather entity."""
        state = self.get_entity_state(entity_id)
        if not state:
            return None

        attrs = state.attributes
        return WeatherData(
            condition=state.state,
            temperature=attrs.get("temperature", 0),
            temperature_unit=attrs.get("temperature_unit", "°F"),
            humidity=attrs.get("humidity"),
        )

    def fetch_dashboard_data(self) -> DashboardData:
        """Fetch all data needed for a dashboard render."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = today_start + timedelta(days=2)

        # Fetch calendar events
        all_events: list[CalendarEvent] = []
        for cal_id in self.config.calendars:
            events = self.get_calendar_events(cal_id, today_start, tomorrow_end)
            all_events.extend(events)

        # Split into today/tomorrow
        tomorrow_start = today_start + timedelta(days=1)
        events_today = [e for e in all_events if e.start < tomorrow_start or e.all_day]
        events_tomorrow = [e for e in all_events if e.start >= tomorrow_start]

        # Fetch all watched entity states
        all_states: dict[str, EntityState] = {}
        attention_items: list[EntityState] = []
        climate_states: list[EntityState] = []

        for entity_id in self.config.watched_entities.all_entity_ids:
            state = self.get_entity_state(entity_id)
            if state:
                all_states[entity_id] = state
                if entity_id in self.config.watched_entities.climate:
                    climate_states.append(state)
                elif state.is_problem:
                    attention_items.append(state)

        # Fetch weather
        weather = None
        if self.config.show_weather:
            weather = self.get_weather(self.config.weather_entity)

        return DashboardData(
            timestamp=now,
            events_today=events_today,
            events_tomorrow=events_tomorrow,
            attention_items=attention_items,
            climate_states=climate_states,
            weather=weather,
            all_states=all_states,
        )
