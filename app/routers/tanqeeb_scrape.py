"""Tanqeeb scraping API (persists into same ``jobs`` table as LinkedIn)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_superadmin
from app.models import User
from app.scraper.schemas import (
    ImportUrlResult,
    ImportUrlsResponse,
    TanqeebImportUrlsRequest,
    TanqeebSearchImportRequest,
)
from app.scraper.services.tanqeeb_runner import import_tanqeeb_search, import_tanqeeb_urls

router = APIRouter(prefix="/api/v1/tanqeeb_scrape", tags=["tanqeeb_scrape"])


@router.post("/import-search", response_model=ImportUrlsResponse, status_code=status.HTTP_200_OK)
async def import_search(
    request: TanqeebSearchImportRequest,
    _: User = Depends(require_superadmin),
) -> ImportUrlsResponse:
    """
    Crawl a Tanqeeb search URL (all pages until empty), scrape each job, and save rows.

    Field mapping to ``jobs`` / ``ScrapedJob``:

    - ``job_url`` -> ``linkedin_url`` (unique source URL column)
    - ``title`` -> ``job_title``
    - ``description`` -> ``job_description``
    - ``job_details`` key ``Post date`` -> ``posted_date``
    - remaining ``job_details`` entries -> ``extra_details`` as a JSON string
    - ``job_id`` is derived as ``tanqeeb-<digits>`` from the ``.html`` path
    """
    try:
        raw_results = await import_tanqeeb_search(
            search_url=request.search_url,
            timeout_seconds=request.timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tanqeeb scraper script missing: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tanqeeb import failed: {exc}",
        ) from exc

    results = [ImportUrlResult(**r) for r in raw_results]
    return ImportUrlsResponse(
        saved=sum(1 for r in results if r.status == "saved"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        errors=sum(1 for r in results if r.status == "error"),
        results=results,
    )


@router.post("/import-urls", response_model=ImportUrlsResponse, status_code=status.HTTP_200_OK)
async def import_urls(
    request: TanqeebImportUrlsRequest,
    _: User = Depends(require_superadmin),
) -> ImportUrlsResponse:
    """Scrape and persist specific Tanqeeb job URLs (same mapping as ``/import-search``)."""
    try:
        raw_results = await import_tanqeeb_urls(
            urls=request.urls,
            timeout_seconds=request.timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tanqeeb scraper script missing: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tanqeeb import failed: {exc}",
        ) from exc

    results = [ImportUrlResult(**r) for r in raw_results]
    return ImportUrlsResponse(
        saved=sum(1 for r in results if r.status == "saved"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        errors=sum(1 for r in results if r.status == "error"),
        results=results,
    )
