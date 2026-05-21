# Severe Weather RV Monitor

A Home Assistant custom integration that provides **real-time, GPS-driven severe weather monitoring** for full-time travelers. Dynamically follows your RV's position — no manual location updates, no YAML to edit.

Data sources: **NOAA NWS Alerts API**, **SPC (Storm Prediction Center)**, **NHC (National Hurricane Center)**. All free, no API keys required.

---

## Features

- **Dynamic GPS tracking** — reads coordinates from any `device_tracker`, `person`, or pair of `input_number` helpers
- **Real-time NWS alerts** — all active alerts for your exact GPS point, polled every 5 minutes (configurable)
- **Derived threat levels** — separate sensors for tornado, severe thunderstorm/hail, and hurricane at `NONE / WATCH / WARNING / EMERGENCY`
- **Overall summary sensor** — single-state rollup from `ALL CLEAR` through `TORNADO EMERGENCY`
- **9 binary sensors** — granular on/off states for every threat type, great for automations
- **11 camera entities** — SPC Day 1–3 categorical outlooks, Day 1–2 tornado/hail probability maps, NHC 2-day and 7-day Atlantic/Pacific tropical outlooks
- **NHC storm tracking** — count and attributes for all active named storms
- **Automation blueprints** — real-time threat alert + daily morning briefing, installable from the UI

---

## Requirements

