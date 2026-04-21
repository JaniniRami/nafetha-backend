#!/usr/bin/env python3
"""Fetch Tanqeeb jobs and print structured job data."""

from __future__ import annotations

import argparse
import json
import random
import re
import ssl
import sys
import time
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SEARCH_URL = (
    "https://jordan.tanqeeb.com/jobs/search"
    "?keywords=intern&countries[]=24&page_no=1&dictionary=1&"
)
BASE_URL = "https://jordan.tanqeeb.com"
ABSOLUTE_MAX_PAGES = 100
MAX_FETCH_RETRIES = 3

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
]


class TanqeebJobUrlParser(HTMLParser):
    """Parse Tanqeeb search result page and collect job hrefs."""

    def __init__(self) -> None:
        super().__init__()
        self._inside_jobs_list = False
        self._jobs_list_depth = 0
        self.urls: List[str] = []
        self._seen = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)

        if tag == "div" and attrs_dict.get("id") == "jobs_list":
            self._inside_jobs_list = True
            self._jobs_list_depth = 1
            return

        if self._inside_jobs_list and tag == "div":
            self._jobs_list_depth += 1

        if not self._inside_jobs_list or tag != "a":
            return

        anchor_id = attrs_dict.get("id", "")
        data_id = attrs_dict.get("data-id", "")
        href = attrs_dict.get("href", "")

        # Stable signals from sample page:
        # - id starts with JOB-
        # - job anchors include data-id
        # - href points to /jobs-.../*.html
        if (
            anchor_id.startswith("JOB-")
            and data_id.isdigit()
            and href.startswith("/jobs-")
            and href.endswith(".html")
        ):
            full_url = urljoin(BASE_URL, href)
            if full_url not in self._seen:
                self._seen.add(full_url)
                self.urls.append(full_url)

    def handle_endtag(self, tag: str) -> None:
        if not self._inside_jobs_list or tag != "div":
            return

        self._jobs_list_depth -= 1
        if self._jobs_list_depth == 0:
            self._inside_jobs_list = False


def fetch_html(url: str, timeout_seconds: int) -> str:
    """Fetch HTML with SSL verification and browser-like headers."""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }

    # Small jitter helps avoid "robotic" timing when invoked repeatedly.
    time.sleep(random.uniform(0.4, 1.2))

    request = Request(url=url, headers=headers, method="GET")
    ssl_context = ssl.create_default_context()  # Cert validation is enabled.
    with urlopen(request, timeout=timeout_seconds, context=ssl_context) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_html_with_retries(url: str, timeout_seconds: int) -> str | None:
    """Fetch HTML with retries and return None on repeated failures."""
    for attempt in range(1, MAX_FETCH_RETRIES + 1):
        try:
            return fetch_html(url, timeout_seconds)
        except HTTPError as exc:
            if exc.code == 500:
                return None
        except (URLError, Exception):
            pass

        if attempt < MAX_FETCH_RETRIES:
            time.sleep(1.0 * attempt)

    return None


def extract_job_urls(html: str) -> List[str]:
    parser = TanqeebJobUrlParser()
    parser.feed(html)
    parser.close()
    return parser.urls


