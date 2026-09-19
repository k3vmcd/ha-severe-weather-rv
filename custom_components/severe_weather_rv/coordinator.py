"""DataUpdateCoordinator for Severe Weather RV Monitor."""
from __future__ import annotations

import logging
import math
import re
import time
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    NWS_ALERTS_URL,
    NWS_POINTS_URL,
    NHC_STORMS_URL,
    NWS_USER_AGENT,
    CONF_GPS_TYPE,
    CONF_GPS_ENTITY,
    CONF_GPS_LAT_ENTITY,
    CONF_GPS_LON_ENTITY,
    CONF_ALERT_SCAN_INTERVAL,
    CONF_FORECAST_SCAN_INTERVAL,
    DEFAULT_ALERT_SCAN_INTERVAL,
    DEFAULT_FORECAST_SCAN_INTERVAL,
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
    SPC_GEOJSON_URLS,
    STORM_PROXIMITY_CLOSE_MILES,
    STORM_PROXIMITY_FAR_MILES,
    LOCATION_CHANGE_THRESHOLD,
    MAX_FORECAST_PERIODS,
    SIGNAL_SPC_DATA_UPDATED,
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


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in statute miles between two lat/lon points."""
    r = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def _point_in_polygon(lat: float, lon: float, ring: list) -> bool:
    """Ray-casting point-in-polygon test for a GeoJSON exterior ring.

    GeoJSON coordinates are stored as [longitude, latitude] pairs.
    The ray is cast in the +longitude direction from the test point.
    """
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]   # xi = lon, yi = lat
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = xi + (lat - yi) * (xj - xi) / (yj - yi)
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _point_in_geometry(lat: float, lon: float, geometry: dict) -> bool:
    """Check if (lat, lon) lies inside a GeoJSON Polygon or MultiPolygon."""
    geom_type = geometry.get("type", "")
    coords = geometry.get("coordinates") or []
    try:
        if geom_type == "Polygon":
            # coords[0] is the exterior ring
            return bool(coords) and _point_in_polygon(lat, lon, coords[0])
        if geom_type == "MultiPolygon":
            return any(
                polygon and _point_in_polygon(lat, lon, polygon[0])
                for polygon in coords
            )
    except (IndexError, TypeError, ZeroDivisionError):
        pass
    return False


def _highest_categorical_risk(lat: float, lon: float, features: list) -> str:
    """Return the highest SPC categorical risk level for the given point.

    Checks every feature polygon and returns the most severe risk name
    whose polygon contains the point, or "No Risk" if none does.
    """
    found: set[str] = set()
    for feat in features:
        geom = feat.get("geometry") or {}
        label = (feat.get("properties") or {}).get("LABEL", "")
        if label and _point_in_geometry(lat, lon, geom):
            found.add(label.upper())

    for abbr, name in (
        ("HIGH", "High"),
        ("MDT",  "Moderate"),
        ("ENH",  "Enhanced"),
        ("SLGT", "Slight"),
        ("MRGL", "Marginal"),
        ("TSTM", "General Thunder"),
    ):
        if abbr in found:
            return name
    return "No Risk"


def _highest_hazard_risk(lat: float, lon: float, features: list) -> str:
    """Return the highest probability label for a hazard-specific SPC GeoJSON.

    SPC hazard GeoJSON LABEL values are decimal probability strings such as
    "0.02" (2%), "0.05" (5%), "0.10" (10%), "0.15" (15%), "0.30" (30%),
    "0.45" (45%), or "0.60" (60%).  A significant-severe label appends "sig"
    (e.g. "0.10sig").  Returns e.g. "5%" or "No Risk".
    """
    best_prob: float = 0.0
    best_label: str = "No Risk"

    for feat in features:
        geom = feat.get("geometry") or {}
        label_raw = str((feat.get("properties") or {}).get("LABEL", ""))
        if not label_raw or not _point_in_geometry(lat, lon, geom):
            continue
        label_lower = label_raw.lower()
        is_sig = "sig" in label_lower
        try:
            prob = float(label_lower.replace("sig", "").strip())
        except (ValueError, TypeError):
            continue
        if prob > best_prob:
            best_prob = prob
            pct = round(prob * 100)
            best_label = f"{pct}% (Significant)" if is_sig else f"{pct}%"

    return best_label


def _storm_category(classification: str, intensity_kts: int | None) -> str:
    """Return a human-readable Saffir-Simpson category for an NHC storm."""
    _CLASS_MAP = {
        "TD": "Tropical Depression", "TS": "Tropical Storm",
        "HU": "Hurricane",           "MH": "Major Hurricane",
        "DB": "Disturbance",         "EX": "Extratropical Cyclone",
        "SD": "Subtropical Depression", "SS": "Subtropical Storm",
        "LO": "Low",                 "WV": "Tropical Wave",
        "PT": "Post-Tropical Cyclone",
    }
    if intensity_kts is None:
        return _CLASS_MAP.get(classification, classification or "Unknown")
    if intensity_kts < 34:
        return "Tropical Depression"
    if intensity_kts < 64:
        return "Tropical Storm"
    if intensity_kts < 83:
        return "Hurricane (Cat 1–2)"
    if intensity_kts < 96:
        return "Hurricane (Cat 3)"
    if intensity_kts < 113:
        return "Hurricane (Cat 4)"
    return "Hurricane (Cat 5)"


def _storm_coords(storm: dict) -> tuple[float, float] | None:
    """Extract (lat, lon) from an NHC storm dict. Returns None if unavailable."""
    for lat_key, lon_key in (
        ("latitudeNumeric", "longitudeNumeric"),
        ("lat", "lon"),
        ("latitude", "longitude"),
    ):
        s_lat = storm.get(lat_key)
        s_lon = storm.get(lon_key)
        if s_lat is not None and s_lon is not None:
            try:
                return float(s_lat), float(s_lon)
            except (TypeError, ValueError):
                continue
    return None


def _parse_obs_value(field: dict | None, conversions: dict[str, object]) -> float | None:
    """Parse an NWS observation measurement dict and apply a unit conversion.

    ``conversions`` maps a unit-code substring to a callable ``(float) -> float``.
    The first matching conversion is applied.  If no unit matches the raw numeric
    value is returned as-is.
    """
    if not field or field.get("value") is None:
        return None
    try:
        value = float(field["value"])
    except (TypeError, ValueError):
        return None
    unit = field.get("unitCode", "")
    for unit_substr, converter in conversions.items():
        if unit_substr in unit:
            return converter(value)  # type: ignore[operator]
    return value


def _trim_forecast_period(period: dict) -> dict:
    """Extract and normalise essential fields from a NWS forecast period."""
    precip = period.get("probabilityOfPrecipitation") or {}
    precip_val = precip.get("value") if isinstance(precip, dict) else None
    return {
        "name": period.get("name", ""),
        "temperature": period.get("temperature"),
        "temperature_unit": period.get("temperatureUnit", "F"),
        "wind_speed": period.get("windSpeed", ""),
        "wind_direction": period.get("windDirection", ""),
        "short_forecast": period.get("shortForecast", ""),
        "detailed_forecast": (period.get("detailedForecast") or "")[:600],
        "precip_probability": int(precip_val) if precip_val is not None else 0,
        "is_daytime": bool(period.get("isDaytime", True)),
    }


# ---------------------------------------------------------------------------
# Hourly forecast helpers
# ---------------------------------------------------------------------------

def _find_precip_windows(hourly: list[dict]) -> list[dict]:
    """Group consecutive rainy/stormy hours into contiguous windows."""
    windows: list[dict] = []
    current: dict | None = None

    for h in hourly:
        if h["is_rain"]:
            if current is None:
                current = {
                    "start_hour": h["hour"],
                    "start_str": h["hour_str"],
                    "end_hour": h["hour"],
                    "end_str": h["hour_str"],
                    "max_prob": h["prob"],
                    "has_storm": h["is_storm"],
                    "count": 1,
                }
            else:
                current["end_hour"] = h["hour"]
                current["end_str"] = h["hour_str"]
                current["max_prob"] = max(current["max_prob"], h["prob"])
                current["has_storm"] = current["has_storm"] or h["is_storm"]
                current["count"] += 1
        else:
            if current is not None:
                windows.append(current)
                current = None

    if current is not None:
        windows.append(current)

    return windows


def _generate_rain_summary(windows: list[dict], hourly: list[dict]) -> str:
    """Return a plain-English rain summary for today."""
    if not hourly:
        return "No hourly data available"
    if not windows:
        return "No rain expected in the next 24 hours"

    if len(windows) == 1:
        w = windows[0]
        dur = w["count"]
        weather = "thunderstorm" if w["has_storm"] else "rain"
        if dur <= 1:
            label = f"Brief {weather} around {w['start_str']}"
        elif dur <= 2:
            label = f"Brief {weather} {w['start_str']}–{w['end_str']}"
        elif dur >= 8:
            label = f"All-day {weather}"
        else:
            label = f"{weather.capitalize()} {w['start_str']}–{w['end_str']} ({dur}h)"
        return f"{label} ({w['max_prob']}% chance)"

    parts: list[str] = []
    for w in windows:
        kind = "storm" if w["has_storm"] else "rain"
        if w["count"] <= 2:
            parts.append(f"brief {kind} ~{w['start_str']}")
        else:
            parts.append(f"{kind} {w['start_str']}–{w['end_str']}")
    return "; ".join(parts)


def _generate_day_outlook(windows: list[dict], hourly: list[dict]) -> str:
    """Return a broad day-planning summary with the best clear window."""
    if not hourly:
        return "No hourly data available"

    rain_count = sum(1 for h in hourly if h["is_rain"])
    storm_count = sum(1 for h in hourly if h["is_storm"])
    total = len(hourly)

    if rain_count == 0:
        return "Dry conditions expected — good day to be outside"

    rain_pct = rain_count / total
    if storm_count > 0 and rain_pct >= 0.5:
        base = "Storm-dominated day — limit outdoor time"
    elif rain_pct >= 0.7:
        base = "Rainy all day — plan indoor activities"
    elif rain_pct >= 0.4:
        base = "Mixed day — plan around the rain windows"
    elif rain_count <= 2:
        base = "Mostly clear with a brief wet stretch"
    else:
        base = "Some rain expected, but good windows available"

    # Find the longest dry window
    clear_runs: list[list[dict]] = []
    run: list[dict] = []
    for h in hourly:
        if not h["is_rain"]:
            run.append(h)
        else:
            if run:
                clear_runs.append(run)
                run = []
    if run:
        clear_runs.append(run)

    if clear_runs:
        best = max(clear_runs, key=len)
        if len(best) >= 2:
            base += f". Best window: {best[0]['hour_str']}–{best[-1]['hour_str']}"

    return base


def _risk_percent(label: str | None) -> int:
    """Extract an integer risk percent from SPC labels.

    Examples:
    - "No Risk" -> 0
    - "5%" -> 5
    - "15% (Significant)" -> 15
    """
    if not label:
        return 0
    match = re.search(r"(\d+)", str(label))
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _categorical_rank(level: str | None) -> int:
    """Return numeric severity rank for SPC categorical outlook labels."""
    order = {
        "No Risk": 0,
        "General Thunder": 1,
        "Marginal": 2,
        "Slight": 3,
        "Enhanced": 4,
        "Moderate": 5,
        "High": 6,
    }
    return order.get(level or "No Risk", 0)


def _compute_risk_changes(previous: dict, current: dict) -> dict:
    """Compute concise risk-transition messages between updates."""
    if not previous:
        return {
            "risk_changes": [],
            "risk_change_summary": "No material severe-risk changes since the last update",
            "hail_delta": 0,
            "tornado_delta": 0,
            "wind_delta": 0,
        }

    changes: list[str] = []

    prev_cat = previous.get("spc_day1_risk", "No Risk")
    curr_cat = current.get("spc_day1_risk", "No Risk")
    if _categorical_rank(curr_cat) > _categorical_rank(prev_cat):
        changes.append(f"SPC Day 1 risk increased: {prev_cat} -> {curr_cat}")

    hazard_pairs = (
        ("hail", "spc_day1_hail_risk"),
        ("tornado", "spc_day1_tornado_risk"),
        ("wind", "spc_day1_wind_risk"),
    )
    deltas: dict[str, int] = {}
    for label, key in hazard_pairs:
        prev_raw = previous.get(key, "No Risk")
        curr_raw = current.get(key, "No Risk")
        prev_pct = _risk_percent(prev_raw)
        curr_pct = _risk_percent(curr_raw)
        delta = curr_pct - prev_pct
        deltas[f"{label}_delta"] = delta
        if prev_pct == 0 and curr_pct > 0:
            changes.append(f"{label.capitalize()} risk entered your location: 0% -> {curr_pct}%")
        elif delta > 0:
            changes.append(f"{label.capitalize()} risk increased: {prev_pct}% -> {curr_pct}%")

    prev_dist = previous.get("nearest_storm_distance")
    curr_dist = current.get("nearest_storm_distance")
    if isinstance(prev_dist, (int, float)) and isinstance(curr_dist, (int, float)):
        if curr_dist < prev_dist and (prev_dist - curr_dist) >= 50:
            name = current.get("nearest_storm_name", "Nearest tropical system")
            changes.append(
                f"{name} moved closer: {round(prev_dist)} mi -> {round(curr_dist)} mi"
            )

    summary = changes[0] if changes else "No material severe-risk changes since the last update"
    return {
        "risk_changes": changes[:5],
        "risk_change_summary": summary,
        **deltas,
    }


# ---------------------------------------------------------------------------
# DIKA action-level computation
# ---------------------------------------------------------------------------

def _compute_action_level(data: dict) -> dict:
    """Derive a DIKA-model action level + reasons + recommendations from data."""
    tornado = data.get("tornado_level", "NONE")
    thunder = data.get("thunderstorm_level", "NONE")
    hurricane = data.get("hurricane_level", "NONE")
    day1 = data.get("spc_day1_risk", "No Risk")
    day1_torn = data.get("spc_day1_tornado_risk", "No Risk")
    day1_hail = data.get("spc_day1_hail_risk", "No Risk")
    day2 = data.get("spc_day2_risk", "No Risk")
    wind_risk = data.get("spc_day1_wind_risk", "No Risk")
    rain_summary = data.get("rain_summary", "")
    day_outlook = data.get("day_outlook", "")
    risk_change_summary = data.get("risk_change_summary", "")
    risk_changes = data.get("risk_changes", [])
    windows = data.get("rain_windows", [])
    next_window = windows[0] if windows else None

    level = "NORMAL"
    reasons: list[str] = []
    recs: list[str] = []

    # --- ACT NOW ---
    if tornado == "EMERGENCY":
        level = "ACT NOW"
        reasons.append("Tornado Emergency in effect at your location")
        recs = [
            "Seek shelter NOW — lowest floor, interior room",
            "Mobile homes are NOT safe — find a sturdy structure",
            "Protect head and neck",
        ]
    elif tornado == "WARNING" or day1 == "High":
        level = "ACT NOW"
        if tornado == "WARNING":
            reasons.append("Tornado Warning in effect")
        if day1 == "High":
            reasons.append("SPC High Risk — widespread violent tornadoes likely")
        recs = [
            "Move to your primary shelter location now",
            "Delay road movement until warning threat clears",
            "Keep wireless alerts loud and active",
        ]
    elif hurricane == "EMERGENCY":
        level = "ACT NOW"
        reasons.append("Hurricane Emergency — catastrophic conditions imminent")
        recs = [
            "Evacuate surge zones immediately",
            "Shelter in solid structure if you cannot leave",
            "Stay off all roads",
        ]

    # --- PREPARE ---
    elif tornado == "WATCH" or day1 in ("Moderate", "Enhanced") or thunder == "WARNING":
        level = "PREPARE"
        if tornado == "WATCH":
            reasons.append("Tornado Watch — tornadoes possible today")
        if day1 == "Moderate":
            reasons.append("SPC Moderate Risk — significant severe weather expected")
        elif day1 == "Enhanced":
            reasons.append("SPC Enhanced Risk — several severe storms likely")
        if thunder == "WARNING":
            reasons.append("Severe Thunderstorm Warning in effect")
        recs = [
            "Stage for rapid sheltering within minutes",
            "Secure awnings/loose gear and prep to relocate RV",
            "Top off fuel and battery before storm window",
        ]
    elif hurricane in ("WARNING", "WATCH"):
        level = "PREPARE"
        reasons.append(f"Hurricane/Tropical Storm {hurricane} in effect")
        recs = [
            "Review evacuation route — top off fuel",
            "Monitor NHC every 3 hours",
            "Be ready to move on 12-hour notice",
        ]

    # --- MONITOR ---
    elif (
        day1 in ("Slight", "Marginal")
        or day1_torn not in ("No Risk",)
        or day1_hail not in ("No Risk",)
        or day1 == "General Thunder"
        or thunder == "WATCH"
        or day2 not in ("No Risk", "General Thunder")
    ):
        level = "MONITOR"
        if day1 in ("Slight", "Marginal"):
            reasons.append(f"SPC {day1} Risk — isolated severe storms possible")
        if day1_torn not in ("No Risk",):
            reasons.append(f"Tornado probability: {day1_torn}")
        if day1_hail not in ("No Risk",):
            reasons.append(f"Hail probability: {day1_hail}")
        if day1 == "General Thunder":
            reasons.append("General thunderstorms possible today")
        if thunder == "WATCH":
            reasons.append("Severe Thunderstorm Watch in effect")
        if not reasons and day2 not in ("No Risk", "General Thunder"):
            reasons.append(f"SPC Day 2 {day2} Risk — elevated risk tomorrow")
        if next_window:
            reasons.append(
                f"Next likely impact window: {next_window['start_str']}–{next_window['end_str']}"
            )
        recs = [
            f"Monitor for hail ({day1_hail}) / wind ({wind_risk}) trend changes",
            "Avoid exposed parking when hail risk is present",
            "Review nearby sturdy shelter options before the window starts",
        ]

    # --- NORMAL --- (no action recs needed)
    else:
        if risk_change_summary and "No material" not in risk_change_summary:
            reasons.append(risk_change_summary)
        if rain_summary and "no rain" not in rain_summary.lower():
            reasons.append(rain_summary)
        if day_outlook and "dry" not in day_outlook.lower() and rain_summary:
            reasons.append(day_outlook)

    if risk_changes:
        reasons.insert(0, risk_changes[0])

    return {
        "action_level": level,
        "action_reasons": reasons[:3],
        "action_recommendations": recs[:4],
    }


class SevereWeatherCoordinator(DataUpdateCoordinator):
    """Coordinator that polls NWS alerts, NHC storm data, forecasts, and observations."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        interval = entry.options.get(CONF_ALERT_SCAN_INTERVAL, DEFAULT_ALERT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        # NWS point data cache — refreshed when location changes by ≥ LOCATION_CHANGE_THRESHOLD°
        self._cached_point_lat: float | None = None
        self._cached_point_lon: float | None = None
        self._cached_forecast_url: str | None = None
        self._cached_hourly_url: str | None = None
        self._cached_obs_station_url: str | None = None
        self._cached_obs_station_name: str | None = None
        self._cached_radar_station: str | None = None
        # Extended data cache (forecast + observations + SPC GeoJSON)
        # Refreshed every CONF_FORECAST_SCAN_INTERVAL seconds.
        self._last_forecast_fetch: float = 0.0
        self._cached_extended: dict = {}
        # Set by the SPC issuance-schedule tracker to force an immediate
        # slow-tier refresh, independent of the forecast_scan_interval gate.
        self._force_extended_refresh: bool = False

    # ------------------------------------------------------------------
    # Forced refresh — called by the SPC issuance-schedule tracker
    # ------------------------------------------------------------------

    async def async_force_refresh(self) -> None:
        """Force an immediate full refresh, including slow-tier SPC data.

        Used by the SPC convective-outlook issuance schedule so risk sensors
        and map images update as soon as SPC publishes new data, rather than
        waiting for the next forecast_scan_interval tick.
        """
        self._force_extended_refresh = True
        await self.async_request_refresh()

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
    # NWS point data cache helpers
    # ------------------------------------------------------------------

    def _point_cache_stale(self, lat: float, lon: float) -> bool:
        """Return True when the NWS point data cache needs refreshing.

        Cache is considered stale on first run or when the location has moved
        by more than LOCATION_CHANGE_THRESHOLD degrees (≈7 statute miles).
        """
        if self._cached_point_lat is None or self._cached_point_lon is None:
            return True
        return (
            abs(lat - self._cached_point_lat) > LOCATION_CHANGE_THRESHOLD
            or abs(lon - self._cached_point_lon) > LOCATION_CHANGE_THRESHOLD
        )

    # ------------------------------------------------------------------
    # NWS point data — forecast URL, nearest observation station, radar ID
    # ------------------------------------------------------------------

    async def _fetch_nws_point_data(
        self, session: aiohttp.ClientSession, lat: float, lon: float
    ) -> None:
        """Fetch and cache NWS gridpoint metadata for the given coordinates.

        Retrieves the 7-day forecast URL, the nearest ASOS/AWOS observation
        station (and its observation URL), and the nearest NEXRAD radar station
        identifier.  Results are stored on the coordinator instance so that
        subsequent update cycles can reuse them without additional network calls.
        """
        url = f"{NWS_POINTS_URL}/{lat},{lon}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    _LOGGER.warning(
                        "NWS points API returned HTTP %s for %s,%s", resp.status, lat, lon
                    )
                    return
                payload = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _LOGGER.warning("Network error fetching NWS point data: %s", exc)
            return
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Unexpected error fetching NWS point data: %s", exc)
            return

        props = payload.get("properties") or {}
        self._cached_forecast_url = props.get("forecast")
        self._cached_hourly_url = props.get("forecastHourly")
        self._cached_radar_station = props.get("radarStation")
        stations_url = props.get("observationStations")

        # Resolve the nearest observation station
        if stations_url:
            try:
                async with session.get(stations_url) as resp:
                    if resp.status == 200:
                        st_data = await resp.json(content_type=None)
                        features = st_data.get("features") or []
                        if features:
                            st_props = features[0].get("properties") or {}
                            # "@id" is the canonical station URL
                            self._cached_obs_station_url = (
                                st_props.get("@id") or st_props.get("id")
                            )
                            self._cached_obs_station_name = st_props.get(
                                "name", "Unknown Station"
                            )
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.debug("Could not resolve observation stations: %s", exc)

        self._cached_point_lat = lat
        self._cached_point_lon = lon
        _LOGGER.debug(
            "NWS point cache updated: radar=%s station=%s forecast=%s",
            self._cached_radar_station,
            self._cached_obs_station_name,
            self._cached_forecast_url,
        )

    # ------------------------------------------------------------------
    # NWS hourly forecast — rain/storm window analysis
    # ------------------------------------------------------------------

    async def _fetch_nws_hourly_forecast(
        self, session: aiohttp.ClientSession
    ) -> dict:
        """Fetch NWS hourly data and produce rain window + day-plan summaries."""
        result: dict = {
            "hourly_periods": [],
            "rain_windows": [],
            "rain_summary": "No hourly forecast available",
            "day_outlook": "Unknown",
        }
        if not self._cached_hourly_url:
            return result

        try:
            async with session.get(self._cached_hourly_url) as resp:
                if resp.status != 200:
                    _LOGGER.debug(
                        "NWS hourly forecast returned HTTP %s", resp.status
                    )
                    return result
                payload = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _LOGGER.debug("Network error fetching hourly forecast: %s", exc)
            return result
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("Unexpected error fetching hourly forecast: %s", exc)
            return result

        from datetime import datetime, timezone, timedelta  # local import — stdlib

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=25)  # next ~24 hours

        periods = (payload.get("properties") or {}).get("periods") or []
        hourly: list[dict] = []
        for p in periods:
            try:
                start = datetime.fromisoformat(p.get("startTime", ""))
            except (ValueError, TypeError):
                continue
            if start < now or start > cutoff:
                continue

            raw_precip = p.get("probabilityOfPrecipitation") or {}
            prob = 0
            if isinstance(raw_precip, dict):
                try:
                    prob = int(raw_precip.get("value") or 0)
                except (TypeError, ValueError):
                    prob = 0

            short = p.get("shortForecast", "")
            short_lower = short.lower()
            is_storm = any(
                w in short_lower for w in ("thunder", "tstm", "storm")
            )
            is_rain = prob >= 30 or any(
                w in short_lower
                for w in ("rain", "shower", "drizzle", "precipitation", "sleet")
            )

            local_start = start.astimezone()
            hourly.append(
                {
                    "hour": local_start.hour,
                    "hour_str": local_start.strftime("%I%p").lstrip("0"),
                    "prob": prob,
                    "short_forecast": short,
                    "is_storm": is_storm,
                    "is_rain": is_rain or is_storm,
                }
            )

        result["hourly_periods"] = hourly
        windows = _find_precip_windows(hourly)
        result["rain_windows"] = windows
        result["rain_summary"] = _generate_rain_summary(windows, hourly)
        result["day_outlook"] = _generate_day_outlook(windows, hourly)
        return result

    # ------------------------------------------------------------------
    # NWS 7-day forecast
    # ------------------------------------------------------------------

    async def _fetch_nws_forecast(self, session: aiohttp.ClientSession) -> dict:
        """Fetch and return processed NWS 7-day forecast data."""
        result: dict = {
            "forecast_today": "No forecast available",
            "forecast_tonight": "No forecast available",
            "precipitation_chance_today": 0,
            "forecast_periods": [],
            "rain_likely_today": False,
            "storm_likely_today": False,
        }
        if not self._cached_forecast_url:
            return result

        try:
            async with session.get(self._cached_forecast_url) as resp:
                if resp.status != 200:
                    _LOGGER.warning("NWS forecast returned HTTP %s", resp.status)
                    return result
                payload = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _LOGGER.warning("Network error fetching NWS forecast: %s", exc)
            return result
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Unexpected error fetching NWS forecast: %s", exc)
            return result

        periods = (payload.get("properties") or {}).get("periods") or []
        trimmed = [_trim_forecast_period(p) for p in periods[:MAX_FORECAST_PERIODS]]
        result["forecast_periods"] = trimmed

        if trimmed:
            first = trimmed[0]
            if first.get("is_daytime", True):
                result["forecast_today"] = first.get("short_forecast", "")
                result["precipitation_chance_today"] = first.get("precip_probability", 0)
                result["rain_likely_today"] = result["precipitation_chance_today"] >= 40
                result["storm_likely_today"] = "thunderstorm" in (
                    first.get("detailed_forecast") or ""
                ).lower()
                if len(trimmed) > 1:
                    result["forecast_tonight"] = trimmed[1].get("short_forecast", "")
            else:
                # First available period is tonight (early evening update)
                result["forecast_tonight"] = first.get("short_forecast", "")
                if len(trimmed) > 1:
                    result["forecast_today"] = trimmed[1].get("short_forecast", "")

        return result

    # ------------------------------------------------------------------
    # NWS current observations
    # ------------------------------------------------------------------

    async def _fetch_nws_observations(self, session: aiohttp.ClientSession) -> dict:
        """Fetch and return the latest observation from the nearest NWS station."""
        result: dict = {
            "current_conditions": "Unknown",
            "current_temperature": None,
            "current_wind_speed": None,
            "current_wind_direction": None,
            "current_humidity": None,
            "current_visibility": None,
            "current_weather_station": self._cached_obs_station_name or "Unknown",
            "precipitation_active": False,
        }
        if not self._cached_obs_station_url:
            return result

        obs_url = f"{self._cached_obs_station_url}/observations/latest"
        try:
            async with session.get(obs_url) as resp:
                if resp.status != 200:
                    _LOGGER.debug("NWS observations returned HTTP %s from %s", resp.status, obs_url)
                    return result
                payload = await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            _LOGGER.debug("Network error fetching NWS observations: %s", exc)
            return result
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("Unexpected error fetching NWS observations: %s", exc)
            return result

        props = payload.get("properties") or {}
        result["current_conditions"] = props.get("textDescription") or "Unknown"
        result["current_weather_station"] = self._cached_obs_station_name or "Unknown"

        # Temperature: wmoUnit:degC → °F
        result["current_temperature"] = _parse_obs_value(
            props.get("temperature"),
            {"degC": lambda c: round(c * 9 / 5 + 32, 1)},
        )
        # Wind speed: wmoUnit:m_s-1 → mph (also handle km_h-1)
        result["current_wind_speed"] = _parse_obs_value(
            props.get("windSpeed"),
            {
                "m_s-1":  lambda v: round(v * 2.23694, 1),
                "km_h-1": lambda v: round(v * 0.621371, 1),
            },
        )
        # Wind direction: degrees (no conversion needed)
        wd = props.get("windDirection") or {}
        if isinstance(wd, dict) and wd.get("value") is not None:
            try:
                result["current_wind_direction"] = round(float(wd["value"]))
            except (TypeError, ValueError):
                pass

        # Relative humidity: percent
        result["current_humidity"] = _parse_obs_value(
            props.get("relativeHumidity"),
            {"percent": lambda v: round(v, 1)},
        )
        # Visibility: wmoUnit:m → statute miles
        result["current_visibility"] = _parse_obs_value(
            props.get("visibility"),
            {"m": lambda v: round(v * 0.000621371, 2)},
        )
        # Detect active precipitation from the text description
        cond_lower = (result["current_conditions"] or "").lower()
        result["precipitation_active"] = any(
            kw in cond_lower
            for kw in (
                "rain", "drizzle", "shower", "snow", "sleet",
                "freezing", "hail", "thunderstorm",
            )
        )
        return result

    # ------------------------------------------------------------------
    # SPC GeoJSON — point-in-polygon risk checks
    # ------------------------------------------------------------------

    async def _fetch_spc_geojson(
        self, session: aiohttp.ClientSession, lat: float, lon: float
    ) -> dict:
        """Fetch all SPC outlook GeoJSON files and detect whether the monitored
        location falls inside any risk polygon.

        Categorical risk is mapped to a display name ("Slight", "Moderate", …).
        Hazard-specific risk (tornado / hail / wind) is returned as a probability
        string ("5%", "30%", …) or "No Risk".
        """
        result: dict = {
            "spc_day1_risk":         "No Risk",
            "spc_day2_risk":         "No Risk",
            "spc_day3_risk":         "No Risk",
            "spc_day1_tornado_risk": "No Risk",
            "spc_day1_hail_risk":    "No Risk",
            "spc_day1_wind_risk":    "No Risk",
            "spc_day2_tornado_risk": "No Risk",
            "spc_day2_hail_risk":    "No Risk",
            "spc_day2_wind_risk":    "No Risk",
            "in_spc_risk_area":          False,
            "in_spc_moderate_high_risk": False,
            "in_spc_tornado_risk":       False,
            "in_spc_hail_risk":          False,
            "in_spc_wind_risk":          False,
        }

        _CATEGORICAL = frozenset({"day1_categorical", "day2_categorical", "day3_categorical"})
        _KEY_MAP = {
            "day1_categorical": "spc_day1_risk",
            "day2_categorical": "spc_day2_risk",
            "day3_categorical": "spc_day3_risk",
            "day1_tornado":     "spc_day1_tornado_risk",
            "day1_hail":        "spc_day1_hail_risk",
            "day1_wind":        "spc_day1_wind_risk",
            "day2_tornado":     "spc_day2_tornado_risk",
            "day2_hail":        "spc_day2_hail_risk",
            "day2_wind":        "spc_day2_wind_risk",
        }

        spc_timeout = aiohttp.ClientTimeout(total=20)
        for geojson_key, result_key in _KEY_MAP.items():
            url = SPC_GEOJSON_URLS.get(geojson_key)
            if not url:
                continue
            try:
                async with session.get(url, timeout=spc_timeout) as resp:
                    if resp.status != 200:
                        _LOGGER.debug(
                            "SPC GeoJSON '%s' returned HTTP %s", geojson_key, resp.status
                        )
                        continue
                    payload = await resp.json(content_type=None)
            except aiohttp.ClientError as exc:
                _LOGGER.debug("Network error fetching SPC GeoJSON '%s': %s", geojson_key, exc)
                continue
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.debug("Error fetching SPC GeoJSON '%s': %s", geojson_key, exc)
                continue

            features = payload.get("features") or []
            if geojson_key in _CATEGORICAL:
                result[result_key] = _highest_categorical_risk(lat, lon, features)
            else:
                result[result_key] = _highest_hazard_risk(lat, lon, features)

        # Derive binary convenience flags.
        # in_spc_risk_area excludes "General Thunder" (TSTM) — that level means
        # ordinary thunderstorms are possible, NOT elevated severe weather risk.
        # Marginal and above are the meaningful severe-risk levels.
        _TSTM_ONLY = {"No Risk", "General Thunder"}
        result["in_spc_risk_area"] = result["spc_day1_risk"] not in _TSTM_ONLY
        result["in_spc_moderate_high_risk"] = result["spc_day1_risk"] in ("Moderate", "High")
        result["in_spc_tornado_risk"] = result["spc_day1_tornado_risk"] != "No Risk"
        result["in_spc_hail_risk"]    = result["spc_day1_hail_risk"]    != "No Risk"
        result["in_spc_wind_risk"]    = result["spc_day1_wind_risk"]    != "No Risk"
        return result

    # ------------------------------------------------------------------
    # NHC storm processing — adds haversine distance to each storm
    # ------------------------------------------------------------------

    def _process_nhc_storms(
        self, storms: list, lat: float, lon: float
    ) -> dict:
        """Enhance each NHC storm with distance-to-location and summarise nearest."""
        enhanced: list[dict] = []
        nearest_name     = "None"
        nearest_distance: float | None = None
        nearest_category = "None"
        nearest_movement = "Unknown"

        for storm in storms:
            coords = _storm_coords(storm)
            enhanced_storm = dict(storm)
            if coords:
                s_lat, s_lon = coords
                dist = round(_haversine_distance(lat, lon, s_lat, s_lon), 1)
                enhanced_storm["distance_miles"] = dist

                if nearest_distance is None or dist < nearest_distance:
                    nearest_distance = dist
                    nearest_name = storm.get("name", "Unknown")

                    classification = storm.get("classification", "")
                    try:
                        intensity = int(storm.get("intensity") or 0)
                    except (TypeError, ValueError):
                        intensity = None
                    nearest_category = _storm_category(classification, intensity)

                    move_dir = storm.get("movementDir")
                    move_spd = storm.get("movementSpeed")
                    if move_dir is not None and move_spd is not None:
                        nearest_movement = f"{move_spd} kt toward {move_dir}°"
                    elif move_dir is not None:
                        nearest_movement = f"Toward {move_dir}°"
                    else:
                        nearest_movement = "Unknown"
            else:
                enhanced_storm["distance_miles"] = None
            enhanced.append(enhanced_storm)

        return {
            "nhc_storms":             enhanced,
            "nearest_storm_name":     nearest_name,
            "nearest_storm_distance": nearest_distance,
            "nearest_storm_category": nearest_category,
            "nearest_storm_movement": nearest_movement,
            "storm_within_300mi": (
                nearest_distance is not None
                and nearest_distance <= STORM_PROXIMITY_CLOSE_MILES
            ),
            "storm_within_500mi": (
                nearest_distance is not None
                and nearest_distance <= STORM_PROXIMITY_FAR_MILES
            ),
        }

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Fetch all weather data and return the unified coordinator data dict.

        The update is split into two frequency tiers:

        * **Fast tier** (every ``alert_scan_interval``, default 5 min):
          NWS active alerts and NHC storm data with distance calculations.

        * **Slow tier** (every ``forecast_scan_interval``, default 30 min):
          NWS 7-day forecast, nearest station observations, and SPC GeoJSON
          point-in-polygon risk checks for all nine outlook products.

        NWS gridpoint metadata (forecast URL, observation station, radar station)
        is fetched once per significant location change and cached.
        """
        previous_data = self.data or {}

        try:
            lat, lon = self._get_coordinates()
        except UpdateFailed:
            raise
        except Exception as exc:
            raise UpdateFailed(f"Unexpected error reading GPS coordinates: {exc}") from exc

        # ── Build data dict — defaults for ALL keys ───────────────────────
        data: dict = {
            # Location
            "latitude": lat,
            "longitude": lon,
            "radar_station": self._cached_radar_station,
            # Active alerts
            "all_alerts": [],
            "threat_alerts": [],
            "alert_count": 0,
            "threat_count": 0,
            "tornado_level": "NONE",
            "thunderstorm_level": "NONE",
            "hurricane_level": "NONE",
            "summary": "ALL CLEAR",
            "highest_severity": "None",
            "top_headline": "No active alerts",
            # NHC storms (enhanced with distance)
            "nhc_storms": [],
            "nearest_storm_name": "None",
            "nearest_storm_distance": None,
            "nearest_storm_category": "None",
            "nearest_storm_movement": "Unknown",
            "storm_within_300mi": False,
            "storm_within_500mi": False,
            # Current conditions
            "current_conditions": "Unknown",
            "current_temperature": None,
            "current_wind_speed": None,
            "current_wind_direction": None,
            "current_humidity": None,
            "current_visibility": None,
            "current_weather_station": "Unknown",
            "precipitation_active": False,
            # 7-day forecast
            "forecast_today": "No forecast available",
            "forecast_tonight": "No forecast available",
            "precipitation_chance_today": 0,
            "forecast_periods": [],
            "rain_likely_today": False,
            "storm_likely_today": False,
            # SPC outlook risk
            "spc_day1_risk":         "No Risk",
            "spc_day2_risk":         "No Risk",
            "spc_day3_risk":         "No Risk",
            "spc_day1_tornado_risk": "No Risk",
            "spc_day1_hail_risk":    "No Risk",
            "spc_day1_wind_risk":    "No Risk",
            "spc_day2_tornado_risk": "No Risk",
            "spc_day2_hail_risk":    "No Risk",
            "spc_day2_wind_risk":    "No Risk",
            "in_spc_risk_area":          False,
            "in_spc_moderate_high_risk": False,
            "in_spc_tornado_risk":       False,
            "in_spc_hail_risk":          False,
            "in_spc_wind_risk":          False,
            # Hourly forecast analysis
            "hourly_periods":  [],
            "rain_windows":    [],
            "rain_summary":    "No hourly forecast available",
            "day_outlook":     "Unknown",
            # DIKA action level
            "action_level":            "NORMAL",
            "action_reasons":          [],
            "action_recommendations":  [],
            "risk_changes":            [],
            "risk_change_summary":     "No material severe-risk changes since the last update",
            "hail_delta":              0,
            "tornado_delta":           0,
            "wind_delta":              0,
        }

        # Merge cached slow-tier data — may be overwritten below if stale
        data.update(self._cached_extended)

        headers = {"User-Agent": NWS_USER_AGENT, "Accept": "application/geo+json"}
        timeout = aiohttp.ClientTimeout(total=15)
        slow_tier_updated = False

        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:

            # ── Fast tier: NWS alerts ────────────────────────────────────
            try:
                url = f"{NWS_ALERTS_URL}?point={lat},{lon}"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        payload = await resp.json(content_type=None)
                        features = payload.get("features", [])
                        data["all_alerts"] = [
                            _trim_alert(f) for f in features[:MAX_ALERT_ATTRS]
                        ]
                        data["alert_count"] = len(features)
                    else:
                        _LOGGER.warning(
                            "NWS alerts returned HTTP %s for %s,%s", resp.status, lat, lon
                        )
            except aiohttp.ClientError as exc:
                _LOGGER.warning("Network error fetching NWS alerts: %s", exc)
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.warning("Unexpected error fetching NWS alerts: %s", exc)

            # ── Fast tier: NHC storms + distance ────────────────────────
            try:
                async with session.get(NHC_STORMS_URL) as resp:
                    if resp.status == 200:
                        payload = await resp.json(content_type=None)
                        raw_storms = payload.get("activeStorms", [])
                        data.update(self._process_nhc_storms(raw_storms, lat, lon))
                    else:
                        _LOGGER.warning("NHC storms returned HTTP %s", resp.status)
            except aiohttp.ClientError as exc:
                _LOGGER.warning("Network error fetching NHC storms: %s", exc)
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.warning("Unexpected error fetching NHC storms: %s", exc)

            # ── Point data cache — refresh when location changes ─────────
            if self._point_cache_stale(lat, lon):
                await self._fetch_nws_point_data(session, lat, lon)
                data["radar_station"] = self._cached_radar_station
                # Invalidate slow-tier cache so fresh data is fetched below
                self._last_forecast_fetch = 0.0

            # ── Slow tier: forecast + observations + SPC GeoJSON ─────────
            forecast_interval = self.entry.options.get(
                CONF_FORECAST_SCAN_INTERVAL, DEFAULT_FORECAST_SCAN_INTERVAL
            )
            now = time.monotonic()
            slow_tier_updated = False
            if self._force_extended_refresh or now - self._last_forecast_fetch >= forecast_interval:
                self._force_extended_refresh = False
                extended: dict = {}
                extended.update(await self._fetch_nws_forecast(session))
                extended.update(await self._fetch_nws_observations(session))
                extended.update(await self._fetch_spc_geojson(session, lat, lon))
                extended.update(await self._fetch_nws_hourly_forecast(session))
                self._cached_extended = extended
                self._last_forecast_fetch = now
                data.update(extended)
                slow_tier_updated = True

        # ── Derive threat levels from active alert events ─────────────────
        active_events = {a["event"] for a in data["all_alerts"]}
        threat_alerts = [
            a for a in data["all_alerts"] if a["event"] in ALL_THREAT_EVENTS
        ]
        data["threat_alerts"] = threat_alerts
        data["threat_count"] = len(threat_alerts)

        for event in TORNADO_EVENTS:
            if event in active_events:
                data["tornado_level"] = TORNADO_LEVEL_MAP[event]
                break
        for event in THUNDERSTORM_EVENTS:
            if event in active_events:
                data["thunderstorm_level"] = THUNDERSTORM_LEVEL_MAP[event]
                break
        for event in HURRICANE_EVENTS:
            if event in active_events:
                data["hurricane_level"] = HURRICANE_LEVEL_MAP[event]
                break

        # ── Overall summary (highest-priority wins) ───────────────────────
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
        elif s == "WATCH" or h in (
            "WATCH", "TROPICAL STORM WARNING", "TROPICAL STORM WATCH"
        ):
            data["summary"] = "ELEVATED THREAT"
        else:
            data["summary"] = "ALL CLEAR"

        # ── Highest NWS severity across all alerts ────────────────────────
        severity_present = {a["severity"] for a in data["all_alerts"]}
        for sev in SEVERITY_ORDER:
            if sev in severity_present:
                data["highest_severity"] = sev
                break

        # ── Top headline ──────────────────────────────────────────────────
        if data["all_alerts"]:
            data["top_headline"] = data["all_alerts"][0].get(
                "headline", "Active alert — see details"
            )

        # ── Risk transitions since previous update ───────────────────────
        data.update(_compute_risk_changes(previous_data, data))

        # ── DIKA action level (computed last — uses all derived fields) ────
        data.update(_compute_action_level(data))

        # ── Notify SPC map images so they refresh in step with risk sensors ──
        if slow_tier_updated:
            async_dispatcher_send(
                self.hass, f"{SIGNAL_SPC_DATA_UPDATED}_{self.entry.entry_id}"
            )

        return data
