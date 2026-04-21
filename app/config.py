import os

from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in the environment")
    return url


DATABASE_URL = get_database_url()


def parse_csv_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


# Required for /api/register, /api/login, and token refresh (Alembic can run without it).
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
CORS_ALLOWED_ORIGINS = parse_csv_env("CORS_ALLOWED_ORIGINS")
CORS_ALLOWED_ORIGIN_REGEX = os.getenv("CORS_ALLOWED_ORIGIN_REGEX", "").strip()

# Browser cookie session (optional; used when login/register sets use_session_cookie=True).
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "") or os.getenv("JWT_SECRET_KEY", "")
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(14 * 24 * 3600)))
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "nafetha_session")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes")

ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "change-me-use-a-long-random-secret")
# SQLAdmin browser UI at `/admin` (panel login, not app JWT users). Defaults suit local dev;
# set both in production (or rely on a strong ADMIN_PASSWORD only).
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

# Playwright: true = headless (servers/CI); false/unset = visible browser (LinkedIn demos).
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "").lower() in ("1", "true", "yes")

# Optional: admin AI display-field generation (local Ollama). Set OLLAMA_HOST if not default.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()

# LinkedIn login strategy when no valid session exists.
# true  = wait for the user to log in manually in the browser window.
# false = use LINKEDIN_EMAIL / LINKEDIN_PASSWORD from .env (programmatic).
MANUAL_LOGIN = os.getenv("MANUAL_LOGIN", "").lower() in ("1", "true", "yes")
