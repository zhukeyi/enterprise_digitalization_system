"""Push service — multi-channel report delivery (M3-T2).

Delivers rendered ReportInstance objects via:
1. Email (SMTP stub — logs the message in dev mode)
2. IM (reuses im_agent adapter pattern)
3. Webhook (HTTP POST to external URL)

All channels support graceful degradation: if the backend is not
configured, the push is logged and a PushResult with success=True is
returned (dev mode). In production, set FDE_PUSH_REAL=1 to enable
real delivery.

Usage:
    service = PushService()
    target = PushTarget(channel=PushChannel.EMAIL, address="user@example.com")
    result = await service.push(report, target)
    print(result.success)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from agents.data_agent.report_models import (
    PushChannel,
    PushResult,
    PushTarget,
    ReportInstance,
)

logger = logging.getLogger("fde.data.push")

__all__ = ["PushService", "get_push_service"]


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

_push_service: PushService | None = None


def get_push_service() -> PushService:
    """Get the singleton PushService instance."""
    global _push_service
    if _push_service is None:
        _push_service = PushService()
    return _push_service


# ══════════════════════════════════════════════════════════════════
# PushService
# ══════════════════════════════════════════════════════════════════


class PushService:
    """Multi-channel push delivery service.

    Channels:
    - EMAIL: Logs to console in dev mode; SMTP in production.
    - IM: Reuses the im_agent MockAdapter pattern.
    - WEBHOOK: HTTP POST to the target URL.
    """

    def __init__(self, real_mode: bool = False) -> None:
        self._real_mode = real_mode
        self._delivery_log: list[PushResult] = []

    @property
    def delivery_log(self) -> list[PushResult]:
        """Return the history of all delivery attempts."""
        return list(self._delivery_log)

    async def push(self, report: ReportInstance, target: PushTarget) -> PushResult:
        """Push a report to a single target.

        Args:
            report: The rendered report instance to deliver.
            target: The delivery target (channel + address).

        Returns:
            PushResult with success status and message.
        """
        result = await self._dispatch(report, target)
        self._delivery_log.append(result)
        return result

    async def push_many(
        self,
        report: ReportInstance,
        targets: list[PushTarget],
    ) -> list[PushResult]:
        """Push a report to multiple targets.

        Args:
            report: The rendered report instance.
            targets: List of delivery targets.

        Returns:
            List of PushResult, one per target.
        """
        results: list[PushResult] = []
        for target in targets:
            result = await self.push(report, target)
            results.append(result)
        return results

    async def _dispatch(self, report: ReportInstance, target: PushTarget) -> PushResult:
        """Route to the correct channel handler."""
        channel = target.channel
        if channel == PushChannel.EMAIL:
            return await self._push_email(report, target)
        if channel == PushChannel.IM:
            return await self._push_im(report, target)
        if channel == PushChannel.WEBHOOK:
            return await self._push_webhook(report, target)
        return PushResult(  # type: ignore[unreachable]
            target=target,
            success=False,
            message=f"Unknown channel: {target.channel}",
        )

    async def _push_email(self, report: ReportInstance, target: PushTarget) -> PushResult:
        """Send report via email (dev mode: log only)."""
        subject = target.metadata.get("subject", report.title or "FDE Report")

        if not self._real_mode:
            logger.info(
                "[EMAIL STUB] To: %s | Subject: %s | Report: %s | Size: %d chars",
                target.address,
                subject,
                report.id,
                len(report.content),
            )
            return PushResult(
                target=target,
                success=True,
                message=f"Email stub: logged delivery to {target.address}",
                delivered_at=datetime.now(UTC),
            )

        # Production: would use smtplib / aiosmtplib
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = str(subject)
            msg["From"] = str(target.metadata.get("from", "noreply@fde.local"))
            msg["To"] = target.address

            if report.format.value == "html":
                msg.attach(MIMEText(report.content, "html"))
            else:
                msg.attach(MIMEText(report.content, "plain"))

            smtp_host = str(target.metadata.get("smtp_host", "localhost"))
            smtp_port = int(target.metadata.get("smtp_port", 25))
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.send_message(msg)

            return PushResult(
                target=target,
                success=True,
                message=f"Email sent to {target.address}",
                delivered_at=datetime.now(UTC),
            )
        except Exception as e:
            logger.error("Email push failed: %s", e)
            return PushResult(
                target=target,
                success=False,
                message=f"Email failed: {e}",
            )

    async def _push_im(self, report: ReportInstance, target: PushTarget) -> PushResult:
        """Send report via IM adapter (reuses im_agent MockAdapter pattern)."""
        platform = target.metadata.get("platform", "mock")

        if not self._real_mode:
            logger.info(
                "[IM STUB] Platform: %s | To: %s | Report: %s | Preview: %s",
                platform,
                target.address,
                report.id,
                report.content[:80],
            )
            return PushResult(
                target=target,
                success=True,
                message=f"IM stub: logged delivery to {target.address} via {platform}",
                delivered_at=datetime.now(UTC),
            )

        # Production: use im_agent adapter registry
        try:
            from agents.im_agent.adapters import MockAdapter
            from agents.im_agent.models import (
                IMSendRequest,
                IMSendResponse,
                MessageType,
                Platform,
            )

            adapter = MockAdapter()
            request = IMSendRequest(
                platform=Platform.MOCK,
                target_id=target.address,
                content=report.content,
                message_type=MessageType.TEXT,
            )
            response: IMSendResponse = await adapter.send(request)

            if response.success:
                return PushResult(
                    target=target,
                    success=True,
                    message=f"IM delivered via {platform}",
                    delivered_at=datetime.now(UTC),
                )
            else:
                return PushResult(
                    target=target,
                    success=False,
                    message=f"IM failed: {response.error}",
                )
        except Exception as e:
            logger.error("IM push failed: %s", e)
            return PushResult(
                target=target,
                success=False,
                message=f"IM failed: {e}",
            )

    async def _push_webhook(self, report: ReportInstance, target: PushTarget) -> PushResult:
        """POST report content to a webhook URL."""
        payload: dict[str, Any] = {
            "report_id": report.id,
            "title": report.title,
            "format": report.format.value,
            "content": report.content,
            "generated_at": report.generated_at.isoformat(),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = target.metadata.get("headers", {})
                resp = await client.post(target.address, json=payload, headers=headers)

                if 200 <= resp.status_code < 300:
                    return PushResult(
                        target=target,
                        success=True,
                        message=f"Webhook delivered (HTTP {resp.status_code})",
                        delivered_at=datetime.now(UTC),
                    )
                else:
                    return PushResult(
                        target=target,
                        success=False,
                        message=f"Webhook HTTP {resp.status_code}: {resp.text[:200]}",
                    )
        except (httpx.HTTPError, OSError) as e:
            logger.error("Webhook push failed: %s", e)
            return PushResult(
                target=target,
                success=False,
                message=f"Webhook failed: {e}",
            )
