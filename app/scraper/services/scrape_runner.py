"""Core scraping workflow executed by background jobs."""

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import re
import sys
from uuid import UUID

logger = logging.getLogger(__name__)

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

# Repo vendored package lives under nafetha-scrapers/linkedin_scraper/ (inner linkedin_scraper/ is the import root).
# Prepend so it wins over a global conda/pip ``linkedin_scraper`` that may differ or be a namespace stub.
_SCRAPER_FS_ROOT = Path(__file__).resolve().parents[3] / "nafetha-scrapers"
_LINKEDIN_DIST = _SCRAPER_FS_ROOT / "linkedin_scraper"
if _LINKEDIN_DIST.is_dir() and str(_LINKEDIN_DIST) not in sys.path:
    sys.path.insert(0, str(_LINKEDIN_DIST))

from linkedin_scraper import BrowserManager, CompanyScraper, JobScraper, JobSearchScraper  # noqa: E402
from linkedin_scraper.callbacks import ConsoleCallback, SilentCallback  # noqa: E402

from app.config import HEADLESS_MODE
from app.database import SessionLocal
from app.models import ScrapedCompany, ScrapedJob
from app.scraper.services.auth import ensure_authenticated_session


@dataclass
class ScrapeOutputs:
    jobs_saved: int
    companies_saved: int


def _extract_linkedin_job_id(linkedin_url: str | None) -> str | None:
    """
    Extract numeric job id from URLs like:
    https://www.linkedin.com/jobs/view/4376990611/
    """
    if not linkedin_url:
        return None
    match = re.search(r"/jobs/view/(\d+)/?", linkedin_url)
    return match.group(1) if match else None


def _normalize_linkedin_url(linkedin_url: str | None) -> str | None:
    if not linkedin_url:
        return None
    normalized = linkedin_url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return normalized or None


def _should_skip_job_for_region(
    *,
    location: str | None,
    title: str | None = None,
    company: str | None = None,
) -> bool:
    """
    Skip broad region postings (EMEA/MENA) even if location parser varies.
    """
    haystack = " | ".join([title or "", company or "", location or ""])
    return bool(re.search(r"\b(?:EMEA|MENA)\b", haystack, flags=re.IGNORECASE))


async def _page_indicates_emea_region(page, posted_date: str | None = None) -> bool:
    """
    Check only the job *header* area (title, company, location chips) for EMEA/MENA.
    Deliberately excludes the job description so postings that merely *mention*
    EMEA/MENA in their description body are not incorrectly filtered out.
    """
    try:
        main = page.locator("main").first
        if await main.count() == 0:
            return False
        full_text = await main.inner_text()
    except Exception:
        return False

    if not full_text:
        return False

    # Subtract the job description body so we only scan header metadata.
    description_text = ""
    for desc_selector in (
        '[data-testid="expandable-text-box"]',
        'article',
        '[class*="description"]',
    ):
        try:
            el = page.locator(desc_selector).first
            if await el.count() > 0:
                description_text = (await el.inner_text(timeout=3000)) or ""
                break
        except Exception:
            continue

    header_text = full_text
    if description_text:
        header_text = full_text.replace(description_text, "", 1)

    return bool(re.search(r"\b(?:EMEA|MENA)\b", header_text, flags=re.IGNORECASE))


