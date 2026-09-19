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
        "mdi:weather-tornado",
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
    # ── Current conditions ───────────────────────────────────────────────
    (
        "current_conditions",
        "Current Conditions",
        "mdi:weather-partly-cloudy",
        None,
        lambda d: d["current_conditions"],
        lambda d: {
            "weather_station": d["current_weather_station"],
            "precipitation_active": d["precipitation_active"],
        },
    ),
    (
        "current_temperature",
        "Current Temperature",
        "mdi:thermometer",
        "°F",
        lambda d: d["current_temperature"],
        lambda d: {},
    ),
    (
        "current_wind_speed",
        "Current Wind Speed",
        "mdi:weather-windy",
        "mph",
        lambda d: d["current_wind_speed"],
        lambda d: {"direction_degrees": d["current_wind_direction"]},
    ),
    (
        "current_wind_direction",
        "Current Wind Direction",
        "mdi:compass-rose",
        "°",
        lambda d: d["current_wind_direction"],
        lambda d: {},
    ),
    (
        "current_humidity",
        "Current Humidity",
        "mdi:water-percent",
        "%",
        lambda d: d["current_humidity"],
        lambda d: {},
    ),
    (
        "current_visibility",
        "Current Visibility",
        "mdi:eye",
        "mi",
        lambda d: d["current_visibility"],
        lambda d: {},
    ),
    # ── 7-day forecast ───────────────────────────────────────────────────
    (
        "forecast_today",
        "Forecast Today",
        "mdi:weather-sunny-alert",
        None,
        lambda d: d["forecast_today"],
        lambda d: {"precipitation_chance": d["precipitation_chance_today"]},
    ),
    (
        "forecast_tonight",
        "Forecast Tonight",
        "mdi:weather-night",
        None,
        lambda d: d["forecast_tonight"],
        lambda d: {},
    ),
    (
        "precipitation_chance_today",
        "Precipitation Chance Today",
        "mdi:weather-rainy",
        "%",
        lambda d: d["precipitation_chance_today"],
        lambda d: {},
    ),
    (
        "forecast_7day",
        "7-Day Forecast",
        "mdi:calendar-week",
        "periods",
        lambda d: len(d["forecast_periods"]),
        lambda d: {"periods": d["forecast_periods"]},
    ),
    # ── SPC categorical risk ─────────────────────────────────────────────
    (
        "spc_day1_risk",
        "SPC Day 1 Risk",
        "mdi:alert-box",
        None,
        lambda d: d["spc_day1_risk"],
        lambda d: {
            "tornado_risk": d["spc_day1_tornado_risk"],
            "hail_risk":    d["spc_day1_hail_risk"],
            "wind_risk":    d["spc_day1_wind_risk"],
        },
    ),
    (
        "spc_day2_risk",
        "SPC Day 2 Risk",
        "mdi:alert-box-outline",
        None,
        lambda d: d["spc_day2_risk"],
        lambda d: {
            "tornado_risk": d["spc_day2_tornado_risk"],
            "hail_risk":    d["spc_day2_hail_risk"],
            "wind_risk":    d["spc_day2_wind_risk"],
        },
    ),
    (
        "spc_day3_risk",
        "SPC Day 3 Risk",
        "mdi:alert-circle-outline",
        None,
        lambda d: d["spc_day3_risk"],
        lambda d: {},
    ),
    # ── SPC hazard-specific risk ─────────────────────────────────────────
    (
        "spc_day1_tornado_risk",
        "SPC Day 1 Tornado Risk",
        "mdi:weather-tornado",
        None,
        lambda d: d["spc_day1_tornado_risk"],
        lambda d: {},
    ),
    (
        "spc_day1_hail_risk",
        "SPC Day 1 Hail Risk",
        "mdi:weather-hail",
        None,
        lambda d: d["spc_day1_hail_risk"],
        lambda d: {},
    ),
    (
        "spc_day1_wind_risk",
        "SPC Day 1 Wind Risk",
        "mdi:weather-windy-variant",
        None,
        lambda d: d["spc_day1_wind_risk"],
        lambda d: {},
    ),
    (
        "spc_day2_tornado_risk",
        "SPC Day 2 Tornado Risk",
        "mdi:weather-tornado",
        None,
        lambda d: d["spc_day2_tornado_risk"],
        lambda d: {},
    ),
    (
        "spc_day2_hail_risk",
        "SPC Day 2 Hail Risk",
        "mdi:weather-hail",
        None,
        lambda d: d["spc_day2_hail_risk"],
        lambda d: {},
    ),
    (
        "spc_day2_wind_risk",
        "SPC Day 2 Wind Risk",
        "mdi:weather-windy-variant",
        None,
        lambda d: d["spc_day2_wind_risk"],
        lambda d: {},
    ),
    # ── NHC storm tracking ───────────────────────────────────────────────
    (
        "nearest_storm_name",
        "Nearest Storm Name",
        "mdi:weather-hurricane-outline",
        None,
        lambda d: d["nearest_storm_name"],
        lambda d: {
            "distance_miles": d["nearest_storm_distance"],
            "category":       d["nearest_storm_category"],
            "movement":       d["nearest_storm_movement"],
        },
    ),
    (
        "nearest_storm_distance",
        "Nearest Storm Distance",
        "mdi:map-marker-distance",
        "mi",
        lambda d: d["nearest_storm_distance"],
        lambda d: {
            "storm_name": d["nearest_storm_name"],
            "category":   d["nearest_storm_category"],
        },
    ),
    (
        "nearest_storm_category",
        "Nearest Storm Category",
        "mdi:weather-hurricane",
        None,
        lambda d: d["nearest_storm_category"],
        lambda d: {"movement": d["nearest_storm_movement"]},
    ),
    # ── Hourly rain planning ─────────────────────────────────────────────
    (
        "rain_summary",
        "Rain Summary",
        "mdi:weather-rainy",
        None,
        lambda d: d.get("rain_summary", "No hourly forecast available"),
        lambda d: {
            "rain_windows": d.get("rain_windows", []),
            "hourly_periods": d.get("hourly_periods", []),
        },
    ),
    (
        "day_outlook",
        "Day Outlook",
        "mdi:calendar-today",
        None,
        lambda d: d.get("day_outlook", "Unknown"),
        lambda d: {},
    ),
    # ── DIKA action level ─────────────────────────────────────────────────
    (
        "action_level",
        "Action Level",
        "mdi:shield-alert",
        None,
        lambda d: d.get("action_level", "NORMAL"),
        lambda d: {
            "reasons":          d.get("action_reasons", []),
            "recommendations":  d.get("action_recommendations", []),
            "risk_change_summary": d.get("risk_change_summary"),
            "risk_changes": d.get("risk_changes", []),
        },
    ),
    (
        "risk_change_summary",
        "Risk Change Summary",
        "mdi:chart-line-variant",
        None,
        lambda d: d.get("risk_change_summary", "No material severe-risk changes since the last update"),
        lambda d: {
            "risk_changes": d.get("risk_changes", []),
            "hail_delta": d.get("hail_delta", 0),
            "tornado_delta": d.get("tornado_delta", 0),
            "wind_delta": d.get("wind_delta", 0),
        },
    ),
    (
        "hail_risk_delta",
        "Hail Risk Delta",
        "mdi:weather-hail",
        "%",
        lambda d: d.get("hail_delta", 0),
        lambda d: {},
    ),
    (
        "tornado_risk_delta",
        "Tornado Risk Delta",
        "mdi:weather-tornado",
        "%",
        lambda d: d.get("tornado_delta", 0),
        lambda d: {},
    ),
    (
        "wind_risk_delta",
        "Wind Risk Delta",
        "mdi:weather-windy-variant",
        "%",
        lambda d: d.get("wind_delta", 0),
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

    _attr_has_entity_name = True

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
