"""Constants for Severe Weather RV Monitor."""

DOMAIN = "severe_weather_rv"

# Config entry keys
CONF_GPS_TYPE = "gps_type"
CONF_GPS_ENTITY = "gps_entity"
CONF_GPS_LAT_ENTITY = "gps_lat_entity"
CONF_GPS_LON_ENTITY = "gps_lon_entity"
CONF_ALERT_SCAN_INTERVAL = "alert_scan_interval"
CONF_OUTLOOK_SCAN_INTERVAL = "outlook_scan_interval"

# GPS source types
GPS_TYPE_HA_HOME = "ha_home"
GPS_TYPE_DEVICE_TRACKER = "device_tracker"
GPS_TYPE_INPUT_NUMBER = "input_number"

# Defaults
DEFAULT_ALERT_SCAN_INTERVAL = 300    # 5 minutes
DEFAULT_OUTLOOK_SCAN_INTERVAL = 3600  # 1 hour
DEFAULT_FORECAST_SCAN_INTERVAL = 1800  # 30 minutes

# Config entry keys — scan intervals
CONF_FORECAST_SCAN_INTERVAL = "forecast_scan_interval"

# API endpoints
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
NWS_POINTS_URL = "https://api.weather.gov/points"
NHC_STORMS_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"
NWS_USER_AGENT = "(severe_weather_rv Home Assistant integration)"

# Ordered highest → lowest severity
SEVERITY_ORDER = ["Extreme", "Severe", "Moderate", "Minor", "Unknown"]

# Events that trigger each threat type (ordered highest → lowest)
TORNADO_EVENTS = [
    "Tornado Emergency",
    "Tornado Warning",
    "Tornado Watch",
]
THUNDERSTORM_EVENTS = [
    "Severe Thunderstorm Warning",
    "Severe Thunderstorm Watch",
]
HURRICANE_EVENTS = [
    "Hurricane Emergency",
    "Hurricane Warning",
    "Hurricane Watch",
    "Tropical Storm Warning",
    "Tropical Storm Watch",
]
ALL_THREAT_EVENTS = TORNADO_EVENTS + THUNDERSTORM_EVENTS + HURRICANE_EVENTS

# Map event name → display level
TORNADO_LEVEL_MAP = {
    "Tornado Emergency": "EMERGENCY",
    "Tornado Warning": "WARNING",
    "Tornado Watch": "WATCH",
}
THUNDERSTORM_LEVEL_MAP = {
    "Severe Thunderstorm Warning": "WARNING",
    "Severe Thunderstorm Watch": "WATCH",
}
HURRICANE_LEVEL_MAP = {
    "Hurricane Emergency": "EMERGENCY",
    "Hurricane Warning": "WARNING",
    "Hurricane Watch": "WATCH",
    "Tropical Storm Warning": "TROPICAL STORM WARNING",
    "Tropical Storm Watch": "TROPICAL STORM WATCH",
}

# Base URL for SPC static outlook PNG images.
# These are pre-rendered by SPC and update in-place whenever a new outlook is issued,
# so they are always the latest available image without any timestamp in the URL.
_SPC_OUTLOOK_BASE = "https://www.spc.noaa.gov/products/outlook"

# SPC reference overlay images (transparent PNGs composited on top of the outlook image).
# Layers are applied in order: pop → interstates → cities.
_SPC_OVERLAY_BASE = f"{_SPC_OUTLOOK_BASE}/imgs_v2"
_SPC_REFERENCE_OVERLAYS = [
    f"{_SPC_OVERLAY_BASE}/pop.png",
    f"{_SPC_OVERLAY_BASE}/interstates.png",
    f"{_SPC_OVERLAY_BASE}/cities.png",
]

def _spc_layers(outlook_url: str) -> list[str]:
    """Return a bottom-to-top layer list for an SPC outlook image."""
    return [outlook_url, *_SPC_REFERENCE_OVERLAYS]


# Image entity definitions: key, display name, layer_urls (bottom→top), MIME type.
# SPC entries use ``layer_urls`` so the outlook image is composited below the
# reference overlays (pop centres, interstates, city labels).  When PIL is not
# available the first entry — the complete SPC outlook PNG — is shown on its own.
# NHC entries use ``url`` only (no compositing needed).
SPC_IMAGE_DEFS = [
    {
        "key": "spc_day1_categorical",
        "name": "SPC Day 1 Categorical Outlook",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day1otlk.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day1_tornado_prob",
        "name": "SPC Day 1 Tornado Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day1probotlk_torn.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day1_hail_prob",
        "name": "SPC Day 1 Hail Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day1probotlk_hail.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day1_wind_prob",
        "name": "SPC Day 1 Wind Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day1probotlk_wind.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day2_categorical",
        "name": "SPC Day 2 Categorical Outlook",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day2otlk.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day2_tornado_prob",
        "name": "SPC Day 2 Tornado Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day2probotlk_torn.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day2_hail_prob",
        "name": "SPC Day 2 Hail Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day2probotlk_hail.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day2_wind_prob",
        "name": "SPC Day 2 Wind Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day2probotlk_wind.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day3_categorical",
        "name": "SPC Day 3 Categorical Outlook",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day3otlk.png"),
        "content_type": "image/png",
    },
    {
        "key": "nhc_atlantic_2day",
        "name": "NHC Atlantic 2-Day Tropical Outlook",
        "url": "https://www.nhc.noaa.gov/xgtwo/two_atl_2d0.png",
        "content_type": "image/png",
    },
    {
        "key": "nhc_atlantic_7day",
        "name": "NHC Atlantic 7-Day Tropical Outlook",
        "url": "https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png",
        "content_type": "image/png",
    },
    {
        "key": "nhc_pacific_2day",
        "name": "NHC Eastern Pacific 2-Day Tropical Outlook",
        "url": "https://www.nhc.noaa.gov/xgtwo/two_pac_2d0.png",
        "content_type": "image/png",
    },
]

