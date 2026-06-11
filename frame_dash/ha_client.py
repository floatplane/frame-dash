"""Home Assistant REST API client.

Fetches calendar events, entity states, and weather data from the HA API.
When running as an add-on, uses the Supervisor API proxy automatically.
"""

import logging
from datetime import date, datetime, timedelta, timezone
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
        if domain == "cover":
            # Closure covers (garage/door/gate/window) are a problem when open;
            # shades/blinds/awnings being open is normal, so they're ignored.
            device_class = self.attributes.get("device_class", "")
            if device_class in ("garage", "door", "gate", "window"):
                return self.state == "open"
            return False
        if domain == "light":
            return self.state == "on"
        if domain == "climate":
            # Not really a "problem" — always show climate info
            return True
        if domain == "sensor":
            # An alert/status sensor is shown when it has a non-empty label;
            # the state text IS the label. Templates output "" to hide it.
            return bool(
                self.state
                and self.state.strip()
                and self.state not in ("unknown", "unavailable")
            )

        return False


@dataclass
class HourlyForecast:
    time: datetime
    temperature: float
    condition: str
    precip_probability: float | None = None

    @property
    def hour_label(self) -> str:
        # e.g. "8am", "12pm", "10pm"
        return self.time.strftime("%-I%p").lower()


@dataclass
class WeatherData:
    condition: str  # e.g., "sunny", "cloudy", "rainy"
    temperature: float
    temperature_unit: str  # "°F" or "°C"
    temp_high: float | None = None
    temp_low: float | None = None
    hourly: list[HourlyForecast] = field(default_factory=list)


@dataclass
class VehicleData:
    name: str
    range: float | None
    range_unit: str
    battery: float | None = None
    charging: bool = False
    plugged_in: bool = False

    @property
    def charge_status(self) -> str:
        if self.charging:
            return "Charging"
        if self.plugged_in:
            return "Plugged in"
        return "Unplugged"


@dataclass
class EnergyData:
    independence: float | None  # % of today's home energy not from the grid
    source: str  # current dominant source: "solar" | "battery" | "grid"


