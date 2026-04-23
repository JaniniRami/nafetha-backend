"""In-memory background job manager for scraping jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from app.scraper.schemas import JobProgress, JobStatusResponse, ScrapeRequest

JobState = Literal["queued", "running", "completed", "failed", "cancelling", "cancelled"]

_MAX_JOB_LOG_LINES = 2000


def _append_job_log(job: ScrapeJob, message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job.log_lines.append(f"[{ts}] {message}")
    if len(job.log_lines) > _MAX_JOB_LOG_LINES:
        del job.log_lines[: len(job.log_lines) - _MAX_JOB_LOG_LINES]


@dataclass
class ScrapeJob:
    id: str
    request: ScrapeRequest
    status: JobState = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: JobProgress = field(default_factory=JobProgress)
    output_jobs_xlsx: str | None = None
    output_companies_xlsx: str | None = None
    error: str | None = None
    cancel_requested: bool = False
    task: asyncio.Task | None = None
    log_lines: list[str] = field(default_factory=list)

    def to_response(self) -> JobStatusResponse:
        progress = self.progress.model_copy(update={"logs": list(self.log_lines)})
        return JobStatusResponse(
            id=self.id,
            status=self.status,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            request=self.request,
            progress=progress,
            output_jobs_xlsx=self.output_jobs_xlsx,
            output_companies_xlsx=self.output_companies_xlsx,
            error=self.error,
        )


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, ScrapeJob] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, request: ScrapeRequest) -> ScrapeJob:
        job = ScrapeJob(id=str(uuid4()), request=request)
        async with self._lock:
            self._jobs[job.id] = job
            _append_job_log(job, "Job queued")
            job.task = asyncio.create_task(self._run_job(job.id), name=f"scrape-job-{job.id}")
        return job

    async def list_jobs(self) -> list[JobStatusResponse]:
        async with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda item: item.created_at, reverse=True)
        return [job.to_response() for job in jobs]

    async def get_job(self, job_id: str) -> ScrapeJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def cancel_job(self, job_id: str) -> ScrapeJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if job.status in {"completed", "failed", "cancelled"}:
                return job
            job.cancel_requested = True
            job.status = "cancelling"
            job.progress.last_message = "Cancellation requested"
            _append_job_log(job, "Cancellation requested")
            if job.task and not job.task.done():
                job.task.cancel()
            return job

    async def _run_job(self, job_id: str) -> None:
        job = await self.get_job(job_id)
        if not job:
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.progress.last_message = "Running"
        _append_job_log(job, "Running")

        async def update_progress(
            *,
            total_locations: int = 0,
            locations_completed: int = 0,
            current_location: str | None = None,
            pages_processed: int = 0,
            job_urls_found: int = 0,
            jobs_scraped: int = 0,
            companies_discovered: int = 0,
            companies_scraped: int = 0,
            last_message: str | None = None,
        ) -> None:
            if total_locations:
                job.progress.total_locations = total_locations
            if locations_completed:
                job.progress.locations_completed += locations_completed
            if current_location is not None:
                job.progress.current_location = current_location
            if pages_processed:
                job.progress.pages_processed += pages_processed
            if job_urls_found:
                job.progress.job_urls_found += job_urls_found
            if jobs_scraped:
                job.progress.jobs_scraped += jobs_scraped
            if companies_discovered:
                job.progress.companies_discovered += companies_discovered
            if companies_scraped:
                job.progress.companies_scraped += companies_scraped
            if last_message:
                job.progress.last_message = last_message
                _append_job_log(job, last_message)

        def is_cancel_requested() -> bool:
            return job.cancel_requested

        try:
            from app.scraper.services.scrape_runner import run_scrape_job

            outputs = await run_scrape_job(
                keywords=job.request.keywords,
                locations=job.request.locations,
                jobs_per_location=job.request.jobs_per_location,
                delay_seconds=job.request.delay_seconds,
                session_path=job.request.session_path,
                output_dir=job.request.output_dir,
                verbose=job.request.verbose,
                progress_updater=update_progress,
                is_cancel_requested=is_cancel_requested,
            )
            job.status = "completed"
            job.progress.last_message = "Completed"
            job.output_jobs_xlsx = None
            job.output_companies_xlsx = None
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.progress.last_message = "Cancelled"
            _append_job_log(job, "Cancelled")
        except Exception as exc:  # pragma: no cover
            job.status = "failed"
            job.error = str(exc)
            job.progress.last_message = "Failed"
            _append_job_log(job, f"Failed: {exc}")
        finally:
            job.completed_at = datetime.now(timezone.utc)


job_manager = JobManager()
