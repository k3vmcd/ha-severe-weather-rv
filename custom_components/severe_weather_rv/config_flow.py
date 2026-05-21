"""Config flow for Severe Weather RV Monitor."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_GPS_TYPE,
    CONF_GPS_ENTITY,
    CONF_GPS_LAT_ENTITY,
    CONF_GPS_LON_ENTITY,
    CONF_ALERT_SCAN_INTERVAL,
    CONF_OUTLOOK_SCAN_INTERVAL,
    GPS_TYPE_DEVICE_TRACKER,
    GPS_TYPE_INPUT_NUMBER,
    DEFAULT_ALERT_SCAN_INTERVAL,
    DEFAULT_OUTLOOK_SCAN_INTERVAL,
)


class SevereWeatherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._gps_type: str = GPS_TYPE_DEVICE_TRACKER

    # ------------------------------------------------------------------
    # Step 1: Choose GPS source type
    # ------------------------------------------------------------------

    async def async_step_user(self, user_input: dict | None = None):
        """Show GPS source type picker."""
        if user_input is not None:
            self._gps_type = user_input[CONF_GPS_TYPE]
            if self._gps_type == GPS_TYPE_DEVICE_TRACKER:
                return await self.async_step_device_tracker()
            return await self.async_step_input_numbers()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GPS_TYPE, default=GPS_TYPE_DEVICE_TRACKER): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "label": "Device Tracker / Person entity (has lat/lon attributes)",
                                    "value": GPS_TYPE_DEVICE_TRACKER,
                                },
                                {
                                    "label": "Two input_number helpers (separate latitude & longitude)",
                                    "value": GPS_TYPE_INPUT_NUMBER,
                                },
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 2a: Device tracker path
    # ------------------------------------------------------------------

    async def async_step_device_tracker(self, user_input: dict | None = None):
        """Pick a device_tracker or person entity."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_GPS_ENTITY]
            state = self.hass.states.get(entity_id)
            if state is None:
                errors[CONF_GPS_ENTITY] = "entity_not_found"
            elif state.attributes.get("latitude") is None:
                errors[CONF_GPS_ENTITY] = "no_coordinates"
            else:
                return self.async_create_entry(
                    title="Severe Weather RV Monitor",
                    data={
                        CONF_GPS_TYPE: GPS_TYPE_DEVICE_TRACKER,
                        CONF_GPS_ENTITY: entity_id,
                    },
                    options={
                        CONF_ALERT_SCAN_INTERVAL: DEFAULT_ALERT_SCAN_INTERVAL,
                        CONF_OUTLOOK_SCAN_INTERVAL: DEFAULT_OUTLOOK_SCAN_INTERVAL,
                    },
                )

        return self.async_show_form(
            step_id="device_tracker",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GPS_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["device_tracker", "person"]
                        )
                    )
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2b: Input number pair path
    # ------------------------------------------------------------------

    async def async_step_input_numbers(self, user_input: dict | None = None):
        """Pick latitude and longitude input_number helpers."""
        errors: dict[str, str] = {}

        if user_input is not None:
            lat_id = user_input[CONF_GPS_LAT_ENTITY]
            lon_id = user_input[CONF_GPS_LON_ENTITY]
            lat_state = self.hass.states.get(lat_id)
            lon_state = self.hass.states.get(lon_id)

            if lat_state is None:
                errors[CONF_GPS_LAT_ENTITY] = "entity_not_found"
            elif lon_state is None:
                errors[CONF_GPS_LON_ENTITY] = "entity_not_found"
            else:
                try:
                    float(lat_state.state)
                    float(lon_state.state)
                    return self.async_create_entry(
                        title="Severe Weather RV Monitor",
                        data={
                            CONF_GPS_TYPE: GPS_TYPE_INPUT_NUMBER,
                            CONF_GPS_LAT_ENTITY: lat_id,
                            CONF_GPS_LON_ENTITY: lon_id,
                        },
                        options={
                            CONF_ALERT_SCAN_INTERVAL: DEFAULT_ALERT_SCAN_INTERVAL,
                            CONF_OUTLOOK_SCAN_INTERVAL: DEFAULT_OUTLOOK_SCAN_INTERVAL,
                        },
                    )
                except ValueError:
                    errors["base"] = "invalid_coordinates"

        return self.async_show_form(
            step_id="input_numbers",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GPS_LAT_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="input_number")
                    ),
                    vol.Required(CONF_GPS_LON_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="input_number")
                    ),
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Options flow entry point
    # ------------------------------------------------------------------

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return SevereWeatherOptionsFlow(config_entry)


class SevereWeatherOptionsFlow(config_entries.OptionsFlow):
    """Handle options (scan intervals) updates without reinstalling."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ALERT_SCAN_INTERVAL,
                        default=current.get(CONF_ALERT_SCAN_INTERVAL, DEFAULT_ALERT_SCAN_INTERVAL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=60,
                            max=3600,
                            step=60,
                            unit_of_measurement="seconds",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        CONF_OUTLOOK_SCAN_INTERVAL,
                        default=current.get(CONF_OUTLOOK_SCAN_INTERVAL, DEFAULT_OUTLOOK_SCAN_INTERVAL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1800,
                            max=86400,
                            step=1800,
                            unit_of_measurement="seconds",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
        )
