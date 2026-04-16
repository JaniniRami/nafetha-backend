"""
Job scraper for LinkedIn.

Extracts job posting information from LinkedIn job pages.
"""
import logging
import asyncio
from typing import Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from ..models.job import Job
from ..core.exceptions import ProfileNotFoundError
from ..callbacks import ProgressCallback, SilentCallback
from .base import BaseScraper

logger = logging.getLogger(__name__)


class JobScraper(BaseScraper):
    """
    Scraper for LinkedIn job postings.
    
    Example:
        async with BrowserManager() as browser:
            scraper = JobScraper(browser.page)
            job = await scraper.scrape("https://www.linkedin.com/jobs/view/123456/")
            print(job.to_json())
    """
    
    def __init__(self, page: Page, callback: Optional[ProgressCallback] = None):
        """
        Initialize job scraper.
        
        Args:
            page: Playwright page object
            callback: Optional progress callback
        """
        super().__init__(page, callback or SilentCallback())
    
    async def scrape(self, linkedin_url: str) -> Job:
        """
        Scrape a LinkedIn job posting.
        
        Args:
            linkedin_url: URL of the LinkedIn job posting
            
        Returns:
            Job object with scraped data
            
        Raises:
            ProfileNotFoundError: If job posting not found
        """
        logger.info(f"Starting job scraping: {linkedin_url}")
        await self.callback.on_start("Job", linkedin_url)
        
        # Navigate to job page
        await self.navigate_and_wait(linkedin_url)
        await self.callback.on_progress("Navigated to job page", 10)

        # Job pages are dynamic; give the page a moment and try to remove blockers.
        await self.wait_and_focus(1)
        await self.close_modals()

        # Ensure we actually landed on the job page before extracting content.
        try:
            await self.page.wait_for_url(lambda url: "/jobs/view/" in url, timeout=10_000)
        except Exception:
            # If we can't confirm, extraction fallbacks below will still try.
            pass
        
        # Check if page exists
        await self.check_rate_limit()
        
        # Extract job details
        job_title = await self._get_job_title()
        await self.callback.on_progress(f"Got job title: {job_title}", 20)
        
        company = await self._get_company()
        await self.callback.on_progress("Got company name", 30)
        
        location = await self._get_location()
        await self.callback.on_progress("Got location", 40)
        
        posted_date = await self._get_posted_date()
        await self.callback.on_progress("Got posted date", 50)
        
        applicant_count = await self._get_applicant_count()
        await self.callback.on_progress("Got applicant count", 60)
        
        job_description = await self._get_description()
        await self.callback.on_progress("Got job description", 80)
        
        company_url = await self._get_company_url()
        await self.callback.on_progress("Got company URL", 90)
        
        # Create job object
        job = Job(
            linkedin_url=linkedin_url,
            job_title=job_title,
            company=company,
            company_linkedin_url=company_url,
            location=location,
            posted_date=posted_date,
            applicant_count=applicant_count,
            job_description=job_description
        )
        
        await self.callback.on_progress("Scraping complete", 100)
        await self.callback.on_complete("Job", job)

        logger.info(
            "Successfully extracted job page data: title=%r (persisting to DB is done later by the scrape pipeline; "
            "check logs for [scrape:save])",
            job_title,
        )
        return job
    
    async def _get_job_title(self) -> Optional[str]:
        """Extract job title from the LinkedIn job detail page.

        The title lives in: div[data-display-contents="true"] > p
        (direct-child p only, to avoid deeply-nested non-title paragraphs).
        We iterate through all matching elements and return the first one
        that passes the plausibility checks.
        """

        # Phrases that are definitely NOT a job title.
        _EXCLUDE = {
            "notification", "people you can reach out", "promoted by",
            "responses managed", "on-site", "full-time", "part-time",
            "remote", "hybrid", "apply", "save", "·", "about the job",
        }

        def _normalize(text: str) -> str:
            return " ".join(text.split()).strip()

        def _is_plausible(text: str) -> bool:
            n = _normalize(text)
            if not n or len(n) < 3 or len(n) > 200:
                return False
            low = n.lower()
            for phrase in _EXCLUDE:
                if phrase in low:
                    return False
            return True

        # Ordered: most-specific first, broad fallbacks last.
        selectors = [
            # Observed LinkedIn layout: title is a direct-child <p> of a
            # div[data-display-contents="true"] that sits inside the job card.
            'div[data-display-contents="true"] > p',
            # Legacy / alternate layouts
            "h1[data-test-job-title]",
            "[data-test-job-title]",
            "h1",
            "h2",
        ]

        for _ in range(4):
            for selector in selectors:
                try:
                    base = self.page.locator(selector)
                    count = await base.count()
                    if count == 0:
                        continue

                    for i in range(min(count, 10)):
                        elem = base.nth(i)
                        try:
                            await elem.wait_for(state="visible", timeout=1500)
                        except PlaywrightTimeoutError:
                            continue

                        text = await elem.text_content(timeout=2000)
                        if text and _is_plausible(text):
                            return _normalize(text)
                except Exception:
                    continue

            await asyncio.sleep(1)

        return None
    
    async def _get_company(self) -> Optional[str]:
        """Extract company name from company link."""
        try:
            # Find company links that have text (not just images)
            company_links = await self.page.locator('a[href*="/company/"]').all()
            for link in company_links:
                text = await link.inner_text()
                text = text.strip()
                # Skip empty or very short text (likely image-only links)
                if text and len(text) > 1 and not text.startswith('logo'):
                    return text
        except:
            pass
        return None
    
    async def _get_company_url(self) -> Optional[str]:
        """Extract company LinkedIn URL."""
        try:
            company_link = self.page.locator('a[href*="/company/"]').first
            if await company_link.count() > 0:
                href = await company_link.get_attribute('href')
                if href:
                    if '?' in href:
                        href = href.split('?')[0]
                    if not href.startswith('http'):
                        href = f"https://www.linkedin.com{href}"
                    return href
        except:
            pass
        return None
    
    async def _get_location(self) -> Optional[str]:
        """Extract job location from job details panel."""
        try:
            job_panel = self.page.locator('h1').first.locator('xpath=ancestor::*[5]')
            if await job_panel.count() > 0:
                text_elements = await job_panel.locator('span, div').all()
                for elem in text_elements:
                    text = await elem.inner_text()
                    if text and (',' in text or 'Remote' in text or 'United States' in text):
                        text = text.strip()
                        if len(text) > 3 and len(text) < 100 and not text.startswith('$'):
                            return text
        except:
            pass
        return None
    
    async def _get_posted_date(self) -> Optional[str]:
        """Extract posted date from job details."""
        try:
            text_elements = await self.page.locator('span, div').all()
            for elem in text_elements:
                text = await elem.inner_text()
                if text and ('ago' in text.lower() or 'day' in text.lower() or 'week' in text.lower() or 'hour' in text.lower()):
                    text = text.strip()
                    if len(text) < 50:
                        return text
        except:
            pass
        return None
    
    async def _get_applicant_count(self) -> Optional[str]:
        """Extract applicant count from job details."""
        try:
            main_content = self.page.locator('main').first
            if await main_content.count() > 0:
                text_elements = await main_content.locator('span, div').all()
                for elem in text_elements:
                    text = await elem.inner_text()
                    text = text.strip()
                    if text and len(text) < 50:
                        text_lower = text.lower()
                        if 'applicant' in text_lower or 'people clicked' in text_lower or 'applied' in text_lower:
                            return text
        except:
            pass
        return None
    
    async def _get_description(self) -> Optional[str]:
        """Extract job description from the expandable-text-box or About the job section."""
        # Primary: stable data-testid used by LinkedIn's expandable description box.
        try:
            box = self.page.locator('[data-testid="expandable-text-box"]').first
            if await box.count() > 0:
                try:
                    await box.wait_for(state="visible", timeout=5000)
                except Exception:
                    pass
                text = await box.inner_text(timeout=5000)
                if text and text.strip():
                    return text.strip()
        except Exception:
            pass

        # Fallback 1: sibling content after the "About the job" h2.
        try:
            about_heading = self.page.locator('h2:has-text("About the job")').first
            if await about_heading.count() > 0:
                # Try the parent container of the heading and grab its full text.
                parent = about_heading.locator('xpath=ancestor::div[1]')
                if await parent.count() > 0:
                    text = await parent.inner_text(timeout=5000)
                    if text and text.strip():
                        return text.strip()
        except Exception:
            pass

        # Fallback 2: article element.
        try:
            article = self.page.locator('article').first
            if await article.count() > 0:
                text = await article.inner_text(timeout=5000)
                if text and text.strip():
                    return text.strip()
        except Exception:
            pass

        return None