@dataclass
class TodoItem:
    """A single task due today (mirrors a Todoist "Today" view entry)."""
    summary: str
    overdue: bool = False
    time_str: str = ""  # "5:00 pm" for a timed task due today; "" otherwise


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
    sunrise: datetime | None = None
    sunset: datetime | None = None
    vehicle: VehicleData | None = None
    energy: EnergyData | None = None
    todos: list[TodoItem] = field(default_factory=list)


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
        self,
        calendar_id: str,
        start: datetime,
        end: datetime,
        calendar_name: str | None = None,
    ) -> list[CalendarEvent]:
        """Fetch events from a calendar entity.

        `calendar_name` labels each event with which calendar it came from;
        if not given, it's derived from the entity ID.
        """
        params = {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        data = self._get(f"/api/calendars/{calendar_id}", params=params)
        if not isinstance(data, list):
            return []

        # Anchor all-day events to local midnight so they bucket into the correct
        # day against the local today/tomorrow boundaries (a UTC-midnight anchor
        # drifts a day in tz's behind UTC).
        local_tz = datetime.now().astimezone().tzinfo

        events = []
        for item in data:
            start_raw = item.get("start", {})
            end_raw = item.get("end", {})

            # All-day events have "date", timed events have "dateTime"
            all_day = "date" in start_raw
            if all_day:
                evt_start = datetime.fromisoformat(start_raw["date"]).replace(tzinfo=local_tz)
                evt_end = datetime.fromisoformat(end_raw["date"]).replace(tzinfo=local_tz)
            else:
                evt_start = datetime.fromisoformat(start_raw["dateTime"])
                evt_end = datetime.fromisoformat(end_raw["dateTime"])
                if evt_start.tzinfo is None:
                    evt_start = evt_start.replace(tzinfo=timezone.utc)
                if evt_end.tzinfo is None:
                    evt_end = evt_end.replace(tzinfo=timezone.utc)

            # Label each event with its calendar's name
            cal_name = calendar_name or (
                calendar_id.replace("calendar.", "").replace("_", " ").title()
            )

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
        """Fetch weather data from a weather entity, including today's high/low."""
        state = self.get_entity_state(entity_id)
        if not state:
            return None

        attrs = state.attributes
        temp_high = None
        temp_low = None
        hourly: list[HourlyForecast] = []

        # Fetch hourly forecast for today's high/low and the upcoming-hours strip
        try:
            resp = self.client.post(
                "/api/services/weather/get_forecasts",
                json={"type": "hourly", "entity_id": entity_id},
                params={"return_response": "true"},
            )
            resp.raise_for_status()
            forecasts = resp.json().get("service_response", {}).get(entity_id, {}).get("forecast", [])

            now = datetime.now().astimezone()
            today = now.date()
            today_temps = [
                f["temperature"]
                for f in forecasts
                if "datetime" in f and "temperature" in f
                and datetime.fromisoformat(f["datetime"]).astimezone().date() == today
            ]
            if today_temps:
                temp_high = max(today_temps)
                temp_low = min(today_temps)

            # 8 entries every 2 hours from the current hour (~16h whole-day view)
            hour_start = now.replace(minute=0, second=0, microsecond=0)
            upcoming = [
                f for f in forecasts
                if "datetime" in f and "temperature" in f
                and datetime.fromisoformat(f["datetime"]) >= hour_start
            ]
            for f in upcoming[::2][:8]:
                t = datetime.fromisoformat(f["datetime"])
                hourly.append(HourlyForecast(
                    time=t,
                    temperature=f["temperature"],
                    condition=f.get("condition", ""),
                    precip_probability=f.get("precipitation_probability"),
                ))
        except Exception as e:
            logger.warning(f"Could not fetch hourly forecast for {entity_id}: {e}")

        return WeatherData(
            condition=state.state,
            temperature=attrs.get("temperature", 0),
            temperature_unit=attrs.get("temperature_unit", "°F"),
            temp_high=temp_high,
            temp_low=temp_low,
            hourly=hourly,
        )

    @staticmethod
    def _strip_battery_suffix(name: str) -> str:
        """Trim a trailing 'Battery'/'Battery Level' so labels read cleanly."""
        for suffix in (" battery level", " battery"):
            if name.lower().endswith(suffix):
                return name[: -len(suffix)].strip()
        return name

    def get_low_battery(self, threshold: int, exclude: list[str]) -> EntityState | None:
        """Scan all battery entities; return a synthetic status item if any are low.

        Catches numeric battery sensors (0 <= level < threshold) and battery
        binary_sensors (on = low). Entities whose id or friendly name contains
        any `exclude` substring are skipped. Returns None if nothing is low.
        """
        data = self._get("/api/states")
        if not isinstance(data, list):
            return None

        exclude_lc = [x.lower() for x in exclude]
        items: list[tuple[float, str]] = []  # (level for sorting, label)
        for st in data:
            if not isinstance(st, dict):
                continue
            attrs = st.get("attributes", {})
            if attrs.get("device_class") != "battery":
                continue

            entity_id = st.get("entity_id", "")
            name = attrs.get("friendly_name", entity_id)
            if any(x in entity_id.lower() or x in name.lower() for x in exclude_lc):
                continue

            label_name = self._strip_battery_suffix(name)
            if entity_id.split(".")[0] == "binary_sensor":
                if st.get("state") == "on":  # on = low for battery device_class
                    items.append((0.0, f"{label_name} low"))
            else:
                try:
                    level = float(st.get("state"))
                except (TypeError, ValueError):
                    continue
                if 0 <= level < threshold:
                    items.append((level, f"{label_name} {level:.0f}%"))

        if not items:
            return None

        items.sort(key=lambda x: x[0])  # lowest battery first
        summary = " · ".join(label for _, label in items)
        # A sensor with a non-empty state renders as a status item (state = label)
        return EntityState(
            entity_id="sensor.frame_dash_low_battery",
            state=f"Low battery: {summary}",
            friendly_name="Low battery",
        )

    def get_vehicle(self) -> VehicleData | None:
        """Build the vehicle widget data from the configured entities."""
        cfg = self.config
        if not cfg.vehicle_range_entity:
            return None
        rng = self.get_entity_state(cfg.vehicle_range_entity)
        if rng is None:
            return None

        def num(state: EntityState | None) -> float | None:
            if state is None:
                return None
            try:
                return float(state.state)
            except (TypeError, ValueError):
                return None

        battery = num(self.get_entity_state(cfg.vehicle_battery_entity)) \
            if cfg.vehicle_battery_entity else None
        charging = False
        if cfg.vehicle_charging_entity:
            c = self.get_entity_state(cfg.vehicle_charging_entity)
            charging = bool(c and c.state == "on")
        plugged = False
        if cfg.vehicle_plugged_entity:
            p = self.get_entity_state(cfg.vehicle_plugged_entity)
            plugged = bool(p and p.state == "on")

        return VehicleData(
            name=cfg.vehicle_name or rng.friendly_name,
            range=num(rng),
            range_unit=rng.attributes.get("unit_of_measurement", "mi"),
            battery=battery,
            charging=charging,
            plugged_in=plugged,
        )

    def get_energy(self) -> EnergyData | None:
        """Build the energy-independence widget data.

        Independence = share of today's home consumption that did NOT come from
        the grid (1 - grid_import / home_use). The icon reflects the current
        dominant source: solar if it covers >=50% of home load, else battery if
        discharging, else grid.
        """
        cfg = self.config
        if not cfg.energy_home_use_entity:
            return None

        def num(eid: str) -> float | None:
            if not eid:
                return None
            s = self.get_entity_state(eid)
            if s is None:
                return None
            try:
                return float(s.state)
            except (TypeError, ValueError):
                return None

        home_use = num(cfg.energy_home_use_entity)
        grid_import = num(cfg.energy_grid_import_entity)
        independence = None
        if home_use and home_use > 0 and grid_import is not None:
            independence = max(0.0, min(100.0, (1 - grid_import / home_use) * 100))

        # Current dominant source (instant power)
        solar = num(cfg.energy_solar_power_entity) or 0.0
        home_load = num(cfg.energy_home_load_entity) or 0.0
        battery_discharge = num(cfg.energy_battery_discharge_entity) or 0.0
        if solar > 0 and solar >= 0.5 * home_load:
            source = "solar"
        elif battery_discharge >= 0.3:
            source = "battery"
        else:
            source = "grid"

        return EnergyData(independence=independence, source=source)

    def get_todos(self, exclude: list[str]) -> list[TodoItem]:
        """Reconstruct a Todoist-style "Today" view across all to-do lists.

        Auto-discovers every `todo.*` entity (like the battery scan), pulls its
        incomplete items via the `todo.get_items` service, and keeps the ones
        due today or earlier — overdue tasks roll forward exactly as they do in
        Todoist's Today smart filter. Undated tasks are not part of "Today" and
        are skipped. `exclude` filters lists by entity-id/name substring.
        """
        data = self._get("/api/states")
        if not isinstance(data, list):
            return []

        exclude_lc = [x.lower() for x in exclude]
        today = datetime.now().astimezone().date()
        # (sort_dt, overdue, time_str, summary) — sort_dt orders within a bucket
        collected: list[tuple[datetime, bool, str, str]] = []

        for st in data:
            if not isinstance(st, dict):
                continue
            entity_id = st.get("entity_id", "")
            if not entity_id.startswith("todo."):
                continue
            attrs = st.get("attributes", {})
            name = attrs.get("friendly_name", entity_id)
            if any(x in entity_id.lower() or x in name.lower() for x in exclude_lc):
                continue

            try:
                resp = self.client.post(
                    "/api/services/todo/get_items",
                    json={"entity_id": entity_id, "status": ["needs_action"]},
                    params={"return_response": "true"},
                )
                resp.raise_for_status()
                items = (
                    resp.json()
                    .get("service_response", {})
                    .get(entity_id, {})
                    .get("items", [])
                )
            except (httpx.HTTPError, ValueError) as e:
                # Lists that don't support get_items (or transient errors) are skipped
                logger.warning(f"Could not fetch to-do items for {entity_id}: {e}")
                continue

            for it in items:
                due_raw = it.get("due")
                if not due_raw:
                    continue  # undated tasks aren't part of a "Today" view
                try:
                    if "T" in due_raw:
                        due_dt = datetime.fromisoformat(due_raw).astimezone()
                        due_date = due_dt.date()
                        sort_dt = due_dt.replace(tzinfo=None)
                    else:
                        due_date = date.fromisoformat(due_raw)
                        due_dt = None
                        sort_dt = datetime.combine(due_date, datetime.min.time())
                except ValueError:
                    continue

                if due_date > today:
                    continue  # future task — not due yet

                overdue = due_date < today
                # Show a time only for a timed task that's actually due today
                time_str = (
                    due_dt.strftime("%-I:%M %p").lower()
                    if (due_dt is not None and not overdue)
                    else ""
                )
                collected.append((sort_dt, overdue, time_str, it.get("summary", "")))

        # Overdue first, then earliest-due first, then alphabetical
        collected.sort(key=lambda x: (not x[1], x[0], x[3].lower()))
        return [
            TodoItem(summary=summary, overdue=overdue, time_str=time_str)
            for _, overdue, time_str, summary in collected
        ]

    @staticmethod
    def _merge_duplicate_events(events: list[CalendarEvent]) -> list[CalendarEvent]:
        """Collapse the same event appearing on multiple calendars into one.

        When an event is on more than one calendar (e.g. both spouses are
        invited), HA returns an identical copy per calendar. We keep a single
        copy and join the calendar labels with " & " (e.g. "Brian & Seonaidh").
        Identity is (summary, start, end, all_day); first occurrence wins, and
        calendar names are merged in the order first seen.
        """
        kept: dict[tuple, CalendarEvent] = {}
        names: dict[tuple, list[str]] = {}
        order: list[tuple] = []
        for e in events:
            key = (e.summary, e.start, e.end, e.all_day)
            if key not in kept:
                kept[key] = e
                names[key] = []
                order.append(key)
            if e.calendar_name and e.calendar_name not in names[key]:
                names[key].append(e.calendar_name)

        merged = []
        for key in order:
            e = kept[key]
            e.calendar_name = " & ".join(names[key])
            merged.append(e)
        return merged

    def fetch_dashboard_data(self) -> DashboardData:
        """Fetch all data needed for a dashboard render."""
        now = datetime.now().astimezone()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = today_start + timedelta(days=2)

        # Fetch calendar events, labeling each with its calendar's display name
        all_events: list[CalendarEvent] = []
        for cal_id in self.config.calendars:
            cal_state = self.get_entity_state(cal_id)
            cal_name = cal_state.friendly_name if cal_state else None
            events = self.get_calendar_events(
                cal_id, today_start, tomorrow_end, calendar_name=cal_name
            )
            all_events.extend(events)

        # Collapse the same event appearing on multiple calendars into one
        all_events = self._merge_duplicate_events(all_events)

        # Split into today/tomorrow by start, then sort each by time across all
        # calendars (all-day events first, then timed events ascending) so events
        # from different calendars are interleaved rather than grouped by calendar.
        # All-day starts are local midnight, so a pure start comparison buckets
        # them into the right day with no double-counting.
        tomorrow_start = today_start + timedelta(days=1)
        sort_key = lambda e: (not e.all_day, e.start)  # noqa: E731
        # Today: drop timed events that have already ended; keep all-day events
        # for the whole day and any timed event still in progress.
        events_today = sorted(
            (
                e for e in all_events
                if e.start < tomorrow_start and (e.all_day or e.end > now)
            ),
            key=sort_key,
        )
        events_tomorrow = sorted(
            (e for e in all_events if e.start >= tomorrow_start),
            key=sort_key,
        )

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

        # Low-battery scan across all battery entities (one synthetic item).
        # Exclude the vehicle's battery — the vehicle widget already covers it.
        if self.config.low_battery_enabled:
            exclude = list(self.config.battery_exclude)
            if self.config.vehicle_battery_entity:
                exclude.append(self.config.vehicle_battery_entity)
            low_batt = self.get_low_battery(self.config.low_battery_threshold, exclude)
            if low_batt:
                attention_items.append(low_batt)

        # Today's to-do items (overdue + due today, across all to-do lists)
        todos: list[TodoItem] = []
        if self.config.todo_enabled:
            todos = self.get_todos(self.config.todo_exclude)

        # Fetch weather
        weather = None
        if self.config.show_weather:
            weather = self.get_weather(self.config.weather_entity)

        # Fetch sunrise/sunset from the built-in sun entity
        sunrise = sunset = None
        sun = self.get_entity_state("sun.sun")
        if sun:
            try:
                if sun.attributes.get("next_rising"):
                    sunrise = datetime.fromisoformat(sun.attributes["next_rising"]).astimezone()
                if sun.attributes.get("next_setting"):
                    sunset = datetime.fromisoformat(sun.attributes["next_setting"]).astimezone()
            except ValueError:
                pass

        return DashboardData(
            timestamp=now,
            events_today=events_today,
            events_tomorrow=events_tomorrow,
            attention_items=attention_items,
            climate_states=climate_states,
            weather=weather,
            all_states=all_states,
            sunrise=sunrise,
            sunset=sunset,
            vehicle=self.get_vehicle(),
            energy=self.get_energy(),
            todos=todos,
        )