def _job_exists(db, *, job_id: str | None, linkedin_url: str | None) -> bool:
    conditions = []
    if job_id:
        conditions.append(ScrapedJob.job_id == job_id)
    if linkedin_url:
        conditions.append(ScrapedJob.linkedin_url == linkedin_url)
    if not conditions:
        return False
    stmt = select(ScrapedJob.id).where(or_(*conditions)).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def _company_exists(db, *, company_name: str | None, linkedin_url: str | None) -> bool:
    conditions = []
    if company_name:
        conditions.append(ScrapedCompany.company_name == company_name)
    if linkedin_url:
        conditions.append(ScrapedCompany.linkedin_url == linkedin_url)
    if not conditions:
        return False
    stmt = select(ScrapedCompany.id).where(or_(*conditions)).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def _get_or_create_company(
    db,
    *,
    company_name: str | None,
    linkedin_url: str | None,
) -> ScrapedCompany | None:
    clean_name = (company_name or "").strip() or None
    clean_url = _normalize_linkedin_url(linkedin_url)
    if not clean_name or not clean_url:
        return None

    existing_stmt = (
        select(ScrapedCompany)
        .where(
            or_(
                ScrapedCompany.linkedin_url == clean_url,
                ScrapedCompany.company_name == clean_name,
            )
        )
        .limit(1)
    )
    existing = db.execute(existing_stmt).scalar_one_or_none()
    if existing:
        return existing

    company = ScrapedCompany(
        company_name=clean_name,
        linkedin_url=clean_url,
    )
    db.add(company)
    try:
        db.commit()
        db.refresh(company)
        return company
    except IntegrityError:
        db.rollback()
        return db.execute(existing_stmt).scalar_one_or_none()


def _update_company_details(
    db,
    *,
    company_name: str | None,
    linkedin_url: str | None,
    industry: str | None,
    company_size: str | None,
    website: str | None,
    phone: str | None,
    about_us: str | None,
) -> tuple[ScrapedCompany | None, bool]:
    clean_name = (company_name or "").strip() or None
    clean_url = _normalize_linkedin_url(linkedin_url)
    if not clean_name or not clean_url:
        return None, False

    stmt = (
        select(ScrapedCompany)
        .where(or_(ScrapedCompany.linkedin_url == clean_url, ScrapedCompany.company_name == clean_name))
        .limit(1)
    )
    company = db.execute(stmt).scalar_one_or_none()
    created = False
    if not company:
        company = ScrapedCompany(company_name=clean_name, linkedin_url=clean_url)
        db.add(company)
        created = True

    company.industry = industry
    company.company_size = company_size
    company.website = website
    company.phone = phone
    company.about_us = about_us

    try:
        db.commit()
        db.refresh(company)
        return company, created
    except IntegrityError:
        db.rollback()
        company = db.execute(stmt).scalar_one_or_none()
        return company, False


