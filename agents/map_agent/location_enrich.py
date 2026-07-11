"""Location Enrichment -- Convert coordinates to physical attributes via Baidu Maps API.

For each entity coordinate, call Baidu Place API to obtain surrounding POI density,
business district level, geographic info and other numeric attributes for
correlation analysis.

Uses Baidu Maps server-side AK, supporting:
- Reverse geocoding: obtain administrative district, business district info
- Nearby POI search: count POIs by category (food/shopping/finance/education/medical/transport etc.)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger("fde.map.location_enrich")

# ── Config ──────────────────────────────────────────────────────────
BAIDU_AK = os.getenv("BAIDU_SERVER_AK", "")
PLACE_API = "https://api.map.baidu.com/place/v2/search"
GEOCODE_API = "https://api.map.baidu.com/reverse_geocoding/v3/"
DEFAULT_RADIUS = 1000  # meters
REQUEST_DELAY = 0.3  # seconds between requests (Baidu rate limit)

# POI categories used for enrichment
POI_CATEGORIES: dict[str, str] = {
    "poi_food": "餐饮",
    "poi_shopping": "购物",
    "poi_hotel": "酒店",
    "poi_education": "学校",
    "poi_medical": "医院",
    "poi_finance": "银行",
    "poi_transport": "地铁站",
    "poi_office": "写字楼",
    "poi_scenic": "景区",
    "poi_residential": "小区",
}


@dataclass
class LocationProfile:
    """Enriched location data for a single coordinate."""

    lng: float
    lat: float
    # Geocoding
    address: str = ""
    district: str = ""
    business_area: str = ""
    adcode: str = ""
    # POI counts
    poi_total: int = 0
    poi_density: float = 0.0  # per km^2
    poi_counts: dict[str, int] = field(default_factory=dict)
    # Meta
    enrichment_ms: int = 0
    errors: list[str] = field(default_factory=list)

    def to_properties(self) -> dict[str, Any]:
        """Convert to entity properties dict for GeoEntity."""
        props: dict[str, Any] = {
            "address": self.address,
            "district": self.district,
            "business_area": self.business_area,
            "adcode": self.adcode,
            "poi_total": self.poi_total,
            "poi_density": round(self.poi_density, 2),
        }
        for key, count in self.poi_counts.items():
            props[key] = count
        return props


# ══════════════════════════════════════════════════════════════════
# API Calls
# ══════════════════════════════════════════════════════════════════


async def _fetch_poi_count(
    session: aiohttp.ClientSession,
    keyword: str,
    lng: float,
    lat: float,
    radius: int = DEFAULT_RADIUS,
) -> int:
    """Fetch POI count for a single category keyword."""
    params: dict[str, str] = {
        "ak": BAIDU_AK,
        "query": keyword,
        "location": f"{lat},{lng}",
        "radius": str(radius),
        "output": "json",
        "page_size": "1",
        "scope": "2",
    }
    try:
        async with session.get(
            PLACE_API, params=params, timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            if resp.status != 200:
                return 0
            data: dict[str, Any] = await resp.json()
            if data.get("status") != 0:
                return 0
            return int(data.get("total", 0))
    except Exception:
        return 0


async def _fetch_geocode(
    session: aiohttp.ClientSession,
    lng: float,
    lat: float,
) -> dict[str, str]:
    """Reverse geocode a coordinate."""
    params: dict[str, str] = {
        "ak": BAIDU_AK,
        "location": f"{lat},{lng}",
        "output": "json",
        "coordtype": "wgs84ll",
    }
    try:
        async with session.get(
            GEOCODE_API, params=params, timeout=aiohttp.ClientTimeout(total=5)
        ) as resp:
            if resp.status != 200:
                return {}
            data: dict[str, Any] = await resp.json()
            if data.get("status") != 0:
                return {}
            result = data.get("result", {})
            comp = result.get("addressComponent", {})
            return {
                "address": result.get("formatted_address", ""),
                "district": comp.get("district", ""),
                "adcode": comp.get("adcode", ""),
                "business": result.get("business", ""),
            }
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════
# Main Enrichment Function
# ══════════════════════════════════════════════════════════════════


async def enrich_location(
    lng: float,
    lat: float,
    radius: int = DEFAULT_RADIUS,
) -> LocationProfile:
    """Enrich a single coordinate with location data.

    Parallel fetches all POI categories + geocoding via aiohttp.
    """
    start = time.monotonic()
    profile = LocationProfile(lng=lng, lat=lat)

    async with aiohttp.ClientSession() as session:
        # Fetch geocode + all POI categories in parallel via asyncio.gather
        geo_task = _fetch_geocode(session, lng, lat)
        poi_keys = list(POI_CATEGORIES.keys())
        poi_coros = [
            _fetch_poi_count(session, POI_CATEGORIES[key], lng, lat, radius) for key in poi_keys
        ]

        # Run all requests concurrently
        geo_result, poi_results = await asyncio.gather(geo_task, asyncio.gather(*poi_coros))

        # Process geocode
        profile.address = geo_result.get("address", "")
        profile.district = geo_result.get("district", "")
        profile.adcode = geo_result.get("adcode", "")
        profile.business_area = geo_result.get("business", "")

        # Process POI counts
        poi_counts: dict[str, int] = {}
        poi_total = 0
        for key, count in zip(poi_keys, poi_results, strict=True):
            poi_counts[key] = count
            poi_total += count

        profile.poi_counts = poi_counts
        profile.poi_total = poi_total
        # density: POI per km^2 within the circle
        area_km2 = 3.14159 * (radius / 1000) ** 2
        profile.poi_density = round(poi_total / area_km2, 2) if area_km2 > 0 else 0

    profile.enrichment_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "Enriched (%.4f, %.4f): %d POIs in %d categories, %s, %dms",
        lng,
        lat,
        poi_total,
        len(poi_counts),
        profile.district or "?",
        profile.enrichment_ms,
    )
    return profile


async def enrich_locations(
    locations: list[tuple[float, float]],
) -> list[LocationProfile]:
    """Enrich multiple coordinates sequentially with rate limiting."""
    profiles: list[LocationProfile] = []
    for lng, lat in locations:
        profile = await enrich_location(lng, lat)
        profiles.append(profile)
        if len(locations) > 1:
            await asyncio.sleep(REQUEST_DELAY)
    return profiles


# Synchronous wrapper for use in non-async pipeline
def enrich_locations_sync(
    locations: list[tuple[float, float]],
) -> list[LocationProfile]:
    """Synchronous wrapper for pipeline integration."""
    try:
        loop = asyncio.get_running_loop()
        # Running loop exists — create new loop in thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(_run_in_new_loop, locations).result()
    except RuntimeError:
        # No running loop — create a new one
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(enrich_locations(locations))
        finally:
            loop.close()


def _run_in_new_loop(locations: list[tuple[float, float]]) -> list[LocationProfile]:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(enrich_locations(locations))
    finally:
        loop.close()
