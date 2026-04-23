"""Import Nahno volunteering events into ``VolunteeringEvent`` rows."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import VolunteeringEvent

logger = logging.getLogger(__name__)

_NAHNO_SCRAPER_FILE = (
    Path(__file__).resolve().parents[3]
    / "nafetha-scrapers"
    / "nahno_scraper"
    / "volunteer_events_scraper.py"
)


def _load_nahno_scraper_module() -> Any:
    if not _NAHNO_SCRAPER_FILE.is_file():
        raise FileNotFoundError(str(_NAHNO_SCRAPER_FILE))
    spec = importlib.util.spec_from_file_location("nahno_volunteer_events_scraper", _NAHNO_SCRAPER_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Nahno scraper from {_NAHNO_SCRAPER_FILE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _event_exists_by_url(db, event_url: str) -> bool:
    stmt = select(VolunteeringEvent.id).where(VolunteeringEvent.event_url == event_url).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def _normalize_optional(value: object, max_len: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    if not out:
        return None
    if max_len is not None:
        return out[:max_len]
    return out


def _normalize_event_url(value: object) -> str | None:
    raw = _normalize_optional(value, max_len=1024)
    if not raw:
        return None
    parts = urlsplit(raw)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _persist_event_payload(db, payload: Any) -> dict[str, Any]:
    event_url = _normalize_event_url(getattr(payload, "url", None))
    if not event_url:
        return {
            "event_url": "",
            "status": "error",
            "title": None,
            "reason": "missing_event_url",
        }

    if _event_exists_by_url(db, event_url):
        return {
            "event_url": event_url,
            "status": "skipped",
            "title": _normalize_optional(getattr(payload, "title", None), max_len=512),
            "reason": "already_in_database",
        }

    row = VolunteeringEvent(
        event_url=event_url,
        title=_normalize_optional(getattr(payload, "title", None), max_len=512),
        subtitle=_normalize_optional(getattr(payload, "subtitle", None), max_len=512),
        organizer=_normalize_optional(getattr(payload, "organizer", None), max_len=512),
        organizer_website=_normalize_optional(getattr(payload, "organizer_website", None), max_len=1024),
        description=_normalize_optional(getattr(payload, "description", None)),
        duration_dates=_normalize_optional(getattr(payload, "duration_dates", None), max_len=255),
        days=_normalize_optional(getattr(payload, "days", None), max_len=512),
        keywords=_normalize_optional(getattr(payload, "keywords", None), max_len=1024),
    )
    db.add(row)
    try:
        db.commit()
        return {
            "event_url": event_url,
            "status": "saved",
            "title": row.title,
            "reason": None,
        }
    except IntegrityError as exc:
        db.rollback()
        return {
            "event_url": event_url,
            "status": "skipped",
            "title": row.title,
            "reason": f"integrity_error: {exc}",
        }


async def import_nahno_events(
    *,
    max_pages: int | None,
    delay_seconds: float,
    lang: str,
) -> list[dict[str, Any]]:
    """Scrape Nahno volunteering events and persist each event immediately after scraping."""
    mod = _load_nahno_scraper_module()
    results: list[dict[str, Any]] = []

    def _run_and_persist() -> None:
        db = SessionLocal()
        processed_count = 0
        saved_count = 0
        skipped_count = 0
        error_count = 0
        print(
            f"[nahno] import started: max_pages={max_pages} delay_seconds={delay_seconds} lang={lang}",
            flush=True,
        )
        try:
            details_session = mod.requests.Session()
            for event_url in mod.scrape_event_urls(
                max_pages=max_pages,
                delay_seconds=delay_seconds,
                lang=lang,
            ):
                processed_count += 1
                payload = mod.fetch_event_details(details_session, event_url, delay_seconds=delay_seconds)
                result = _persist_event_payload(db, payload)
                results.append(result)
                status = result.get("status")
                if status == "saved":
                    saved_count += 1
                    print(
                        f"[nahno] added {saved_count} (processed={processed_count}): {result.get('event_url')}",
                        flush=True,
                    )
                    logger.info(
                        "[nahno] saved volunteering event to database (count=%s): %s",
                        saved_count,
                        result.get("event_url"),
                    )
                elif status == "skipped":
                    skipped_count += 1
                    print(
                        f"[nahno] skipped {skipped_count} (processed={processed_count}): "
                        f"{result.get('event_url')} reason={result.get('reason')}",
                        flush=True,
                    )
                else:
                    error_count += 1
                    print(
                        f"[nahno] error {error_count} (processed={processed_count}): "
                        f"{result.get('event_url')} reason={result.get('reason')}",
                        flush=True,
                    )
        finally:
            print(
                "[nahno] import finished: "
                f"processed={processed_count} saved={saved_count} skipped={skipped_count} errors={error_count}",
                flush=True,
            )
            db.close()

    await asyncio.to_thread(_run_and_persist)
    return results
