"""Import Tanqeeb job listings into ``ScrapedJob`` rows (same table as LinkedIn)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import ScrapedCompany, ScrapedJob

logger = logging.getLogger(__name__)

_TANQEEB_SCRAPER_FILE = (
    Path(__file__).resolve().parents[3] / "nafetha-scrapers" / "tanqeeb_scraper" / "scrape_job_urls.py"
)

# Minimum ``SequenceMatcher`` ratio to treat two company names as the same (e.g. "Zain" vs "Zain Company").
_FUZZY_COMPANY_RATIO = 0.74


def _load_tanqeeb_scraper_module() -> Any:
    if not _TANQEEB_SCRAPER_FILE.is_file():
        raise FileNotFoundError(str(_TANQEEB_SCRAPER_FILE))
    spec = importlib.util.spec_from_file_location("tanqeeb_scrape_job_urls", _TANQEEB_SCRAPER_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Tanqeeb scraper from {_TANQEEB_SCRAPER_FILE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _normalize_job_url(job_url: str) -> str:
    return job_url.split("?", 1)[0].split("#", 1)[0].strip()


def _tanqeeb_external_job_id(job_url: str) -> str | None:
    """Stable id for ``jobs.job_id`` (unique, max 64)."""
    match = re.search(r"/(\d+)\.html?(?:$|[?#])", job_url, flags=re.IGNORECASE)
    if not match:
        return None
    return f"tanqeeb-{match.group(1)}"


def _is_post_date_key(key: str) -> bool:
    normalized = key.strip().lower().replace(" ", "_")
    return normalized in ("post_date", "postdate") or key.strip().lower() == "post date"


def _split_posted_date_and_extra_details(job_details: object) -> tuple[str | None, str | None]:
    """
    ``Post date`` / ``post_date`` -> ``posted_date`` column.
    All other entries from ``job_details`` -> JSON string for ``extra_details``.
    """
    if not isinstance(job_details, dict):
        return None, None

    posted_date: str | None = None
    extra: dict[str, str] = {}

    for raw_key, raw_value in job_details.items():
        key = str(raw_key).strip()
        if not key:
            continue
        value = raw_value if isinstance(raw_value, str) else str(raw_value)
        value = value.strip()
        if _is_post_date_key(key):
            posted_date = value or None
            continue
        if value:
            extra[key] = value

    if not extra:
        return posted_date, None
    return posted_date, json.dumps(extra, ensure_ascii=False)


def _canonical_company_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _resolve_or_create_company_id(db, scraped_company_name: str | None) -> UUID | None:
    """
    Match ``ScrapedCompany.company_name`` (case-insensitive), then fuzzy similarity / substring;
    otherwise insert a minimal company row (name only).
    """
    if not scraped_company_name or not str(scraped_company_name).strip():
        return None

    scraped_clean = str(scraped_company_name).strip()[:512]
    target = _canonical_company_name(scraped_clean)

    companies = list(db.scalars(select(ScrapedCompany)).all())

    for company in companies:
        if _canonical_company_name(company.company_name) == target:
            return company.id

    best: ScrapedCompany | None = None
    best_score = 0.0
    for company in companies:
        candidate = _canonical_company_name(company.company_name)
        score = SequenceMatcher(None, candidate, target).ratio()
        if len(candidate) >= 3 and len(target) >= 3:
            if candidate in target or target in candidate:
                score = max(score, 0.93)
        if score > best_score:
            best_score = score
            best = company

    if best is not None and best_score >= _FUZZY_COMPANY_RATIO:
        return best.id

    new_row = ScrapedCompany(
        company_name=scraped_clean,
        linkedin_url=None,
    )
    db.add(new_row)
    try:
        db.commit()
        db.refresh(new_row)
        logger.info("[tanqeeb] created company id=%s name=%r", new_row.id, scraped_clean)
        return new_row.id
    except IntegrityError:
        db.rollback()
        for company in db.scalars(select(ScrapedCompany)).all():
            if _canonical_company_name(company.company_name) == target:
                return company.id
        logger.warning("[tanqeeb] could not create or resolve company name=%r", scraped_clean)
        return None


def _job_exists_by_source_url(db, job_url: str) -> bool:
    stmt = select(ScrapedJob.id).where(ScrapedJob.linkedin_url == job_url).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def _persist_tanqeeb_payload(db, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Map scraped dict to DB and commit one row.
    Returns a result dict compatible with ``ImportUrlResult``.
    """
    raw_url = str(payload.get("job_url") or "")
    job_url = _normalize_job_url(raw_url)
    if not job_url:
        return {
            "url": raw_url,
            "status": "error",
            "job_id": None,
            "job_title": None,
            "reason": "missing_job_url",
        }

    ext_id = _tanqeeb_external_job_id(job_url)
    if not ext_id:
        return {
            "url": raw_url,
            "status": "error",
            "job_id": None,
            "job_title": payload.get("title"),
            "reason": "could_not_resolve_tanqeeb_job_id",
        }

    if _job_exists_by_source_url(db, job_url):
        return {
            "url": raw_url,
            "status": "skipped",
            "job_id": ext_id,
            "job_title": payload.get("title"),
            "reason": "already_in_database",
        }

    title = payload.get("title")
    if isinstance(title, str):
        title = title.strip() or None
    else:
        title = None

    description = payload.get("description")
    if isinstance(description, str):
        description = description.strip() or None
    else:
        description = None

    posted_date, extra_details = _split_posted_date_and_extra_details(payload.get("job_details"))

    company_name = payload.get("company_name")
    if not isinstance(company_name, str):
        company_name = None
    company_id = _resolve_or_create_company_id(db, company_name)

    row = ScrapedJob(
        company_id=company_id,
        job_id=ext_id,
        job_title=title,
        posted_date=posted_date,
        job_description=description,
        extra_details=extra_details,
        linkedin_url=job_url,
        keyword="tanqeeb",
    )
    db.add(row)
    try:
        db.commit()
        return {
            "url": raw_url,
            "status": "saved",
            "job_id": ext_id,
            "job_title": title,
            "reason": None,
        }
    except IntegrityError as exc:
        db.rollback()
        logger.warning("[tanqeeb] integrity_error job_id=%s detail=%s", ext_id, exc)
        return {
            "url": raw_url,
            "status": "skipped",
            "job_id": ext_id,
            "job_title": title,
            "reason": f"integrity_error: {exc}",
        }


