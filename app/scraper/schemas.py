"""Pydantic schemas for scraper API contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.scraper.config import DEFAULT_OUTPUT_DIR, DEFAULT_SESSION_PATH


class ScrapeRequest(BaseModel):
    keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Keyword queries for LinkedIn job search. "
            "Pass an empty list [] or [\"\"] to search with no keyword filter."
        ),
    )
    locations: list[str] = Field(
        default_factory=list,
        description=(
            "One or more LinkedIn location filters. "
            "Pass an empty list [] to search with no location filter."
        ),
    )
    jobs_per_location: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="How many jobs to scrape per location; null means no cap",
    )
    delay_seconds: float = Field(
        default=2.0,
        ge=0.0,
        le=30.0,
        description="Delay between scrape requests to reduce rate limiting",
    )
    session_path: str = Field(
        default=str(DEFAULT_SESSION_PATH),
        description="Path to persisted LinkedIn session file",
    )
    output_dir: str = Field(
        default=str(DEFAULT_OUTPUT_DIR),
        description="Directory where XLSX files are written",
    )
    verbose: bool = Field(default=False, description="Enable verbose console callback logging")

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        # Strip whitespace from each entry; keep empty strings so that an
        # empty/blank keyword is treated as "no keyword filter".
        cleaned = [item.strip() for item in value]
        # Deduplicate while preserving order, keeping at most one empty entry.
        seen: set[str] = set()
        result: list[str] = []
        for kw in cleaned:
            if kw not in seen:
                seen.add(kw)
                result.append(kw)
        # If the list is completely empty, add a single empty string so the
        # scraper still runs one iteration with no keyword filter.
        return result if result else [""]


class JobProgress(BaseModel):
    total_locations: int = 0
    locations_completed: int = 0
    current_location: str | None = None
    pages_processed: int = 0
    job_urls_found: int = 0
    jobs_scraped: int = 0
    companies_discovered: int = 0
    companies_scraped: int = 0
    last_message: str = "Queued"
    logs: list[str] = Field(
        default_factory=list,
        description="Timestamped progress lines for this job (most recent at the end).",
    )


class JobStatusResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed", "cancelling", "cancelled"]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    request: ScrapeRequest
    progress: JobProgress
    output_jobs_xlsx: str | None = None
    output_companies_xlsx: str | None = None
    error: str | None = None


class StartJobResponse(BaseModel):
    job_id: str
    status: str


class ImportUrlsRequest(BaseModel):
    urls: list[str] = Field(
        min_length=1,
        description="One or more LinkedIn job URLs, e.g. https://www.linkedin.com/jobs/view/4359006443/",
    )
    session_path: str = Field(
        default=str(DEFAULT_SESSION_PATH),
        description="Path to persisted LinkedIn session file",
    )
    delay_seconds: float = Field(
        default=1.0,
        ge=0.0,
        le=30.0,
        description="Delay between scrape requests",
    )
    verbose: bool = Field(default=True)

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, value: list[str]) -> list[str]:
        cleaned = [u.strip() for u in value if u.strip()]
        invalid = [u for u in cleaned if "linkedin.com/jobs/view/" not in u]
        if invalid:
            raise ValueError(
                f"All URLs must be LinkedIn job URLs (contain /jobs/view/). Invalid: {invalid}"
            )
        return cleaned


class ImportUrlResult(BaseModel):
    url: str
    status: Literal["saved", "skipped", "error"]
    job_id: str | None = None
    job_title: str | None = None
    reason: str | None = None


class ImportUrlsResponse(BaseModel):
    saved: int
    skipped: int
    errors: int
    results: list[ImportUrlResult]


class TanqeebSearchImportRequest(BaseModel):
    """Run Tanqeeb search pagination + job pages, then persist to ``jobs``."""

    search_url: str | None = Field(
        default=None,
        description="Full Tanqeeb search URL; omit to use scraper default.",
    )
    timeout_seconds: int = Field(
        default=20,
        ge=5,
        le=120,
        description="HTTP timeout per request when fetching Tanqeeb pages.",
    )


class TanqeebImportUrlsRequest(BaseModel):
    """Scrape explicit Tanqeeb job detail URLs and persist."""

    urls: list[str] = Field(
        min_length=1,
        description="Tanqeeb job page URLs, e.g. https://jordan.tanqeeb.com/jobs-in-jordan/all/jobs/020916285.html",
    )
    timeout_seconds: int = Field(default=20, ge=5, le=120)

    @field_validator("urls")
    @classmethod
    def validate_tanqeeb_urls(cls, value: list[str]) -> list[str]:
        cleaned = [u.strip() for u in value if u.strip()]
        invalid = [u for u in cleaned if "tanqeeb.com" not in u.lower() or ".html" not in u.lower()]
        if invalid:
            raise ValueError(
                "All URLs must be Tanqeeb job HTML pages (tanqeeb.com host and .html path). "
                f"Invalid: {invalid}"
            )
        return cleaned
