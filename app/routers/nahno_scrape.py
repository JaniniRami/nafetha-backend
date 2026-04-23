"""Nahno volunteering events scraping API."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import require_superadmin
from app.models import User
from app.scraper.schemas import NahnoImportRequest, NahnoImportResponse, NahnoImportResult
from app.scraper.services.nahno_runner import import_nahno_events

router = APIRouter(prefix="/api/v1/nahno_scrape", tags=["nahno_scrape"])


@router.post("/import-events", response_model=NahnoImportResponse, status_code=status.HTTP_200_OK)
async def import_events(
    request: NahnoImportRequest,
    _: User = Depends(require_superadmin),
) -> NahnoImportResponse:
    """
    Crawl Nahno volunteering listings, scrape each event page, and persist to ``volunteering_events``.

    Persistence is incremental: each event is written to DB right after it is scraped.
    """
    try:
        raw_results = await import_nahno_events(
            max_pages=request.max_pages,
            delay_seconds=request.delay_seconds,
            lang=request.lang,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nahno scraper script missing: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nahno import failed: {exc}",
        ) from exc

    results = [NahnoImportResult(**r) for r in raw_results]
    return NahnoImportResponse(
        saved=sum(1 for r in results if r.status == "saved"),
        skipped=sum(1 for r in results if r.status == "skipped"),
        errors=sum(1 for r in results if r.status == "error"),
        results=results,
    )