# ---------------------------------------------------------------------------
# SPC GeoJSON URLs for point-in-polygon risk detection
# Each URL returns a FeatureCollection with polygon risk areas.
# Categorical: LABEL property → "HIGH","MDT","ENH","SLGT","MRGL","TSTM"
# Hazard-specific: LABEL property → decimal probability string ("0.02","0.05",
#   "0.10","0.15","0.30","0.45","0.60") or "0.10sig" for significant severe.
# Correct URL format uses the no-layered (donut-hole) GeoJSON variant.
# ---------------------------------------------------------------------------
SPC_GEOJSON_URLS: dict[str, str] = {
    "day1_categorical": f"{_SPC_OUTLOOK_BASE}/day1otlk_cat.nolyr.geojson",
    "day2_categorical": f"{_SPC_OUTLOOK_BASE}/day2otlk_cat.nolyr.geojson",
    "day3_categorical": f"{_SPC_OUTLOOK_BASE}/day3otlk_cat.nolyr.geojson",
    "day1_tornado":     f"{_SPC_OUTLOOK_BASE}/day1otlk_torn.nolyr.geojson",
    "day1_hail":        f"{_SPC_OUTLOOK_BASE}/day1otlk_hail.nolyr.geojson",
    "day1_wind":        f"{_SPC_OUTLOOK_BASE}/day1otlk_wind.nolyr.geojson",
    "day2_tornado":     f"{_SPC_OUTLOOK_BASE}/day2otlk_torn.nolyr.geojson",
    "day2_hail":        f"{_SPC_OUTLOOK_BASE}/day2otlk_hail.nolyr.geojson",
    "day2_wind":        f"{_SPC_OUTLOOK_BASE}/day2otlk_wind.nolyr.geojson",
}

# SPC categorical risk display names, ordered highest → lowest
SPC_RISK_ORDER: list[str] = [
    "High", "Moderate", "Enhanced", "Slight", "Marginal", "General Thunder",
]

# Map SPC categorical LABEL → display name
SPC_CATEGORICAL_LABEL_MAP: dict[str, str] = {
    "HIGH": "High",
    "MDT":  "Moderate",
    "ENH":  "Enhanced",
    "SLGT": "Slight",
    "MRGL": "Marginal",
    "TSTM": "General Thunder",
}

# Storm proximity thresholds (statute miles from storm center)
STORM_PROXIMITY_CLOSE_MILES: int = 300
STORM_PROXIMITY_FAR_MILES: int = 500

# Location change threshold (decimal degrees) that triggers a NWS point re-fetch (~7 miles)
LOCATION_CHANGE_THRESHOLD: float = 0.1

# Maximum forecast periods to store (14 = 7 day/night pairs)
MAX_FORECAST_PERIODS: int = 14

# ---------------------------------------------------------------------------
# SPC convective outlook issuance schedule (UTC hour, minute).
# Source: https://www.spc.noaa.gov/misc/about.html (Convective Outlook Issuance Times)
#   Day 1 Outlook — 0600Z, 1300Z, 1630Z, 2000Z, 0100Z
#   Day 2 Outlook — 1 AM CST/CDT (0700Z/0600Z) and 1730Z
#   Day 3 Outlook — 2:30 AM CST/CDT (0830Z/0730Z) and 1930Z
# The Day 2/Day 3 morning issuances are published in local Central time rather
# than a fixed UTC time, so both the CST and CDT variants are included below;
# the extra trigger a few times a year is harmless since fetches are cheap and
# conditionally cached (ETag/Last-Modified).
# ---------------------------------------------------------------------------
SPC_OUTLOOK_SCHEDULE_UTC: list[tuple[int, int]] = [
    (1, 0),    # Day 1 (0100Z)
    (6, 0),    # Day 1 (0600Z) / Day 2 morning (CDT)
    (7, 0),    # Day 2 morning (CST) / Day 3 morning (CDT, approx)
    (8, 0),    # Day 3 morning (CST, approx)
    (13, 0),   # Day 1 (1300Z)
    (16, 30),  # Day 1 (1630Z)
    (17, 30),  # Day 2 afternoon (1730Z)
    (19, 30),  # Day 3 afternoon (1930Z)
    (20, 0),   # Day 1 (2000Z)
]

# Minutes to wait after a scheduled issuance time before fetching, so SPC has
# time to publish the updated PNG/GeoJSON files on their web server.
SPC_FETCH_DELAY_MINUTES: int = 5
