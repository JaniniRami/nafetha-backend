"""Scraping API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_superadmin
from app.models import User
from app.scraper.job_manager import job_manager
from app.scraper.schemas import (
    ImportUrlResult,
    ImportUrlsRequest,
    ImportUrlsResponse,
    JobStatusResponse,
    ScrapeRequest,
    StartJobResponse,
)
from app.scraper.services.scrape_runner import import_job_urls

router = APIRouter(prefix="/api/v1/linkedin_scrape", tags=["linkedin_scrape"])


@router.post("", response_model=StartJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_scrape(
    request: ScrapeRequest,
    _: User = Depends(require_superadmin),
) -> StartJobResponse:
    """
    Start a LinkedIn scrape job.

    Headless vs visible browser is controlled by ``HEADLESS_MODE`` in the environment
    (``true`` / ``1`` / ``yes`` = headless; otherwise visible).
    """
    job = await job_manager.create_job(request)
    return StartJobResponse(job_id=job.id, status=job.status)


@router.get("", response_model=list[JobStatusResponse])
async def list_jobs(_: User = Depends(require_superadmin)) -> list[JobStatusResponse]:
    return await job_manager.list_jobs()


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str, _: User = Depends(require_superadmin)) -> JobStatusResponse:
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job.to_response()


@router.post("/{job_id}/cancel", response_model=JobStatusResponse)
async def cancel_job(job_id: str, _: User = Depends(require_superadmin)) -> JobStatusResponse:
    job = await job_manager.cancel_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job.to_response()


@router.post("/import-urls", response_model=ImportUrlsResponse, status_code=status.HTTP_200_OK)
async def import_urls(
    request: ImportUrlsRequest,
    _: User = Depends(require_superadmin),
) -> ImportUrlsResponse:
    """
    Scrape and persist specific LinkedIn job URLs directly.

    Accepts a single URL or a list. Each URL is scraped, filtered, and saved
    exactly like a normal scrape job (blacklist/duplicate checks apply).

    Example body:
    ```json
    {
      "urls": [
        "https://www.linkedin.com/jobs/view/4359006443/",
        "https://www.linkedin.com/jobs/view/4376990611/"
      ]
    }
    ```
    """
    raw_results = await import_job_urls(
        urls=request.urls,
        session_path=request.session_path,
        delay_seconds=request.delay_seconds,
        verbose=request.verbose,
    )
    results = [ImportUrlResult(**r) for r in raw_results]
    return ImportUrlsResponse(
        saved=sum(1 for r in results if r.status == "saved"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        errors=sum(1 for r in results if r.status == "error"),
        results=results,
    )
