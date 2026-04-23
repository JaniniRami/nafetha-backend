"""Superadmin JSON API for managing scraped companies and jobs."""

import asyncio
import json
import time
from datetime import datetime, timezone
import re
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.company_display_ai import (
    generate_display_fields_from_about,
    keywords_to_stored_string,
)
from app.job_display_ai import generate_display_fields_from_job_description
from app.config import HEADLESS_MODE, OLLAMA_MODEL
from app.database import get_db
from app.database import SessionLocal
from app.deps import require_superadmin
from app.models import (
    ProfilePrerequisite,
    ScrapedCompany,
    ScrapedJob,
    User,
    UserRoadmap,
    UserRoadmapStep,
    VolunteeringEvent,
)
from app.scraper.services.linkedin_runtime import (
    LinkedInScraperUnavailable,
    get_browser_manager_class,
)
from app.volunteering_keyword_ai import classify_volunteering_keyword
from app.schemas import (
    CompanyAboutBackfillRequest,
    CompanyAboutBackfillResponse,
    CompanyAboutBackfillJobQueued,
    CompanyAboutBackfillJobStatus,
    CompanyAboutBackfillRowResult,
    CompanyDisplayAIJobQueued,
    CompanyDisplayAIJobRequest,
    CompanyDisplayAIJobStatus,
    CompanyDisplayAIResponse,
    JobDisplayAIJobQueued,
    JobDisplayAIJobRequest,
    JobDisplayAIJobStatus,
    JobDisplayAIResponse,
    ScrapedCompanyCreate,
    ScrapedCompanyOut,
    ScrapedCompanyUpdate,
    ScrapedJobCreate,
    ScrapedJobOut,
    ScrapedJobUpdate,
    VolunteeringKeywordAIResponse,
    VolunteeringEventOut,
    VolunteeringEventUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_about_backfill_jobs: dict[str, CompanyAboutBackfillJobStatus] = {}
_display_ai_jobs: dict[str, CompanyDisplayAIJobStatus] = {}
_job_display_ai_jobs: dict[str, JobDisplayAIJobStatus] = {}

# Per-URL browser cap; slow/hung LinkedIn loads fall through to website when one exists.
_BROWSER_FETCH_TIMEOUT_SEC = 75.0

# Long-poll window for GET .../jobs/{id}?wait=1 (reduces client poll spam).
_JOB_STATUS_WAIT_MAX_SEC = 55.0
_JOB_STATUS_WAIT_INTERVAL_SEC = 1.5


def _normalize_text(text: str, *, max_chars: int = 2000) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    return compact[:max_chars]


async def _fetch_with_browser(url: str) -> tuple[str | None, str | None]:
    try:
        BrowserManager = get_browser_manager_class()
        async with BrowserManager(headless=HEADLESS_MODE) as browser:
            await browser.page.goto(url, wait_until="domcontentloaded")
            await browser.page.wait_for_timeout(1500)
            page_text = await browser.page.evaluate(
                """
                () => {
                  const selectors = [
                    "script","style","noscript","svg","template","iframe",
                    "header","footer","nav","aside",
                    '[id*="cookie" i]','[class*="cookie" i]',
                    '[id*="consent" i]','[class*="consent" i]',
                    '[id*="banner" i]','[class*="banner" i]',
                    '[id*="modal" i]','[class*="modal" i]',
                    '[id*="popup" i]','[class*="popup" i]'
                  ];
                  selectors.forEach((sel) => {
                    document.querySelectorAll(sel).forEach((el) => el.remove());
                  });
                  return (document.body && document.body.innerText) ? document.body.innerText : "";
                }
                """
            )
    except LinkedInScraperUnavailable as exc:
        return None, f"browser_unavailable:{exc}"
    except Exception as exc:
        return None, f"browser_fetch_failed:{exc}"

    text = _normalize_text(str(page_text or ""))
    if not text:
        return None, "empty_content_after_cleanup"
    return text, None


async def _fetch_about_with_timeout(url: str) -> tuple[str | None, str | None]:
    """Run ``_fetch_with_browser`` with a wall-clock cap so callers can try another URL (e.g. website after LinkedIn)."""
    try:
        return await asyncio.wait_for(
            _fetch_with_browser(url),
            timeout=_BROWSER_FETCH_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        return None, "fetch_timeout"


def _generate_job_external_id() -> str:
    """Stable unique string for ``jobs.job_id`` (max 64). Prefix marks admin-created rows."""
    return f"admin-{uuid4().hex}"


def _linkedin_url_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s or None


def _pgcode(exc: IntegrityError) -> str | None:
    for candidate in (getattr(exc, "orig", None), getattr(exc, "__cause__", None)):
        if candidate is None:
            continue
        code = getattr(candidate, "pgcode", None)
        if code:
            return str(code)
    return None


def _diag_constraint_name(exc: IntegrityError) -> str | None:
    for candidate in (getattr(exc, "orig", None), getattr(exc, "__cause__", None), exc):
        if candidate is None:
            continue
        diag = getattr(candidate, "diag", None)
        if diag is None:
            continue
        name = getattr(diag, "constraint_name", None)
        if name:
            return str(name)
    return None


def _unique_violation_key_column(message: str) -> str | None:
    """Parse Postgres DETAIL ``Key (colname)=`` (flexible whitespace)."""
    m = re.search(r"key\s*\(\s*([^)]+?)\s*\)\s*=", message, flags=re.IGNORECASE)
    if not m:
        return None
    key = m.group(1).strip().lower().strip('"')
    if "," in key:
        return None
    if key == "company_name":
        return "company_name"
    if key == "linkedin_url":
        return "linkedin_url"
    return None


def _classify_company_integrity_error(exc: IntegrityError) -> str:
    """Return ``name``, ``linkedin``, ``duplicate``, ``linkedin_not_null``, or ``other``.

    Only ``exc.orig`` (DBAPI) text is used for substrings: ``str(exc)`` often embeds
    the full INSERT and lists every column, which breaks naive ``in`` checks.
    """
    orig = getattr(exc, "orig", None)
    orig_text = str(orig or "")
    orig_lower = orig_text.lower()
    combined_lower = orig_lower + "\n" + str(exc).lower()

    # NOT NULL on linkedin_url when DB was never migrated to nullable (23502).
    if _pgcode(exc) == "23502" or "not null violation" in combined_lower or "23502" in combined_lower:
        if "linkedin_url" in combined_lower:
            return "linkedin_not_null"

    col = _unique_violation_key_column(orig_text)
    if col == "company_name":
        return "name"
    if col == "linkedin_url":
        return "linkedin"

    cn = (_diag_constraint_name(exc) or "").lower()
    if cn:
        if "company_name" in cn or "ix_companies_company_name" in cn:
            return "name"
        if "linkedin" in cn or "ix_companies_linkedin_url" in cn:
            return "linkedin"

    if "ix_companies_company_name" in orig_lower:
        return "name"
    if "ix_companies_linkedin_url" in orig_lower:
        return "linkedin"

    if _pgcode(exc) == "23505":
        return "duplicate"

    exc_lower = str(exc).lower()
    if "23505" in exc_lower or "uniqueviolation" in exc_lower.replace(" ", ""):
        return "duplicate"

    return "other"


@router.get("/companies", response_model=list[ScrapedCompanyOut])
def admin_list_companies(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> list[ScrapedCompany]:
    stmt = select(ScrapedCompany).order_by(ScrapedCompany.scraped_at.desc())
    return list(db.scalars(stmt).all())


@router.get("/companies/{company_id}", response_model=ScrapedCompanyOut)
def admin_get_company(
    company_id: UUID,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> ScrapedCompany:
    row = db.get(ScrapedCompany, company_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return row


@router.post("/companies", response_model=ScrapedCompanyOut, status_code=status.HTTP_201_CREATED)
def admin_create_company(
    payload: ScrapedCompanyCreate,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> ScrapedCompany:
    linkedin_url = _linkedin_url_or_none(payload.linkedin_url)

    if db.scalar(select(ScrapedCompany.id).where(ScrapedCompany.company_name == payload.company_name).limit(1)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this name already exists.",
        )
    if linkedin_url is not None and db.scalar(
        select(ScrapedCompany.id).where(ScrapedCompany.linkedin_url == linkedin_url).limit(1)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A company with this LinkedIn URL already exists.",
        )

    row = ScrapedCompany(
        company_name=payload.company_name,
        linkedin_url=linkedin_url,
        blacklisted=payload.blacklisted,
        industry=payload.industry,
        company_size=payload.company_size,
        website=payload.website,
        phone=payload.phone,
        about_us=payload.about_us,
        displayed_description=payload.displayed_description,
        displayed_keywords=payload.displayed_keywords,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        kind = _classify_company_integrity_error(exc)
        if kind == "name":
            detail = "A company with this name already exists."
        elif kind == "linkedin":
            detail = "A company with this LinkedIn URL already exists."
        elif kind == "duplicate":
            detail = "A company with this name or LinkedIn URL already exists."
        else:
            detail = "Could not create company (database constraint violation)."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None
    db.refresh(row)
    return row


@router.patch("/companies/{company_id}", response_model=ScrapedCompanyOut)
def admin_update_company(
    company_id: UUID,
    payload: ScrapedCompanyUpdate,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> ScrapedCompany:
    row = db.get(ScrapedCompany, company_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if "company_name" in data:
        name = data["company_name"]
        if db.scalar(
            select(ScrapedCompany.id)
            .where(ScrapedCompany.company_name == name, ScrapedCompany.id != company_id)
            .limit(1)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A company with this name already exists.",
            )
        row.company_name = name

    if "linkedin_url" in data:
        linkedin_url = _linkedin_url_or_none(data["linkedin_url"]) if data["linkedin_url"] is not None else None
        if linkedin_url is not None and db.scalar(
            select(ScrapedCompany.id)
            .where(ScrapedCompany.linkedin_url == linkedin_url, ScrapedCompany.id != company_id)
            .limit(1)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A company with this LinkedIn URL already exists.",
            )
        row.linkedin_url = linkedin_url

    if "blacklisted" in data:
        row.blacklisted = bool(data["blacklisted"])
    if "industry" in data:
        row.industry = data["industry"]
    if "company_size" in data:
        row.company_size = data["company_size"]
    if "website" in data:
        row.website = data["website"]
    if "phone" in data:
        row.phone = data["phone"]
    if "about_us" in data:
        row.about_us = data["about_us"]
    if "displayed_description" in data:
        row.displayed_description = data["displayed_description"]
    if "displayed_keywords" in data:
        row.displayed_keywords = data["displayed_keywords"]

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        kind = _classify_company_integrity_error(exc)
        if kind == "name":
            detail = "A company with this name already exists."
        elif kind == "linkedin":
            detail = "A company with this LinkedIn URL already exists."
        elif kind == "duplicate":
            detail = "A company with this name or LinkedIn URL already exists."
        else:
            detail = "Could not update company (database constraint violation)."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from None
    db.refresh(row)
    return row


def _has_any_display_field(row: ScrapedCompany) -> bool:
    """True if displayed description or keywords already has content."""
    d = (row.displayed_description or "").strip()
    k = (row.displayed_keywords or "").strip()
    return bool(d or k)


def _rows_for_display_ai_job(db: Session, payload: CompanyDisplayAIJobRequest) -> list[ScrapedCompany]:
    stmt = select(ScrapedCompany).order_by(ScrapedCompany.scraped_at.desc())
    if payload.company_ids:
        stmt = stmt.where(ScrapedCompany.id.in_(payload.company_ids))
    if not payload.company_ids and payload.limit is not None:
        stmt = stmt.limit(payload.limit)
    return list(db.scalars(stmt).all())


def _assign_display_fields_from_ai_parse(row: ScrapedCompany, parsed: dict[str, Any]) -> None:
    keywords_str = keywords_to_stored_string(parsed.get("keywords", []))
    row.displayed_description = (parsed.get("description") or "").strip() or None
    row.displayed_keywords = keywords_str or None


@router.post("/companies/{company_id}/ai-display", response_model=CompanyDisplayAIResponse)
def admin_company_generate_ai_display_fields(
    company_id: UUID,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> CompanyDisplayAIResponse:
    """Use local Ollama on ``about_us`` to fill ``displayed_description`` and ``displayed_keywords`` when extraction succeeds."""
    if not OLLAMA_MODEL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OLLAMA_MODEL is not configured.",
        )

    row = db.get(ScrapedCompany, company_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    about = (row.about_us or "").strip()
    if not about:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company has no about_us text to analyze.",
        )

    try:
        parsed = generate_display_fields_from_about(about)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Model response could not be parsed: {exc}",
        ) from exc

    if not parsed["success"]:
        return CompanyDisplayAIResponse(
            success=False,
            description="",
            keywords=[],
            saved=False,
            company=None,
        )

    _assign_display_fields_from_ai_parse(row, parsed)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not save display fields: {exc}",
        ) from exc
    db.refresh(row)

    return CompanyDisplayAIResponse(
        success=True,
        description=parsed["description"],
        keywords=parsed["keywords"],
        saved=True,
        company=ScrapedCompanyOut.model_validate(row),
    )


async def _enqueue_about_backfill_job(payload: CompanyAboutBackfillRequest) -> CompanyAboutBackfillJobQueued:
    """Must be called from an ``async`` route so ``asyncio.create_task`` has a running event loop."""
    print(
        "[about-backfill] enqueue job "
        f"n_company_ids={len(payload.company_ids)} only_missing={payload.only_missing} limit={payload.limit}",
        flush=True,
    )
    job_id = str(uuid4())
    _about_backfill_jobs[job_id] = CompanyAboutBackfillJobStatus(
        job_id=job_id,
        status="queued",
        only_missing=payload.only_missing,
        company_ids=list(payload.company_ids),
        limit=payload.limit,
        created_at=datetime.now(timezone.utc),
    )
    asyncio.create_task(_run_company_about_backfill_job(job_id))
    return CompanyAboutBackfillJobQueued(job_id=job_id, status="queued")


@router.post("/companies/{company_id}/backfill-about", response_model=CompanyAboutBackfillResponse)
async def admin_backfill_one_company_about(
    company_id: UUID,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> CompanyAboutBackfillResponse:
    """Fetch and save ``about_us`` for this company only (synchronous; no job queue)."""
    print(f"[about-backfill] single POST /companies/{{id}}/backfill-about company_id={company_id}", flush=True)
    if db.get(ScrapedCompany, company_id) is None:
        print(f"[about-backfill] single company not found: {company_id}", flush=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    payload = CompanyAboutBackfillRequest(company_ids=[company_id], only_missing=True)
    result = await _run_company_about_backfill(db, payload)
    print(
        "[about-backfill] single company finished "
        f"id={company_id} processed={result.processed} updated={result.updated} "
        f"skipped={result.skipped} failed={result.failed}",
        flush=True,
    )
    return result


async def _run_company_display_ai_job(job_id: str) -> None:
    job = _display_ai_jobs.get(job_id)
    if job is None:
        return

    if not OLLAMA_MODEL:
        job.status = "failed"
        job.error = "OLLAMA_MODEL is not configured."
        job.completed_at = datetime.now(timezone.utc)
        return

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)

    payload = CompanyDisplayAIJobRequest(
        company_ids=list(job.company_ids),
        only_missing_display=job.only_missing_display,
        limit=job.limit,
    )
    db = SessionLocal()
    updated = 0
    skipped = 0
    failed = 0
    declined = 0
    try:
        rows = _rows_for_display_ai_job(db, payload)
        job.processed = len(rows)
        for row in rows:
            about = (row.about_us or "").strip()
            if not about:
                skipped += 1
                continue
            if job.only_missing_display and _has_any_display_field(row):
                skipped += 1
                continue
            try:
                parsed = await asyncio.to_thread(generate_display_fields_from_about, about)
            except RuntimeError as exc:
                db.rollback()
                job.updated = updated
                job.skipped = skipped
                job.failed = failed
                job.declined = declined
                job.status = "failed"
                job.error = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                return
            except Exception:
                db.rollback()
                failed += 1
                continue
            if not parsed.get("success"):
                declined += 1
                continue
            try:
                _assign_display_fields_from_ai_parse(row, parsed)
                db.commit()
                updated += 1
            except IntegrityError:
                db.rollback()
                failed += 1
        job.updated = updated
        job.skipped = skipped
        job.failed = failed
        job.declined = declined
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        db.rollback()
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = datetime.now(timezone.utc)
    finally:
        db.close()


@router.post("/companies/ai-display/jobs", response_model=CompanyDisplayAIJobQueued)
async def admin_enqueue_company_display_ai(
    payload: CompanyDisplayAIJobRequest,
    _: User = Depends(require_superadmin),
) -> CompanyDisplayAIJobQueued:
    """Background job: fill displayed fields from about_us. With default ``only_missing_display``, only rows with both fields empty are processed."""
    job_id = str(uuid4())
    _display_ai_jobs[job_id] = CompanyDisplayAIJobStatus(
        job_id=job_id,
        status="queued",
        only_missing_display=payload.only_missing_display,
        company_ids=list(payload.company_ids),
        limit=payload.limit,
        created_at=datetime.now(timezone.utc),
    )
    asyncio.create_task(_run_company_display_ai_job(job_id))
    return CompanyDisplayAIJobQueued(job_id=job_id, status="queued")


@router.get("/companies/ai-display/jobs/{job_id}", response_model=CompanyDisplayAIJobStatus)
async def admin_get_company_display_ai_job(
    job_id: str,
    wait: bool = False,
    _: User = Depends(require_superadmin),
) -> CompanyDisplayAIJobStatus:
    job = _display_ai_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI display job not found")
    if not wait:
        return job
    deadline = time.monotonic() + _JOB_STATUS_WAIT_MAX_SEC
    while job.status not in ("completed", "failed"):
        if time.monotonic() >= deadline:
            return job
        await asyncio.sleep(_JOB_STATUS_WAIT_INTERVAL_SEC)
    return job


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_company(
    company_id: UUID,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(ScrapedCompany, company_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    db.delete(row)
    db.commit()


def _build_company_backfill_query(payload: CompanyAboutBackfillRequest):
    stmt = select(ScrapedCompany).order_by(ScrapedCompany.scraped_at.desc())
    if len(payload.company_ids) > 0:
        stmt = stmt.where(ScrapedCompany.id.in_(payload.company_ids))
    elif payload.only_missing:
        stmt = stmt.where(
            or_(
                ScrapedCompany.about_us.is_(None),
                func.length(func.trim(ScrapedCompany.about_us)) == 0,
            )
        )
    if len(payload.company_ids) == 0 and payload.limit is not None:
        stmt = stmt.limit(payload.limit)
    return stmt


async def _run_company_about_backfill(
    db: Session,
    payload: CompanyAboutBackfillRequest,
) -> CompanyAboutBackfillResponse:
    print(
        "[about-backfill] run start "
        f"n_company_ids={len(payload.company_ids)} only_missing={payload.only_missing} limit={payload.limit}",
        flush=True,
    )
    stmt = _build_company_backfill_query(payload)
    rows = list(db.scalars(stmt).all())
    print(f"[about-backfill] query matched {len(rows)} company row(s)", flush=True)
    results: list[CompanyAboutBackfillRowResult] = []
    updated = 0
    skipped = 0
    failed = 0

    for row in rows:
        preferred_source_url = (row.linkedin_url or "").strip() or (row.website or "").strip() or None
        if payload.only_missing and row.about_us and row.about_us.strip():
            skipped += 1
            results.append(
                CompanyAboutBackfillRowResult(
                    company_id=row.id,
                    company_name=row.company_name,
                    source_url=preferred_source_url,
                    status="skipped",
                    reason="already_has_about",
                )
            )
            continue

        linkedin_url = (row.linkedin_url or "").strip()
        website_url = (row.website or "").strip()
        if not linkedin_url and not website_url:
            skipped += 1
            results.append(
                CompanyAboutBackfillRowResult(
                    company_id=row.id,
                    company_name=row.company_name,
                    source_url=None,
                    status="skipped",
                    reason="missing_source_url",
                )
            )
            continue

        source_url: str | None = None
        text: str | None = None
        errors: list[str] = []

        if linkedin_url:
            text, err = await _fetch_about_with_timeout(
                linkedin_url,
            )
            if text:
                source_url = linkedin_url
            elif err:
                errors.append(f"linkedin_url:{err}")

        if text is None and website_url:
            text, err = await _fetch_about_with_timeout(
                website_url,
            )
            if text:
                source_url = website_url
            elif err:
                errors.append(f"website:{err}")

        if not text:
            failed += 1
            results.append(
                CompanyAboutBackfillRowResult(
                    company_id=row.id,
                    company_name=row.company_name,
                    source_url=preferred_source_url,
                    status="failed",
                    reason="; ".join(errors) if errors else "unknown_error",
                )
            )
            continue

        row.about_us = text
        updated += 1
        results.append(
            CompanyAboutBackfillRowResult(
                company_id=row.id,
                company_name=row.company_name,
                source_url=source_url,
                status="updated",
                saved_chars=len(text),
            )
        )

    if updated:
        db.commit()

    print(
        "[about-backfill] run end "
        f"processed={len(rows)} updated={updated} skipped={skipped} failed={failed}",
        flush=True,
    )
    return CompanyAboutBackfillResponse(
        processed=len(rows),
        updated=updated,
        skipped=skipped,
        failed=failed,
        results=results,
    )


async def _run_company_about_backfill_job(job_id: str) -> None:
    job = _about_backfill_jobs.get(job_id)
    if job is None:
        return
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)

    payload = CompanyAboutBackfillRequest(
        company_ids=job.company_ids,
        only_missing=job.only_missing,
        limit=job.limit,
    )
    print(
        "[about-backfill] queued job running "
        f"job_id={job_id} n_company_ids={len(payload.company_ids)} only_missing={payload.only_missing} limit={payload.limit}",
        flush=True,
    )
    db = SessionLocal()
    try:
        result = await _run_company_about_backfill(db, payload)
        job.processed = result.processed
        job.updated = result.updated
        job.skipped = result.skipped
        job.failed = result.failed
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        db.rollback()
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = datetime.now(timezone.utc)
    finally:
        db.close()


@router.post("/companies/backfill-about", response_model=CompanyAboutBackfillResponse)
async def admin_backfill_company_about(
    payload: CompanyAboutBackfillRequest,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> CompanyAboutBackfillResponse:
    return await _run_company_about_backfill(db, payload)


@router.post("/companies/backfill-about/jobs", response_model=CompanyAboutBackfillJobQueued)
async def admin_enqueue_company_about_backfill(
    payload: CompanyAboutBackfillRequest,
    _: User = Depends(require_superadmin),
) -> CompanyAboutBackfillJobQueued:
    return await _enqueue_about_backfill_job(payload)


@router.get("/companies/backfill-about/jobs/{job_id}", response_model=CompanyAboutBackfillJobStatus)
async def admin_get_company_about_backfill_job(
    job_id: str,
    wait: bool = False,
    _: User = Depends(require_superadmin),
) -> CompanyAboutBackfillJobStatus:
    job = _about_backfill_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backfill job not found")
    if not wait:
        return job
    deadline = time.monotonic() + _JOB_STATUS_WAIT_MAX_SEC
    while job.status not in ("completed", "failed"):
        if time.monotonic() >= deadline:
            return job
        await asyncio.sleep(_JOB_STATUS_WAIT_INTERVAL_SEC)
    return job


def _has_any_job_display_field(row: ScrapedJob) -> bool:
    d = (row.displayed_description or "").strip()
    k = (row.displayed_keywords or "").strip()
    return bool(d or k)


def _rows_for_job_display_ai_job(db: Session, payload: JobDisplayAIJobRequest) -> list[ScrapedJob]:
    stmt = select(ScrapedJob).order_by(ScrapedJob.scraped_at.desc())
    if payload.job_ids:
        stmt = stmt.where(ScrapedJob.id.in_(payload.job_ids))
    if not payload.job_ids and payload.limit is not None:
        stmt = stmt.limit(payload.limit)
    return list(db.scalars(stmt).all())


def _assign_job_display_fields_from_ai_parse(row: ScrapedJob, parsed: dict[str, Any]) -> None:
    keywords_str = keywords_to_stored_string(parsed.get("keywords", []))
    row.displayed_description = (parsed.get("description") or "").strip() or None
    row.displayed_keywords = keywords_str or None


def _count_csv_keywords(value: str | None) -> int:
    if not value:
        return 0
    return len([part for part in value.split(",") if part.strip()])


@router.post("/jobs/{job_row_id}/ai-display", response_model=JobDisplayAIResponse)
def admin_job_generate_ai_display_fields(
    job_row_id: UUID,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> JobDisplayAIResponse:
    """Use local Ollama on ``job_description`` to fill ``displayed_description`` and ``displayed_keywords`` when extraction succeeds."""
    if not OLLAMA_MODEL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OLLAMA_MODEL is not configured.",
        )

    row = db.get(ScrapedJob, job_row_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    desc = (row.job_description or "").strip()
    if not desc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job has no description text to analyze.",
        )

    try:
        parsed = generate_display_fields_from_job_description(desc)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Model response could not be parsed: {exc}",
        ) from exc

    if not parsed["success"]:
        return JobDisplayAIResponse(
            success=False,
            description="",
            keywords=[],
            saved=False,
            job=None,
        )

    _assign_job_display_fields_from_ai_parse(row, parsed)
    print(
        "[job-ai-display] prepared "
        f"id={row.id} add_keywords_count={_count_csv_keywords(row.displayed_keywords)} "
        f"keywords={row.displayed_keywords or ''}",
        flush=True,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not save display fields: {exc}",
        ) from None
    db.refresh(row)

    return JobDisplayAIResponse(
        success=True,
        description=parsed["description"],
        keywords=parsed["keywords"],
        saved=True,
        job=ScrapedJobOut.model_validate(row),
    )


async def _run_job_display_ai_job(batch_job_id: str) -> None:
    job = _job_display_ai_jobs.get(batch_job_id)
    if job is None:
        return

    if not OLLAMA_MODEL:
        job.status = "failed"
        job.error = "OLLAMA_MODEL is not configured."
        job.completed_at = datetime.now(timezone.utc)
        return

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)

    payload = JobDisplayAIJobRequest(
        job_ids=list(job.job_ids),
        only_missing_display=job.only_missing_display,
        limit=job.limit,
    )
    db = SessionLocal()
    updated = 0
    skipped = 0
    failed = 0
    declined = 0
    try:
        rows = _rows_for_job_display_ai_job(db, payload)
        job.processed = len(rows)
        print(
            f"[job-ai-display] batch_start id={batch_job_id} total_rows={len(rows)}",
            flush=True,
        )
        for row in rows:
            text = (row.job_description or "").strip()
            if not text:
                print(f"[job-ai-display] skip id={row.id} reason=missing_job_description", flush=True)
                skipped += 1
                continue
            if job.only_missing_display and _has_any_job_display_field(row):
                print(f"[job-ai-display] skip id={row.id} reason=already_has_display_fields", flush=True)
                skipped += 1
                continue
            try:
                parsed = await asyncio.to_thread(generate_display_fields_from_job_description, text)
            except RuntimeError as exc:
                db.rollback()
                job.updated = updated
                job.skipped = skipped
                job.failed = failed
                job.declined = declined
                job.status = "failed"
                job.error = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                return
            except Exception:
                db.rollback()
                print(f"[job-ai-display] fail id={row.id} reason=ai_or_parse_error", flush=True)
                failed += 1
                continue
            if not parsed.get("success"):
                print(f"[job-ai-display] decline id={row.id} reason=model_success_false", flush=True)
                declined += 1
                continue
            try:
                _assign_job_display_fields_from_ai_parse(row, parsed)
                print(
                    "[job-ai-display] prepared "
                    f"id={row.id} add_keywords_count={_count_csv_keywords(row.displayed_keywords)} "
                    f"keywords={row.displayed_keywords or ''}",
                    flush=True,
                )
                db.commit()
                updated += 1
                print(f"[job-ai-display] updated id={row.id}", flush=True)
            except IntegrityError:
                db.rollback()
                print(f"[job-ai-display] fail id={row.id} reason=db_integrity_error", flush=True)
                failed += 1
        job.updated = updated
        job.skipped = skipped
        job.failed = failed
        job.declined = declined
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        print(
            "[job-ai-display] batch_summary "
            f"id={batch_job_id} processed={len(rows)} updated={updated} skipped={skipped} failed={failed} declined={declined}",
            flush=True,
        )
    except Exception as exc:
        db.rollback()
        job.status = "failed"
        job.error = str(exc)
        job.completed_at = datetime.now(timezone.utc)
    finally:
        db.close()


def _enqueue_job_display_ai_job(payload: JobDisplayAIJobRequest) -> JobDisplayAIJobQueued:
    batch_job_id = str(uuid4())
    _job_display_ai_jobs[batch_job_id] = JobDisplayAIJobStatus(
        job_id=batch_job_id,
        status="queued",
        only_missing_display=payload.only_missing_display,
        job_ids=list(payload.job_ids),
        limit=payload.limit,
        created_at=datetime.now(timezone.utc),
    )
    asyncio.create_task(_run_job_display_ai_job(batch_job_id))
    return JobDisplayAIJobQueued(job_id=batch_job_id, status="queued")


@router.post("/jobs/ai-display/jobs", response_model=JobDisplayAIJobQueued)
async def admin_enqueue_job_display_ai(
    payload: JobDisplayAIJobRequest,
    _: User = Depends(require_superadmin),
) -> JobDisplayAIJobQueued:
    """Background job: fill displayed fields from job_description."""
    return _enqueue_job_display_ai_job(payload)


@router.post("/public/jobs/ai-display/regenerate-all", response_model=JobDisplayAIJobQueued)
async def public_regenerate_all_jobs_ai_display() -> JobDisplayAIJobQueued:
    """Unauthenticated: enqueue AI keyword/description regeneration for all jobs."""
    payload = JobDisplayAIJobRequest(
        job_ids=[],
        only_missing_display=False,
        limit=None,
    )
    return _enqueue_job_display_ai_job(payload)


@router.get("/jobs/ai-display/jobs/{job_id}", response_model=JobDisplayAIJobStatus)
async def admin_get_job_display_ai_job(
    job_id: str,
    wait: bool = False,
    _: User = Depends(require_superadmin),
) -> JobDisplayAIJobStatus:
    job = _job_display_ai_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI display job not found")
    if not wait:
        return job
    deadline = time.monotonic() + _JOB_STATUS_WAIT_MAX_SEC
    while job.status not in ("completed", "failed"):
        if time.monotonic() >= deadline:
            return job
        await asyncio.sleep(_JOB_STATUS_WAIT_INTERVAL_SEC)
    return job


@router.get("/public/jobs/ai-display/jobs/{job_id}", response_model=JobDisplayAIJobStatus)
async def public_get_job_display_ai_job(
    job_id: str,
    wait: bool = False,
) -> JobDisplayAIJobStatus:
    """Unauthenticated: read status for a public job-display AI batch."""
    job = _job_display_ai_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI display job not found")
    if not wait:
        return job
    deadline = time.monotonic() + _JOB_STATUS_WAIT_MAX_SEC
    while job.status not in ("completed", "failed"):
        if time.monotonic() >= deadline:
            return job
        await asyncio.sleep(_JOB_STATUS_WAIT_INTERVAL_SEC)
    return job


@router.get("/jobs", response_model=list[ScrapedJobOut])
def admin_list_jobs(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> list[ScrapedJob]:
    stmt = (
        select(ScrapedJob)
        .options(selectinload(ScrapedJob.company))
        .order_by(ScrapedJob.scraped_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("/jobs", response_model=ScrapedJobOut, status_code=status.HTTP_201_CREATED)
def admin_create_job(
    payload: ScrapedJobCreate,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> ScrapedJob:
    if payload.company_id is not None:
        company = db.get(ScrapedCompany, payload.company_id)
        if company is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_id not found")

    external_job_id = payload.job_id or _generate_job_external_id()

    row = ScrapedJob(
        company_id=payload.company_id,
        job_id=external_job_id,
        job_title=payload.job_title,
        posted_date=payload.posted_date,
        job_description=payload.job_description,
        extra_details=payload.extra_details,
        linkedin_url=payload.job_url.strip(),
        keyword=payload.keyword,
        displayed_description=payload.displayed_description,
        displayed_keywords=payload.displayed_keywords,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job with this job_id or LinkedIn URL already exists",
        ) from None
    db.refresh(row)
    return row


@router.patch("/jobs/{job_row_id}", response_model=ScrapedJobOut)
def admin_update_job(
    job_row_id: UUID,
    payload: ScrapedJobUpdate,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> ScrapedJob:
    row = db.get(ScrapedJob, job_row_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if "company_id" in data:
        cid = data["company_id"]
        if cid is not None and db.get(ScrapedCompany, cid) is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_id not found")
        row.company_id = cid

    if "job_id" in data:
        jid = data["job_id"]
        if jid is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_id cannot be cleared")
        if db.scalar(
            select(ScrapedJob.id).where(ScrapedJob.job_id == jid, ScrapedJob.id != job_row_id).limit(1)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another job already uses this job_id.",
            )
        row.job_id = jid

    if "job_url" in data:
        url = (data["job_url"] or "").strip()
        if not url:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_url cannot be empty")
        if db.scalar(
            select(ScrapedJob.id).where(ScrapedJob.linkedin_url == url, ScrapedJob.id != job_row_id).limit(1)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another job already uses this LinkedIn URL.",
            )
        row.linkedin_url = url

    if "job_title" in data:
        row.job_title = data["job_title"]
    if "posted_date" in data:
        row.posted_date = data["posted_date"]
    if "job_description" in data:
        row.job_description = data["job_description"]
    if "extra_details" in data:
        row.extra_details = data["extra_details"]
    if "keyword" in data:
        row.keyword = data["keyword"]
    if "displayed_description" in data:
        row.displayed_description = data["displayed_description"]
    if "displayed_keywords" in data:
        row.displayed_keywords = data["displayed_keywords"]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job with this job_id or LinkedIn URL already exists",
        ) from None
    db.refresh(row)
    return row


@router.delete("/jobs/{job_row_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_job(
    job_row_id: UUID,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(ScrapedJob, job_row_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    db.delete(row)
    db.commit()


@router.get("/volunteering-events", response_model=list[VolunteeringEventOut])
def admin_list_volunteering_events(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> list[VolunteeringEvent]:
    stmt = select(VolunteeringEvent).order_by(VolunteeringEvent.scraped_at.desc())
    return list(db.scalars(stmt).all())


@router.patch("/volunteering-events/{event_id}", response_model=VolunteeringEventOut)
def admin_update_volunteering_event(
    event_id: UUID,
    payload: VolunteeringEventUpdate,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> VolunteeringEvent:
    row = db.get(VolunteeringEvent, event_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteering event not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    if "event_url" in data:
        url = data["event_url"]
        if url is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="event_url cannot be empty")
        if db.scalar(
            select(VolunteeringEvent.id).where(VolunteeringEvent.event_url == url, VolunteeringEvent.id != event_id).limit(1)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Another volunteering event already uses this URL.",
            )
        row.event_url = url
    if "title" in data:
        row.title = data["title"]
    if "subtitle" in data:
        row.subtitle = data["subtitle"]
    if "organizer" in data:
        row.organizer = data["organizer"]
    if "organizer_website" in data:
        row.organizer_website = data["organizer_website"]
    if "description" in data:
        row.description = data["description"]
    if "duration_dates" in data:
        row.duration_dates = data["duration_dates"]
    if "days" in data:
        row.days = data["days"]
    if "keywords" in data:
        row.keywords = data["keywords"]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Volunteering event URL already exists",
        ) from None
    db.refresh(row)
    return row


@router.post("/volunteering-events/{event_id}/ai-keyword", response_model=VolunteeringKeywordAIResponse)
def admin_generate_volunteering_event_ai_keyword(
    event_id: UUID,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> VolunteeringKeywordAIResponse:
    if not OLLAMA_MODEL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OLLAMA_MODEL is not configured.",
        )

    row = db.get(VolunteeringEvent, event_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteering event not found")

    event_text = "\n".join(
        [
            f"title: {(row.title or '').strip()}",
            f"subtitle: {(row.subtitle or '').strip()}",
            f"organizer: {(row.organizer or '').strip()}",
            f"description: {(row.description or '').strip()}",
            f"duration_dates: {(row.duration_dates or '').strip()}",
            f"days: {(row.days or '').strip()}",
        ]
    ).strip()
    if not event_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Volunteering event has no text to analyze.",
        )

    try:
        parsed = classify_volunteering_keyword(event_text)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Model response could not be parsed: {exc}",
        ) from exc

    if not parsed["success"]:
        return VolunteeringKeywordAIResponse(
            success=False,
            keyword="",
            saved=False,
            event=None,
        )

    row.keywords = parsed["keyword"] or None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not save event keyword: {exc}",
        ) from None
    db.refresh(row)
    return VolunteeringKeywordAIResponse(
        success=True,
        keyword=parsed["keyword"],
        saved=True,
        event=VolunteeringEventOut.model_validate(row),
    )


@router.delete("/volunteering-events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_volunteering_event(
    event_id: UUID,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(VolunteeringEvent, event_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Volunteering event not found")
    db.delete(row)
    db.commit()


@router.delete("/reset/skills")
def admin_reset_skills_data(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """
    Delete all saved user prerequisite selections (per skill).
    Does not delete profile interests.
    """
    deleted_prerequisites = db.execute(delete(ProfilePrerequisite)).rowcount or 0
    db.commit()
    return {
        "deleted_profile_prerequisites": int(deleted_prerequisites),
    }


@router.delete("/reset/roadmaps")
def admin_reset_saved_roadmaps(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """
    Delete all saved generated roadmaps and steps.
    """
    deleted_steps = db.execute(delete(UserRoadmapStep)).rowcount or 0
    deleted_roadmaps = db.execute(delete(UserRoadmap)).rowcount or 0
    db.commit()
    return {
        "deleted_roadmap_steps": int(deleted_steps),
        "deleted_roadmaps": int(deleted_roadmaps),
    }
