"""Image platform for Severe Weather RV Monitor — SPC and NHC outlook maps.

These are periodically-refreshed static pictures, not live video feeds, so they
are modelled as ``image`` entities rather than ``camera`` entities.  This matters
for caching: ``ImageEntity``'s picture URL embeds ``image_last_updated``, so the
URL itself only changes when we actually publish a new picture.  HA's image proxy
uses that to send long-lived Cache-Control/ETag headers, so the browser can serve
the picture instantly from its own cache — across dashboard reloads, tabs, and
brand-new sessions — until we truly have a new image.

Freshness is driven entirely by a ``DataUpdateCoordinator`` (``SPCImageCoordinator``)
plus ``CoordinatorEntity``, the same proven pattern that already keeps the risk
sensors up to date. An earlier version used bespoke per-entity timers/dispatcher
signals to trigger refreshes, but dispatcher targets that aren't decorated with
``@callback`` get run in a worker thread by Home Assistant — calling
``hass.async_create_task`` from there raised a thread-safety error on every
attempt, silently breaking every scheduled refresh. Routing everything through a
coordinator sidesteps that whole class of bug: ``_handle_coordinator_update`` is
always invoked correctly on the event loop by HA core.
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SPC_IMAGE_DEFS,
    CONF_OUTLOOK_SCAN_INTERVAL,
    DEFAULT_OUTLOOK_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_MAX_LAYER_CACHE_ITEMS = 128
_MAX_COMPOSITE_CACHE_ITEMS = 48

# Shared in-memory HTTP cache (URL -> payload/headers metadata)
_HTTP_LAYER_CACHE: OrderedDict[str, dict] = OrderedDict()
_HTTP_LAYER_LOCKS: dict[str, asyncio.Lock] = {}

# Shared in-memory composite image cache (signature -> composed JPEG bytes)
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

# SPC/NHC source images are ~1500-2000px wide — far larger than any dashboard
# card needs. Downscaling and re-encoding as JPEG cuts payload size roughly
# 10-20x versus the original full-resolution PNG, which is what made the very
# first (cold-cache) dashboard load feel slow.
_MAX_IMAGE_WIDTH = 900
_JPEG_QUALITY = 80

# Bound on how many outbound map-image fetches run at once, shared across all
# entities. A cold-start burst of ~15 simultaneous requests to spc.noaa.gov was
# triggering failures/slow responses; capping concurrency fixes that at the
# small cost of some fetches queueing briefly.
_FETCH_CONCURRENCY = 4
_FETCH_SEMAPHORE = asyncio.Semaphore(_FETCH_CONCURRENCY)


def _encode_jpeg(img) -> bytes:
    """Flatten to RGB, downscale if oversized, and JPEG-encode for a small payload."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        # JPEG has no alpha channel — flatten transparency onto white first.
        rgba = img.convert("RGBA")
        background = _PILImage.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > _MAX_IMAGE_WIDTH:
        ratio = _MAX_IMAGE_WIDTH / img.width
        img = img.resize(
            (_MAX_IMAGE_WIDTH, max(1, round(img.height * ratio))), _PILImage.LANCZOS
        )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return buf.getvalue()


