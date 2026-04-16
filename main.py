from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware

from app.admin_views import (
    ProfileInterestAdmin,
    ScrapedCompanyAdmin,
    ScrapedJobAdmin,
    UserAdmin,
    UserProfileAdmin,
    build_authentication_backend,
)
from app.config import (
    ADMIN_SECRET_KEY,
    CORS_ALLOWED_ORIGINS,
    CORS_ALLOWED_ORIGIN_REGEX,
    JWT_SECRET_KEY,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_MAX_AGE_SECONDS,
    SESSION_SECRET_KEY,
)
from app.database import SessionLocal, engine
from app.routers.auth import router as auth_router
from app.routers.catalog import router as catalog_router
from app.routers.profile import router as profile_router
from app.routers.scrape import router as scrape_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("Database connection initialized")
    yield
    engine.dispose()
    print("Database connection closed")


app = FastAPI(lifespan=lifespan)

if CORS_ALLOWED_ORIGINS or CORS_ALLOWED_ORIGIN_REGEX:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED_ORIGINS,
        allow_origin_regex=CORS_ALLOWED_ORIGIN_REGEX or None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # Keep origin strict, but allow any requested headers for browser preflight.
        allow_headers=["*"],
    )

_session_secret = SESSION_SECRET_KEY or JWT_SECRET_KEY or ADMIN_SECRET_KEY
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    max_age=SESSION_MAX_AGE_SECONDS,
    session_cookie=SESSION_COOKIE_NAME,
    same_site="lax",
    https_only=SESSION_COOKIE_SECURE,
)

app.include_router(auth_router, prefix="/api")
app.include_router(profile_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(scrape_router)

admin = Admin(
    app,
    engine,
    session_maker=SessionLocal,
    authentication_backend=build_authentication_backend(),
    title="Nafetha Admin",
)
admin.add_view(UserAdmin)
admin.add_view(UserProfileAdmin)
admin.add_view(ProfileInterestAdmin)
admin.add_view(ScrapedJobAdmin)
admin.add_view(ScrapedCompanyAdmin)


@app.get("/")
def hello_world():
    return {"message": "Hello World"}
