"""Lazy loading helpers for optional LinkedIn scraper dependencies."""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
import sys
from typing import Any

_SCRAPER_FS_ROOT = Path(__file__).resolve().parents[3] / "nafetha-scrapers"
_LINKEDIN_DIST = _SCRAPER_FS_ROOT / "linkedin_scraper"
_UNAVAILABLE_MESSAGE = (
    "LinkedIn scraping is unavailable in this environment because Playwright "
    "and the vendored scraper dependencies are not installed."
)


class LinkedInScraperUnavailable(RuntimeError):
    """Raised when LinkedIn scraping dependencies are not available."""


def _ensure_scraper_path() -> None:
    if _LINKEDIN_DIST.is_dir() and str(_LINKEDIN_DIST) not in sys.path:
        sys.path.insert(0, str(_LINKEDIN_DIST))


@lru_cache(maxsize=1)
def _load_linkedin_module() -> Any:
    _ensure_scraper_path()
    try:
        return importlib.import_module("linkedin_scraper")
    except Exception as exc:  # pragma: no cover - environment dependent
        raise LinkedInScraperUnavailable(_UNAVAILABLE_MESSAGE) from exc


@lru_cache(maxsize=1)
def _load_callbacks_module() -> Any:
    _ensure_scraper_path()
    try:
        return importlib.import_module("linkedin_scraper.callbacks")
    except Exception as exc:  # pragma: no cover - environment dependent
        raise LinkedInScraperUnavailable(_UNAVAILABLE_MESSAGE) from exc


def assert_linkedin_scraper_available() -> None:
    _load_linkedin_module()
    _load_callbacks_module()


def get_browser_manager_class() -> Any:
    return _load_linkedin_module().BrowserManager


def get_auth_runtime() -> tuple[Any, Any, Any]:
    module = _load_linkedin_module()
    return module.is_logged_in, module.login_with_credentials, module.wait_for_manual_login


def get_scrape_runtime() -> tuple[Any, Any, Any, Any, Any, Any]:
    module = _load_linkedin_module()
    callbacks = _load_callbacks_module()
    return (
        module.BrowserManager,
        module.CompanyScraper,
        module.JobScraper,
        module.JobSearchScraper,
        callbacks.ConsoleCallback,
        callbacks.SilentCallback,
    )
