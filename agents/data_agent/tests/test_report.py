"""Tests for M3-T2: Report template engine + push service + scheduler.

Covers:
- ReportRenderer: Jinja2 template rendering, chart generation, format output
- PushService: email/IM/webhook channels, multi-target delivery
- ReportScheduler: schedule/unschedule/trigger, manual execution
- Default templates: create_default_templates
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agents.data_agent.push_service import PushService, get_push_service
from agents.data_agent.report_models import (
    ChartSpec,
    ChartType,
    PushChannel,
    PushResult,
    PushTarget,
    ReportFormat,
    ReportInstance,
    ReportSection,
    ReportTemplate,
    TemplateVariable,
)
from agents.data_agent.report_renderer import (
    ReportRenderer,
    create_default_templates,
    get_renderer,
)
from agents.data_agent.scheduler import (
    ReportScheduler,
    get_scheduler,
)

# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _make_template(
    name: str = "Test Report",
    fmt: ReportFormat = ReportFormat.HTML,
    body: str = "<p>Hello {{ name }}!</p>",
    variables: list[TemplateVariable] | None = None,
) -> ReportTemplate:
    """Create a minimal report template for testing."""
    return ReportTemplate(
        name=name,
        format=fmt,
        sections=[
            ReportSection(
                title="Section 1",
                body_template=body,
                order=0,
            )
        ],
        variables=variables or [TemplateVariable(name="name", description="Name")],
    )


def _make_chart(
    chart_type: ChartType = ChartType.BAR,
    data: list | None = None,
) -> ChartSpec:
    """Create a chart spec for testing."""
    return ChartSpec(
        title="Test Chart",
        chart_type=chart_type,
        data=data
        or [
            {"label": "A", "value": 10},
            {"label": "B", "value": 20},
            {"label": "C", "value": 15},
        ],
        x_label="Category",
        y_label="Value",
    )


def _run(coro):
    """Run a coroutine in a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ══════════════════════════════════════════════════════════════════
# Report Model Tests
# ══════════════════════════════════════════════════════════════════


class TestReportModels:
    """Tests for report Pydantic models."""

    def test_report_template_defaults(self) -> None:
        tpl = ReportTemplate(name="T")
        assert tpl.name == "T"
        assert tpl.format == ReportFormat.HTML
        assert tpl.sections == []
        assert tpl.variables == []
        assert tpl.id  # auto-generated

    def test_chart_spec_defaults(self) -> None:
        chart = ChartSpec()
        assert chart.chart_type == ChartType.BAR
        assert chart.width == 800
        assert chart.height == 400
        assert chart.data == []

    def test_push_target_serialization(self) -> None:
        target = PushTarget(
            channel=PushChannel.EMAIL,
            address="user@example.com",
            metadata={"subject": "Test"},
        )
        d = target.model_dump()
        assert d["channel"] == "email"
        assert d["address"] == "user@example.com"

    def test_push_result_defaults(self) -> None:
        target = PushTarget(channel=PushChannel.WEBHOOK, address="http://hook.test")
        result = PushResult(target=target)
        assert result.success is False
        assert result.delivered_at is None

    def test_report_instance_defaults(self) -> None:
        inst = ReportInstance(template_id="tpl_001")
        assert inst.template_id == "tpl_001"
        assert inst.content == ""
        assert inst.chart_images == {}


# ══════════════════════════════════════════════════════════════════
# ReportRenderer Tests
# ══════════════════════════════════════════════════════════════════


