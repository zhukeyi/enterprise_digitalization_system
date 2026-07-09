"""Tests for marker persistence + tag extraction (v2.0)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# ══════════════════════════════════════════════════════════════════
# Tag Extractor Tests
# ══════════════════════════════════════════════════════════════════


class TestTagExtractor:
    def test_empty_text(self) -> None:
        from agents.map_agent.tag_extractor import extract_tags

        assert extract_tags("") == []
        assert extract_tags("   ") == []

    def test_transport_keywords(self) -> None:
        from agents.map_agent.tag_extractor import extract_tags

        tags = extract_tags("杭州东站是高铁枢纽站，连接京沪高铁")
        assert "交通" in tags

    def test_government_keywords(self) -> None:
        from agents.map_agent.tag_extractor import extract_tags

        tags = extract_tags("浙江省政府所在地，省委办公厅")
        assert "政务" in tags

    def test_commercial_keywords(self) -> None:
        from agents.map_agent.tag_extractor import extract_tags

        tags = extract_tags("大型商场和购物中心，繁华商圈")
        assert "商业" in tags

    def test_multiple_tags(self) -> None:
        from agents.map_agent.tag_extractor import extract_tags

        tags = extract_tags("杭州东站是高铁枢纽，周边有大型商场，人流量大")
        assert "交通" in tags
        assert "商业" in tags
        assert "高人流" in tags

    def test_max_tags_limit(self) -> None:
        from agents.map_agent.tag_extractor import extract_tags

        tags = extract_tags("高铁站旁边有政府大楼、商场、医院、学校、工厂", max_tags=3)
        assert len(tags) <= 3

    def test_no_keywords_fallback(self) -> None:
        from agents.map_agent.tag_extractor import extract_tags

        # Text with no keyword matches — should fall back to jieba/char freq
        tags = extract_tags("一个普通的地方名字")
        assert isinstance(tags, list)

    def test_dedup_tags(self) -> None:
        from agents.map_agent.tag_extractor import extract_tags

        # Multiple matches for the same tag should not duplicate
        tags = extract_tags("火车站高铁地铁站都是交通设施")
        assert tags.count("交通") <= 1


# ══════════════════════════════════════════════════════════════════
# Marker Store Tests
# ══════════════════════════════════════════════════════════════════


@pytest.fixture()
def temp_store():
    """Create a MarkerStore backed by a temp file."""
    from agents.map_agent.marker_store import MarkerStore

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b"[]")
        path = Path(f.name)
    store = MarkerStore(path=path)
    yield store
    path.unlink(missing_ok=True)


class TestMarkerStore:
    def test_create_marker(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate

        marker = temp_store.create(
            MarkerCreate(name="杭州东站", lng=120.213, lat=30.290, note="高铁枢纽站")
        )
        assert marker.id
        assert marker.name == "杭州东站"
        assert marker.lng == 120.213
        assert marker.lat == 30.290
        assert "交通" in marker.tags

    def test_list_empty(self, temp_store) -> None:
        assert temp_store.list_all() == []

    def test_list_all(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate

        temp_store.create(MarkerCreate(name="A", lng=1.0, lat=1.0, note=""))
        temp_store.create(MarkerCreate(name="B", lng=2.0, lat=2.0, note=""))
        markers = temp_store.list_all()
        assert len(markers) == 2

    def test_get_by_id(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate

        created = temp_store.create(MarkerCreate(name="测试点", lng=1.0, lat=1.0, note=""))
        found = temp_store.get(created.id)
        assert found is not None
        assert found.name == "测试点"

    def test_get_not_found(self, temp_store) -> None:
        assert temp_store.get("nonexistent-id") is None

    def test_update_marker_note(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate, MarkerUpdate

        created = temp_store.create(MarkerCreate(name="空点", lng=1.0, lat=1.0, note=""))
        updated = temp_store.update(
            created.id,
            MarkerUpdate(note="这里是一个高铁站"),
        )
        assert updated is not None
        assert updated.note == "这里是一个高铁站"
        assert "交通" in updated.tags

    def test_update_marker_name(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate, MarkerUpdate

        created = temp_store.create(MarkerCreate(name="旧名", lng=1.0, lat=1.0, note=""))
        updated = temp_store.update(created.id, MarkerUpdate(name="新名"))
        assert updated is not None
        assert updated.name == "新名"

    def test_update_not_found(self, temp_store) -> None:
        from agents.map_agent.models import MarkerUpdate

        assert temp_store.update("nonexistent", MarkerUpdate(name="X")) is None

    def test_delete_marker(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate

        created = temp_store.create(MarkerCreate(name="待删除", lng=1.0, lat=1.0, note=""))
        assert temp_store.delete(created.id) is True
        assert temp_store.get(created.id) is None
        assert temp_store.delete(created.id) is False

    def test_search_by_name(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate

        temp_store.create(MarkerCreate(name="杭州东站", lng=1.0, lat=1.0, note=""))
        temp_store.create(MarkerCreate(name="北京西站", lng=2.0, lat=2.0, note=""))
        results = temp_store.search("杭州")
        assert len(results) == 1
        assert results[0].name == "杭州东站"

    def test_search_by_note(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate

        temp_store.create(MarkerCreate(name="某点", lng=1.0, lat=1.0, note="这是一个特殊的备注"))
        results = temp_store.search("特殊")
        assert len(results) == 1

    def test_filter_by_tag(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate

        temp_store.create(MarkerCreate(name="A", lng=1.0, lat=1.0, note="高铁站"))
        temp_store.create(MarkerCreate(name="B", lng=2.0, lat=2.0, note="医院"))
        transport = temp_store.filter_by_tag("交通")
        assert len(transport) == 1
        assert transport[0].name == "A"

    def test_get_all_tags(self, temp_store) -> None:
        from agents.map_agent.models import MarkerCreate

        temp_store.create(MarkerCreate(name="A", lng=1.0, lat=1.0, note="高铁站"))
        temp_store.create(MarkerCreate(name="B", lng=2.0, lat=2.0, note="地铁站"))
        temp_store.create(MarkerCreate(name="C", lng=3.0, lat=3.0, note="医院"))
        tags = temp_store.get_all_tags()
        tag_dict = dict(tags)
        assert tag_dict["交通"] == 2
        assert tag_dict["医疗"] == 1

    def test_persistence_across_instances(self, temp_store) -> None:
        """Data should persist when a new store instance reads the same file."""
        from agents.map_agent.marker_store import MarkerStore
        from agents.map_agent.models import MarkerCreate

        temp_store.create(MarkerCreate(name="持久化测试", lng=1.0, lat=1.0, note="高铁站"))

        # Create a new store pointing to the same file
        new_store = MarkerStore(path=temp_store.path)
        markers = new_store.list_all()
        assert len(markers) == 1
        assert markers[0].name == "持久化测试"
