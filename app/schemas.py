from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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
    job_id: str
    job_title: str | None
    company_linkedin_url: str | None
    posted_date: str | None
    job_description: str | None
    linkedin_url: str
    seed_location: str | None
    keyword: str | None
    scraped_at: datetime


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
    scraped_at: datetime


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


class ScrapedJobUpdate(BaseModel):
    """Partial update for admin-managed scraped jobs."""

    model_config = ConfigDict(extra="forbid")

    job_id: str | None = Field(default=None, max_length=64)
    linkedin_url: str | None = Field(default=None, min_length=1, max_length=1024)
    company_id: UUID | None = None
    job_title: str | None = Field(default=None, max_length=512)
    company_linkedin_url: str | None = Field(default=None, max_length=1024)
    posted_date: str | None = Field(default=None, max_length=255)
    job_description: str | None = None
    seed_location: str | None = Field(default=None, max_length=255)
    keyword: str | None = Field(default=None, max_length=255)

    @field_validator("job_id", mode="before")
    @classmethod
    def job_id_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @field_validator("linkedin_url", mode="before")
    @classmethod
    def linkedin_url_strip(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip()
        return v


class ScrapedJobCreate(BaseModel):
    """Admin create body. ``job_id`` is optional; the server assigns a unique external id when omitted."""

    model_config = ConfigDict(extra="forbid")

    job_id: str | None = Field(default=None, max_length=64)
    linkedin_url: str = Field(min_length=1, max_length=1024)
    company_id: UUID | None = None
    job_title: str | None = Field(default=None, max_length=512)
    company_linkedin_url: str | None = Field(default=None, max_length=1024)
    posted_date: str | None = Field(default=None, max_length=255)
    job_description: str | None = None
    seed_location: str | None = Field(default=None, max_length=255)
    keyword: str | None = Field(default=None, max_length=255)

    @field_validator("job_id", mode="before")
    @classmethod
    def job_id_strip_or_none(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v


class CommunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    website: str | None
    created_by_user_id: UUID | None
    created_at: datetime


class CommunityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=50_000)
    website: str | None = Field(default=None, max_length=1024)

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


class CommunityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=50_000)
    website: str | None = Field(default=None, max_length=1024)

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


class CommunityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    community_id: UUID
    name: str
    event_at: datetime
    location: str
    description: str
    website: str | None
    created_at: datetime


class CommunityEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    event_at: datetime
    location: str = Field(min_length=1, max_length=1024)
    description: str = Field(default="", max_length=50_000)
    website: str | None = Field(default=None, max_length=1024)

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


class CommunityEventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    event_at: datetime | None = None
    location: str | None = Field(default=None, min_length=1, max_length=1024)
    description: str | None = Field(default=None, max_length=50_000)
    website: str | None = Field(default=None, max_length=1024)

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


class SubscriptionStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    community_id: UUID
    subscribed: bool


class FavoriteStateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    favorited: bool