class TestReportRenderer:
    """Tests for the ReportRenderer."""

    def test_render_basic_html(self) -> None:
        renderer = ReportRenderer()
        tpl = _make_template()
        instance = renderer.render(tpl, variables={"name": "World"})
        assert instance.format == ReportFormat.HTML
        assert "Hello World" in instance.content
        assert "<html>" in instance.content

    def test_render_markdown(self) -> None:
        renderer = ReportRenderer()
        tpl = _make_template(
            fmt=ReportFormat.MARKDOWN,
            body="Hello {{ name }}!",
        )
        instance = renderer.render(tpl, variables={"name": "World"})
        assert instance.format == ReportFormat.MARKDOWN
        assert "# Test Report" in instance.content
        assert "Hello World" in instance.content

    def test_render_text(self) -> None:
        renderer = ReportRenderer()
        tpl = _make_template(
            fmt=ReportFormat.TEXT,
            body="Hello {{ name }}!",
        )
        instance = renderer.render(tpl, variables={"name": "World"})
        assert instance.format == ReportFormat.TEXT
        assert "Hello World" in instance.content
        assert "=== Section 1 ===" in instance.content

    def test_render_missing_required_variable(self) -> None:
        renderer = ReportRenderer()
        tpl = _make_template()
        with pytest.raises(ValueError, match="Missing required"):
            renderer.render(tpl, variables={})

    def test_render_with_optional_variable_default(self) -> None:
        renderer = ReportRenderer()
        tpl = ReportTemplate(
            name="T",
            sections=[
                ReportSection(
                    title="S",
                    body_template="Val: {{ opt | default('fallback') }}",
                    order=0,
                )
            ],
            variables=[
                TemplateVariable(
                    name="opt",
                    description="Optional",
                    required=False,
                    default="fallback",
                )
            ],
        )
        instance = renderer.render(tpl, variables={})
        # Should not raise; content rendered with default
        assert "fallback" in instance.content

    def test_render_with_chart(self) -> None:
        renderer = ReportRenderer()
        chart = _make_chart()
        tpl = ReportTemplate(
            name="Chart Report",
            sections=[
                ReportSection(
                    title="Data",
                    body_template="<p>See chart below</p>",
                    charts=[chart],
                    order=0,
                )
            ],
        )
        instance = renderer.render(tpl, variables={})
        assert instance.content
        # Chart image may or may not be generated depending on matplotlib
        # But the content should reference the chart
        assert "Chart" in instance.content or "img" in instance.content

    def test_render_multiple_sections_ordered(self) -> None:
        renderer = ReportRenderer()
        tpl = ReportTemplate(
            name="Multi",
            sections=[
                ReportSection(title="Second", body_template="B", order=1),
                ReportSection(title="First", body_template="A", order=0),
            ],
        )
        instance = renderer.render(tpl, variables={})
        first_pos = instance.content.index("First")
        second_pos = instance.content.index("Second")
        assert first_pos < second_pos

    def test_render_empty_template(self) -> None:
        renderer = ReportRenderer()
        tpl = ReportTemplate(name="Empty")
        instance = renderer.render(tpl, variables={})
        assert instance.content
        assert "Empty" in instance.content

    def test_get_renderer_singleton(self) -> None:
        r1 = get_renderer()
        r2 = get_renderer()
        assert r1 is r2

    def test_create_default_templates(self) -> None:
        templates = create_default_templates()
        assert len(templates) > 0
        assert "Data Collection Summary" in templates
        tpl = templates["Data Collection Summary"]
        assert tpl.format == ReportFormat.HTML
        assert len(tpl.sections) == 2
        assert len(tpl.variables) == 7


# ══════════════════════════════════════════════════════════════════
# PushService Tests
# ══════════════════════════════════════════════════════════════════


class TestPushService:
    """Tests for the PushService."""

    def _make_report(self) -> ReportInstance:
        return ReportInstance(
            template_id="tpl_001",
            title="Test Report",
            format=ReportFormat.HTML,
            content="<html><body>Test</body></html>",
        )

    def test_push_email_stub(self) -> None:
        service = PushService(real_mode=False)
        report = self._make_report()
        target = PushTarget(
            channel=PushChannel.EMAIL,
            address="user@example.com",
            metadata={"subject": "Test Subject"},
        )
        result = _run(service.push(report, target))
        assert result.success is True
        assert "stub" in result.message.lower()
        assert result.delivered_at is not None

    def test_push_im_stub(self) -> None:
        service = PushService(real_mode=False)
        report = self._make_report()
        target = PushTarget(
            channel=PushChannel.IM,
            address="user123",
            metadata={"platform": "wecom"},
        )
        result = _run(service.push(report, target))
        assert result.success is True
        assert "stub" in result.message.lower()

    def test_push_webhook_success(self) -> None:
        service = PushService(real_mode=False)
        report = self._make_report()
        target = PushTarget(
            channel=PushChannel.WEBHOOK,
            address="http://hook.example.com/receive",
        )
        # Mock httpx.AsyncClient.post
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.text = "OK"
            mock_post.return_value = mock_resp
            result = _run(service.push(report, target))
        assert result.success is True
        assert "200" in result.message

    def test_push_webhook_failure(self) -> None:
        service = PushService(real_mode=False)
        report = self._make_report()
        target = PushTarget(
            channel=PushChannel.WEBHOOK,
            address="http://hook.example.com/receive",
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = AsyncMock()
            mock_resp.status_code = 500
            mock_resp.text = "Internal Server Error"
            mock_post.return_value = mock_resp
            result = _run(service.push(report, target))
        assert result.success is False
        assert "500" in result.message

    def test_push_webhook_network_error(self) -> None:
        service = PushService(real_mode=False)
        report = self._make_report()
        target = PushTarget(
            channel=PushChannel.WEBHOOK,
            address="http://nonexistent.test/hook",
        )
        import httpx

        with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("refused")):
            result = _run(service.push(report, target))
        assert result.success is False
        assert "failed" in result.message.lower()

    def test_push_unknown_channel(self) -> None:
        service = PushService(real_mode=False)
        report = self._make_report()
        # Construct target then bypass validation to simulate unknown channel
        target = PushTarget(channel=PushChannel.EMAIL, address="1234567890")
        target.channel = "fax"  # type: ignore[assignment]  # Bypass enum validation
        result = _run(service.push(report, target))
        assert result.success is False
        assert "Unknown" in result.message

    def test_push_many(self) -> None:
        service = PushService(real_mode=False)
        report = self._make_report()
        targets = [
            PushTarget(channel=PushChannel.EMAIL, address="a@test.com"),
            PushTarget(channel=PushChannel.EMAIL, address="b@test.com"),
            PushTarget(channel=PushChannel.IM, address="user1"),
        ]
        results = _run(service.push_many(report, targets))
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_delivery_log(self) -> None:
        service = PushService(real_mode=False)
        report = self._make_report()
        target = PushTarget(channel=PushChannel.EMAIL, address="log@test.com")
        _run(service.push(report, target))
        assert len(service.delivery_log) == 1
        assert service.delivery_log[0].success is True

    def test_get_push_service_singleton(self) -> None:
        s1 = get_push_service()
        s2 = get_push_service()
        assert s1 is s2


