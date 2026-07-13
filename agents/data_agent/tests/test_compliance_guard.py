"""Tests for the customs-marketing compliance guard (P1-C C-5)."""

from __future__ import annotations

from agents.data_agent.compliance_guard import (
    ComplianceDecision,
    OutreachComplianceGate,
    SanctionsGuard,
    append_unsubscribe_footer,
    enterprise_outreach_allowed,
    screen_sanctions,
)


class TestSanctionsScreen:
    def test_sample_hit_blocks(self) -> None:
        guard = SanctionsGuard()
        result = guard.screen("SANCTIONED SAMPLE CORP")
        assert result.blocked
        assert result.hits
        assert result.hits[0].match_type == "exact"

    def test_alias_substring_hit(self) -> None:
        guard = SanctionsGuard()
        result = guard.screen("We are SSC partners Ltd")
        assert result.blocked  # 'ssc' alias matches substring

    def test_clean_name_passes(self) -> None:
        guard = SanctionsGuard()
        result = guard.screen("Acme Importers Inc.")
        assert not result.blocked
        assert result.hits == []

    def test_convenience_function(self) -> None:
        result = screen_sanctions("BLOCKED EXAMPLE HOLDINGS")
        assert result.blocked


class TestEnterpriseOutreach:
    def test_corporate_email_allowed(self) -> None:
        assert enterprise_outreach_allowed("buyer@acme.com", None) is True

    def test_free_email_denied(self) -> None:
        assert enterprise_outreach_allowed("buyer@gmail.com", None) is False
        assert enterprise_outreach_allowed("buyer@qq.com", None) is False

    def test_none_email_allowed(self) -> None:
        assert enterprise_outreach_allowed(None, None) is True

    def test_revoked_consent_denied(self) -> None:
        assert enterprise_outreach_allowed("buyer@acme.com", consent=False) is False


class TestUnsubscribeFooter:
    def test_footer_appended(self) -> None:
        text = "Hi Acme, learn about our connectors."
        out = append_unsubscribe_footer(text, "https://fde.example/unsub/abc")
        assert "https://fde.example/unsub/abc" in out
        assert "opt out" in out.lower()


class TestOutreachComplianceGate:
    def test_sanctioned_buyer_denied(self) -> None:
        gate = OutreachComplianceGate()
        decision = gate.evaluate(
            buyer_name="SANCTIONED SAMPLE CORP",
            email="contact@acme.com",
            unsubscribe_url="https://fde.example/unsub/x",
        )
        assert isinstance(decision, ComplianceDecision)
        assert not decision.allowed
        assert any("sanction" in r for r in decision.reasons)

    def test_clean_corporate_allowed(self) -> None:
        gate = OutreachComplianceGate()
        decision = gate.evaluate(
            buyer_name="Acme Importers Inc.",
            email="buyer@acme.com",
            unsubscribe_url="https://fde.example/unsub/x",
        )
        assert decision.allowed
        assert decision.reasons == ["ok"]

    def test_free_email_denied(self) -> None:
        gate = OutreachComplianceGate()
        decision = gate.evaluate(
            buyer_name="Acme Importers Inc.",
            email="buyer@gmail.com",
            unsubscribe_url="https://fde.example/unsub/x",
        )
        assert not decision.allowed
        assert "channel:free_mailbox_not_enterprise" in decision.reasons

    def test_missing_unsubscribe_denied(self) -> None:
        gate = OutreachComplianceGate()
        decision = gate.evaluate(
            buyer_name="Acme Importers Inc.",
            email="buyer@acme.com",
            # no unsubscribe_url
        )
        assert not decision.allowed
        assert "can_spam:missing_unsubscribe" in decision.reasons
