import argparse
import asyncio
import os
from collections import defaultdict
from typing import Dict, List, Optional, Set

from dotenv import load_dotenv  # type: ignore
from openpyxl import Workbook  # type: ignore

from linkedin_scraper import (
    BrowserManager,
    CompanyScraper,
    JobScraper,
    JobSearchScraper,
    login_with_credentials,
    wait_for_manual_login,
)  # type: ignore
from linkedin_scraper.callbacks import ConsoleCallback  # type: ignore
from linkedin_scraper.core.exceptions import AuthenticationError, RateLimitError  # type: ignore


def _as_joined(items: Set[str]) -> str:
    return "; ".join(sorted({i for i in items if i}))


def export_companies_to_excel(
    companies: List[dict],
    output_path: str,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "companies"

    headers = [
        "company_name",
        "linkedin_url",
        "industry",
        "company_size",
        "headquarters",
        "founded",
        "specialties",
        "website",
        "phone",
        "about_us",
        "locations_found",
    ]
    ws.append(headers)

    for row in companies:
        ws.append(
            [
                row.get("name"),
                row.get("linkedin_url"),
                row.get("industry"),
                row.get("company_size"),
                row.get("headquarters"),
                row.get("founded"),
                row.get("specialties"),
                row.get("website"),
                row.get("phone"),
                row.get("about_us"),
                row.get("locations_found"),
            ]
        )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    wb.save(output_path)


async def ensure_session(
    browser: BrowserManager,
    session_path: str,
    login_mode: str,
) -> None:
    if os.path.exists(session_path):
        await browser.load_session(session_path)
        return

    # No saved session: create one (manual by default).
    if login_mode == "credentials":
        load_dotenv()
        await login_with_credentials(
            browser.page,
            email=os.getenv("LINKEDIN_EMAIL"),
            password=os.getenv("LINKEDIN_PASSWORD"),
            warm_up=True,
        )
    else:
        await browser.page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await wait_for_manual_login(browser.page, timeout=300_000)

    await browser.save_session(session_path)


async def scrape_companies_from_locations(
    *,
    keywords: str,
    locations: List[str],
    jobs_per_location: int,
    delay_s: float,
    session_path: str,
    output_path: str,
    login_mode: str,
    verbose: bool,
) -> None:
    callback = ConsoleCallback(verbose=verbose)

    company_sources: Dict[str, Set[str]] = defaultdict(set)
    company_urls: Set[str] = set()
    companies_out: List[dict] = []

    async with BrowserManager() as browser:
        await ensure_session(browser, session_path=session_path, login_mode=login_mode)

        # 1) Find job URLs in the target locations.
        search_scraper = JobSearchScraper(browser.page, callback=callback)
        job_scraper = JobScraper(browser.page, callback=callback)

        for loc in locations:
            print(f"\n🔍 Searching jobs in: {loc}")
            job_urls = await search_scraper.search(
                keywords=keywords,
                location=loc,
                limit=jobs_per_location,
            )
            print(f"Found {len(job_urls)} job urls in {loc}")

            for i, job_url in enumerate(job_urls, start=1):
                print(f"  [{i}/{len(job_urls)}] Scraping job: {job_url}")
                job = await job_scraper.scrape(job_url)

                if job.company_linkedin_url:
                    company_urls.add(job.company_linkedin_url)
                    company_sources[job.company_linkedin_url].add(loc)

                if delay_s > 0:
                    await asyncio.sleep(delay_s)

        # 2) Scrape unique company pages.
        company_scraper = CompanyScraper(browser.page, callback=callback)

        company_urls_ordered = sorted(company_urls)
        print(f"\n🏢 Unique companies to scrape: {len(company_urls_ordered)}")

        for i, company_url in enumerate(company_urls_ordered, start=1):
            print(f"  [{i}/{len(company_urls_ordered)}] Scraping company: {company_url}")
            company = await company_scraper.scrape(company_url)

            companies_out.append(
                {
                    "linkedin_url": company.linkedin_url,
                    "name": company.name,
                    "industry": company.industry,
                    "company_size": company.company_size,
                    "headquarters": company.headquarters,
                    "founded": company.founded,
                    "specialties": company.specialties,
                    "website": company.website,
                    "phone": company.phone,
                    "about_us": company.about_us,
                    "locations_found": _as_joined(company_sources.get(company.linkedin_url, set())),
                }
            )

            if delay_s > 0:
                await asyncio.sleep(delay_s)

        export_companies_to_excel(companies_out, output_path=output_path)
        print(f"\n✅ Saved {len(companies_out)} companies to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape LinkedIn companies in Jordan using job search seeds.")
    parser.add_argument("--keywords", default="software engineer", help="Job keywords to find companies via job postings.")
    parser.add_argument(
        "--locations",
        nargs="*",
        default=["Amman, Jordan", "Irbid, Jordan"],
        help="Job locations to search for (seeds for company scraping).",
    )
    parser.add_argument("--jobs-per-location", type=int, default=25, help="How many job URLs to scrape per location.")
    parser.add_argument("--delay-s", type=float, default=2.0, help="Delay between requests to reduce rate-limiting.")
    parser.add_argument("--session", default="session.json", help="Path to saved LinkedIn browser session.")
    parser.add_argument("--output", default="companies.xlsx", help="Output .xlsx file path.")
    parser.add_argument(
        "--login-mode",
        choices=["manual", "credentials"],
        default="manual",
        help="How to create a session if session file doesn't exist.",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose per-scraper progress logging.")
    args = parser.parse_args()

    try:
        asyncio.run(
            scrape_companies_from_locations(
                keywords=args.keywords,
                locations=args.locations,
                jobs_per_location=args.jobs_per_location,
                delay_s=args.delay_s,
                session_path=args.session,
                output_path=args.output,
                login_mode=args.login_mode,
                verbose=args.verbose,
            )
        )
    except AuthenticationError as e:
        print(f"\n❌ Authentication error: {e}")
        raise SystemExit(1)
    except RateLimitError as e:
        print(f"\n❌ Rate limited: {e}. Suggested wait: {getattr(e, 'suggested_wait_time', 'unknown')}s")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