async def import_job_urls(
    *,
    urls: list[str],
    session_path: str,
    delay_seconds: float = 1.0,
    verbose: bool = True,
) -> list[dict]:
    """
    Scrape a provided list of LinkedIn job URLs and persist them directly.
    Returns a list of result dicts: {url, status, job_id, job_title, reason}.
    """
    from app.scraper.schemas import ImportUrlResult  # local import to avoid circular

    callback = ConsoleCallback(verbose=verbose) if verbose else SilentCallback()
    results: list[dict] = []
    db = SessionLocal()

    try:
        async with BrowserManager(headless=HEADLESS_MODE) as browser:
            await ensure_authenticated_session(browser, Path(session_path).resolve())
            job_scraper = JobScraper(browser.page, callback=callback)

            for raw_url in urls:
                url = _normalize_linkedin_url(raw_url) or raw_url
                job_id = _extract_linkedin_job_id(url)

                if _job_exists(db, job_id=job_id, linkedin_url=url):
                    logger.info("[import] skip url=%s reason=already_in_database", url)
                    results.append({"url": raw_url, "status": "skipped", "job_id": job_id, "job_title": None, "reason": "already_in_database"})
                    continue

                try:
                    job = await job_scraper.scrape(raw_url)
                except Exception as exc:
                    logger.warning("[import] error scraping url=%s error=%s", url, exc)
                    results.append({"url": raw_url, "status": "error", "job_id": None, "job_title": None, "reason": str(exc)})
                    continue

                linkedin_url = _normalize_linkedin_url(job.linkedin_url) or url
                job_id = _extract_linkedin_job_id(linkedin_url) or _extract_linkedin_job_id(url)

                if not job_id or not linkedin_url:
                    results.append({"url": raw_url, "status": "error", "job_id": None, "job_title": job.job_title, "reason": "could_not_resolve_job_id_or_url"})
                    continue

                if _job_exists(db, job_id=job_id, linkedin_url=linkedin_url):
                    results.append({"url": raw_url, "status": "skipped", "job_id": job_id, "job_title": job.job_title, "reason": "already_in_database"})
                    continue

                company = _get_or_create_company(db, company_name=job.company, linkedin_url=job.company_linkedin_url)
                company_id: UUID | None = None
                if company is not None:
                    if company.blacklisted:
                        logger.info("[import] skip url=%s reason=company_blacklisted company_id=%s", url, company.id)
                        results.append({"url": raw_url, "status": "skipped", "job_id": job_id, "job_title": job.job_title, "reason": "company_blacklisted"})
                        continue
                    company_id = company.id
                else:
                    logger.warning("[import] saving without company_id url=%s company=%r company_url=%r", url, job.company, job.company_linkedin_url)

                db.add(ScrapedJob(
                    company_id=company_id,
                    job_id=job_id,
                    job_title=job.job_title,
                    posted_date=job.posted_date,
                    job_description=job.job_description,
                    linkedin_url=linkedin_url,
                    keyword=None,
                ))
                try:
                    db.commit()
                    logger.info("[import] committed job_id=%s title=%r", job_id, job.job_title)
                    results.append({"url": raw_url, "status": "saved", "job_id": job_id, "job_title": job.job_title, "reason": None})
                except IntegrityError as exc:
                    db.rollback()
                    logger.warning("[import] integrity_error job_id=%s detail=%s", job_id, exc)
                    results.append({"url": raw_url, "status": "skipped", "job_id": job_id, "job_title": job.job_title, "reason": f"integrity_error: {exc}"})

                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
    finally:
        db.close()

    return results


