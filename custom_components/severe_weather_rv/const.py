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
DEFAULT_ALERT_SCAN_INTERVAL = 300   # 5 minutes
DEFAULT_OUTLOOK_SCAN_INTERVAL = 3600  # 1 hour

# API endpoints
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
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


# Camera definitions: key, display name, layer_urls (bottom→top), MIME type.
# SPC cameras use ``layer_urls`` so the outlook image is composited below the
# reference overlays (pop centres, interstates, city labels).  When PIL is not
# available the first entry — the complete SPC outlook PNG — is shown on its own.
# NHC cameras use ``url`` only (no compositing needed).
SPC_CAMERAS = [
    {
        "key": "spc_day1_categorical",
        "name": "SPC Day 1 Categorical Outlook",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day1otlk.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day1_tornado_prob",
        "name": "SPC Day 1 Tornado Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day1probotlk_torn_v2.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day1_hail_prob",
        "name": "SPC Day 1 Hail Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day1probotlk_hail_v2.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day1_wind_prob",
        "name": "SPC Day 1 Wind Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day1probotlk_wind_v2.png"),
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
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day2probotlk_torn_v2.png"),
        "content_type": "image/png",
    },
    {
        "key": "spc_day2_hail_prob",
        "name": "SPC Day 2 Hail Probability",
        "layer_urls": _spc_layers(f"{_SPC_OUTLOOK_BASE}/day2probotlk_hail_v2.png"),
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
