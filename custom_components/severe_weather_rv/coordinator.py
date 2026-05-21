"""DataUpdateCoordinator for Severe Weather RV Monitor."""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    NWS_ALERTS_URL,
    NHC_STORMS_URL,
    NWS_USER_AGENT,
    CONF_GPS_TYPE,
    CONF_GPS_ENTITY,
    CONF_GPS_LAT_ENTITY,
    CONF_GPS_LON_ENTITY,
    CONF_ALERT_SCAN_INTERVAL,
    DEFAULT_ALERT_SCAN_INTERVAL,
    GPS_TYPE_HA_HOME,
    GPS_TYPE_DEVICE_TRACKER,
    GPS_TYPE_INPUT_NUMBER,
    SEVERITY_ORDER,
    ALL_THREAT_EVENTS,
    TORNADO_EVENTS,
    THUNDERSTORM_EVENTS,
    HURRICANE_EVENTS,
    TORNADO_LEVEL_MAP,
    THUNDERSTORM_LEVEL_MAP,
    HURRICANE_LEVEL_MAP,
)

_LOGGER = logging.getLogger(__name__)

# Max alerts to store in attributes to avoid HA DB bloat
MAX_ALERT_ATTRS = 10


def _trim_alert(alert: dict) -> dict:
    """Extract only essential fields from a NWS alert feature."""
    props = alert.get("properties", {})
    return {
        "event": props.get("event", "Unknown"),
        "severity": props.get("severity", "Unknown"),
        "urgency": props.get("urgency", "Unknown"),
        "certainty": props.get("certainty", "Unknown"),
        "headline": (props.get("headline") or "")[:255],
        "description_short": (props.get("description") or "")[:500],
        "effective": props.get("effective"),
        "expires": props.get("expires"),
        "sender_name": props.get("senderName"),
        "area_desc": (props.get("areaDesc") or "")[:200],
    }


