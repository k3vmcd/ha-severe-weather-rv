"""Camera platform for Severe Weather RV Monitor — SPC and NHC outlook maps."""
from __future__ import annotations

import logging
import time

import aiohttp

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SPC_CAMERAS,
    NWS_USER_AGENT,
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
        SevereWeatherCamera(entry, cam_def, scan_interval)
        for cam_def in SPC_CAMERAS
    )


class SevereWeatherCamera(Camera):
    """Camera entity that fetches and caches remote weather map images."""

    def __init__(
        self,
        entry: ConfigEntry,
        cam_def: dict,
        scan_interval: int,
    ) -> None:
        super().__init__()
        self._entry = entry
        self._cam_def = cam_def
        self._scan_interval = scan_interval
        self._attr_name = cam_def["name"]
        self._attr_unique_id = f"{entry.entry_id}_{cam_def['key']}"
        self._attr_is_streaming = False
        self._content_type_override = cam_def["content_type"]
        self._image_cache: bytes | None = None
        self._last_fetch: float = 0.0

    @property
    def content_type(self) -> str:
        return self._content_type_override

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
        headers = {"User-Agent": NWS_USER_AGENT}
        timeout = aiohttp.ClientTimeout(total=20)

        try:
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url) as resp:
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
