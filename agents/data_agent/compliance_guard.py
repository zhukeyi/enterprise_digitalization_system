"""Compliance guard for customs-derived GEO marketing (P1-C, C-5).

Implements the three P1-C compliance red lines for the marketing layer that
consumes the customs data base:

1. **Redistribution authorization** — handled upstream by delivering only
   ``BuyerEntity`` derivative profiles (never raw BOL). This module adds the
   **sanctions screen**: a buyer must pass OFAC/EU-style screening before any
   outreach.
2. **Privacy & anti-spam** — ``enterprise_outreach_allowed`` enforces corporate
   (non-personal) contact channels; ``append_unsubscribe_footer`` adds a
   CAN-SPAM/CASL/GDPR-compliant unsubscribe footer.
3. **Sanctions screening** — ``SanctionsGuard`` / ``OutreachComplianceGate``.

The default denylist is a clearly-labeled **SAMPLE**. Production MUST load the
official OFAC SDN / EU Consolidated list (YAML/JSON) via ``SanctionsGuard.load``.
Screening is permissive-by-design: a miss does not assert a party is clean.
"""

from __future__ import annotations

import re
from typing import Any

import yaml
from pydantic import BaseModel, Field

__all__ = [
    "ComplianceDecision",
    "OutreachComplianceGate",
    "SanctionHit",
    "SanctionsGuard",
    "SanctionsScreenResult",
    "append_unsubscribe_footer",
    "enterprise_outreach_allowed",
    "screen_sanctions",
]

# Free / personal mailbox domains — outreach to these is denied (privacy red line).
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "live.com",
        "qq.com",
        "163.com",
        "126.com",
        "foxmail.com",
        "icloud.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
        "mail.ru",
        "yandex.com",
        "naver.com",
        "gmx.com",
        "zoho.com",
    }
)

# SAMPLE denylist — replace with the official OFAC/EU consolidated list in prod.
_SAMPLE_DENYLIST: list[dict[str, Any]] = [
    {
        "name": "SANCTIONED SAMPLE CORP",
        "list_name": "OFAC-SDN-SAMPLE",
        "aliases": ["SSC", "SAMPLE CORP SANCTIONED", "SANCTIONED SAMPLE"],
    },
    {
        "name": "BLOCKED EXAMPLE HOLDINGS",
        "list_name": "EU-CONSOLIDATED-SAMPLE",
        "aliases": ["BEH", "BLOCKED EXAMPLE"],
    },
]


def _normalize_screen(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.,&/()]", " ", name.lower())).strip()


class SanctionHit(BaseModel):
    """A single sanction list match."""

    name: str = Field(description="Matched list entry name")
    list_name: str = Field(description="Sanction list identifier")
    match_type: str = Field(description="exact | substring | alias")
    score: float = Field(default=1.0, description="Match confidence (0-1)")


class SanctionsScreenResult(BaseModel):
    """Result of screening a name/country against sanction lists."""

    screened_name: str = Field(description="Normalized screened name")
    screened_country: str | None = Field(default=None, description="Screened country")
    hits: list[SanctionHit] = Field(default_factory=list)
    blocked: bool = Field(default=False, description="True if any hit blocked outreach")

    @property
    def reasons(self) -> list[str]:
        """Human-readable reasons for the decision."""
        return [f"sanction:{h.list_name}:{h.match_type}:{h.name}" for h in self.hits]


class SanctionsGuard:
    """Sanction-list screener (OFAC/EU-style)."""

    def __init__(self, denylist: list[dict[str, Any]] | None = None) -> None:
        """Initialize with a denylist.

        Args:
            denylist: List of ``{"name", "list_name", "aliases": [...]}`` entries.
                Defaults to a clearly-labeled SAMPLE (not for production use).
        """
        self._entries = denylist if denylist is not None else _SAMPLE_DENYLIST
        # Pre-normalize for substring/alias matching.
        self._norm: list[tuple[str, list[str], str, str]] = []
        for e in self._entries:
            name = _normalize_screen(str(e.get("name", "")))
            aliases = [_normalize_screen(a) for a in e.get("aliases", []) if a]
            self._norm.append((name, aliases, str(e.get("list_name", "UNKNOWN")), str(e.get("name", ""))))

    def load(self, path: str) -> None:
        """Load a denylist from a YAML/JSON file (official OFAC/EU consolidated list)."""
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if isinstance(data, dict) and "denylist" in data:
            data = data["denylist"]
        if not isinstance(data, list):
            raise ValueError("Denylist file must contain a list of entries")
        self._entries = data
        self._norm = []
        for e in self._entries:
            name = _normalize_screen(str(e.get("name", "")))
            aliases = [_normalize_screen(a) for a in e.get("aliases", []) if a]
            self._norm.append((name, aliases, str(e.get("list_name", "UNKNOWN")), str(e.get("name", ""))))

    def screen(self, name: str, country: str | None = None) -> SanctionsScreenResult:
        """Screen a name (and optional country) against the denylist.

        Args:
            name: Entity / buyer name to screen.
            country: Optional country for context (not yet used for blocking).

        Returns:
            SanctionsScreenResult with hits and ``blocked`` flag.
        """
        norm = _normalize_screen(name)
        hits: list[SanctionHit] = []
        for entry_name, aliases, list_name, raw_name in self._norm:
            if not entry_name:
                continue
            if norm == entry_name:
                hits.append(SanctionHit(name=raw_name, list_name=list_name, match_type="exact", score=1.0))
            elif entry_name in norm or norm in entry_name:
                hits.append(SanctionHit(name=raw_name, list_name=list_name, match_type="substring", score=0.9))
            else:
                for alias in aliases:
                    if alias and (alias in norm or norm in alias):
                        hits.append(
                            SanctionHit(name=raw_name, list_name=list_name, match_type="alias", score=0.8)
                        )
                        break
        return SanctionsScreenResult(
            screened_name=norm,
            screened_country=country,
            hits=hits,
            blocked=bool(hits),
        )