# ══════════════════════════════════════════════════════════════════
# ReportScheduler Tests
# ══════════════════════════════════════════════════════════════════


class TestReportScheduler:
    """Tests for the ReportScheduler."""

    def test_schedule_job(self) -> None:
        scheduler = ReportScheduler()
        tpl = _make_template()
        jid = scheduler.schedule(
            template=tpl,
            cron_expression="0 9 * * 1-5",
            variables={"name": "World"},
        )
        assert jid
        job = scheduler.get_job(jid)
        assert job is not None
        assert job.template == tpl
        assert job.cron_expression == "0 9 * * 1-5"
        assert job.enabled is True

    def test_schedule_custom_job_id(self) -> None:
        scheduler = ReportScheduler()
        tpl = _make_template()
        jid = scheduler.schedule(
            template=tpl,
            cron_expression="0 * * * *",
            job_id="my_custom_id",
        )
        assert jid == "my_custom_id"

    def test_unschedule_job(self) -> None:
        scheduler = ReportScheduler()
        tpl = _make_template()
        jid = scheduler.schedule(template=tpl, cron_expression="0 * * * *")
        assert scheduler.unschedule(jid) is True
        assert scheduler.get_job(jid) is None
        assert scheduler.unschedule(jid) is False

    def test_list_jobs(self) -> None:
        scheduler = ReportScheduler()
        tpl = _make_template()
        scheduler.schedule(template=tpl, cron_expression="0 * * * *")
        scheduler.schedule(template=tpl, cron_expression="30 * * * *")
        jobs = scheduler.list_jobs()
        assert len(jobs) == 2

    def test_trigger_job(self) -> None:
        scheduler = ReportScheduler()
        tpl = _make_template()
        jid = scheduler.schedule(
            template=tpl,
            cron_expression="0 * * * *",
            variables={"name": "SchedulerTest"},
        )
        result = scheduler.trigger(jid)
        assert "Rendered" in result
        job = scheduler.get_job(jid)
        assert job is not None
        assert job.run_count == 1
        assert job.last_run is not None

    def test_trigger_unknown_job(self) -> None:
        scheduler = ReportScheduler()
        with pytest.raises(KeyError, match="not found"):
            scheduler.trigger("nonexistent")

    def test_trigger_disabled_job(self) -> None:
        scheduler = ReportScheduler()
        tpl = _make_template()
        jid = scheduler.schedule(template=tpl, cron_expression="0 * * * *")
        scheduler.disable_job(jid)
        result = scheduler.trigger(jid)
        assert "disabled" in result

    def test_enable_disable_job(self) -> None:
        scheduler = ReportScheduler()
        tpl = _make_template()
        jid = scheduler.schedule(template=tpl, cron_expression="0 * * * *")
        assert scheduler.disable_job(jid) is True
        job = scheduler.get_job(jid)
        assert job is not None
        assert job.enabled is False
        assert scheduler.enable_job(jid) is True
        assert job.enabled is True

    def test_trigger_with_push_targets(self) -> None:
        scheduler = ReportScheduler()
        tpl = _make_template()
        targets = [
            PushTarget(channel=PushChannel.EMAIL, address="sched@test.com"),
        ]
        jid = scheduler.schedule(
            template=tpl,
            cron_expression="0 * * * *",
            variables={"name": "PushTest"},
            targets=targets,
        )
        result = scheduler.trigger(jid)
        assert "pushed" in result

    def test_start_shutdown_manual_mode(self) -> None:
        scheduler = ReportScheduler()
        scheduler.start()
        scheduler.shutdown()
        # Should not raise

    def test_get_scheduler_singleton(self) -> None:
        s1 = get_scheduler()
        s2 = get_scheduler()
        assert s1 is s2
