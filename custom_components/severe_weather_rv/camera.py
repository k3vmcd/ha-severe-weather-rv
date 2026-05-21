"""Camera platform for Severe Weather RV Monitor — SPC and NHC outlook maps."""
from __future__ import annotations

import io
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

try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PILImage = None  # type: ignore[assignment]
    _PIL_AVAILABLE = False
    _LOGGER.warning(
        "Pillow (PIL) is not installed; SPC reference-map compositing is disabled"
    )


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
        """Fetch the remote image, compositing all layers when available.

        If ``layer_urls`` is present the images are fetched in order (bottom to top)
        and composited with PIL.  When PIL is unavailable only the first URL (the
        complete SPC outlook PNG) is fetched and displayed on its own.
        For cameras that only define ``url`` (e.g. NHC) a simple single-image fetch
        is performed regardless of PIL availability.
        """
        layer_urls: list[str] = self._cam_def.get("layer_urls", [])
        if layer_urls:
            if _PIL_AVAILABLE:
                await self._fetch_composite_layers(layer_urls)
            else:
                await self._fetch_single_url(layer_urls[0])
        else:
            await self._fetch_single_url(self._cam_def["url"])

    async def _fetch_single_url(self, url: str) -> None:
        """Fetch a single remote image and update the cache."""
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

    async def _fetch_composite_layers(self, layer_urls: list[str]) -> None:
        """Fetch all layers in order and composite them bottom-to-top into one PNG.

        The first URL is the base/bottom image (e.g. SPC's complete outlook PNG).
        Subsequent URLs are transparent overlay PNGs (pop centres, interstates, cities).
        Any layer that fails to fetch is silently skipped so the remaining layers
        still render correctly.  The composite is only stored when the bottom/base
        layer (index 0) was fetched successfully.
        """
        session = async_get_clientsession(self._hass)
        timeout = aiohttp.ClientTimeout(total=30)
        layer_bytes: list[bytes] = []
        base_fetched = False

        for idx, url in enumerate(layer_urls):
            try:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        layer_bytes.append(data)
                        if idx == 0:
                            base_fetched = True
                        _LOGGER.debug(
                            "Camera %s: fetched layer %d (%d bytes)",
                            self._cam_def["key"], idx, len(data),
                        )
                    else:
                        _LOGGER.debug(
                            "Camera %s: layer %d returned HTTP %s (%s)",
                            self._cam_def["key"], idx, resp.status, url,
                        )
            except aiohttp.ClientError as exc:
                _LOGGER.debug(
                    "Camera %s: network error fetching layer %d (%s): %s",
                    self._cam_def["key"], idx, url, exc,
                )
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.debug(
                    "Camera %s: unexpected error fetching layer %d (%s): %s",
                    self._cam_def["key"], idx, url, exc,
                )

        if not base_fetched:
            _LOGGER.warning(
                "Camera %s: base layer failed to fetch; skipping composite",
                self._cam_def["key"],
            )
            return

        try:
            composite = _composite_layers(layer_bytes)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to composite layers for %s: %s", self._cam_def["key"], exc)
            return

        if composite is not None:
            self._image_cache = composite
            self._last_fetch = time.monotonic()


def _composite_layers(layer_bytes: list[bytes]) -> bytes | None:
    """Composite a list of PNG images (bottom-to-top order) into one PNG.

    Each image is alpha-composited over the previous using its own alpha channel.
    A white opaque background is used as the starting canvas so the result is
    always a fully opaque RGB image suitable for display.
    Returns ``None`` if no valid images could be decoded.
    """
    if not layer_bytes or _PILImage is None:
        return None

    # Decode first valid image to get the canvas dimensions
    composite: "_PILImage.Image | None" = None  # type: ignore[name-defined]
    for raw in layer_bytes:
        try:
            img = _PILImage.open(io.BytesIO(raw)).convert("RGBA")
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("Skipping undecodable layer: %s", exc)
            continue

        if composite is None:
            # Initialise a white background at the same size as the first valid layer
            composite = _PILImage.new("RGBA", img.size, (255, 255, 255, 255))

        # Resize layer if it doesn't match the canvas (defensive — should never happen)
        if img.size != composite.size:
            img = img.resize(composite.size, _PILImage.LANCZOS)

        composite.alpha_composite(img)

    if composite is None:
        return None

    buf = io.BytesIO()
    composite.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
