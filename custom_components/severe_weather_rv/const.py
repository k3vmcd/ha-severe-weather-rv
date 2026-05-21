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

# NOAA ArcGIS MapServer export base URL for SPC outlooks.
# This service is not Cloudflare-protected and is publicly accessible.
# Layer IDs verified 2026-05 against mapservices.weather.noaa.gov services.
# transparent=true so the weather polygons can be composited over reference layers.
_SPC_MAPSERVER_BASE = (
    "https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/"
    "SPC_wx_outlks/MapServer/export"
    "?bbox=-126.0,23.0,-66.0,50.5&bboxSR=4326"
    "&size=1024,630&imageSR=4326&format=png&transparent=true&f=image"
)

# NOAA nowcoast reference map layers used as background for SPC cameras.
# Each URL returns a transparent PNG with its geographic features rendered;
# they are composited in order (bottom → top) before the weather polygons.
_NOWCOAST_REF = (
    "https://nowcoast.noaa.gov/arcgis/rest/services/nowcoast/{service}/MapServer/export"
    "?bbox=-126.0,23.0,-66.0,50.5&bboxSR=4326"
    "&size=1024,630&imageSR=4326&format=png&transparent=true&f=image"
)
NOWCOAST_REFERENCE_URLS = [
    # State and county boundaries — geographic orientation base
    _NOWCOAST_REF.format(service="reference_us_stco"),
    # Population density / populated places overlay
    _NOWCOAST_REF.format(service="reference_us_pop_places"),
    # Interstates and major highways
    _NOWCOAST_REF.format(service="reference_us_intrstates_major_roads_hvywys"),
    # Major cities and populated place labels
    _NOWCOAST_REF.format(service="reference_us_cities"),
]

# Camera definitions: key, display name, URL, MIME type, suggested refresh (seconds)
# SPC cameras include reference_urls so the weather layer is composited on top of
# the standard NWS reference map (state/county borders, population, interstates, cities).
SPC_CAMERAS = [
    {
        "key": "spc_day1_categorical",
        "name": "SPC Day 1 Categorical Outlook",
        "url": _SPC_MAPSERVER_BASE + "&layers=show:1",
        "content_type": "image/png",
        "reference_urls": NOWCOAST_REFERENCE_URLS,
    },
    {
        "key": "spc_day1_tornado_prob",
        "name": "SPC Day 1 Tornado Probability",
        "url": _SPC_MAPSERVER_BASE + "&layers=show:3",
        "content_type": "image/png",
        "reference_urls": NOWCOAST_REFERENCE_URLS,
    },
    {
        "key": "spc_day1_hail_prob",
        "name": "SPC Day 1 Hail Probability",
        "url": _SPC_MAPSERVER_BASE + "&layers=show:5",
        "content_type": "image/png",
        "reference_urls": NOWCOAST_REFERENCE_URLS,
    },
    {
        "key": "spc_day1_wind_prob",
        "name": "SPC Day 1 Wind Probability",
        "url": _SPC_MAPSERVER_BASE + "&layers=show:7",
        "content_type": "image/png",
        "reference_urls": NOWCOAST_REFERENCE_URLS,
    },
    {
        "key": "spc_day2_categorical",
        "name": "SPC Day 2 Categorical Outlook",
        "url": _SPC_MAPSERVER_BASE + "&layers=show:9",
        "content_type": "image/png",
        "reference_urls": NOWCOAST_REFERENCE_URLS,
    },
    {
        "key": "spc_day2_tornado_prob",
        "name": "SPC Day 2 Tornado Probability",
        "url": _SPC_MAPSERVER_BASE + "&layers=show:11",
        "content_type": "image/png",
        "reference_urls": NOWCOAST_REFERENCE_URLS,
    },
    {
        "key": "spc_day2_hail_prob",
        "name": "SPC Day 2 Hail Probability",
        "url": _SPC_MAPSERVER_BASE + "&layers=show:13",
        "content_type": "image/png",
        "reference_urls": NOWCOAST_REFERENCE_URLS,
    },
    {
        "key": "spc_day3_categorical",
        "name": "SPC Day 3 Categorical Outlook",
        "url": _SPC_MAPSERVER_BASE + "&layers=show:17",
        "content_type": "image/png",
        "reference_urls": NOWCOAST_REFERENCE_URLS,
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
