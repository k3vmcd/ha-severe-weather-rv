"""Image platform for Severe Weather RV Monitor — SPC and NHC outlook maps.

These are periodically-refreshed static pictures, not live video feeds, so they
are modelled as ``image`` entities rather than ``camera`` entities.  This matters
for caching: ``ImageEntity``'s picture URL embeds ``image_last_updated``, so the
URL itself only changes when we actually publish a new picture.  HA's image proxy
uses that to send long-lived Cache-Control/ETag headers, so the browser can serve
the picture instantly from its own cache — across dashboard reloads, tabs, and
brand-new sessions — until we truly have a new image.  (The camera proxy can't do
this safely because a camera's URL/token isn't tied to the image content.)
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
from collections import OrderedDict
from datetime import timedelta

import aiohttp

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SPC_IMAGE_DEFS,
    CONF_OUTLOOK_SCAN_INTERVAL,
    DEFAULT_OUTLOOK_SCAN_INTERVAL,
    SIGNAL_SPC_DATA_UPDATED,
)
from .coordinator import SevereWeatherCoordinator

_LOGGER = logging.getLogger(__name__)

_MAX_LAYER_CACHE_ITEMS = 128
_MAX_COMPOSITE_CACHE_ITEMS = 48

# Shared in-memory HTTP cache (URL -> payload/headers metadata)
_HTTP_LAYER_CACHE: OrderedDict[str, dict] = OrderedDict()
_HTTP_LAYER_LOCKS: dict[str, asyncio.Lock] = {}

# Shared in-memory composite image cache (signature -> composed PNG bytes)
_COMPOSITE_CACHE: OrderedDict[str, bytes] = OrderedDict()

try:
    from PIL import Image as _PILImage
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PILImage = None  # type: ignore[assignment]
    _PIL_AVAILABLE = False
    _LOGGER.warning(
        "Pillow (PIL) is not installed; SPC reference-map compositing is disabled"
    )


# Bound on how long integration setup waits for the initial map fetch —
# prevents a slow/unreachable server from hanging entity registration.
_PREWARM_TIMEOUT = 25


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create image entities for SPC/NHC maps and the NEXRAD regional radar."""
    coordinator: SevereWeatherCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    scan_interval = entry.options.get(CONF_OUTLOOK_SCAN_INTERVAL, DEFAULT_OUTLOOK_SCAN_INTERVAL)
    entities: list = [
        SevereWeatherImage(hass, entry, img_def, scan_interval)
        for img_def in SPC_IMAGE_DEFS
    ]
    entities.append(RadarImage(hass, entry, coordinator, scan_interval))

    # Warm every image's cache *before* entities are exposed to the frontend,
    # so the very first dashboard view is never the one blocking on a live
    # fetch (and never risks HA's ~10s image-proxy request timeout).
    async def _prewarm_bounded(img) -> None:
        try:
            await asyncio.wait_for(img.async_prewarm(), timeout=_PREWARM_TIMEOUT)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Timed out warming the map cache for %s; will retry in the background",
                getattr(img, "_attr_unique_id", img),
            )

    await asyncio.gather(*(_prewarm_bounded(img) for img in entities))

    async_add_entities(entities)

    # Background fallback refresh — entirely decoupled from dashboard/viewer
    # traffic, so images stay fresh even if nobody ever opens the dashboard.
    # SPC images are additionally kept in step with the real SPC issuance
    # schedule and risk-sensor updates (see __init__.py / coordinator.py).
    async def _periodic_refresh(_now) -> None:
        await asyncio.gather(*(img.async_prewarm() for img in entities))

    entry.async_on_unload(
        async_track_time_interval(
            hass, _periodic_refresh, timedelta(seconds=scan_interval)
        )
    )


