import asyncio
import json
from typing import Any

from app.core.config import settings
from app.services.delay_risk_service import delay_risk_service
from app.services.email_orchestration_service import email_orchestration_service
from app.services.persistence_service import persistence_service


class SchedulerService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        persistence_service.ensure_default_jobs()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stopping:
            due_jobs = persistence_service.get_due_jobs()
            for job in due_jobs:
                await self._run_single_job(job)
            await asyncio.sleep(max(1, settings.scheduler_poll_seconds))

    async def _run_single_job(self, job: dict[str, Any]) -> None:
        payload_raw = job.get("payload_json") or "{}"
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}

        interval_seconds = int(job.get("interval_seconds") or 300)
        max_retries = int(job.get("max_retries") or 3)
        retry_count = int(job.get("retry_count") or 0)

        try:
            if job.get("job_type") == "process_unread_emails":
                await email_orchestration_service.process_unread(
                    mailbox=str(payload.get("mailbox", "INBOX")),
                    limit=int(payload.get("limit", 10)),
                )
            elif job.get("job_type") == "scan_delay_risks":
                delay_risk_service.scan_and_mark(auto_mark=bool(payload.get("auto_mark", True)))
            else:
                raise RuntimeError(f"Unsupported job_type: {job.get('job_type')}")

            persistence_service.mark_job_success(
                job_id=str(job["id"]),
                interval_seconds=interval_seconds,
            )
        except Exception as exc:
            persistence_service.mark_job_failure(
                job_id=str(job["id"]),
                interval_seconds=interval_seconds,
                max_retries=max_retries,
                retry_count=retry_count,
                error=str(exc),
            )

    async def run_job_now(self, job_id: str) -> None:
        persistence_service.run_job_now(job_id)


scheduler_service = SchedulerService()
