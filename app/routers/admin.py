"""Superadmin JSON API for managing scraped companies and jobs."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import HEADLESS_MODE
from app.database import get_db
from app.database import SessionLocal
from app.deps import require_superadmin
from app.models import ScrapedCompany, ScrapedJob, User
from app.scraper.config import DEFAULT_SESSION_PATH
from app.scraper.services.auth import BrowserManager, ensure_authenticated_session
from app.schemas import (
    CompanyAboutBackfillRequest,
    CompanyAboutBackfillResponse,
    CompanyAboutBackfillJobQueued,
    CompanyAboutBackfillJobStatus,
    CompanyAboutBackfillRowResult,
    ScrapedCompanyCreate,
    ScrapedCompanyOut,
    ScrapedCompanyUpdate,
    ScrapedJobCreate,
    ScrapedJobOut,
    ScrapedJobUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_about_backfill_jobs: dict[str, CompanyAboutBackfillJobStatus] = {}


def _is_linkedin_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        host = (urlparse(value).hostname or "").lower()
    except Exception:
        return False
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def _normalize_text(text: str, *, max_chars: int = 2000) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    return compact[:max_chars]


async def _fetch_with_browser(url: str, *, require_linkedin_auth: bool) -> tuple[str | None, str | None]:
    try:
        async with BrowserManager(headless=HEADLESS_MODE) as browser:
            if require_linkedin_auth:
                await ensure_authenticated_session(browser, Path(DEFAULT_SESSION_PATH).resolve())
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
    except Exception as exc:
        return None, f"browser_fetch_failed:{exc}"

    text = _normalize_text(str(page_text or ""))
    if not text:
        return None, "empty_content_after_cleanup"
    return text, None


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
    if payload.company_ids:
        stmt = stmt.where(ScrapedCompany.id.in_(payload.company_ids))
    elif payload.only_missing:
        stmt = stmt.where(
            or_(
                ScrapedCompany.about_us.is_(None),
                func.length(func.trim(ScrapedCompany.about_us)) == 0,
            )
        )
    if not payload.company_ids and payload.limit is not None:
        stmt = stmt.limit(payload.limit)
    return stmt


async def _run_company_about_backfill(
    db: Session,
    payload: CompanyAboutBackfillRequest,
) -> CompanyAboutBackfillResponse:
    stmt = _build_company_backfill_query(payload)
    rows = list(db.scalars(stmt).all())
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
            text, err = await _fetch_with_browser(
                linkedin_url,
                require_linkedin_auth=_is_linkedin_url(linkedin_url),
            )
            if text:
                source_url = linkedin_url
            elif err:
                errors.append(f"linkedin_url:{err}")

        if text is None and website_url:
            text, err = await _fetch_with_browser(
                website_url,
                require_linkedin_auth=_is_linkedin_url(website_url),
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


@router.get("/companies/backfill-about/jobs/{job_id}", response_model=CompanyAboutBackfillJobStatus)
def admin_get_company_about_backfill_job(
    job_id: str,
    _: User = Depends(require_superadmin),
) -> CompanyAboutBackfillJobStatus:
    job = _about_backfill_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backfill job not found")
    return job


@router.get("/jobs", response_model=list[ScrapedJobOut])
def admin_list_jobs(
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
) -> list[ScrapedJob]:
    stmt = select(ScrapedJob).order_by(ScrapedJob.scraped_at.desc())
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
        company_linkedin_url=payload.company_linkedin_url,
        posted_date=payload.posted_date,
        job_description=payload.job_description,
        linkedin_url=payload.linkedin_url.strip(),
        seed_location=payload.seed_location,
        keyword=payload.keyword,
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

    if "linkedin_url" in data:
        url = (data["linkedin_url"] or "").strip()
        if not url:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="linkedin_url cannot be empty")
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
    if "company_linkedin_url" in data:
        row.company_linkedin_url = data["company_linkedin_url"]
    if "posted_date" in data:
        row.posted_date = data["posted_date"]
    if "job_description" in data:
        row.job_description = data["job_description"]
    if "seed_location" in data:
        row.seed_location = data["seed_location"]
    if "keyword" in data:
        row.keyword = data["keyword"]

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