class SevereWeatherImage(ImageEntity):
    """Image entity that fetches and caches remote weather map pictures."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        img_def: dict,
        scan_interval: int,
    ) -> None:
        super().__init__(hass)
        self._hass = hass
        self._entry = entry
        self._img_def = img_def
        self._scan_interval = scan_interval
        self._attr_name = img_def["name"]
        self._attr_unique_id = f"{entry.entry_id}_{img_def['key']}"
        self._attr_content_type = img_def["content_type"]
        self._image_cache: bytes | None = None
        self._refresh_inflight = False
        self._last_composite_signature: str | None = None

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Severe Weather RV Monitor",
            "manufacturer": "NOAA / NWS / SPC / NHC",
            "model": "Dynamic GPS-Based Weather Monitor",
            "entry_type": "service",
        }

    @property
    def is_spc_image(self) -> bool:
        """Return True for SPC outlook images (as opposed to NHC)."""
        return self._img_def["key"].startswith("spc_")

    async def async_added_to_hass(self) -> None:
        """Subscribe to SPC risk-data updates so maps refresh in step with sensors."""
        await super().async_added_to_hass()
        if self.is_spc_image:
            signal = f"{SIGNAL_SPC_DATA_UPDATED}_{self._entry.entry_id}"
            self.async_on_remove(
                async_dispatcher_connect(self._hass, signal, self._handle_spc_data_updated)
            )

    def _handle_spc_data_updated(self) -> None:
        """Handle a dispatcher signal that new SPC risk data is available."""
        if not self._refresh_inflight:
            self._refresh_inflight = True
            self._hass.async_create_task(self._async_refresh_image())

    async def async_prewarm(self) -> None:
        """Fetch the image immediately, without waiting for a viewer or schedule tick."""
        if self._refresh_inflight:
            return
        self._refresh_inflight = True
        await self._async_refresh_image()

    async def async_image(self) -> bytes | None:
        """Return the cached image — never blocks a viewer on a live fetch.

        Freshness is handled entirely out-of-band: startup prewarm, the
        periodic fallback timer, and the SPC issuance-schedule/dispatcher
        signal (see async_setup_entry / coordinator.py) keep the cache
        current regardless of whether anyone is viewing the dashboard.
        """
        if self._image_cache is None and not self._refresh_inflight:
            self._refresh_inflight = True
            self._hass.async_create_task(self._async_refresh_image())
        return self._image_cache

    def _store_image(self, data: bytes) -> None:
        """Cache new image bytes and bump image_last_updated so the entity
        picture URL changes — this is what lets the browser safely cache the
        picture across dashboard loads, tabs, and sessions until it's stale.
        """
        self._image_cache = data
        self._attr_image_last_updated = dt_util.utcnow()
        if self.entity_id:
            self.async_write_ha_state()

    async def _async_refresh_image(self) -> None:
        """Refresh image in the background to reduce card load latency."""
        try:
            await self._fetch_image()
        finally:
            self._refresh_inflight = False

    async def _fetch_image(self) -> None:
        """Fetch the remote image, compositing all layers when available.

        If ``layer_urls`` is present the images are fetched in order (bottom to top)
        and composited with PIL.  When PIL is unavailable only the first URL (the
        complete SPC outlook PNG) is fetched and displayed on its own.
        For images that only define ``url`` (e.g. NHC) a simple single-image fetch
        is performed regardless of PIL availability.
        """
        layer_urls: list[str] = self._img_def.get("layer_urls", [])
        if layer_urls:
            if _PIL_AVAILABLE:
                await self._fetch_composite_layers(layer_urls)
            else:
                await self._fetch_single_url(layer_urls[0])
        else:
            await self._fetch_single_url(self._img_def["url"])

    async def _fetch_single_url(self, url: str) -> None:
        """Fetch a single remote image and update the cache."""
        payload = await _fetch_http_layer(self._hass, url)
        if payload is not None:
            self._store_image(payload)
            _LOGGER.debug("Fetched %s (%d bytes)", self._img_def["key"], len(payload))
        else:
            _LOGGER.warning("Image %s: failed to fetch %s", self._img_def["key"], url)

    async def _fetch_composite_layers(self, layer_urls: list[str]) -> None:
        """Fetch all layers concurrently and composite them bottom-to-top into one PNG.

        The first URL is the base/bottom image (e.g. SPC's complete outlook PNG).
        Subsequent URLs are transparent overlay PNGs (pop centres, interstates, cities).
        Layers are fetched in parallel (not sequentially) so a cold cache still
        completes well within HA's image-proxy request timeout.  Any layer that
        fails to fetch is silently skipped so the remaining layers still render
        correctly.  The composite is only stored when the bottom/base layer
        (index 0) was fetched successfully.
        """
        fetched = await asyncio.gather(
            *(_fetch_http_layer(self._hass, url) for url in layer_urls)
        )

        layer_bytes: list[bytes] = []
        base_present = False

        for idx, data in enumerate(fetched):
            if data is None:
                _LOGGER.debug(
                    "Image %s: failed to fetch layer %d (%s)",
                    self._img_def["key"], idx, layer_urls[idx],
                )
                continue
            layer_bytes.append(data)
            if idx == 0:
                base_present = True

        if not base_present:
            _LOGGER.warning(
                "Image %s: base layer failed to fetch; skipping composite",
                self._img_def["key"],
            )
            return

        signature = _layer_signature(layer_bytes)
        if signature == self._last_composite_signature and self._image_cache is not None:
            return

        cached_composite = _get_composite_cache(signature)
        if cached_composite is not None:
            self._store_image(cached_composite)
            self._last_composite_signature = signature
            return

        try:
            composite = _composite_layers(layer_bytes)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to composite layers for %s: %s", self._img_def["key"], exc)
            return

        if composite is not None:
            self._store_image(composite)
            self._last_composite_signature = signature
            _set_composite_cache(signature, composite)


def _cache_touch(cache: OrderedDict[str, object], key: str) -> None:
    """Move key to end to keep LRU ordering."""
    cache.move_to_end(key)


def _cache_trim(cache: OrderedDict[str, object], max_items: int) -> None:
    """Trim cache to max size (LRU)."""
    while len(cache) > max_items:
        cache.popitem(last=False)


def _layer_signature(layers: list[bytes]) -> str:
    """Return a stable hash signature for a list of layers."""
    digest = hashlib.sha256()
    for layer in layers:
        digest.update(hashlib.sha256(layer).digest())
    return digest.hexdigest()


def _get_composite_cache(signature: str) -> bytes | None:
    """Read composite cache entry and refresh LRU position."""
    payload = _COMPOSITE_CACHE.get(signature)
    if payload is not None:
        _cache_touch(_COMPOSITE_CACHE, signature)
    return payload


def _set_composite_cache(signature: str, payload: bytes) -> None:
    """Write composite cache entry and enforce LRU size."""
    _COMPOSITE_CACHE[signature] = payload
    _cache_touch(_COMPOSITE_CACHE, signature)
    _cache_trim(_COMPOSITE_CACHE, _MAX_COMPOSITE_CACHE_ITEMS)


async def _fetch_http_layer(hass: HomeAssistant, url: str) -> bytes | None:
    """Fetch a layer with in-memory caching and HTTP conditional revalidation."""
    lock = _HTTP_LAYER_LOCKS.setdefault(url, asyncio.Lock())
    async with lock:
        cached = _HTTP_LAYER_CACHE.get(url)

        headers: dict[str, str] = {}
        if cached:
            etag = cached.get("etag")
            last_modified = cached.get("last_modified")
            if isinstance(etag, str) and etag:
                headers["If-None-Match"] = etag
            if isinstance(last_modified, str) and last_modified:
                headers["If-Modified-Since"] = last_modified

        session = async_get_clientsession(hass)
        timeout = aiohttp.ClientTimeout(total=30)
        try:
            async with session.get(url, timeout=timeout, headers=headers) as resp:
                if resp.status == 304 and cached and cached.get("payload"):
                    cached["fetched_at"] = time.monotonic()
                    _cache_touch(_HTTP_LAYER_CACHE, url)
                    return cached["payload"]

                if resp.status == 200:
                    payload = await resp.read()
                    _HTTP_LAYER_CACHE[url] = {
                        "payload": payload,
                        "etag": resp.headers.get("ETag"),
                        "last_modified": resp.headers.get("Last-Modified"),
                        "fetched_at": time.monotonic(),
                    }
                    _cache_touch(_HTTP_LAYER_CACHE, url)
                    _cache_trim(_HTTP_LAYER_CACHE, _MAX_LAYER_CACHE_ITEMS)
                    return payload

                _LOGGER.debug("Layer fetch HTTP %s for %s", resp.status, url)
        except aiohttp.ClientError as exc:
            _LOGGER.debug("Layer fetch network error for %s: %s", url, exc)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.debug("Layer fetch unexpected error for %s: %s", url, exc)

        if cached and cached.get("payload"):
            return cached["payload"]
        return None


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


# ---------------------------------------------------------------------------
# NEXRAD Regional Radar Image
# ---------------------------------------------------------------------------

# Primary: Iowa State Mesonet NEXRAD current reflectivity for a specific station.
# Iowa State Mesonet tile cache — CONUS N0Q (base reflectivity) composite.
# Tiles use OSM/Google Web Mercator coordinates (zoom / x / y).
_IEM_TILE_BASE = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0"
_IEM_NEXRAD_CONUS = _IEM_TILE_BASE + "/nexrad-n0q-900913/{zoom}/{x}/{y}.png"
# Station-specific fallback (requires radar_station from coordinator).
_IEM_NEXRAD_STATION = _IEM_TILE_BASE + "/ridge::{station}-N0Q-0/{zoom}/{x}/{y}.png"
# Zoom level — 8 ≈ 250×250 km per tile at mid-latitudes (good regional view).
_RADAR_TILE_ZOOM = 8


def _latlon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert WGS-84 coordinates to OSM/Web Mercator tile (x, y) at *zoom*."""
    import math  # local import — math is stdlib, no install overhead
    lat_r = math.radians(lat)
    n = 2 ** zoom
    x = max(0, int((lon + 180.0) / 360.0 * n))
    y = max(0, int(
        (1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi)
        / 2.0 * n
    ))
    return x, y


class RadarImage(ImageEntity):
    """Image entity that shows the current NEXRAD base-reflectivity radar picture.

    The station-specific radar image (Iowa State Mesonet RIDGE) is preferred
    because it gives a zoomed-in view of the RV's region.  If the station is
    unknown or the fetch fails, the NWS national composite is used instead.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: SevereWeatherCoordinator,
        scan_interval: int,
    ) -> None:
        super().__init__(hass)
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._scan_interval = scan_interval
        self._attr_name = "NEXRAD Regional Radar"
        self._attr_unique_id = f"{entry.entry_id}_nexrad_radar"
        self._attr_content_type = "image/png"
        self._image_cache: bytes | None = None
        self._refresh_inflight = False

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Severe Weather RV Monitor",
            "manufacturer": "NOAA / NWS / SPC / NHC",
            "model": "Dynamic GPS-Based Weather Monitor",
            "entry_type": "service",
        }

    @property
    def extra_state_attributes(self) -> dict:
        station = (self._coordinator.data or {}).get("radar_station")
        return {"radar_station": station or "Unknown"}

    def _store_image(self, data: bytes) -> None:
        """Cache new image bytes and bump image_last_updated (see SevereWeatherImage)."""
        self._image_cache = data
        self._attr_image_last_updated = dt_util.utcnow()
        if self.entity_id:
            self.async_write_ha_state()

    async def async_prewarm(self) -> None:
        """Fetch the image immediately, without waiting for a viewer or timer tick."""
        if self._refresh_inflight:
            return
        self._refresh_inflight = True
        try:
            await self._fetch_image()
        finally:
            self._refresh_inflight = False

    async def async_image(self) -> bytes | None:
        """Return the cached radar tile — never blocks a viewer on a live fetch.

        Freshness is handled entirely out-of-band by the periodic fallback
        timer registered in async_setup_entry.
        """
        if self._image_cache is None and not self._refresh_inflight:
            self._hass.async_create_task(self.async_prewarm())
        return self._image_cache

    async def _fetch_image(self) -> None:
        """Fetch the regional radar tile from Iowa State Mesonet tile cache.

        Tries the CONUS N0Q composite first (no station dependency), then falls
        back to the station-specific RIDGE tile if ``radar_station`` is known.
        Tile (x, y) is calculated from the current GPS coordinates so the image
        is always centred on the RV's position.
        """
        cdata = self._coordinator.data or {}
        lat = cdata.get("latitude")
        lon = cdata.get("longitude")
        if lat is None or lon is None:
            return

        x, y = _latlon_to_tile(lat, lon, _RADAR_TILE_ZOOM)
        station = cdata.get("radar_station")

        urls_to_try: list[str] = [
            _IEM_NEXRAD_CONUS.format(zoom=_RADAR_TILE_ZOOM, x=x, y=y),
        ]
        if station:
            urls_to_try.append(
                _IEM_NEXRAD_STATION.format(station=station, zoom=_RADAR_TILE_ZOOM, x=x, y=y)
            )

        session = async_get_clientsession(self._hass)
        timeout = aiohttp.ClientTimeout(total=30)

        for url in urls_to_try:
            try:
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        payload = await resp.read()
                        self._store_image(payload)
                        _LOGGER.debug(
                            "RadarImage: fetched tile %s (%d bytes)", url, len(payload)
                        )
                        return
                    _LOGGER.debug("RadarImage: %s → HTTP %s", url, resp.status)
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.debug("RadarImage: error fetching %s: %s", url, exc)

        _LOGGER.warning("RadarImage: all tile URLs failed — no image cached")
        # Leave self._image_cache as-is (old image or None) rather than clearing it.
