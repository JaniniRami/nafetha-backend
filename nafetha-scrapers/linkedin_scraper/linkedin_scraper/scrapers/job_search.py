"""
Job search scraper for LinkedIn.

Searches for jobs on LinkedIn and extracts job URLs, paginating through
multiple pages until the requested limit is reached.
"""
import asyncio
import logging
from typing import Optional, List, Set
from urllib.parse import urlencode
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from ..callbacks import ProgressCallback, SilentCallback
from .base import BaseScraper

logger = logging.getLogger(__name__)

# LinkedIn shows 25 jobs per page.
_JOBS_PER_PAGE = 25


class JobSearchScraper(BaseScraper):
    """
    Scraper for LinkedIn job search results.

    Automatically paginates through multiple result pages until `limit` is reached.

    Example:
        async with BrowserManager() as browser:
            scraper = JobSearchScraper(browser.page)
            job_urls = await scraper.search(
                keywords="software engineer",
                location="Amman, Jordan",
                limit=200
            )
    """

    def __init__(self, page: Page, callback: Optional[ProgressCallback] = None):
        super().__init__(page, callback or SilentCallback())

    async def search(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        limit: int = 25,
        start: int = 0,
    ) -> List[str]:
        """
        Search for jobs on a single LinkedIn results page.

        Args:
            keywords: Job search keywords
            location: Job location string (e.g. "Amman, Jordan")
            limit: Maximum number of job URLs to return from this page
            start: Pagination offset (0 = page 1, 25 = page 2, 50 = page 3, …)

        Returns:
            List of unique job posting URLs found on this page
        """
        logger.info(
            f"Job search page start={start}: keywords='{keywords}', location='{location}'"
        )

        page_url = self._build_search_url(keywords, location, start=start)
        await self.callback.on_start("JobSearch", page_url)
        await self.navigate_and_wait(page_url)
        await self.callback.on_progress("Navigated to search results", 20)
        await asyncio.sleep(2)  # rate-limit guard between page requests

        try:
            await self.page.wait_for_selector('a[href*="/jobs/view/"]', timeout=10000)
        except PlaywrightTimeoutError:
            logger.info("No job listings found on this page.")
            await self.callback.on_progress("No jobs found", 100)
            await self.callback.on_complete("JobSearch", [])
            return []

        await self.wait_and_focus(1)

        # Wait for all occluded <li data-occludable-job-id> items to appear in
        # the DOM. LinkedIn renders them progressively; we poll until the count
        # stabilises (stops growing) or we hit a timeout.
        await self._wait_for_full_job_list()
        await self.callback.on_progress("Loaded job listings", 60)

        seen: Set[str] = set()
        job_urls = await self._extract_job_urls(limit, seen)

        await self.callback.on_progress(f"Found {len(job_urls)} job URLs on this page", 100)
        await self.callback.on_complete("JobSearch", job_urls)
        logger.info(f"Page (start={start}): found {len(job_urls)} jobs")
        return job_urls

    def _build_search_url(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        start: int = 0,
    ) -> str:
        """Build LinkedIn job search URL with pagination offset."""
        base_url = "https://www.linkedin.com/jobs/search/"
        params: dict = {"f_E": "1"}
        if keywords:
            params["keywords"] = keywords
        if location:
            params["location"] = location
        if start:
            params["start"] = start
        return f"{base_url}?{urlencode(params)}"

    async def _wait_for_full_job_list(
        self,
        target: int = 25,
        polls: int = 10,
        interval: float = 1.0,
    ) -> None:
        """
        Poll until `li[data-occludable-job-id]` count reaches `target` or
        stops growing, so we don't extract before the page is fully loaded.
        """
        prev_count = 0
        for _ in range(polls):
            count = await self.page.locator("li[data-occludable-job-id]").count()
            logger.debug(f"Job list size: {count}")
            if count >= target:
                break
            if count == prev_count and count > 0:
                # Count has stabilised — no more items are coming.
                break
            prev_count = count
            await asyncio.sleep(interval)

    async def _extract_job_urls(
        self, limit: int, seen_urls: Set[str]
    ) -> List[str]:
        """
        Extract job URLs from the current page.

        LinkedIn uses occlusion: only the ~7 visible job cards are fully
        rendered with <a href> links. The rest are empty <li> placeholders
        that still carry `data-occludable-job-id`. We read that attribute
        directly so we always get all 25 IDs regardless of scroll position.
        """
        job_urls: List[str] = []
        try:
            # Primary: read job IDs from the stable data attribute on every <li>.
            items = await self.page.locator("li[data-occludable-job-id]").all()
            for item in items:
                if len(job_urls) >= limit:
                    break
                try:
                    job_id = await item.get_attribute("data-occludable-job-id")
                    if job_id:
                        url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                        if url not in seen_urls:
                            job_urls.append(url)
                            seen_urls.add(url)
                except Exception as e:
                    logger.debug(f"Error reading data-occludable-job-id: {e}")
                    continue

            # Fallback: if the attribute approach found nothing, try rendered links.
            if not job_urls:
                job_links = await self.page.locator('a[href*="/jobs/view/"]').all()
                for link in job_links:
                    if len(job_urls) >= limit:
                        break
                    try:
                        href = await link.get_attribute('href')
                        if href and '/jobs/view/' in href:
                            clean_url = href.split('?')[0] if '?' in href else href
                            if not clean_url.startswith('http'):
                                clean_url = f"https://www.linkedin.com{clean_url}"
                            if clean_url not in seen_urls:
                                job_urls.append(clean_url)
                                seen_urls.add(clean_url)
                    except Exception as e:
                        logger.debug(f"Error extracting job URL from link: {e}")
                        continue

        except Exception as e:
            logger.warning(f"Error extracting job URLs: {e}")
        return job_urls
