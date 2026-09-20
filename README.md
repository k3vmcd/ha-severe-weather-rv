# Severe Weather RV Monitor

A Home Assistant custom integration that provides **real-time, GPS-driven severe weather monitoring** for full-time travelers. Dynamically follows your RV's position — no manual location updates, no YAML to edit.

Data sources: **NOAA NWS Alerts API**, **SPC (Storm Prediction Center)**, **NHC (National Hurricane Center)**. All free, no API keys required.

---

## Features

- **Dynamic GPS tracking** — reads coordinates from any `device_tracker`, `person`, or pair of `input_number` helpers
- **Real-time NWS alerts** — all active alerts for your exact GPS point, polled every 5 minutes (configurable)
- **Derived threat levels** — separate sensors for tornado, severe thunderstorm, and hurricane at `NONE / WATCH / WARNING / EMERGENCY`
- **Action Level** — single sensor rolls up all data into `NORMAL / MONITOR / PREPARE / ACT NOW` with plain-English reasons and recommended actions
- **Hourly rain analysis** — identifies specific rain/storm windows ("⛈ 2PM–5PM, 80% chance, 4h") rather than generic "Showers Possible"
- **Day planning summary** — tells you the best clear window and whether it's worth making outdoor plans
- **NWS 7-day forecast** — period-by-period forecast with precipitation probability
- **NWS current observations** — temperature, wind, humidity, visibility from nearest ASOS/AWOS station
- **SPC outlook risk** — point-in-polygon detection for 9 SPC GeoJSON layers (Day 1–3 categorical, Day 1–2 tornado/hail/wind probabilities)
- **NHC storm tracking** — count and distance to all active named tropical storms
- **Image entities** — SPC Day 1–3 categorical/probability maps + NHC Atlantic/Pacific outlooks, always pre-fetched in the background so the dashboard never has to wait for one to load
- **Automation blueprints** — real-time threat alert + daily morning briefing, importable from the UI

---

## Requirements

