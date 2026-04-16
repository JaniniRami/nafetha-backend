"""Authentication and session lifecycle helpers."""

import logging
from pathlib import Path
import sys

_SCRAPER_FS_ROOT = Path(__file__).resolve().parents[3] / "nafetha-scrapers"
_LINKEDIN_DIST = _SCRAPER_FS_ROOT / "linkedin_scraper"
if _LINKEDIN_DIST.is_dir() and str(_LINKEDIN_DIST) not in sys.path:
    sys.path.insert(0, str(_LINKEDIN_DIST))

from linkedin_scraper import (  # noqa: E402
    BrowserManager,
    is_logged_in,
    login_with_credentials,
    wait_for_manual_login,
)

from app.config import MANUAL_LOGIN

logger = logging.getLogger(__name__)


async def ensure_authenticated_session(browser: BrowserManager, session_path: Path) -> None:
    """
    Ensure an authenticated LinkedIn session is available.

    Session reuse (always attempted first):
    - Load session file → verify on /feed → return if authenticated.

    Fallback when session is missing / expired (controlled by MANUAL_LOGIN):
    - MANUAL_LOGIN=true  → navigate to login page, wait up to 5 min for the
                           user to log in manually (useful for CAPTCHA/2FA).
    - MANUAL_LOGIN=false → use LINKEDIN_EMAIL + LINKEDIN_PASSWORD from .env
                           (programmatic, with browser warm-up).

    A fresh session file is saved after any successful login fallback.
    """
    if session_path.exists():
        try:
            await browser.load_session(str(session_path))
            await browser.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            if await is_logged_in(browser.page):
                logger.info("LinkedIn session loaded from %s", session_path)
                return
        except Exception:
            logger.warning("Session file invalid or expired, falling back to login.")

    if MANUAL_LOGIN:
        logger.info("MANUAL_LOGIN=true — navigate to LinkedIn login in the browser window.")
        await browser.page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await wait_for_manual_login(browser.page, timeout=300_000)
    else:
        logger.info("MANUAL_LOGIN=false — using programmatic credentials login.")
        await login_with_credentials(browser.page, warm_up=True)

    await browser.save_session(str(session_path))
    logger.info("New LinkedIn session saved to %s", session_path)
