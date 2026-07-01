"""MapAI demo data — predefined map regions with entities (Module L).

Provides mock geographic entities for development and demonstration.
Production data would come from GIS databases, CRM, IoT sensors, etc.
"""

from __future__ import annotations

from agents.map_agent.models import GeoEntity, GeoPoint, MapRegion

# ══════════════════════════════════════════════════════════════════
# Beijing Region (default demo)
# ══════════════════════════════════════════════════════════════════

BEIJING_ENTITIES: list[GeoEntity] = [
    GeoEntity(
        entity_id="bj-001",
        name="朝阳CBD",
        location=GeoPoint(lng=116.46, lat=39.92, label="CBD"),
        entity_type="commercial_zone",
        properties={
            "population": 180000,
            "office_rent": 350,
            "traffic_index": 8.5,
            "green_coverage": 15,
            "avg_income": 25000,
        },
    ),
    GeoEntity(
        entity_id="bj-002",
        name="中关村科技园",
        location=GeoPoint(lng=116.31, lat=39.98, label="ZGC"),
        entity_type="tech_park",
        properties={
            "population": 50000,
            "office_rent": 280,
            "traffic_index": 7.2,
            "green_coverage": 35,
            "avg_income": 32000,
        },
    ),
    GeoEntity(
        entity_id="bj-003",
        name="望京商圈",
        location=GeoPoint(lng=116.49, lat=40.00, label="Wangjing"),
        entity_type="commercial_zone",
        properties={
            "population": 120000,
            "office_rent": 220,
            "traffic_index": 6.8,
            "green_coverage": 25,
            "avg_income": 28000,
        },
    ),
    GeoEntity(
        entity_id="bj-004",
        name="通州新城",
        location=GeoPoint(lng=116.66, lat=39.90, label="Tongzhou"),
        entity_type="new_district",
        properties={
            "population": 80000,
            "office_rent": 150,
            "traffic_index": 5.5,
            "green_coverage": 45,
            "avg_income": 18000,
        },
    ),
    GeoEntity(
        entity_id="bj-005",
        name="亦庄经开区",
        location=GeoPoint(lng=116.50, lat=39.78, label="Yizhuang"),
        entity_type="industrial_park",
        properties={
            "population": 35000,
            "office_rent": 120,
            "traffic_index": 4.2,
            "green_coverage": 30,
            "avg_income": 15000,
        },
    ),
    GeoEntity(
        entity_id="bj-006",
        name="金融街",
        location=GeoPoint(lng=116.36, lat=39.91, label="Financial"),
        entity_type="commercial_zone",
        properties={
            "population": 22000,
            "office_rent": 520,
            "traffic_index": 9.0,
            "green_coverage": 10,
            "avg_income": 45000,
        },
    ),
]

# ══════════════════════════════════════════════════════════════════
# Shanghai Region
# ══════════════════════════════════════════════════════════════════

SHANGHAI_ENTITIES: list[GeoEntity] = [
    GeoEntity(
        entity_id="sh-001",
        name="陆家嘴金融区",
        location=GeoPoint(lng=121.50, lat=31.24, label="Lujiazui"),
        entity_type="commercial_zone",
        properties={
            "population": 60000,
            "office_rent": 480,
            "traffic_index": 8.8,
            "green_coverage": 12,
            "avg_income": 42000,
        },
    ),
    GeoEntity(
        entity_id="sh-002",
        name="张江科学城",
        location=GeoPoint(lng=121.61, lat=31.21, label="Zhangjiang"),
        entity_type="tech_park",
        properties={
            "population": 45000,
            "office_rent": 260,
            "traffic_index": 6.5,
            "green_coverage": 38,
            "avg_income": 30000,
        },
    ),
    GeoEntity(
        entity_id="sh-003",
        name="虹桥商务区",
        location=GeoPoint(lng=121.32, lat=31.20, label="Hongqiao"),
        entity_type="commercial_zone",
        properties={
            "population": 95000,
            "office_rent": 310,
            "traffic_index": 7.5,
            "green_coverage": 20,
            "avg_income": 35000,
        },
    ),
    GeoEntity(
        entity_id="sh-004",
        name="临港新片区",
        location=GeoPoint(lng=121.92, lat=30.87, label="Lingang"),
        entity_type="new_district",
        properties={
            "population": 40000,
            "office_rent": 140,
            "traffic_index": 4.0,
            "green_coverage": 50,
            "avg_income": 16000,
        },
    ),
]

# ══════════════════════════════════════════════════════════════════
# Region registry
# ══════════════════════════════════════════════════════════════════

DEMO_REGIONS: list[MapRegion] = [
    MapRegion(
        region_id="beijing",
        name="北京",
        center=GeoPoint(lng=116.40, lat=39.90, label="Beijing"),
        zoom=11,
        entities=BEIJING_ENTITIES,
    ),
    MapRegion(
        region_id="shanghai",
        name="上海",
        center=GeoPoint(lng=121.47, lat=31.23, label="Shanghai"),
        zoom=11,
        entities=SHANGHAI_ENTITIES,
    ),
]


def get_demo_region(region_id: str) -> MapRegion | None:
    """Get a demo region by ID."""
    for region in DEMO_REGIONS:
        if region.region_id == region_id:
            return region
    return None


def get_all_demo_regions() -> list[MapRegion]:
    """Get all demo regions."""
    return list(DEMO_REGIONS)


def get_entities_in_bounds(
    west: float,
    south: float,
    east: float,
    north: float,
    entity_types: list[str] | None = None,
) -> list[GeoEntity]:
    """Query demo entities within a geographic bounding box."""
    results: list[GeoEntity] = []
    for region in DEMO_REGIONS:
        for entity in region.entities:
            if (
                west <= entity.location.lng <= east
                and south <= entity.location.lat <= north
                and (not entity_types or entity.entity_type in entity_types)
            ):
                results.append(entity)
    return results