def _normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _strip_tags(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    return _normalize_ws(no_tags)


def extract_job_data(job_url: str, html: str) -> Dict[str, object]:
    """Extract title, variable job details, and job description."""
    title = ""

    og_title_match = re.search(
        r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if og_title_match:
        title = _normalize_ws(og_title_match.group(1))
        title = re.sub(r"\s*-\s*TanQeeb\.com\s*$", "", title, flags=re.IGNORECASE)

    if not title:
        heading_match = re.search(
            r'<h[1-6][^>]*class=["\'][^"\']*job-title-with-logo[^"\']*["\'][^>]*>(.*?)</h[1-6]>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if heading_match:
            title = _strip_tags(heading_match.group(1))

    if not title:
        title_tag_match = re.search(
            r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL
        )
        if title_tag_match:
            title = _strip_tags(title_tag_match.group(1))
            title = re.sub(r"\s*\|\s*TanQeeb Jobs\s*$", "", title, flags=re.IGNORECASE)

    company_name = ""
    company_match = re.search(
        (
            r'<(?:a|span)[^>]*class=["\'][^"\']*job-meta-company[^"\']*["\'][^>]*>'
            r"(.*?)</(?:a|span)>"
        ),
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if company_match:
        company_name = _strip_tags(company_match.group(1))

    details_matches = re.findall(
        (
            r'<span[^>]*class=["\'][^"\']*text-meta[^"\']*["\'][^>]*>(.*?)</span>\s*'
            r'<span[^>]*class=["\'][^"\']*text-dark[^"\']*["\'][^>]*>(.*?)</span>'
        ),
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    details: Dict[str, str] = {}
    today_label = f"{datetime.now().day} {datetime.now():%B %Y}"
    for raw_key, raw_value in details_matches:
        key = _strip_tags(raw_key).rstrip(":")
        value = _strip_tags(raw_value)
        if key.lower() == "post date" and value.lower() == "today":
            value = today_label
        if key and value:
            details[key] = value

    description_blocks = re.findall(
        r'<div[^>]*class=["\'][^"\']*text-html[^"\']*["\'][^>]*>(.*?)</div>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    descriptions = [_strip_tags(block) for block in description_blocks]
    descriptions = [text for text in descriptions if text]
    description = max(descriptions, key=len, default="")

    return {
        "job_url": job_url,
        "title": title,
        "company_name": company_name,
        "job_details": details,
        "description": description,
    }


def with_page_no(url: str, page_no: int) -> str:
    """Return URL with page_no updated while preserving existing params."""
    parts = urlsplit(url)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    filtered_pairs = [(key, value) for key, value in query_pairs if key != "page_no"]
    filtered_pairs.append(("page_no", str(page_no)))
    new_query = urlencode(filtered_pairs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def scrape_paginated_urls(base_url: str, timeout: int) -> List[str]:
    all_urls: List[str] = []
    seen = set()
    page_no = 1

    while page_no <= ABSOLUTE_MAX_PAGES:
        page_url = with_page_no(base_url, page_no)
        html = fetch_html_with_retries(page_url, timeout)
        if not html:
            break
        page_urls = extract_job_urls(html)

        # Stop as soon as a page has no jobs.
        if len(page_urls) == 0:
            break

        for page_job_url in page_urls:
            if page_job_url not in seen:
                seen.add(page_job_url)
                all_urls.append(page_job_url)

        page_no += 1

    return all_urls


def scrape_jobs(
    base_url: str,
    timeout: int,
    on_job_scraped: Optional[Callable[[Dict[str, object]], None]] = None,
) -> List[Dict[str, object]]:
    job_urls = scrape_paginated_urls(base_url, timeout)
    jobs: List[Dict[str, object]] = []
    for job_url in job_urls:
        job_html = fetch_html_with_retries(job_url, timeout)
        if not job_html:
            continue
        job_data = extract_job_data(job_url, job_html)
        jobs.append(job_data)
        if on_job_scraped is not None:
            on_job_scraped(job_data)
    return jobs


def main() -> int:
    arg_parser = argparse.ArgumentParser(
        description="Scrape Tanqeeb search pages and output job URLs."
    )
    arg_parser.add_argument(
        "--url",
        default=SEARCH_URL,
        help="Search URL to fetch (default: first-page intern query).",
    )
    arg_parser.add_argument(
        "--input-file",
        type=Path,
        help="Read search-list HTML from local file instead of requesting the URL.",
    )
    arg_parser.add_argument(
        "--job-input-file",
        type=Path,
        help="Read one local job page HTML file and print one structured job object.",
    )
    arg_parser.add_argument(
        "--job-url",
        default="local-file://job",
        help="Job URL value used with --job-input-file (set this to the Tanqeeb URL).",
    )
    arg_parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds (default: 20).",
    )
    args = arg_parser.parse_args()

    if args.job_input_file:
        html = args.job_input_file.read_text(encoding="utf-8")
        job = extract_job_data(args.job_url, html)
        print(json.dumps(job, ensure_ascii=False, indent=2))
        print("\nTotal jobs: 1", file=sys.stderr)
        return 0

    if args.input_file:
        html = args.input_file.read_text(encoding="utf-8")
        urls = extract_job_urls(html)
        jobs = [{"job_url": job_url} for job_url in urls]
    else:
        jobs = scrape_jobs(args.url, args.timeout)

    for job in jobs:
        print(json.dumps(job, ensure_ascii=False, indent=2))

    print(f"\nTotal jobs: {len(jobs)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
