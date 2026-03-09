"""Configuration loading for Frame Dash.

Supports two modes:
- HA add-on: reads from /data/options.json (set by FRAME_DASH_CONFIG env var)
- Standalone: reads from config.yaml in the current directory
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
    samsung_tv_ip: str = ""
    update_interval: int = 300
    tv_width: int = 3840
    tv_height: int = 2160
    calendars: list[str] = field(default_factory=lambda: ["calendar.family"])
    watched_entities: WatchedEntities = field(default_factory=WatchedEntities)
    theme: str = "light"
    show_clock: bool = True
    show_weather: bool = True
    weather_entity: str = "weather.home"

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
        elif Path("config.yaml").exists():
            # Standalone mode: YAML config
            with open("config.yaml") as f:
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
            samsung_tv_ip=raw.get("samsung_tv_ip", ""),
            update_interval=raw.get("update_interval", 300),
            tv_width=raw.get("tv_width", 3840),
            tv_height=raw.get("tv_height", 2160),
            calendars=raw.get("calendars", ["calendar.family"]),
            watched_entities=watched,
            theme=raw.get("theme", "light"),
            show_clock=raw.get("show_clock", True),
            show_weather=raw.get("show_weather", True),
            weather_entity=raw.get("weather_entity", "weather.home"),
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