- Home Assistant **2026.5.0** or newer (see `manifest.json`)
- [HACS](https://hacs.xyz) installed
- Your RV's GPS position available as a `device_tracker`, `person`, or two `input_number` helpers in HA

### Recommended frontend cards (install via HACS → Frontend)
- `mushroom` — color-coded action-level status card
- `config-template-card` — dynamic Windy animated radar (optional)

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → three-dot menu → **Custom repositories**
2. Add URL: `https://github.com/k3vmcd/ha-severe-weather-rv`  
   Category: **Integration**
3. Find **Severe Weather RV Monitor** in HACS and click **Download**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** → search **Severe Weather RV Monitor**

### Manual installation

1. Copy the `custom_components/severe_weather_rv/` folder into your HA config's `custom_components/` directory
2. Copy the `blueprints/` folder into your HA config's `blueprints/` directory
3. Restart Home Assistant
4. Add the integration via **Settings → Devices & Services**

---

## Configuration

The setup wizard has two steps:

**Step 1 — GPS source type**
- *Device Tracker / Person* — choose any entity with `latitude`/`longitude` attributes (e.g. the HA Companion app device tracker for your phone mounted in the RV)
- *Input Number helpers* — choose two existing `input_number` helpers for latitude and longitude

**Step 2 — Pick your entity/entities**

That's it. All sensors and images are created automatically.

### Options (adjustable after setup)

Go to **Settings → Devices & Services → Severe Weather RV Monitor → Configure**:

| Option | Default | Description |
|--------|---------|-------------|
| Alert poll interval | 300 s (5 min) | How often NWS alerts are refreshed |
| Outlook map refresh | 3600 s (1 hr) | Fallback refresh interval for SPC/NHC map images |

SPC Day 1–3 map images are also proactively refreshed in the background a few
minutes after each real SPC convective-outlook issuance time (see Notes below),
so the cached image is already current before anyone opens the dashboard —
the interval above is just a safety-net fallback.

---

## Automation Blueprints

Two blueprints are included and copied to your `blueprints/` directory on install.

### Import via UI

1. Go to **Settings → Automations & Scenes → Blueprints**
2. Click **Import Blueprint**
3. Paste the raw GitHub URL for each blueprint:
   - Threat alert: `https://raw.githubusercontent.com/k3vmcd/ha-severe-weather-rv/main/blueprints/automation/severe_weather_rv/threat_alert.yaml`
   - Morning briefing: `https://raw.githubusercontent.com/k3vmcd/ha-severe-weather-rv/main/blueprints/automation/severe_weather_rv/morning_briefing.yaml`

### Threat Alert Blueprint
Fires when any tornado, severe thunderstorm, or hurricane threat becomes active. Sends a rich notification with the SPC Day 1 outlook image attached and a tap-through to your dashboard. Supports iOS Critical Alerts for warnings.

### Morning Briefing Blueprint
Sends a daily summary at your chosen time with current threat levels and the Day 1 outlook image. Optionally only sends when the risk is elevated.

---

## Example Automations (Non-Blueprint)

Blueprints are great for a one-click UI import, but once an automation is created *from* a blueprint, Home Assistant's editor only exposes the blueprint's declared `input:` fields — you can't touch the underlying triggers/conditions/actions without unlinking it. If you want full control to keep customizing an automation over time, use the plain YAML examples in [`automations/`](automations/) instead:

- Copy the file's contents into an automation (UI **Edit in YAML** on a new automation, or your `automations.yaml`)
- Replace the `notify.*` targets and any hardcoded entity IDs with your own
- Edit triggers/conditions/actions freely — there's no blueprint link to break

| File | What it does |
|------|---------------|
| [`automations/severe_weather_alerts.yaml`](automations/severe_weather_alerts.yaml) | Combines SPC Day 1/2 hail risk changes with tornado/hurricane threat-level changes into one automation, with per-hazard images, new-vs-changed wording, and iOS critical alerts on WARNING/EMERGENCY. Notifies two phone groups. |

This doesn't replace the Threat Alert / SPC Risk Area blueprints — those still cover moderate/high-risk-area entry, wind-risk escalation, and storm proximity, which this example doesn't. Use whichever mechanism fits: blueprints for quick setup or sharing with other users, raw automations when you want to keep hand-tuning the logic.

---

## Entities Created

### Sensors (36 total)

| Entity | Description |
|--------|-------------|
| `sensor.severe_weather_rv_monitor_action_level` | Action level: `NORMAL / MONITOR / PREPARE / ACT NOW`. Attributes: `reasons` (list), `recommendations` (list) |
| `sensor.severe_weather_rv_monitor_severe_weather_summary` | Rolled-up summary: `ALL CLEAR` → `TORNADO EMERGENCY` |
| `sensor.severe_weather_rv_monitor_tornado_threat_level` | `NONE / WATCH / WARNING / EMERGENCY` |
| `sensor.severe_weather_rv_monitor_severe_thunderstorm_threat_level` | `NONE / WATCH / WARNING` |
| `sensor.severe_weather_rv_monitor_hurricane_threat_level` | `NONE / WATCH / WARNING / EMERGENCY / TROPICAL STORM WATCH / TROPICAL STORM WARNING` |
| `sensor.severe_weather_rv_monitor_alert_count` | Total active NWS alerts |
| `sensor.severe_weather_rv_monitor_threat_alert_count` | Active tornado/tstorm/hurricane alerts only |
| `sensor.severe_weather_rv_monitor_top_alert_headline` | Headline of highest-priority alert. Attribute: `all_alerts` (list) |
| `sensor.severe_weather_rv_monitor_highest_alert_severity` | NWS severity of most severe active alert |
| `sensor.severe_weather_rv_monitor_rain_summary` | Plain-English rain window: e.g. "⛈ 2PM–5PM (4h, 80%)". Attributes: `rain_windows`, `hourly_periods` |
| `sensor.severe_weather_rv_monitor_day_outlook` | Day planning summary, e.g. "Mostly clear. Best window: 9AM–12PM" |
| `sensor.severe_weather_rv_monitor_forecast_today` | NWS short forecast for today |
| `sensor.severe_weather_rv_monitor_forecast_tonight` | NWS short forecast for tonight |
| `sensor.severe_weather_rv_monitor_precipitation_chance_today` | Today's precipitation probability (%) |
| `sensor.severe_weather_rv_monitor_7_day_forecast` | Period count. Attribute: `periods` (list with name, temperature, wind, short_forecast, precip_probability) |
| `sensor.severe_weather_rv_monitor_current_conditions` | Current sky conditions from nearest ASOS station |
| `sensor.severe_weather_rv_monitor_current_temperature` | Current temperature (°F) |
| `sensor.severe_weather_rv_monitor_current_wind_speed` | Current wind speed (mph) |
| `sensor.severe_weather_rv_monitor_current_wind_direction` | Current wind direction (°) |
| `sensor.severe_weather_rv_monitor_current_humidity` | Current relative humidity (%) |
| `sensor.severe_weather_rv_monitor_current_visibility` | Current visibility (mi) |
| `sensor.severe_weather_rv_monitor_spc_day_1_risk` | SPC Day 1 categorical risk level |
| `sensor.severe_weather_rv_monitor_spc_day_2_risk` | SPC Day 2 categorical risk level |
| `sensor.severe_weather_rv_monitor_spc_day_3_risk` | SPC Day 3 categorical risk level |
| `sensor.severe_weather_rv_monitor_spc_day_1_tornado_risk` | SPC Day 1 tornado probability at your location |
| `sensor.severe_weather_rv_monitor_spc_day_1_hail_risk` | SPC Day 1 hail probability at your location |
| `sensor.severe_weather_rv_monitor_spc_day_1_wind_risk` | SPC Day 1 wind probability at your location |
| `sensor.severe_weather_rv_monitor_spc_day_2_tornado_risk` | SPC Day 2 tornado probability |
| `sensor.severe_weather_rv_monitor_spc_day_2_hail_risk` | SPC Day 2 hail probability |
| `sensor.severe_weather_rv_monitor_spc_day_2_wind_risk` | SPC Day 2 wind probability |
| `sensor.severe_weather_rv_monitor_nhc_active_storms` | Count of active named tropical storms |
| `sensor.severe_weather_rv_monitor_nearest_storm_name` | Name of nearest NHC storm |
| `sensor.severe_weather_rv_monitor_nearest_storm_distance` | Distance to nearest storm (mi) |
| `sensor.severe_weather_rv_monitor_nearest_storm_category` | Category of nearest storm |
| `sensor.severe_weather_rv_monitor_monitored_latitude` | Currently polled latitude |
| `sensor.severe_weather_rv_monitor_monitored_longitude` | Currently polled longitude |

### Binary Sensors (19 total)

| Entity | On when... |
|--------|------------|
| `binary_sensor.severe_weather_rv_monitor_active_severe_weather_threat` | Any tornado/tstorm/hurricane alert active |
| `binary_sensor.severe_weather_rv_monitor_any_weather_alert_active` | Any NWS alert active |
| `binary_sensor.severe_weather_rv_monitor_tornado_watch_or_warning` | Tornado watch or warning |
| `binary_sensor.severe_weather_rv_monitor_tornado_warning` | Tornado warning or emergency |
| `binary_sensor.severe_weather_rv_monitor_tornado_emergency` | Tornado emergency |
| `binary_sensor.severe_weather_rv_monitor_severe_thunderstorm_watch_or_warning` | Severe thunderstorm watch or warning |
| `binary_sensor.severe_weather_rv_monitor_severe_thunderstorm_warning` | Severe thunderstorm warning |
| `binary_sensor.severe_weather_rv_monitor_hurricane_or_tropical_storm_watch_or_warning` | Any tropical threat |
| `binary_sensor.severe_weather_rv_monitor_hurricane_warning` | Hurricane warning or emergency |
| `binary_sensor.severe_weather_rv_monitor_in_spc_day_1_risk_area` | Inside an SPC Day 1 risk polygon (excludes General Thunder) |
| `binary_sensor.severe_weather_rv_monitor_in_spc_day_1_moderate_or_high_risk` | Inside Moderate or High risk |
| `binary_sensor.severe_weather_rv_monitor_in_spc_day_1_tornado_risk_area` | Inside a Day 1 tornado probability polygon |
| `binary_sensor.severe_weather_rv_monitor_in_spc_day_1_hail_risk_area` | Inside a Day 1 hail probability polygon |
| `binary_sensor.severe_weather_rv_monitor_in_spc_day_1_wind_risk_area` | Inside a Day 1 wind probability polygon |
| `binary_sensor.severe_weather_rv_monitor_nhc_storm_within_300_miles` | Tropical storm within 300 mi |
| `binary_sensor.severe_weather_rv_monitor_nhc_storm_within_500_miles` | Tropical storm within 500 mi |
| `binary_sensor.severe_weather_rv_monitor_rain_likely_today` | NWS precipitation chance ≥ 40% today |
| `binary_sensor.severe_weather_rv_monitor_thunderstorm_likely_today` | Thunderstorms mentioned in today's forecast |
| `binary_sensor.severe_weather_rv_monitor_precipitation_active_now` | Active rain/snow at the nearest observation station |

### Image Entities (12 total)

| Entity | Image |
|--------|-------|
| `image.severe_weather_rv_monitor_spc_day_1_categorical_outlook` | SPC Day 1 categorical risk map |
| `image.severe_weather_rv_monitor_spc_day_1_tornado_probability` | SPC Day 1 tornado probability map |
| `image.severe_weather_rv_monitor_spc_day_1_hail_probability` | SPC Day 1 hail probability map |
| `image.severe_weather_rv_monitor_spc_day_1_wind_probability` | SPC Day 1 wind probability map |
| `image.severe_weather_rv_monitor_spc_day_2_categorical_outlook` | SPC Day 2 categorical risk map |
| `image.severe_weather_rv_monitor_spc_day_2_tornado_probability` | SPC Day 2 tornado probability map |
| `image.severe_weather_rv_monitor_spc_day_2_hail_probability` | SPC Day 2 hail probability map |
| `image.severe_weather_rv_monitor_spc_day_2_wind_probability` | SPC Day 2 wind probability map |
| `image.severe_weather_rv_monitor_spc_day_3_categorical_outlook` | SPC Day 3 categorical risk map |
| `image.severe_weather_rv_monitor_nhc_atlantic_2_day_tropical_outlook` | NHC Atlantic 2-day tropical outlook |
| `image.severe_weather_rv_monitor_nhc_atlantic_7_day_tropical_outlook` | NHC Atlantic 7-day tropical outlook |
| `image.severe_weather_rv_monitor_nhc_eastern_pacific_2_day_tropical_outlook` | NHC Eastern Pacific 2-day outlook |

---

## Dashboard

The included `lovelace_dashboard.yaml` is a single-view tab you can add to any existing dashboard.

### Layout (top to bottom)

| Section | What it shows |
|---------|---------------|
| **Action Level** | Color-coded `NORMAL / MONITOR / PREPARE / ACT NOW` with plain-English reasons and 1-line action summary |
| **Today's Plan** | Specific rain windows ("⛈ 2PM–5PM, 80%, 4h") + day outlook ("Best clear window: 9AM–12PM") |
| **Active Threats** | NWS alert count, tornado/thunderstorm/hurricane levels, SPC Day 1 risk |
| **Current Conditions + Radar** | Temp, wind, humidity, visibility + Windy animated radar |
| **Alert Details** | Full NWS alert text with expiry times |
| **7-Day Forecast** | Icon + temp + rain % per period |
| **SPC Maps** | Day 1–3 categorical and probability maps (from integration image entities) |
| **Tropical** | NHC storm tracking + Atlantic outlook maps |

### Installation

1. Open your existing dashboard → Edit → **Raw Configuration Editor**
2. Under `views:`, paste the contents of `lovelace_dashboard.yaml` (starting at `- title: Severe Weather`)

**Required HACS frontend cards:**
- `mushroom` — color-coded Action Level card
- `config-template-card` — dynamic Windy radar centered on your GPS location (optional)

If you don't have `config-template-card`, replace the Live Radar section in the YAML with a plain `iframe` card pointing at a fixed location (it just won't auto-follow your GPS position):
```yaml
- type: iframe
  url: "https://www.rainviewer.com/map.html?loc=35.0,-97.0,9&oC=true&oCS=1&oF=1&c=9&o=83&lm=1&layer=radar&sm=1&sn=1"
  aspect_ratio: 50%
```