class ComplianceDecision(BaseModel):
    """Final outreach compliance decision."""

    allowed: bool = Field(default=False, description="Whether outreach is permitted")
    reasons: list[str] = Field(default_factory=list, description="Reasons (allowed/denied)")


class OutreachComplianceGate:
    """Composite gate: sanctions screen + enterprise channel + (optional) consent."""

    def __init__(self, guard: SanctionsGuard | None = None) -> None:
        self._guard = guard or SanctionsGuard()

    def evaluate(
        self,
        *,
        buyer_name: str,
        country: str | None = None,
        email: str | None = None,
        consent: bool | None = None,
        unsubscribe_url: str | None = None,
    ) -> ComplianceDecision:
        """Evaluate whether outbound marketing to a buyer is compliant.

        Args:
            buyer_name: Buyer / consignee name.
            country: Buyer country.
            email: Contact email (corporate channel required).
            consent: Explicit consent flag (``False`` hard-denies).
            unsubscribe_url: Required for email outreach (CAN-SPAM/CASL).

        Returns:
            ComplianceDecision (allowed / denied + reasons).
        """
        reasons: list[str] = []

        screen = self._guard.screen(buyer_name, country)
        if screen.blocked:
            reasons.extend(screen.reasons)
            return ComplianceDecision(allowed=False, reasons=reasons)

        if email is not None:
            if not enterprise_outreach_allowed(email, consent):
                reasons.append("channel:personal_or_no_consent")
                if consent is False:
                    reasons.append("consent:revoked")
                if _is_free_email(email):
                    reasons.append("channel:free_mailbox_not_enterprise")
            if not unsubscribe_url:
                reasons.append("can_spam:missing_unsubscribe")

        if reasons:
            return ComplianceDecision(allowed=False, reasons=reasons)
        return ComplianceDecision(allowed=True, reasons=["ok"])


def _is_free_email(email: str) -> bool:
    email = email.strip().lower()
    if "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1]
    return domain in FREE_EMAIL_DOMAINS


def enterprise_outreach_allowed(email: str | None, consent: bool | None = None) -> bool:
    """Whether outreach to ``email`` is permitted on enterprise / anti-spam grounds.

    Rules:
    * ``None`` email → allowed (e.g., portal-only outreach, no PII).
    * Personal/free mailbox → denied (PIPL/GDPR/ePrivacy risk).
    * Explicit ``consent is False`` → denied.

    Args:
        email: Contact email, or ``None`` for channel-free outreach.
        consent: Explicit consent flag.

    Returns:
        True if outreach is permitted.
    """
    if consent is False:
        return False
    if email is None:
        return True
    return not _is_free_email(email)


def append_unsubscribe_footer(text: str, unsubscribe_url: str) -> str:
    """Append a CAN-SPAM / CASL / GDPR-compliant unsubscribe footer to ``text``.

    Args:
        text: Original message body.
        unsubscribe_url: One-click unsubscribe URL.

    Returns:
        ``text`` with an appended unsubscribe block.
    """
    footer = (
        "\n\n---\n"
        "You are receiving this business communication as a corporate entity derived from "
        "public trade-data intelligence. You may opt out of future communications at any time: "
        f"{unsubscribe_url}\n"
        "If you believe this message was sent in error, reply with 'UNSUBSCRIBE'."
    )
    return text + footer


# Module-level singletons / convenience functions
_default_guard = SanctionsGuard()


def screen_sanctions(name: str, country: str | None = None) -> SanctionsScreenResult:
    """Convenience: screen using the default guard."""
    return _default_guard.screen(name, country)
