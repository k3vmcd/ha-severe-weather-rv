"""Binary sensor platform for Severe Weather RV Monitor."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SevereWeatherCoordinator

# (key, name, icon_on, icon_off, device_class, value_fn)
BINARY_SENSOR_DEFS = [
    (
        "active_severe_threat",
        "Active Severe Weather Threat",
        "mdi:alert-circle",
        "mdi:check-circle-outline",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["threat_count"] > 0,
    ),
    (
        "any_alert_active",
        "Any Weather Alert Active",
        "mdi:bell-alert",
        "mdi:bell-outline",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["alert_count"] > 0,
    ),
    (
        "tornado_active",
        "Tornado Watch or Warning",
        "mdi:weather-tornado",
        "mdi:weather-tornado",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["tornado_level"] != "NONE",
    ),
    (
        "tornado_warning",
        "Tornado Warning",
        "mdi:weather-tornado",
        "mdi:weather-tornado",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["tornado_level"] in ("WARNING", "EMERGENCY"),
    ),
    (
        "tornado_emergency",
        "Tornado Emergency",
        "mdi:weather-tornado",
        "mdi:weather-tornado",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["tornado_level"] == "EMERGENCY",
    ),
    (
        "thunderstorm_active",
        "Severe Thunderstorm Watch or Warning",
        "mdi:weather-lightning",
        "mdi:weather-lightning",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["thunderstorm_level"] != "NONE",
    ),
    (
        "thunderstorm_warning",
        "Severe Thunderstorm Warning",
        "mdi:weather-lightning",
        "mdi:weather-lightning",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["thunderstorm_level"] == "WARNING",
    ),
    (
        "hurricane_active",
        "Hurricane or Tropical Storm Watch or Warning",
        "mdi:weather-hurricane",
        "mdi:weather-hurricane",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["hurricane_level"] != "NONE",
    ),
    (
        "hurricane_warning",
        "Hurricane Warning",
        "mdi:weather-hurricane",
        "mdi:weather-hurricane",
        BinarySensorDeviceClass.SAFETY,
        lambda d: d["hurricane_level"] in ("WARNING", "EMERGENCY"),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor entities."""
    coordinator: SevereWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        SevereWeatherBinarySensor(coordinator, entry, *defn) for defn in BINARY_SENSOR_DEFS
    )


class SevereWeatherBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """A binary sensor backed by the coordinator."""

    def __init__(
        self,
        coordinator: SevereWeatherCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        icon_on: str,
        icon_off: str,
        device_class: BinarySensorDeviceClass,
        value_fn,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._icon_on = icon_on
        self._icon_off = icon_off
        self._value_fn = value_fn
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool:
        if self.coordinator.data is None:
            return False
        return bool(self._value_fn(self.coordinator.data))

    @property
    def icon(self) -> str:
        return self._icon_on if self.is_on else self._icon_off

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Severe Weather RV Monitor",
            "manufacturer": "NOAA / NWS / SPC / NHC",
            "model": "Dynamic GPS-Based Weather Monitor",
            "entry_type": "service",
        }
