"""Severe Weather RV Monitor integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_utc_time_change

from .const import DOMAIN, SPC_OUTLOOK_SCHEDULE_UTC, SPC_FETCH_DELAY_MINUTES
from .coordinator import SevereWeatherCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "image"]


def _buffered_time(hour: int, minute: int, delay_minutes: int) -> tuple[int, int]:
    """Add a delay (minutes) to an (hour, minute) UTC time, wrapping at 24h."""
    total = (hour * 60 + minute + delay_minutes) % (24 * 60)
    return total // 60, total % 60


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Severe Weather RV from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = SevereWeatherCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the entry if options change (updates scan interval etc.)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Force a full refresh (risk sensors + SPC map images) shortly after each
    # known SPC convective-outlook issuance time, instead of waiting for the
    # next forecast_scan_interval poll.
    async def _scheduled_spc_refresh(_now) -> None:
        await coordinator.async_force_refresh()

    for hour, minute in SPC_OUTLOOK_SCHEDULE_UTC:
        b_hour, b_minute = _buffered_time(hour, minute, SPC_FETCH_DELAY_MINUTES)
        entry.async_on_unload(
            async_track_utc_time_change(
                hass, _scheduled_spc_refresh, hour=b_hour, minute=b_minute, second=0
            )
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
