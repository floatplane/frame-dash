"""Configuration loading for Frame Dash.

Supports two modes:
- HA add-on: reads from /data/options.json (set by FRAME_DASH_CONFIG env var)
- Standalone: reads from local.yaml in the current directory
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class WatchedEntities:
    doors: list[str] = field(default_factory=list)
    lights: list[str] = field(default_factory=list)
    climate: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)

    @property
    def all_entity_ids(self) -> list[str]:
        """Return all watched entity IDs as a flat list."""
        return self.doors + self.lights + self.climate + self.alerts


@dataclass
class Config:
    update_interval: int = 600
    calendars: list[str] = field(default_factory=lambda: ["calendar.family"])
    watched_entities: WatchedEntities = field(default_factory=WatchedEntities)
    show_weather: bool = True
    weather_entity: str = "weather.home"

    # Low-battery scan (auto-discovers all battery entities)
    low_battery_enabled: bool = True
    low_battery_threshold: int = 20
    battery_exclude: list[str] = field(default_factory=list)

    # Vehicle widget (e.g. an EV like a Rivian). Empty range entity = hidden.
    vehicle_name: str = ""
    vehicle_range_entity: str = ""
    vehicle_battery_entity: str = ""
    vehicle_charging_entity: str = ""
    vehicle_plugged_entity: str = ""

    # Energy-independence widget. Empty home-use entity = hidden.
    energy_home_use_entity: str = ""        # today's home consumption (kWh)
    energy_grid_import_entity: str = ""     # today's grid import (kWh)
    energy_solar_power_entity: str = ""     # instant solar production (kW)
    energy_battery_discharge_entity: str = ""  # instant battery discharge (kW)
    energy_home_load_entity: str = ""       # instant home load (kW)

    # E-ink (TRMNL X) render + TRMNL Webhook Image delivery
    eink_width: int = 1872
    eink_height: int = 1404
    eink_webhook_url: str = ""

    # Runtime config (not from user options)
    ha_url: str = ""
    ha_token: str = ""
    data_dir: str = "/data"

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from environment/files."""
        config_path = os.environ.get("FRAME_DASH_CONFIG")

        if config_path and Path(config_path).exists():
            # HA add-on mode: JSON options
            with open(config_path) as f:
                raw = json.load(f)
        elif Path("local.yaml").exists():
            # Standalone mode: YAML config
            with open("local.yaml") as f:
                raw = yaml.safe_load(f)
        else:
            raw = {}

        # Parse watched entities
        we_raw = raw.get("watched_entities", {})
        watched = WatchedEntities(
            doors=we_raw.get("doors", []),
            lights=we_raw.get("lights", []),
            climate=we_raw.get("climate", []),
            alerts=we_raw.get("alerts", []),
        )

        config = cls(
            update_interval=raw.get("update_interval", 600),
            calendars=raw.get("calendars", ["calendar.family"]),
            watched_entities=watched,
            show_weather=raw.get("show_weather", True),
            weather_entity=raw.get("weather_entity", "weather.home"),
            low_battery_enabled=raw.get("low_battery_enabled", True),
            low_battery_threshold=raw.get("low_battery_threshold", 20),
            battery_exclude=raw.get("battery_exclude", []),
            vehicle_name=raw.get("vehicle_name", ""),
            vehicle_range_entity=raw.get("vehicle_range_entity", ""),
            vehicle_battery_entity=raw.get("vehicle_battery_entity", ""),
            vehicle_charging_entity=raw.get("vehicle_charging_entity", ""),
            vehicle_plugged_entity=raw.get("vehicle_plugged_entity", ""),
            energy_home_use_entity=raw.get("energy_home_use_entity", ""),
            energy_grid_import_entity=raw.get("energy_grid_import_entity", ""),
            energy_solar_power_entity=raw.get("energy_solar_power_entity", ""),
            energy_battery_discharge_entity=raw.get("energy_battery_discharge_entity", ""),
            energy_home_load_entity=raw.get("energy_home_load_entity", ""),
            eink_width=raw.get("eink_width", 1872),
            eink_height=raw.get("eink_height", 1404),
            eink_webhook_url=raw.get("eink_webhook_url", ""),
            data_dir=os.environ.get("FRAME_DASH_DATA", "/data"),
        )

        # Resolve HA connection details
        supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
        if supervisor_token:
            # Running as HA add-on
            config.ha_url = "http://supervisor/core"
            config.ha_token = supervisor_token
        else:
            # Standalone mode
            config.ha_url = raw.get("ha_url", "http://localhost:8123")
            config.ha_token = raw.get("ha_token", "")

        return config
