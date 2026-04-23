import argparse
import html
import random
import re
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

import requests


BASE_URL = "https://www.nahno.org"
VOLUNTEER_URL = f"{BASE_URL}/volunteer/"
LOAD_MORE_URL = f"{BASE_URL}/includes/datahandler.php"

EVENT_URL_RE = re.compile(r'href="(https://www\.nahno\.org/project_volunteer/[^"#?]+)"')
SHOW_MORE_DATE_RE = re.compile(r'<div id="([^"]+)" class="button-small show-more_vip"')
HIDDEN_INPUT_RE = re.compile(r'<input[^>]+id="([^"]+)"[^>]+value="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
]


@dataclass
class PagingState:
    last_id: str
    last_date: str
    current_page: str
    explore_filter: str
    explore_cat: str
    hide_campaign: str


@dataclass
class EventDetails:
    url: str
    title: str
    subtitle: str
    organizer: str
    organizer_website: str
    description: str
    duration_dates: str
    days: str
    keywords: str


def build_headers() -> Dict[str, str]:
    ua = random.choice(USER_AGENTS)
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(["ar-JO,ar;q=0.9,en-US;q=0.8,en;q=0.7", "ar,en;q=0.8"]),
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }


def sleep_with_jitter(base_delay: float) -> None:
    time.sleep(max(0.0, base_delay + random.uniform(0.4, 1.6)))


def extract_event_urls(html: str) -> List[str]:
    urls: List[str] = []
    seen: Set[str] = set()
    for url in EVENT_URL_RE.findall(html):
        if url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def clean_text(value: str) -> str:
    stripped_tags = TAG_RE.sub(" ", value)
    unescaped = html.unescape(stripped_tags)
    normalized = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", unescaped)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def first_group(pattern: str, html_body: str) -> str:
    match = re.search(pattern, html_body, flags=re.S)
    if not match:
        return ""
    return clean_text(match.group(1))


def extract_schedule_fields(html_body: str) -> tuple[str, str]:
    schedule_block_match = re.search(
        r'<div class="project-ngo-name" style="width:100%;margin-right:\s*0px;">(.*?)</div>\s*</div>\s*</div>',
        html_body,
        flags=re.S,
    )
    if not schedule_block_match:
        return "", ""

    schedule_block = schedule_block_match.group(1)
    duration_dates = ""
    days = ""

    row_matches = re.finditer(
        r"<div>\s*<span[^>]*>.*?</span>(.*?)</div>",
        schedule_block,
        flags=re.S,
    )
    for row in row_matches:
        row_html = row.group(1)
        orange_parts = [
            clean_text(part)
            for part in re.findall(r'<span class="orange">\s*([^<]+)\s*</span>', row_html, flags=re.S)
            if clean_text(part)
        ]
        if not orange_parts:
            continue

        if not duration_dates:
            duration_dates = f"{orange_parts[0]} -> {orange_parts[1]}" if len(orange_parts) >= 2 else orange_parts[0]
            continue

        if not days:
            days = "، ".join(orange_parts)
            break

    return duration_dates, days


def fetch_event_details(session: requests.Session, event_url: str, delay_seconds: float) -> EventDetails:
    # Rotate user-agent/header profile per event page request.
    session.headers.update(build_headers())
    session.headers.update({"Referer": VOLUNTEER_URL})
    sleep_with_jitter(delay_seconds)

    response = session.get(event_url, timeout=30)
    response.raise_for_status()
    html_body = response.text

    title = first_group(
        r'<div class="project-name name-container">.*?<div class="middle-vertical-align">(.*?)</div>',
        html_body,
    )
    subtitle = first_group(
        r'<div class="project-subcategory">.*?<div class="middle-vertical-align">(.*?)</div>',
        html_body,
    )
    organizer = first_group(
        r'<div class="project-ngo-name">.*?<a [^>]*>\s*(?:<b>)?(.*?)(?:</b>)?\s*</a>',
        html_body,
    )
    organizer_website = first_group(
        r'<div class="orange-link">\s*<a href="([^"]+)"',
        html_body,
    )
    description = first_group(
        r'<div class="project-desc">.*?<p[^>]*>(.*?)</p>',
        html_body,
    )

    duration_dates, days = extract_schedule_fields(html_body)

    return EventDetails(
        url=event_url,
        title=title,
        subtitle=subtitle,
        organizer=organizer,
        organizer_website=organizer_website,
        description=description,
        duration_dates=duration_dates,
        days=days,
        keywords="",
    )


