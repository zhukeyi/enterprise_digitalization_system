"""Report scheduler — APScheduler-based periodic report generation (M3-T2).

Schedules periodic report generation and push delivery:
1. Register report templates with a cron/interval schedule
2. On schedule trigger: render template → push to targets
3. Graceful degradation: if APScheduler is not installed, falls back
   to a simple in-memory task dict that can be triggered manually.

Usage:
    scheduler = ReportScheduler()
    scheduler.schedule(
        template_id="tpl_001",
        cron_expression="0 9 * * 1-5",  # 9 AM weekdays
        variables={"source": "web"},
        targets=[PushTarget(channel=PushChannel.EMAIL, address="user@example.com")],
    )
    scheduler.start()
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agents.data_agent.push_service import get_push_service
from agents.data_agent.report_models import PushTarget, ReportTemplate
from agents.data_agent.report_renderer import get_renderer

logger = logging.getLogger("fde.data.scheduler")

__all__ = ["ReportScheduler", "ScheduledReport", "get_scheduler"]


# ══════════════════════════════════════════════════════════════════
# APScheduler integration (graceful degradation)
# ══════════════════════════════════════════════════════════════════

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    _APS_AVAILABLE = True
except ImportError:
    _APS_AVAILABLE = False
    logger.info("apscheduler not installed; using manual scheduling fallback")


# ══════════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════════


@dataclass
class ScheduledReport:
    """A scheduled report generation job.

    Attributes:
        job_id: Unique job identifier.
        template: Report template to render.
        cron_expression: Cron schedule (e.g. "0 9 * * 1-5").
        variables: Variables for template rendering.
        targets: Push delivery targets.
        enabled: Whether the job is active.
        last_run: Last execution timestamp.
        last_result: Last execution result message.
        run_count: Total number of executions.
    """

    job_id: str
    template: ReportTemplate
    cron_expression: str
    variables: dict[str, Any] = field(default_factory=dict)
    targets: list[PushTarget] = field(default_factory=list)
    enabled: bool = True
    last_run: datetime | None = None
    last_result: str = ""
    run_count: int = 0


# ══════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════

_scheduler: ReportScheduler | None = None


def get_scheduler() -> ReportScheduler:
    """Get the singleton ReportScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ReportScheduler()
    return _scheduler


# ══════════════════════════════════════════════════════════════════
# ReportScheduler
# ══════════════════════════════════════════════════════════════════


class ReportScheduler:
    """Schedules and executes periodic report generation + push.

    Uses APScheduler if available; otherwise provides a manual
    trigger API for testing and dev environments.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledReport] = {}
        self._renderer = get_renderer()
        self._push_service = get_push_service()
        self._aps_scheduler: Any = None
        self._started = False

    def schedule(
        self,
        template: ReportTemplate,
        cron_expression: str,
        variables: dict[str, Any] | None = None,
        targets: list[PushTarget] | None = None,
        job_id: str | None = None,
    ) -> str:
        """Schedule a report for periodic generation.

        Args:
            template: Report template to render on schedule.
            cron_expression: Cron schedule expression.
            variables: Variables for template rendering.
            targets: Push delivery targets.
            job_id: Optional custom job ID (auto-generated if None).

        Returns:
            The job ID.
        """
        import uuid

        jid = job_id or f"job_{uuid.uuid4().hex[:8]}"
        job = ScheduledReport(
            job_id=jid,
            template=template,
            cron_expression=cron_expression,
            variables=variables or {},
            targets=targets or [],
        )
        self._jobs[jid] = job

        if _APS_AVAILABLE and self._started:
            self._register_aps_job(job)

        logger.info("Scheduled report '%s' with cron '%s'", template.name, cron_expression)
        return jid

    def unschedule(self, job_id: str) -> bool:
        """Remove a scheduled report job.

        Args:
            job_id: The job ID to remove.

        Returns:
            True if the job was found and removed.
        """
        if job_id not in self._jobs:
            return False

        if _APS_AVAILABLE and self._aps_scheduler is not None:
            with contextlib.suppress(Exception):
                self._aps_scheduler.remove_job(job_id)

        del self._jobs[job_id]
        logger.info("Unscheduled report job: %s", job_id)
        return True

    def start(self) -> None:
        """Start the scheduler (APScheduler background mode)."""
        if self._started:
            return

        if _APS_AVAILABLE:
            self._aps_scheduler = BackgroundScheduler()
            self._aps_scheduler.start()
            for job in self._jobs.values():
                self._register_aps_job(job)
            self._started = True
            logger.info("ReportScheduler started with APScheduler")
        else:
            self._started = True
            logger.info("ReportScheduler started in manual mode (no APScheduler)")

    def shutdown(self) -> None:
        """Shut down the scheduler."""
        if _APS_AVAILABLE and self._aps_scheduler is not None:
            self._aps_scheduler.shutdown(wait=False)
            self._aps_scheduler = None
        self._started = False
        logger.info("ReportScheduler shut down")

    def list_jobs(self) -> list[ScheduledReport]:
        """List all scheduled report jobs."""
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> ScheduledReport | None:
        """Get a scheduled job by ID."""
        return self._jobs.get(job_id)

    def trigger(self, job_id: str) -> str:
        """Manually trigger a scheduled report job.

        Renders the template and pushes to all targets.

        Args:
            job_id: The job ID to trigger.

        Returns:
            Result message.

        Raises:
            KeyError: If job_id is not found.
        """
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")

        if not job.enabled:
            return f"Job {job_id} is disabled"

        return self._execute_job(job)

    def _execute_job(self, job: ScheduledReport) -> str:
        """Execute a single scheduled report job (sync wrapper)."""
        import asyncio

        loop = None
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a task
                future = asyncio.run_coroutine_threadsafe(self._execute_job_async(job), loop)
                return future.result(timeout=60)
        except RuntimeError:
            pass

        # No running loop — create one
        return asyncio.run(self._execute_job_async(job))

    async def _execute_job_async(self, job: ScheduledReport) -> str:
        """Execute a scheduled report job (async)."""
        try:
            instance = self._renderer.render(job.template, job.variables)
            logger.info("Rendered report '%s' (job: %s)", instance.title, job.job_id)

            if job.targets:
                results = await self._push_service.push_many(instance, job.targets)
                success_count = sum(1 for r in results if r.success)
                msg = f"Rendered + pushed to {success_count}/{len(results)} targets"
            else:
                msg = f"Rendered report (no push targets): {instance.id}"

            job.last_run = datetime.now()
            job.last_result = msg
            job.run_count += 1
            return msg
        except Exception as e:
            job.last_run = datetime.now()
            job.last_result = f"Error: {e}"
            job.run_count += 1
            logger.error("Scheduled report execution failed: %s", e)
            return f"Error: {e}"

    def _register_aps_job(self, job: ScheduledReport) -> None:
        """Register a job with APScheduler."""
        if not _APS_AVAILABLE or self._aps_scheduler is None:
            return

        try:
            trigger = CronTrigger.from_crontab(job.cron_expression)
            self._aps_scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                args=[job],
                id=job.job_id,
                replace_existing=True,
            )
        except Exception as e:
            logger.error("Failed to register APScheduler job '%s': %s", job.job_id, e)

    def enable_job(self, job_id: str) -> bool:
        """Enable a disabled job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.enabled = True
        return True

    def disable_job(self, job_id: str) -> bool:
        """Disable an active job."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.enabled = False
        return True
