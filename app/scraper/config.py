"""Runtime configuration for integrated scraping jobs."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = PROJECT_ROOT / "nafetha-scrapers"
DEFAULT_OUTPUT_DIR = SCRAPER_ROOT / "output"
DEFAULT_SESSION_PATH = SCRAPER_ROOT / "session.json"