async def import_tanqeeb_search(
    *,
    search_url: str | None,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    """
    Run paginated Tanqeeb search scrape and persist each job immediately after each page fetch
    (each persist uses its own DB session inside the worker thread).
    """
    mod = _load_tanqeeb_scraper_module()
    url = search_url or mod.SEARCH_URL
    results: list[dict[str, Any]] = []
    saved_this_run = 0

    def on_job_scraped(payload: dict[str, object]) -> None:
        nonlocal saved_this_run
        if not isinstance(payload, dict):
            return
        db_inner = SessionLocal()
        try:
            result = _persist_tanqeeb_payload(db_inner, payload)
            results.append(result)
            if result.get("status") == "saved":
                saved_this_run += 1
                logger.info(
                    "[tanqeeb] saved job to database (count=%s): job_id=%s title=%r",
                    saved_this_run,
                    result.get("job_id"),
                    result.get("job_title") or "",
                )
        finally:
            db_inner.close()

    await asyncio.to_thread(
        lambda: mod.scrape_jobs(url, timeout_seconds, on_job_scraped=on_job_scraped),
    )

    return results


async def import_tanqeeb_urls(
    *,
    urls: list[str],
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    """Scrape explicit Tanqeeb job page URLs and persist."""
    mod = _load_tanqeeb_scraper_module()
    results: list[dict[str, Any]] = []
    db = SessionLocal()
    saved_this_run = 0
    try:
        for raw_url in urls:
            job_url = _normalize_job_url(raw_url)
            ext_id = _tanqeeb_external_job_id(job_url)

            if not ext_id:
                results.append(
                    {
                        "url": raw_url,
                        "status": "error",
                        "job_id": None,
                        "job_title": None,
                        "reason": "could_not_resolve_tanqeeb_job_id",
                    }
                )
                continue

            if _job_exists_by_source_url(db, job_url):
                results.append(
                    {
                        "url": raw_url,
                        "status": "skipped",
                        "job_id": ext_id,
                        "job_title": None,
                        "reason": "already_in_database",
                    }
                )
                continue

            html = await asyncio.to_thread(mod.fetch_html_with_retries, job_url, timeout_seconds)
            if not html:
                results.append(
                    {
                        "url": raw_url,
                        "status": "error",
                        "job_id": ext_id,
                        "job_title": None,
                        "reason": "fetch_failed",
                    }
                )
                continue

            payload = mod.extract_job_data(job_url, html)
            result = _persist_tanqeeb_payload(db, payload)
            results.append(result)
            if result.get("status") == "saved":
                saved_this_run += 1
                logger.info(
                    "[tanqeeb] saved job to database (count=%s): job_id=%s title=%r",
                    saved_this_run,
                    result.get("job_id"),
                    result.get("job_title") or "",
                )
    finally:
        db.close()

    return results
