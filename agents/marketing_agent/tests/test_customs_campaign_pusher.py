"""Tests for customs-segment push delivery + compliance gates (P1-C, C-10)."""

from __future__ import annotations

from datetime import UTC, datetime

from agents.data_agent.customs_models import BuyerEntity
from agents.data_agent.push_service import PushResult, PushService
from agents.data_agent.report_models import PushChannel, PushTarget, ReportInstance
from agents.marketing_agent.customs_audience_connector import (
    CustomsAudienceConnector,
    SegmentComplianceStatus,
)
from agents.marketing_agent.customs_campaign_content import CustomsCampaignContent
from agents.marketing_agent.customs_campaign_pusher import (
    CustomsCampaignPusher,
    SegmentPushRequest,
)


class _FakePush(PushService):
    """Offline push service that records calls instead of hitting the network."""

    def __init__(self) -> None:
        self.calls: list[tuple[ReportInstance, PushTarget]] = []

    async def push(self, report: ReportInstance, target: PushTarget) -> PushResult:
        self.calls.append((report, target))
        return PushResult(
            target=target, success=True, message="fake", delivered_at=datetime.now(UTC)
        )


def _clean_segment():
    buyers = [
        BuyerEntity(
            raw_name="Globex Corp", normalized_name="globex corp",
            country="US", source_country="CN",
            import_count=30, total_value_usd=500_000.0,
            top_hs_codes=["8517"], top_ports=["Shanghai"],
            first_seen="2023-01-01", last_seen="2026-03-01",
        )
    ]
    return CustomsAudienceConnector().build_from_buyers(buyers)[0]


def _blocked_segment():
    buyers = [
        BuyerEntity(
            raw_name="SANCTIONED SAMPLE CORP", normalized_name="sanctioned sample corp",
            import_count=50, total_value_usd=900_000.0,
            top_hs_codes=["8517"], top_ports=["Shanghai"],
            last_seen="2026-01-01",
        )
    ]
    return CustomsAudienceConnector().build_from_buyers(buyers)[0]


def _content(seg):
    return CustomsCampaignContent(brand="云栖智能").generate(seg)


def test_build_report_is_derivative_only():
    seg = _clean_segment()
    report = CustomsCampaignPusher(_FakePush()).build_report(seg, _content(seg))
    assert report.format.value == "markdown"
    # report is aggregate-only: individual buyer PII must NOT leak into the body
    assert "Globex" not in report.content
    assert "可触达买家" in report.content
    assert "提单" in report.content  # explicit non-disclosure note present


async def test_blocked_segment_refused_async():
    pusher = CustomsCampaignPusher(_FakePush())
    seg = _blocked_segment()
    resp = await pusher.push_segment(
        seg, _content(seg),
        SegmentPushRequest(channel=PushChannel.WEBHOOK, address="https://hook.example.com"),
    )
    assert resp.success is False
    assert "不可触达" in resp.message


async def test_email_corporate_allowed_with_footer():
    fake = _FakePush()
    pusher = CustomsCampaignPusher(fake)
    seg = _clean_segment()
    req = SegmentPushRequest(
        channel=PushChannel.EMAIL,
        address="marketing@acme-corp.com",
        email="marketing@acme-corp.com",
        consent=True,
        unsubscribe_url="https://acme-corp.com/unsubscribe",
    )
    resp = await pusher.push_segment(seg, _content(seg), req)
    assert resp.success is True
    # footer force-appended (R2)
    sent_report = fake.calls[0][0]
    assert "unsubscribe" in sent_report.content.lower()


async def test_email_free_mailbox_denied():
    pusher = CustomsCampaignPusher(_FakePush())
    seg = _clean_segment()
    req = SegmentPushRequest(
        channel=PushChannel.EMAIL,
        address="buyer@gmail.com",
        email="buyer@gmail.com",
        consent=True,
        unsubscribe_url="https://x.com/u",
    )
    resp = await pusher.push_segment(seg, _content(seg), req)
    assert resp.success is False
    assert "free_mailbox" in resp.message or "personal" in resp.message


async def test_webhook_portal_only_allowed():
    fake = _FakePush()
    pusher = CustomsCampaignPusher(fake)
    seg = _clean_segment()
    req = SegmentPushRequest(channel=PushChannel.WEBHOOK, address="https://hook.example.com")
    resp = await pusher.push_segment(seg, _content(seg), req)
    assert resp.success is True
    assert len(fake.calls) == 1