def parse_hidden_inputs(html: str) -> Dict[str, str]:
    return {input_id: value for input_id, value in HIDDEN_INPUT_RE.findall(html)}


def parse_paging_state(html: str) -> Optional[PagingState]:
    hidden = parse_hidden_inputs(html)
    date_match = SHOW_MORE_DATE_RE.search(html)
    if not date_match:
        return None

    last_id = hidden.get("show-more-id", "").strip()
    current_page = hidden.get("current-page", "").strip()
    if not last_id or not current_page:
        return None

    return PagingState(
        last_id=last_id,
        last_date=date_match.group(1).strip(),
        current_page=current_page,
        explore_filter=hidden.get("explore-filter", "3").strip(),
        explore_cat=hidden.get("explore-cat", "").strip(),
        hide_campaign=hidden.get("hide_campaign", "hide_campaign").strip(),
    )


def post_load_more(session: requests.Session, state: PagingState, lang: str) -> str:
    payload = {
        "action": "load-more_vip",
        "lang": lang,
        "args[last-id]": state.last_id,
        "args[last-date]": state.last_date,
        "args[explore-filter]": state.explore_filter,
        "args[explore-cat]": state.explore_cat,
        "args[hide_campaign]": state.hide_campaign,
        "args[current-page]": state.current_page,
    }
    response = session.post(LOAD_MORE_URL, data=payload, timeout=30)
    response.raise_for_status()
    body = response.json()
    return body.get("html", "") if isinstance(body, dict) else ""


def scrape_event_urls(
    max_pages: Optional[int],
    delay_seconds: float,
    lang: str,
) -> Iterable[str]:
    session = requests.Session()
    session.headers.update(build_headers())
    session.get(BASE_URL, timeout=30)
    sleep_with_jitter(delay_seconds)

    page_url = f"{VOLUNTEER_URL}?lang={lang}" if lang else VOLUNTEER_URL
    first_response = session.get(page_url, timeout=30)
    first_response.raise_for_status()
    html = first_response.text

    yielded: Set[str] = set()
    for url in extract_event_urls(html):
        if url not in yielded:
            yield url
            yielded.add(url)

    state = parse_paging_state(html)
    pages_loaded = 1

    while state:
        if max_pages is not None and pages_loaded >= max_pages:
            break

        sleep_with_jitter(delay_seconds)
        chunk_html = post_load_more(session, state, lang or "ar")
        if not chunk_html.strip():
            break

        new_in_chunk = 0
        for url in extract_event_urls(chunk_html):
            if url in yielded:
                continue
            yield url
            yielded.add(url)
            new_in_chunk += 1

        if new_in_chunk == 0:
            break

        state = parse_paging_state(chunk_html)
        pages_loaded += 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Nahno volunteer events and print requested event fields."
    )
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to fetch (including first page).")
    parser.add_argument("--delay", type=float, default=2.5, help="Base delay (seconds) between requests.")
    parser.add_argument("--lang", default="ar", help="Language parameter for the volunteer page (ar/en).")
    args = parser.parse_args()

    try:
        details_session = requests.Session()
        for event_url in scrape_event_urls(
            max_pages=args.max_pages,
            delay_seconds=args.delay,
            lang=args.lang,
        ):
            details = fetch_event_details(details_session, event_url, delay_seconds=args.delay)
            print(f"event_url: {details.url}")
            print(f"title: {details.title}")
            print(f"subtitle: {details.subtitle}")
            print(f"organizer: {details.organizer}")
            print(f"organizer_website: {details.organizer_website}")
            print(f"description: {details.description}")
            print(f"duration_dates: {details.duration_dates}")
            print(f"days: {details.days}")
            print(f"keywords: {details.keywords}")
            print("-" * 80)
    except requests.RequestException as exc:
        raise SystemExit(f"Request failed: {exc}") from exc


if __name__ == "__main__":
    main()