- Home Assistant **2023.1.0** or newer
- [HACS](https://hacs.xyz) installed
- Your RV's GPS position available as a `device_tracker`, `person`, or two `input_number` helpers in HA

### Recommended frontend cards (install via HACS Frontend)
- `mushroom` — status tiles
- `lovelace-card-mod` — conditional color styling (optional)

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → three-dot menu → **Custom repositories**
2. Add URL: `https://github.com/yourusername/ha-severe-weather-rv`  
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

That's it. All sensors and cameras are created automatically.

### Options (adjustable after setup)

Go to **Settings → Devices & Services → Severe Weather RV Monitor → Configure**:

| Option | Default | Description |
|--------|---------|-------------|
| Alert poll interval | 300 s (5 min) | How often NWS alerts are refreshed |
| Outlook map refresh | 3600 s (1 hr) | How often SPC/NHC camera images are re-fetched |

---

## Automation Blueprints

Two blueprints are included and copied to your `blueprints/` directory on install.

### Import via UI

1. Go to **Settings → Automations & Scenes → Blueprints**
2. Click **Import Blueprint**
3. Paste the raw GitHub URL for each blueprint:
   - Threat alert: `https://raw.githubusercontent.com/yourusername/ha-severe-weather-rv/main/blueprints/automation/severe_weather_rv/threat_alert.yaml`
   - Morning briefing: `https://raw.githubusercontent.com/yourusername/ha-severe-weather-rv/main/blueprints/automation/severe_weather_rv/morning_briefing.yaml`

### Threat Alert Blueprint
Fires when any tornado, severe thunderstorm, or hurricane threat becomes active. Sends a rich notification with the SPC Day 1 outlook image attached and a tap-through to your dashboard. Supports iOS Critical Alerts for warnings.

### Morning Briefing Blueprint
Sends a daily summary at your chosen time with current threat levels and the Day 1 outlook image. Optionally only sends when the risk is elevated.

---

## Entities Created

### Sensors

| Entity | Description |
|--------|-------------|
| `sensor.severe_weather_rv_monitor_alert_count` | Total active NWS alerts at your location |
| `sensor.severe_weather_rv_monitor_threat_alert_count` | Active tornado/tstorm/hurricane alerts only |
| `sensor.severe_weather_rv_monitor_tornado_threat_level` | `NONE / WATCH / WARNING / EMERGENCY` |
| `sensor.severe_weather_rv_monitor_severe_thunderstorm_threat_level` | `NONE / WATCH / WARNING` |
| `sensor.severe_weather_rv_monitor_hurricane_threat_level` | `NONE / WATCH / WARNING / EMERGENCY / TROPICAL STORM WATCH / TROPICAL STORM WARNING` |
| `sensor.severe_weather_rv_monitor_severe_weather_summary` | Rolled-up summary: `ALL CLEAR` → `TORNADO EMERGENCY` |
| `sensor.severe_weather_rv_monitor_highest_severity` | NWS severity of most severe active alert |
| `sensor.severe_weather_rv_monitor_top_alert_headline` | Headline text of highest-priority alert |
| `sensor.severe_weather_rv_monitor_nhc_active_storms` | Count of active named tropical storms |
| `sensor.severe_weather_rv_monitor_monitored_latitude` | Currently polled latitude |
| `sensor.severe_weather_rv_monitor_monitored_longitude` | Currently polled longitude |

### Binary Sensors

| Entity | On when... |
|--------|------------|
| `binary_sensor.severe_weather_rv_monitor_active_severe_threat` | Any tornado/tstorm/hurricane alert active |
| `binary_sensor.severe_weather_rv_monitor_any_alert_active` | Any NWS alert active |
| `binary_sensor.severe_weather_rv_monitor_tornado_active` | Tornado watch or warning |
| `binary_sensor.severe_weather_rv_monitor_tornado_warning` | Tornado warning or emergency |
| `binary_sensor.severe_weather_rv_monitor_tornado_emergency` | Tornado emergency only |
| `binary_sensor.severe_weather_rv_monitor_thunderstorm_active` | Severe thunderstorm watch or warning |
| `binary_sensor.severe_weather_rv_monitor_thunderstorm_warning` | Severe thunderstorm warning only |
| `binary_sensor.severe_weather_rv_monitor_hurricane_active` | Any tropical threat |
| `binary_sensor.severe_weather_rv_monitor_hurricane_warning` | Hurricane warning or emergency |

### Cameras

| Entity | Image |
|--------|-------|
| `camera.severe_weather_rv_monitor_spc_day_1_categorical_outlook` | SPC Day 1 categorical risk |
| `camera.severe_weather_rv_monitor_spc_day_1_tornado_probability` | SPC Day 1 tornado probability |
| `camera.severe_weather_rv_monitor_spc_day_1_hail_probability` | SPC Day 1 hail probability |
| `camera.severe_weather_rv_monitor_spc_day_1_wind_probability` | SPC Day 1 wind probability |
| `camera.severe_weather_rv_monitor_spc_day_2_categorical_outlook` | SPC Day 2 categorical risk |
| `camera.severe_weather_rv_monitor_spc_day_2_tornado_probability` | SPC Day 2 tornado probability |
| `camera.severe_weather_rv_monitor_spc_day_2_hail_probability` | SPC Day 2 hail probability |
| `camera.severe_weather_rv_monitor_spc_day_3_categorical_outlook` | SPC Day 3 categorical risk |
| `camera.severe_weather_rv_monitor_nhc_atlantic_2_day_tropical_outlook` | NHC Atlantic 2-day tropical outlook |
| `camera.severe_weather_rv_monitor_nhc_atlantic_7_day_tropical_outlook` | NHC Atlantic 7-day tropical outlook |
| `camera.severe_weather_rv_monitor_nhc_eastern_pacific_2_day_tropical_outlook` | NHC Eastern Pacific 2-day |

---

## Dashboard

Create a new dashboard view and paste this YAML (Edit Dashboard → Raw configuration editor).  
Requires `mushroom` cards from HACS.

```yaml
title: Severe Weather
path: severe-weather
icon: mdi:weather-lightning-rainy
cards:

  # ── Summary header ────────────────────────────────────────────────────
  - type: custom:mushroom-template-card
    primary: "{{ states('sensor.severe_weather_rv_monitor_severe_weather_summary') }}"
    secondary: "{{ states('sensor.severe_weather_rv_monitor_top_alert_headline') }}"
    icon: mdi:weather-lightning-rainy
    icon_color: >
      {% set s = states('sensor.severe_weather_rv_monitor_severe_weather_summary') %}
      {{ 'red' if 'EMERGENCY' in s or 'WARNING' in s
         else 'orange' if 'THREAT' in s or 'WATCH' in s
         else 'green' }}
    multiline_secondary: true
    tap_action:
      action: none

  # ── Threat tiles ──────────────────────────────────────────────────────
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-template-card
        primary: Tornado
        secondary: "{{ states('sensor.severe_weather_rv_monitor_tornado_threat_level') }}"
        icon: mdi:weather-tornado
        fill_container: true
        icon_color: >
          {% set t = states('sensor.severe_weather_rv_monitor_tornado_threat_level') %}
          {{ 'red' if t in ['WARNING','EMERGENCY'] else 'orange' if t == 'WATCH' else 'green' }}

      - type: custom:mushroom-template-card
        primary: Hail / Tstorm
        secondary: "{{ states('sensor.severe_weather_rv_monitor_severe_thunderstorm_threat_level') }}"
        icon: mdi:weather-hail
        fill_container: true
        icon_color: >
          {% set s = states('sensor.severe_weather_rv_monitor_severe_thunderstorm_threat_level') %}
          {{ 'red' if s == 'WARNING' else 'orange' if s == 'WATCH' else 'green' }}

      - type: custom:mushroom-template-card
        primary: Hurricane
        secondary: "{{ states('sensor.severe_weather_rv_monitor_hurricane_threat_level') }}"
        icon: mdi:weather-hurricane
        fill_container: true
        icon_color: >
          {% set h = states('sensor.severe_weather_rv_monitor_hurricane_threat_level') %}
          {{ 'red' if 'WARNING' in h or 'EMERGENCY' in h else 'orange' if 'WATCH' in h else 'green' }}

  # ── Location + alert count ────────────────────────────────────────────
  - type: horizontal-stack
    cards:
      - type: custom:mushroom-template-card
        primary: "{{ states('sensor.severe_weather_rv_monitor_alert_count') }} Active Alerts"
        secondary: >
          {{ states('sensor.severe_weather_rv_monitor_monitored_latitude') }}°,
          {{ states('sensor.severe_weather_rv_monitor_monitored_longitude') }}°
        icon: mdi:map-marker-radius
        fill_container: true

      - type: custom:mushroom-template-card
        primary: "{{ states('sensor.severe_weather_rv_monitor_nhc_active_storms') }} Named Storm(s)"
        secondary: "NHC Active Tropics"
        icon: mdi:weather-hurricane
        fill_container: true

  # ── Active alert details ──────────────────────────────────────────────
  - type: conditional
    conditions:
      - entity: binary_sensor.severe_weather_rv_monitor_any_alert_active
        state: "on"
    card:
      type: markdown
      title: "Active NWS Alerts"
      content: >
        {% set alerts = state_attr('sensor.severe_weather_rv_monitor_top_alert_headline', 'all_alerts') or [] %}
        {% if alerts | length == 0 %}
        ✅ No active alerts.
        {% else %}
        {% for a in alerts %}
        **{{ a.event }}** — {{ a.severity }}
        *{{ a.headline }}*
        Expires: {{ a.expires }}
        ---
        {% endfor %}
        {% endif %}

  # ── SPC Day 1 maps ────────────────────────────────────────────────────
  - type: markdown
    content: "## SPC Convective Outlooks"

  - type: picture-entity
    entity: camera.severe_weather_rv_monitor_spc_day_1_categorical_outlook
    name: "Day 1 — Categorical Risk"
    show_state: false
    tap_action:
      action: url
      url_path: "https://www.spc.noaa.gov/products/outlook/"

  - type: horizontal-stack
    cards:
      - type: picture-entity
        entity: camera.severe_weather_rv_monitor_spc_day_1_tornado_probability
        name: "Tornado Prob"
        show_state: false
        tap_action:
          action: url
          url_path: "https://www.spc.noaa.gov/products/outlook/day1otlk.html"

      - type: picture-entity
        entity: camera.severe_weather_rv_monitor_spc_day_1_hail_probability
        name: "Hail Prob"
        show_state: false
        tap_action:
          action: url
          url_path: "https://www.spc.noaa.gov/products/outlook/day1otlk.html"

  - type: horizontal-stack
    cards:
      - type: picture-entity
        entity: camera.severe_weather_rv_monitor_spc_day_2_categorical_outlook
        name: "Day 2 Categorical"
        show_state: false

      - type: picture-entity
        entity: camera.severe_weather_rv_monitor_spc_day_3_categorical_outlook
        name: "Day 3 Categorical"
        show_state: false

  # ── NHC Hurricane maps ────────────────────────────────────────────────
  - type: markdown
    content: "## Tropical / Hurricane Outlook"

  - type: horizontal-stack
    cards:
      - type: picture-entity
        entity: camera.severe_weather_rv_monitor_nhc_atlantic_2_day_tropical_outlook
        name: "Atlantic 2-Day"
        show_state: false
        tap_action:
          action: url
          url_path: "https://www.nhc.noaa.gov"

      - type: picture-entity
        entity: camera.severe_weather_rv_monitor_nhc_atlantic_7_day_tropical_outlook
        name: "Atlantic 7-Day"
        show_state: false
        tap_action:
          action: url
          url_path: "https://www.nhc.noaa.gov"
```

---

## Notes

- **NWS API** requires a `User-Agent` header per their terms of service. The integration sends `(severe_weather_rv Home Assistant integration)` — update `const.py` with your contact info if you fork this for personal use.
- SPC outlook images are updated at approximately 0600z, 1300z, 1630z, and 2000z daily. The hourly camera refresh is intentionally conservative to avoid hammering SPC servers.
- If the NWS API returns no data immediately after setup, allow up to one poll interval (default 5 min) for the first refresh to complete.

---

## License

MIT