def _optimize_standalone_image(data: bytes) -> tuple[bytes, str]:
    """Re-encode a fetched image as a smaller JPEG; falls back to the original
    bytes (as PNG) if PIL is unavailable or the image can't be decoded.
    """
    if not _PIL_AVAILABLE:
        return data, "image/png"
    try:
        img = _PILImage.open(io.BytesIO(data))
        return _encode_jpeg(img), "image/jpeg"
    except Exception as exc:  # pylint: disable=broad-except
        _LOGGER.debug("Could not re-encode image, using original bytes: %s", exc)
        return data, "image/png"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create image entities for SPC/NHC maps."""
    scan_interval = entry.options.get(CONF_OUTLOOK_SCAN_INTERVAL, DEFAULT_OUTLOOK_SCAN_INTERVAL)

    image_coordinator = SPCImageCoordinator(hass, entry, scan_interval)
    hass.data[DOMAIN][entry.entry_id]["image_coordinator"] = image_coordinator

    entities: list = [
        SevereWeatherImage(image_coordinator, entry, img_def)
        for img_def in SPC_IMAGE_DEFS
    ]
    async_add_entities(entities)

    # Kick off the first fetch in the background so HA startup never blocks on
    # ~15 image requests. After this, the coordinator's own update_interval
    # timer (proven reliable — it's the same mechanism driving the sensors)
    # and the SPC issuance-schedule hook in __init__.py keep it fresh forever.
    hass.async_create_task(image_coordinator.async_refresh())


class SPCImageCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator that fetches/composites/optimizes all SPC/NHC map images.

    Data is a dict of ``key -> (image_bytes, content_type, signature)``. Using a
    coordinator (instead of bespoke per-entity timers) means image freshness
    rides on the same battle-tested polling/listener machinery that already
    reliably drives the risk sensors.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_images",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry

    async def _async_update_data(self) -> dict:
        previous: dict = self.data or {}
        results: dict = {}

        async def _update_one(key: str, payload) -> None:
            resolved = await payload
            if resolved is not None:
                results[key] = resolved
            elif key in previous:
                # Keep the last-known-good image on a transient failure
                # instead of blanking out an already-working picture.
                results[key] = previous[key]

        await asyncio.gather(
            *(
                _update_one(img_def["key"], self._fetch_one(img_def))
                for img_def in SPC_IMAGE_DEFS
            )
        )
        return results

    async def _fetch_one(self, img_def: dict) -> tuple[bytes, str, str] | None:
        """Fetch (and composite/optimize) a single SPC/NHC image definition."""
        layer_urls: list[str] = img_def.get("layer_urls", [])
        if layer_urls and _PIL_AVAILABLE:
            return await self._fetch_composite(img_def["key"], layer_urls)
        url = layer_urls[0] if layer_urls else img_def["url"]
        return await self._fetch_single(img_def["key"], url)

    async def _fetch_single(self, key: str, url: str) -> tuple[bytes, str, str] | None:
        """Fetch a single remote image and re-encode it smaller."""
        payload = await _fetch_http_layer(self.hass, url)
        if payload is None:
            _LOGGER.warning("Image %s: failed to fetch %s", key, url)
            return None
        optimized, content_type = _optimize_standalone_image(payload)
        return optimized, content_type, hashlib.sha256(optimized).hexdigest()

    async def _fetch_composite(
        self, key: str, layer_urls: list[str]
    ) -> tuple[bytes, str, str] | None:
        """Fetch all layers concurrently and composite them into one small JPEG."""
        fetched = await asyncio.gather(
            *(_fetch_http_layer(self.hass, url) for url in layer_urls)
        )

        layer_bytes: list[bytes] = []
        base_present = False
        for idx, data in enumerate(fetched):
            if data is None:
                _LOGGER.debug(
                    "Image %s: failed to fetch layer %d (%s)", key, idx, layer_urls[idx]
                )
                continue
            layer_bytes.append(data)
            if idx == 0:
                base_present = True

        if not base_present:
            _LOGGER.warning("Image %s: base layer failed to fetch; skipping composite", key)
            return None

        signature = _layer_signature(layer_bytes)
        cached_composite = _get_composite_cache(signature)
        if cached_composite is not None:
            return cached_composite, "image/jpeg", signature

        try:
            composite = _composite_layers(layer_bytes)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("Failed to composite layers for %s: %s", key, exc)
            return None
        if composite is None:
            return None

        _set_composite_cache(signature, composite)
        return composite, "image/jpeg", signature


class SevereWeatherImage(CoordinatorEntity[SPCImageCoordinator], ImageEntity):
    """Image entity backed by SPCImageCoordinator for one SPC/NHC map picture."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SPCImageCoordinator,
        entry: ConfigEntry,
        img_def: dict,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, coordinator.hass)
        self._entry = entry
        self._img_def = img_def
        self._attr_name = img_def["name"]
        self._attr_unique_id = f"{entry.entry_id}_{img_def['key']}"
        self._attr_content_type = img_def["content_type"]
        self._image_cache: bytes | None = None
        self._signature: str | None = None
        self._apply_coordinator_data()

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Severe Weather RV Monitor",
            "manufacturer": "NOAA / NWS / SPC / NHC",
            "model": "Dynamic GPS-Based Weather Monitor",
            "entry_type": "service",
        }

    def _apply_coordinator_data(self) -> bool:
        """Pull this entity's image out of coordinator.data. Returns True if changed."""
        payload = (self.coordinator.data or {}).get(self._img_def["key"])
        if payload is None:
            return False
        data, content_type, signature = payload
        if signature == self._signature:
            return False
        self._image_cache = data
        self._attr_content_type = content_type
        self._signature = signature
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._apply_coordinator_data():
            self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update image_last_updated only when the picture actually changed —
        this is what lets the browser keep caching it in between.
        """
        if self._apply_coordinator_data():
            self._attr_image_last_updated = dt_util.utcnow()
            self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return self._image_cache


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
            async with _FETCH_SEMAPHORE, session.get(url, timeout=timeout, headers=headers) as resp:
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
    """Composite a list of PNG images (bottom-to-top order) into one small JPEG.

    Each image is alpha-composited over the previous using its own alpha channel.
    A white opaque background is used as the starting canvas so the result is
    always a fully opaque RGB image suitable for display.  The final composite
    is downscaled/re-encoded via ``_encode_jpeg`` for a much smaller payload.
    Returns ``None`` if no valid images could be decoded.
    """
    if not layer_bytes or _PILImage is None:
        return None

    # Decode first valid image to get the canvas dimensions
    composite = None
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

    return _encode_jpeg(composite)
