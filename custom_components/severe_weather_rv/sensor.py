"""Sensor platform for Severe Weather RV Monitor."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SevereWeatherCoordinator

# Each entry: (key, friendly name, icon, unit, value_fn, extra_attrs_fn)
SENSOR_DEFS = [
    (
        "alert_count",
        "Alert Count",
        "mdi:bell-alert",
        "alerts",
        lambda d: d["alert_count"],
        lambda d: {},
    ),
    (
        "threat_alert_count",
        "Threat Alert Count",
        "mdi:alert-circle",
        "alerts",
        lambda d: d["threat_count"],
        lambda d: {"threat_alerts": d["threat_alerts"]},
    ),
    (
        "tornado_threat_level",
        "Tornado Threat Level",
        "mdi:tornado",
        None,
        lambda d: d["tornado_level"],
        lambda d: {},
    ),
    (
        "thunderstorm_threat_level",
        "Severe Thunderstorm Threat Level",
        "mdi:weather-hail",
        None,
        lambda d: d["thunderstorm_level"],
        lambda d: {},
    ),
    (
        "hurricane_threat_level",
        "Hurricane Threat Level",
        "mdi:weather-hurricane",
        None,
        lambda d: d["hurricane_level"],
        lambda d: {},
    ),
    (
        "severe_weather_summary",
        "Severe Weather Summary",
        "mdi:weather-lightning-rainy",
        None,
        lambda d: d["summary"],
        lambda d: {},
    ),
    (
        "highest_severity",
        "Highest Alert Severity",
        "mdi:shield-alert",
        None,
        lambda d: d["highest_severity"],
        lambda d: {},
    ),
    (
        "top_alert_headline",
        "Top Alert Headline",
        "mdi:text-box-outline",
        None,
        lambda d: d["top_headline"],
        lambda d: {"all_alerts": d["all_alerts"]},
    ),
    (
        "nhc_active_storms",
        "NHC Active Storms",
        "mdi:weather-hurricane",
        "storms",
        lambda d: len(d["nhc_storms"]),
        lambda d: {"storms": d["nhc_storms"]},
    ),
    (
        "monitored_latitude",
        "Monitored Latitude",
        "mdi:latitude",
        "°",
        lambda d: d["latitude"],
        lambda d: {},
    ),
    (
        "monitored_longitude",
        "Monitored Longitude",
        "mdi:longitude",
        "°",
        lambda d: d["longitude"],
        lambda d: {},
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: SevereWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        SevereWeatherSensor(coordinator, entry, *defn) for defn in SENSOR_DEFS
    )


class SevereWeatherSensor(CoordinatorEntity, SensorEntity):
    """A sensor entity backed by the coordinator."""

    def __init__(
        self,
        coordinator: SevereWeatherCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        icon: str,
        unit: str | None,
        value_fn,
        attrs_fn,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self._value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return self._attrs_fn(self.coordinator.data)

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Severe Weather RV Monitor",
            "manufacturer": "NOAA / NWS / SPC / NHC",
            "model": "Dynamic GPS-Based Weather Monitor",
            "entry_type": "service",
        }
