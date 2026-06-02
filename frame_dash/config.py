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
    update_interval: int = 300
    calendars: list[str] = field(default_factory=lambda: ["calendar.family"])
    watched_entities: WatchedEntities = field(default_factory=WatchedEntities)
    show_weather: bool = True
    weather_entity: str = "weather.home"

    # E-ink (TRMNL X) BYOS server
    eink_width: int = 1872
    eink_height: int = 1404
    eink_port: int = 2300

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
            update_interval=raw.get("update_interval", 300),
            calendars=raw.get("calendars", ["calendar.family"]),
            watched_entities=watched,
            show_weather=raw.get("show_weather", True),
            weather_entity=raw.get("weather_entity", "weather.home"),
            eink_width=raw.get("eink_width", 1872),
            eink_height=raw.get("eink_height", 1404),
            eink_port=raw.get("eink_port", 2300),
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
