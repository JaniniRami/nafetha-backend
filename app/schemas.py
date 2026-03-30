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