class SevereWeatherCoordinator(DataUpdateCoordinator):
    """Coordinator that polls NWS alerts and NHC storm data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        interval = entry.options.get(CONF_ALERT_SCAN_INTERVAL, DEFAULT_ALERT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )

    # ------------------------------------------------------------------
    # Coordinate resolution
    # ------------------------------------------------------------------

    def _get_coordinates(self) -> tuple[float, float]:
        """Return (lat, lon) from the configured GPS source entity."""
        gps_type = self.entry.data.get(CONF_GPS_TYPE, GPS_TYPE_DEVICE_TRACKER)

        if gps_type == GPS_TYPE_HA_HOME:
            lat = self.hass.config.latitude
            lon = self.hass.config.longitude
            if lat is None or lon is None:
                raise UpdateFailed("Home Assistant home location is not set")
        elif gps_type == GPS_TYPE_DEVICE_TRACKER:
            entity_id = self.entry.data[CONF_GPS_ENTITY]
            state = self.hass.states.get(entity_id)
            if state is None:
                raise UpdateFailed(f"GPS entity '{entity_id}' not found")
            lat = state.attributes.get("latitude")
            lon = state.attributes.get("longitude")
            if lat is None or lon is None:
                raise UpdateFailed(
                    f"Entity '{entity_id}' has no latitude/longitude attributes. "
                    "Make sure it is a device_tracker or person with GPS data."
                )
        else:  # GPS_TYPE_INPUT_NUMBER
            lat_id = self.entry.data[CONF_GPS_LAT_ENTITY]
            lon_id = self.entry.data[CONF_GPS_LON_ENTITY]
            lat_state = self.hass.states.get(lat_id)
            lon_state = self.hass.states.get(lon_id)
            if lat_state is None:
                raise UpdateFailed(f"Latitude helper '{lat_id}' not found")
            if lon_state is None:
                raise UpdateFailed(f"Longitude helper '{lon_id}' not found")
            try:
                lat = float(lat_state.state)
                lon = float(lon_state.state)
            except ValueError as exc:
                raise UpdateFailed("Latitude/longitude helpers contain non-numeric values") from exc

        return round(float(lat), 4), round(float(lon), 4)

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Fetch alerts from NWS and storm data from NHC."""
        try:
            lat, lon = self._get_coordinates()
        except UpdateFailed:
            raise
        except Exception as exc:
            raise UpdateFailed(f"Unexpected error reading GPS coordinates: {exc}") from exc

        data: dict = {
            "latitude": lat,
            "longitude": lon,
            "all_alerts": [],
            "threat_alerts": [],
            "nhc_storms": [],
            # Derived
            "tornado_level": "NONE",
            "thunderstorm_level": "NONE",
            "hurricane_level": "NONE",
            "summary": "ALL CLEAR",
            "highest_severity": "None",
            "top_headline": "No active alerts",
            "alert_count": 0,
            "threat_count": 0,
        }

        headers = {"User-Agent": NWS_USER_AGENT, "Accept": "application/geo+json"}
        timeout = aiohttp.ClientTimeout(total=15)

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            # ── NWS all active alerts at GPS point ──────────────────────
            try:
                url = f"{NWS_ALERTS_URL}?point={lat},{lon}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        payload = await resp.json(content_type=None)
                        features = payload.get("features", [])
                        data["all_alerts"] = [_trim_alert(f) for f in features[:MAX_ALERT_ATTRS]]
                        data["alert_count"] = len(features)
                    else:
                        _LOGGER.warning("NWS alerts returned HTTP %s for %s,%s", resp.status, lat, lon)
            except aiohttp.ClientError as exc:
                _LOGGER.warning("Network error fetching NWS alerts: %s", exc)
            except Exception as exc:
                _LOGGER.warning("Unexpected error fetching NWS alerts: %s", exc)

            # ── NHC active storms ────────────────────────────────────────
            try:
                async with session.get(NHC_STORMS_URL) as resp:
                    if resp.status == 200:
                        payload = await resp.json(content_type=None)
                        data["nhc_storms"] = payload.get("activeStorms", [])
                    else:
                        _LOGGER.warning("NHC storms returned HTTP %s", resp.status)
            except aiohttp.ClientError as exc:
                _LOGGER.warning("Network error fetching NHC storms: %s", exc)
            except Exception as exc:
                _LOGGER.warning("Unexpected error fetching NHC storms: %s", exc)

        # ── Derive threat levels from active events ──────────────────────
        active_events = {a["event"] for a in data["all_alerts"]}
        threat_alerts = [a for a in data["all_alerts"] if a["event"] in ALL_THREAT_EVENTS]
        data["threat_alerts"] = threat_alerts
        data["threat_count"] = len(threat_alerts)

        # Tornado
        for event in TORNADO_EVENTS:
            if event in active_events:
                data["tornado_level"] = TORNADO_LEVEL_MAP[event]
                break

        # Thunderstorm / hail
        for event in THUNDERSTORM_EVENTS:
            if event in active_events:
                data["thunderstorm_level"] = THUNDERSTORM_LEVEL_MAP[event]
                break

        # Hurricane / tropical
        for event in HURRICANE_EVENTS:
            if event in active_events:
                data["hurricane_level"] = HURRICANE_LEVEL_MAP[event]
                break

        # Overall summary
        t = data["tornado_level"]
        h = data["hurricane_level"]
        s = data["thunderstorm_level"]

        if t == "EMERGENCY":
            data["summary"] = "TORNADO EMERGENCY"
        elif t == "WARNING":
            data["summary"] = "TORNADO WARNING"
        elif h == "EMERGENCY":
            data["summary"] = "HURRICANE EMERGENCY"
        elif h == "WARNING":
            data["summary"] = "HURRICANE WARNING"
        elif t == "WATCH" or s == "WARNING":
            data["summary"] = "SEVERE THREAT"
        elif s == "WATCH" or h in ("WATCH", "TROPICAL STORM WARNING", "TROPICAL STORM WATCH"):
            data["summary"] = "ELEVATED THREAT"
        else:
            data["summary"] = "ALL CLEAR"

        # Highest NWS severity across all alerts
        severity_present = {a["severity"] for a in data["all_alerts"]}
        for sev in SEVERITY_ORDER:
            if sev in severity_present:
                data["highest_severity"] = sev
                break

        # Top headline
        if data["all_alerts"]:
            data["top_headline"] = data["all_alerts"][0].get("headline", "Active alert — see details")

        return data