async def run_scrape_job(
    *,
    keywords: list[str],
    locations: list[str],
    jobs_per_location: int | None,
    delay_seconds: float,
    session_path: str,
    output_dir: str,
    verbose: bool,
    progress_updater,
    is_cancel_requested,
) -> ScrapeOutputs:
    """
    Execute scraping workflow and keep progress synced through callbacks.
    """
    callback = ConsoleCallback(verbose=True) if verbose else SilentCallback()
    cleaned_keywords = [item.strip() for item in keywords if item and item.strip()]
    if not cleaned_keywords:
        cleaned_keywords = [""]
    # Empty locations list means "no location filter" — run once with None.
    effective_locations = locations if locations else [None]
    total_targets = len(effective_locations) * len(cleaned_keywords)

    await progress_updater(
        total_locations=total_targets,
        last_message="Starting browser session",
    )

    seen_job_ids: set[str] = set()
    seen_job_urls: set[str] = set()
    scraped_company_urls: set[str] = set()
    jobs_saved = 0
    companies_saved = 0
    db = SessionLocal()

    try:
        async with BrowserManager(headless=HEADLESS_MODE) as browser:
            await ensure_authenticated_session(browser, Path(session_path).resolve())

            search_scraper = JobSearchScraper(browser.page, callback=callback)
            job_scraper = JobScraper(browser.page, callback=callback)
            company_scraper = CompanyScraper(browser.page, callback=callback)

            target_index = 0
            for location in effective_locations:
                for keyword in cleaned_keywords:
                    target_index += 1
                    keyword_label = keyword or "(no keyword)"
                    if is_cancel_requested():
                        raise asyncio.CancelledError()

                    page_num = 0
                    total_jobs_this_location = 0
                    unlimited_jobs = jobs_per_location is None
                    await progress_updater(
                        current_location=location,
                        last_message=f"Searching jobs in {location} with keyword '{keyword_label}'",
                    )

                    while unlimited_jobs or total_jobs_this_location < jobs_per_location:
                        if is_cancel_requested():
                            raise asyncio.CancelledError()

                        start_offset = page_num * 25
                        remaining = None if unlimited_jobs else jobs_per_location - total_jobs_this_location
                        job_urls = await search_scraper.search(
                            keywords=keyword or None,
                            location=location,
                            limit=25 if unlimited_jobs else min(25, remaining),
                            start=start_offset,
                        )

                        await progress_updater(
                            pages_processed=1,
                            job_urls_found=len(job_urls),
                            last_message=f"Page {page_num + 1} processed in {location}",
                        )

                        if not job_urls:
                            break

                        page_company_urls: set[str] = set()

                        for job_url in job_urls:
                            if is_cancel_requested():
                                raise asyncio.CancelledError()

                            seed_url = _normalize_linkedin_url(job_url)
                            seed_job_id = _extract_linkedin_job_id(seed_url)
                            if seed_job_id and seed_job_id in seen_job_ids:
                                logger.info(
                                    "[scrape:save] skip seed_url=%s job_id=%s reason=already_seen_this_run",
                                    seed_url,
                                    seed_job_id,
                                )
                                continue
                            if seed_url and seed_url in seen_job_urls:
                                logger.info(
                                    "[scrape:save] skip seed_url=%s reason=url_already_seen_this_run",
                                    seed_url,
                                )
                                continue
                            if _job_exists(db, job_id=seed_job_id, linkedin_url=seed_url):
                                logger.info(
                                    "[scrape:save] skip seed_url=%s job_id=%s reason=already_in_database",
                                    seed_url,
                                    seed_job_id,
                                )
                                continue

                            job = await job_scraper.scrape(job_url)
                            if _should_skip_job_for_region(
                                location=job.location,
                                title=job.job_title,
                                company=job.company,
                            ):
                                logger.info(
                                    "[scrape:save] skip after_scrape job_id=%s url=%s reason=emea_mena_filter "
                                    "(title=%r company=%r location=%r)",
                                    seed_job_id,
                                    seed_url,
                                    job.job_title,
                                    job.company,
                                    job.location,
                                )
                                continue
                            if await _page_indicates_emea_region(browser.page, posted_date=job.posted_date):
                                logger.info(
                                    "[scrape:save] skip after_scrape job_id=%s url=%s reason=page_contains_emea_mena",
                                    seed_job_id,
                                    seed_url,
                                )
                                continue
                            linkedin_url = _normalize_linkedin_url(job.linkedin_url) or seed_url
                            job_id = _extract_linkedin_job_id(linkedin_url) or seed_job_id
                            company = _get_or_create_company(
                                db,
                                company_name=job.company,
                                linkedin_url=job.company_linkedin_url,
                            )

                            if not job_id or not linkedin_url:
                                logger.info(
                                    "[scrape:save] skip after_scrape seed_url=%s resolved_job_id=%r resolved_url=%r "
                                    "reason=missing_job_id_or_url",
                                    seed_url,
                                    job_id,
                                    linkedin_url,
                                )
                                continue

                            company_id: UUID | None = None
                            if company is not None:
                                if company.blacklisted:
                                    logger.info(
                                        "[scrape:save] skip job_id=%s url=%s company_id=%s reason=company_blacklisted",
                                        job_id,
                                        linkedin_url,
                                        company.id,
                                    )
                                    continue
                                company_id = company.id
                            else:
                                # Company row requires name + URL; LinkedIn often omits company URL in DOM.
                                # Still persist the job so listings are not silently dropped.
                                logger.warning(
                                    "[scrape:save] saving job without company_id job_id=%s url=%s "
                                    "company_name=%r company_linkedin_url=%r (backfill company later or fix scraper)",
                                    job_id,
                                    linkedin_url,
                                    job.company,
                                    job.company_linkedin_url,
                                )

                            if job_id in seen_job_ids or linkedin_url in seen_job_urls:
                                logger.info(
                                    "[scrape:save] skip job_id=%s url=%s reason=duplicate_after_scrape_this_run",
                                    job_id,
                                    linkedin_url,
                                )
                                continue
                            if _job_exists(db, job_id=job_id, linkedin_url=linkedin_url):
                                logger.info(
                                    "[scrape:save] skip job_id=%s url=%s reason=already_in_database_after_scrape",
                                    job_id,
                                    linkedin_url,
                                )
                                continue

                            db.add(
                                ScrapedJob(
                                    company_id=company_id,
                                    job_id=job_id,
                                    job_title=job.job_title,
                                    posted_date=job.posted_date,
                                    job_description=job.job_description,
                                    linkedin_url=linkedin_url,
                                    keyword=keyword or None,
                                )
                            )
                            try:
                                db.commit()
                            except IntegrityError as exc:
                                db.rollback()
                                logger.warning(
                                    "[scrape:save] skip job_id=%s url=%s reason=commit_integrity_error detail=%s",
                                    job_id,
                                    linkedin_url,
                                    exc,
                                )
                                continue

                            seen_job_ids.add(job_id)
                            seen_job_urls.add(linkedin_url)
                            jobs_saved += 1
                            logger.info(
                                "[scrape:save] committed job_id=%s linkedin_url=%s company_id=%s title=%r",
                                job_id,
                                linkedin_url,
                                company.id,
                                (job.job_title or "")[:80],
                            )
                            await progress_updater(
                                jobs_scraped=1,
                                last_message=f"Saved job {jobs_saved} (id={job_id})",
                            )

                            normalized_company_url = _normalize_linkedin_url(job.company_linkedin_url)
                            if normalized_company_url and normalized_company_url not in scraped_company_urls:
                                page_company_urls.add(normalized_company_url)

                            if delay_seconds > 0:
                                await asyncio.sleep(delay_seconds)

                        if page_company_urls:
                            await progress_updater(
                                companies_discovered=len(page_company_urls),
                                last_message=f"Scraping {len(page_company_urls)} companies from {location}",
                            )
                            for company_url in sorted(page_company_urls):
                                if is_cancel_requested():
                                    raise asyncio.CancelledError()

                                normalized_company_url = _normalize_linkedin_url(company_url) or company_url
                                if normalized_company_url in scraped_company_urls:
                                    continue

                                existing_company = db.execute(
                                    select(ScrapedCompany)
                                    .where(ScrapedCompany.linkedin_url == normalized_company_url)
                                    .limit(1)
                                ).scalar_one_or_none()
                                if existing_company and existing_company.blacklisted:
                                    scraped_company_urls.add(normalized_company_url)
                                    continue

                                company = await company_scraper.scrape(normalized_company_url)
                                scraped_company_urls.add(normalized_company_url)
                                existed_before = _company_exists(
                                    db,
                                    company_name=company.name,
                                    linkedin_url=company.linkedin_url,
                                )
                                _, created = _update_company_details(
                                    db,
                                    company_name=company.name,
                                    linkedin_url=company.linkedin_url,
                                    industry=company.industry,
                                    company_size=company.company_size,
                                    website=company.website,
                                    phone=company.phone,
                                    about_us=company.about_us,
                                )
                                if created or not existed_before:
                                    companies_saved += 1
                                await progress_updater(
                                    companies_scraped=1,
                                    last_message=f"Scraped company {len(scraped_company_urls)}",
                                )
                                if delay_seconds > 0:
                                    await asyncio.sleep(delay_seconds)

                        total_jobs_this_location += len(job_urls)
                        page_num += 1
                        if len(job_urls) < 25:
                            break

                        await asyncio.sleep(10)

                    await progress_updater(
                        locations_completed=1,
                        last_message=f"Completed target {target_index}/{total_targets}: {location} + '{keyword_label}'",
                    )
    finally:
        db.close()

    await progress_updater(last_message="Completed")
    return ScrapeOutputs(
        jobs_saved=jobs_saved,
        companies_saved=companies_saved,
    )
