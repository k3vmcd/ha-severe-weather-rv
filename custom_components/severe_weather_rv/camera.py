"""Camera platform for Severe Weather RV Monitor — SPC and NHC outlook maps."""
from __future__ import annotations

import logging
import time

import aiohttp

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SPC_CAMERAS,
    CONF_OUTLOOK_SCAN_INTERVAL,
    DEFAULT_OUTLOOK_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a camera entity for each SPC/NHC map."""
    scan_interval = entry.options.get(CONF_OUTLOOK_SCAN_INTERVAL, DEFAULT_OUTLOOK_SCAN_INTERVAL)
    async_add_entities(
        SevereWeatherCamera(hass, entry, cam_def, scan_interval)
        for cam_def in SPC_CAMERAS
    )


class SevereWeatherCamera(Camera):
    """Camera entity that fetches and caches remote weather map images."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        cam_def: dict,
        scan_interval: int,
    ) -> None:
        super().__init__()
        self._hass = hass
        self._entry = entry
        self._cam_def = cam_def
        self._scan_interval = scan_interval
        self._attr_name = cam_def["name"]
        self._attr_unique_id = f"{entry.entry_id}_{cam_def['key']}"
        self._attr_is_streaming = False
        self._attr_content_type = cam_def["content_type"]
        self._image_cache: bytes | None = None
        self._last_fetch: float = 0.0

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Severe Weather RV Monitor",
            "manufacturer": "NOAA / NWS / SPC / NHC",
            "model": "Dynamic GPS-Based Weather Monitor",
            "entry_type": "service",
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the latest cached image, refreshing if stale."""
        now = time.monotonic()
        age = now - self._last_fetch

        if self._image_cache is None or age >= self._scan_interval:
            await self._fetch_image()

        return self._image_cache

    async def _fetch_image(self) -> None:
        """Fetch the remote image and update the cache."""
        url = self._cam_def["url"]
        session = async_get_clientsession(self._hass)
        timeout = aiohttp.ClientTimeout(total=30)

        try:
            async with session.get(url, timeout=timeout) as resp:
                if resp.status == 200:
                    self._image_cache = await resp.read()
                    self._last_fetch = time.monotonic()
                    _LOGGER.debug(
                        "Fetched %s (%d bytes)", self._cam_def["key"], len(self._image_cache)
                    )
                else:
                    _LOGGER.warning(
                        "Camera %s: HTTP %s from %s",
                        self._cam_def["key"],
                        resp.status,
                        url,
                    )
        except aiohttp.ClientError as exc:
            _LOGGER.warning("Network error fetching %s: %s", self._cam_def["key"], exc)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Unexpected error fetching %s: %s", self._cam_def["key"], exc)