---

## Notes

- **Upgrading from an older version:** SPC/NHC/radar pictures moved from the `camera.*` domain to the `image.*` domain (e.g. `camera.severe_weather_rv_monitor_spc_day_1_categorical_outlook` → `image.severe_weather_rv_monitor_spc_day_1_categorical_outlook`). This is required for the browser to properly cache the pictures (see below) but it means the old `camera.*` entities will show as unavailable — update any dashboards/automations referencing them (the included dashboard, blueprints, and example automation are already updated) and remove the orphaned `camera.*` entities from **Settings → Devices & Services → Entities**.
- **Why `image` instead of `camera`:** these pictures are periodically-refreshed stills, not live video, so they use HA's `image` platform. Its entity-picture URL only changes when a new picture is actually fetched, which lets the browser cache it safely — including across dashboard reloads, new tabs, and new sessions — until the next real update, instead of re-requesting it every time the dashboard loads.
- **Image size:** SPC/NHC source images (~1500–2000px wide PNGs) are downscaled to a max width of 900px and re-encoded as JPEG (quality 80) before being cached, cutting payload size roughly 10–20x versus the original full-resolution PNG. This is what keeps even a cold-cache first load fast. If Pillow isn't installed, the original full-size PNG is served as-is instead.
- **NWS API** requires a `User-Agent` header per their terms of service. The integration sends `(severe_weather_rv Home Assistant integration)` — update `const.py` with your contact info if you fork this for personal use.
- SPC issues Day 1 outlooks at 0100z, 0600z, 1300z, 1630z, and 2000z; Day 2 at ~0600/0700z and 1730z; Day 3 at ~0730/0830z and 1930z. The integration proactively re-fetches all SPC map images and risk-percentage sensors ~5 minutes after each of these times (plus once immediately on startup/reload), so the cached maps and `sensor.severe_weather_rv_monitor_spc_*_risk` entities stay in sync without anyone having to view the dashboard. The outlook scan interval above is only a fallback in case a scheduled fetch is missed.
- Hourly forecast data (used for rain windows) is fetched on the same slow-tier interval as the 7-day forecast to avoid over-polling the NWS API.
- If entities show "unavailable" immediately after setup, allow up to one poll interval (default 5 min) for the first refresh to complete.

---

## License


MIT
