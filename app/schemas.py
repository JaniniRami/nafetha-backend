from datetime import datetime
from decimal import Decimal
from typing import Any, Self
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


def normalize_displayed_keywords_input(v: object) -> object:
    """Comma-separated keywords; spaces inside a token become hyphens (same rule as AI ``keywords_to_stored_string``)."""
    if v is None:
        return None
    if not isinstance(v, str):
        return v
    s = v.strip()
    if not s:
        return None
    parts: list[str] = []
    for raw in s.split(","):
        token = " ".join(raw.split())
        if not token:
            continue
        token = token.replace(" ", "-")
        if token and token not in parts:
            parts.append(token)
    return ",".join(parts) if parts else None


class UserSetupStatus(BaseModel):
    """Grouped flags the client can use for routing (onboarding wizard, interests picker, etc.)."""

    model_config = ConfigDict(extra="forbid")

    onboarded: bool
    interests_set: bool


class TokenUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: str
    setup: UserSetupStatus


class AuthSession(BaseModel):
    """Tokens + user profile for app session after register or login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: TokenUserOut
    profile: "UserProfileOut | None" = None
    daily_highlights: "DailyHighlightsOut | None" = None


class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    use_session_cookie: bool = False
    """If True (e.g. same-site web app), also opens a signed cookie session until it expires."""


class RefreshTokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class UserRegister(BaseModel):
    """Role is assigned server-side only (not accepted in this body)."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)
    use_session_cookie: bool = False

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_full_name(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


_GRADUATION_SEMESTER_NORMALIZED: dict[str, str] = {
    "first": "First",
    "second": "Second",
    "summer": "Summer",
}


class OnboardingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    university: str = Field(min_length=1, max_length=255)
    major: str = Field(min_length=1, max_length=255)
    year_of_study: int = Field(ge=0)
    graduation_semester: str
    graduation_year: int = Field(ge=1900, le=3000)

    # The user chooses which GPA scale they are entering.
    # Example: if gpa_scale=5 then gpa_value is out of 5.
    gpa_scale: int
    gpa_value: Decimal = Field(ge=0)

    @field_validator("graduation_semester", mode="before")
    @classmethod
    def normalize_graduation_semester(cls, v: object) -> object:
        if not isinstance(v, str):
            raise ValueError("graduation_semester must be a string")
        key = v.strip().lower()
        if key not in _GRADUATION_SEMESTER_NORMALIZED:
            raise ValueError("graduation_semester must be First, Second, or Summer")
        return _GRADUATION_SEMESTER_NORMALIZED[key]

    @field_validator("gpa_scale")
    @classmethod
    def validate_gpa_scale(cls, v: int) -> int:
        if v not in (5, 100):
            raise ValueError("gpa_scale must be 5 or 100")
        return v

    @field_validator("gpa_value")
    @classmethod
    def validate_gpa_value(cls, v: Decimal, info) -> Decimal:
        scale = info.data.get("gpa_scale")
        if scale is None:
            return v
        if v > Decimal(scale):
            raise ValueError("gpa_value must be <= gpa_scale")
        return v


class UserProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    university: str
    major: str
    year_of_study: int
    graduation_semester: str
    graduation_year: int
    gpa_scale: int
    gpa_value: Decimal
    created_at: datetime
    updated_at: datetime


class InterestsReplaceIn(BaseModel):
    """Replace the whole interest set for the authenticated user's profile."""

    model_config = ConfigDict(extra="forbid")

    interests: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("interests")
    @classmethod
    def normalize_interests(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in v:
            s = str(raw).strip().lower()
            if not s:
                raise ValueError("Each interest must be a non-empty string")
            if len(s) > 128:
                raise ValueError("Each interest must be at most 128 characters")
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out


class InterestsOut(BaseModel):
    """Current interests for the user's profile (sorted). Empty if no profile or none saved."""

    interests: list[str]
    has_interests: bool


class ScrapedJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID | None
    company_name: str | None = None
    job_id: str
    job_title: str | None
    posted_date: str | None
    job_description: str | None
    extra_details: str | None
    job_url: str = Field(validation_alias=AliasChoices("job_url", "linkedin_url"))
    keyword: str | None
    displayed_description: str | None
    displayed_keywords: str | None
    matching_percentage: float | None = None
    scraped_at: datetime

    @model_validator(mode="before")
    @classmethod
    def attach_company_name(cls, data: Any) -> Any:
        from app.models import ScrapedJob

        if isinstance(data, ScrapedJob):
            company_name = None
            company = getattr(data, "company", None)
            if company is not None:
                company_name = company.company_name
            return {
                "id": data.id,
                "company_id": data.company_id,
                "company_name": company_name,
                "job_id": data.job_id,
                "job_title": data.job_title,
                "posted_date": data.posted_date,
                "job_description": data.job_description,
                "extra_details": data.extra_details,
                "job_url": data.linkedin_url,
                "keyword": data.keyword,
                "displayed_description": data.displayed_description,
                "displayed_keywords": data.displayed_keywords,
                "matching_percentage": getattr(data, "matching_percentage", None),
                "scraped_at": data.scraped_at,
            }
        return data


class ScrapedCompanyOut(BaseModel):
    """Company row as returned to clients; list endpoint only includes non-blacklisted rows."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: str
    linkedin_url: str | None
    blacklisted: bool
    industry: str | None
    company_size: str | None
    website: str | None
    phone: str | None
    about_us: str | None
    displayed_description: str | None
    displayed_keywords: str | None
    matching_percentage: float | None = None
    scraped_at: datetime


class VolunteeringEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_url: str
    title: str | None
    subtitle: str | None
    organizer: str | None
    organizer_website: str | None
    description: str | None
    duration_dates: str | None
    days: str | None
    keywords: str | None
    matching_percentage: float | None = None
    scraped_at: datetime


class VolunteeringEventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_url: str | None = Field(default=None, min_length=1, max_length=1024)
    title: str | None = Field(default=None, max_length=512)
    subtitle: str | None = Field(default=None, max_length=512)
    organizer: str | None = Field(default=None, max_length=512)
    organizer_website: str | None = Field(default=None, max_length=1024)
    description: str | None = None
    duration_dates: str | None = Field(default=None, max_length=255)
    days: str | None = Field(default=None, max_length=512)
    keywords: str | None = Field(default=None, max_length=1024)

    @field_validator(
        "event_url",
        "title",
        "subtitle",
        "organizer",
        "organizer_website",
        "duration_dates",
        "days",
        "keywords",
        mode="before",
    )
    @classmethod
    def strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("keywords", mode="before")
    @classmethod
    def keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class VolunteeringKeywordAIResponse(BaseModel):
    success: bool
    keyword: str = ""
    saved: bool = False
    event: VolunteeringEventOut | None = None


class ScrapedCompanyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=1, max_length=512)
    linkedin_url: str | None = Field(default=None, max_length=1024)
    blacklisted: bool = False
    industry: str | None = Field(default=None, max_length=255)
    company_size: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=1024)
    phone: str | None = Field(default=None, max_length=255)
    about_us: str | None = None
    displayed_description: str | None = None
    displayed_keywords: str | None = Field(default=None, max_length=1024)

    @field_validator("company_name", mode="before")
    @classmethod
    def strip_company_name(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("linkedin_url", mode="before")
    @classmethod
    def linkedin_url_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("displayed_keywords", mode="before")
    @classmethod
    def displayed_keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class ScrapedCompanyUpdate(BaseModel):
    """Partial update for admin-managed scraped companies."""

    model_config = ConfigDict(extra="forbid")

    company_name: str | None = Field(default=None, min_length=1, max_length=512)
    linkedin_url: str | None = Field(default=None, max_length=1024)
    blacklisted: bool | None = None
    industry: str | None = Field(default=None, max_length=255)
    company_size: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=1024)
    phone: str | None = Field(default=None, max_length=255)
    about_us: str | None = None
    displayed_description: str | None = None
    displayed_keywords: str | None = Field(default=None, max_length=1024)

    @field_validator("company_name", mode="before")
    @classmethod
    def strip_company_name(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("linkedin_url", mode="before")
    @classmethod
    def linkedin_url_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("displayed_keywords", mode="before")
    @classmethod
    def displayed_keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class CompanyAboutBackfillRequest(BaseModel):
    """Backfill company about text from website/linkedin pages."""

    model_config = ConfigDict(extra="forbid")

    company_ids: list[UUID] = Field(
        default_factory=list,
        max_length=500,
        description="Optional explicit set of company ids to process.",
    )
    only_missing: bool = Field(
        default=True,
        description="When true, skip rows that already have non-empty about_us.",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Optional max rows to process (applies only when company_ids is empty).",
    )


class CompanyAboutBackfillRowResult(BaseModel):
    company_id: UUID
    company_name: str
    source_url: str | None
    status: str
    reason: str | None = None
    saved_chars: int | None = None


class CompanyAboutBackfillResponse(BaseModel):
    processed: int
    updated: int
    skipped: int
    failed: int
    results: list[CompanyAboutBackfillRowResult]


class CompanyAboutBackfillJobQueued(BaseModel):
    job_id: str
    status: str


class CompanyAboutBackfillJobStatus(BaseModel):
    job_id: str
    status: str
    only_missing: bool
    company_ids: list[UUID]
    limit: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processed: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    error: str | None = None


class CompanyDisplayAIResponse(BaseModel):
    """Result of Gemini extraction from company about_us; DB updated only when extraction succeeds."""

    success: bool
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    saved: bool = False
    company: ScrapedCompanyOut | None = None


class CompanyDisplayAIJobRequest(BaseModel):
    """Queue bulk AI display-field generation."""

    model_config = ConfigDict(extra="forbid")

    company_ids: list[UUID] = Field(
        default_factory=list,
        max_length=500,
        description="Optional subset of companies; empty means all (subject to limit).",
    )
    only_missing_display: bool = Field(
        default=True,
        description="When true, only process rows where both displayed_description and displayed_keywords are empty; skip if either is already set.",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Max companies from the query when company_ids is empty.",
    )


class CompanyDisplayAIJobQueued(BaseModel):
    job_id: str
    status: str


class CompanyDisplayAIJobStatus(BaseModel):
    job_id: str
    status: str
    only_missing_display: bool
    company_ids: list[UUID]
    limit: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processed: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    declined: int = 0
    error: str | None = None


class JobDisplayAIResponse(BaseModel):
    """Result of Gemini extraction from job description; DB updated only when extraction succeeds."""

    success: bool
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    saved: bool = False
    job: ScrapedJobOut | None = None


class JobDisplayAIJobRequest(BaseModel):
    """Queue bulk AI display-field generation for scraped job rows."""

    model_config = ConfigDict(extra="forbid")

    job_ids: list[UUID] = Field(
        default_factory=list,
        max_length=500,
        description="Optional subset of job row ids; empty means all (subject to limit).",
    )
    only_missing_display: bool = Field(
        default=True,
        description="When true, only process rows where both displayed_description and displayed_keywords are empty.",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Max jobs from the query when job_ids is empty.",
    )


class JobDisplayAIJobQueued(BaseModel):
    job_id: str
    status: str


class JobDisplayAIJobStatus(BaseModel):
    job_id: str
    status: str
    only_missing_display: bool
    job_ids: list[UUID]
    limit: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processed: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    declined: int = 0
    error: str | None = None


class ScrapedJobUpdate(BaseModel):
    """Partial update for admin-managed scraped jobs."""

    model_config = ConfigDict(extra="forbid")

    job_id: str | None = Field(default=None, max_length=64)
    job_url: str | None = Field(
        default=None,
        min_length=1,
        max_length=1024,
        validation_alias=AliasChoices("job_url", "linkedin_url"),
    )
    company_id: UUID | None = None
    job_title: str | None = Field(default=None, max_length=512)
    posted_date: str | None = Field(default=None, max_length=255)
    job_description: str | None = None
    extra_details: str | None = None
    keyword: str | None = Field(default=None, max_length=255)
    displayed_description: str | None = None
    displayed_keywords: str | None = Field(default=None, max_length=1024)

    @field_validator("job_id", mode="before")
    @classmethod
    def job_id_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("job_url", mode="before")
    @classmethod
    def job_url_strip(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("keyword", mode="before")
    @classmethod
    def keyword_max_three_parts(cls, v: object) -> object:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            return v
        s = v.strip()
        if not s:
            return None
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) > 3:
            raise ValueError("At most 3 comma-separated keywords are allowed for jobs")
        return ",".join(parts)

    @field_validator("displayed_keywords", mode="before")
    @classmethod
    def job_displayed_keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class ScrapedJobCreate(BaseModel):
    """Admin create body. ``job_id`` is optional; the server assigns a unique external id when omitted."""

    model_config = ConfigDict(extra="forbid")

    job_id: str | None = Field(default=None, max_length=64)
    job_url: str = Field(
        min_length=1,
        max_length=1024,
        validation_alias=AliasChoices("job_url", "linkedin_url"),
    )
    company_id: UUID | None = None
    job_title: str | None = Field(default=None, max_length=512)
    posted_date: str | None = Field(default=None, max_length=255)
    job_description: str | None = None
    extra_details: str | None = None
    keyword: str | None = Field(default=None, max_length=255)
    displayed_description: str | None = None
    displayed_keywords: str | None = Field(default=None, max_length=1024)

    @field_validator("job_id", mode="before")
    @classmethod
    def job_id_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("keyword", mode="before")
    @classmethod
    def create_keyword_max_three_parts(cls, v: object) -> object:
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            return v
        s = v.strip()
        if not s:
            return None
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) > 3:
            raise ValueError("At most 3 comma-separated keywords are allowed for jobs")
        return ",".join(parts)

    @field_validator("displayed_keywords", mode="before")
    @classmethod
    def create_displayed_keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class CommunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    website: str | None
    keywords: str | None
    created_by_user_id: UUID | None
    created_at: datetime


class CommunityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=50_000)
    website: str | None = Field(default=None, max_length=1024)
    keywords: str | None = Field(default=None, max_length=1024)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("website", mode="before")
    @classmethod
    def website_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("keywords", mode="before")
    @classmethod
    def create_keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class CommunityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=50_000)
    website: str | None = Field(default=None, max_length=1024)
    keywords: str | None = Field(default=None, max_length=1024)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("website", mode="before")
    @classmethod
    def website_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("keywords", mode="before")
    @classmethod
    def update_keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class CommunityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    community_id: UUID
    name: str
    event_at: datetime
    location: str
    description: str
    website: str | None
    keywords: str | None
    matching_percentage: float | None = None
    created_at: datetime


class DailyHighlightUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    role: str
    onboarded: bool
    created_at: datetime


class DailyHighlightsOut(BaseModel):
    user: DailyHighlightUserOut | None = None
    job: ScrapedJobOut | None = None
    volunteering_event: VolunteeringEventOut | None = None
    community_event: CommunityEventOut | None = None


class CatalogMatchScoreItem(BaseModel):
    id: UUID
    score_percent: float


class CatalogMatchScoresOut(BaseModel):
    model_name: str
    profile_text: str
    jobs: list[CatalogMatchScoreItem]
    companies: list[CatalogMatchScoreItem]
    communities: list[CatalogMatchScoreItem]
    community_events: list[CatalogMatchScoreItem]
    volunteering_events: list[CatalogMatchScoreItem]


class CatalogItemMatchScoreOut(BaseModel):
    id: UUID
    catalog_type: str
    matching_percentage: float


class CommunityWithEventsOut(CommunityOut):
    """Community row including all events (sorted by ``event_at`` ascending)."""

    events: list[CommunityEventOut] = Field(default_factory=list)

    @model_validator(mode="after")
    def sort_events_by_time(self) -> Self:
        self.events = sorted(self.events, key=lambda e: e.event_at)
        return self


class CommunityEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    event_at: datetime
    location: str = Field(min_length=1, max_length=1024)
    description: str = Field(default="", max_length=50_000)
    website: str | None = Field(default=None, max_length=1024)
    keywords: str | None = Field(default=None, max_length=1024)

    @field_validator("name", "location", mode="before")
    @classmethod
    def strip_strings(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("website", mode="before")
    @classmethod
    def website_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("keywords", mode="before")
    @classmethod
    def create_keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class CommunityEventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    event_at: datetime | None = None
    location: str | None = Field(default=None, min_length=1, max_length=1024)
    description: str | None = Field(default=None, max_length=50_000)
    website: str | None = Field(default=None, max_length=1024)
    keywords: str | None = Field(default=None, max_length=1024)

    @field_validator("name", "location", mode="before")
    @classmethod
    def strip_strings(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("website", mode="before")
    @classmethod
    def website_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("keywords", mode="before")
    @classmethod
    def update_keywords_normalize(cls, v: object) -> object:
        return normalize_displayed_keywords_input(v)


class CommunityEventKeywordsRegenerateResponse(BaseModel):
    processed: int
    updated: int
    skipped: int
    failed: int


class SubscriptionStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    community_id: UUID
    subscribed: bool


class FavoriteStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    favorited: bool


class CompanyFavoriteStateOut(BaseModel):
    """Toggle or query favorite state for a catalog company (row id = ``companies.id``)."""

    model_config = ConfigDict(extra="forbid")

    company_id: UUID
    favorited: bool


class JobFavoriteStateOut(BaseModel):
    """Toggle or query favorite state for an internship / scraped job row (``jobs.id``)."""

    model_config = ConfigDict(extra="forbid")

    job_row_id: UUID
    favorited: bool
