from datetime import datetime
from decimal import Decimal
from uuid import UUID as PyUUID
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

DEFAULT_USER_ROLE = "student"
USER_ROLES: tuple[str, ...] = ("student", "superadmin")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'student'"),
        default=DEFAULT_USER_ROLE,
    )
    onboarded: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user",
        uselist=False,
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    __table_args__ = (
        CheckConstraint(
            "gpa_scale IN (5, 100)",
            name="ck_user_profiles_gpa_scale_valid",
        ),
        CheckConstraint(
            "gpa_value >= 0 AND gpa_value <= gpa_scale",
            name="ck_user_profiles_gpa_value_valid",
        ),
        CheckConstraint(
            "graduation_semester IN ('First','Second','Summer')",
            name="ck_user_profiles_graduation_semester_valid",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    university: Mapped[str] = mapped_column(String(255), nullable=False)
    major: Mapped[str] = mapped_column(String(255), nullable=False)
    year_of_study: Mapped[int] = mapped_column(Integer, nullable=False)
    graduation_semester: Mapped[str] = mapped_column(String(10), nullable=False)
    graduation_year: Mapped[int] = mapped_column(Integer, nullable=False)
    gpa_scale: Mapped[int] = mapped_column(Integer, nullable=False)
    gpa_value: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="profile")
    interest_rows: Mapped[list["ProfileInterest"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class ProfileInterest(Base):
    """One row per interest label for a user profile (stored lowercase)."""

    __tablename__ = "profile_interests"
    __table_args__ = (
        UniqueConstraint(
            "user_profile_id",
            "interest",
            name="uq_profile_interests_profile_interest",
        ),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_profile_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    interest: Mapped[str] = mapped_column(String(128), nullable=False)

    profile: Mapped["UserProfile"] = relationship(back_populates="interest_rows")


class ScrapedJob(Base):
    __tablename__ = "jobs"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company_linkedin_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    posted_date: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[str] = mapped_column(String(1024), unique=True, index=True, nullable=False)
    seed_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ScrapedCompany(Base):
    __tablename__ = "companies"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_name: Mapped[str] = mapped_column(String(512), unique=True, index=True, nullable=False)
    linkedin_url: Mapped[str] = mapped_column(String(1024), unique=True, index=True, nullable=False)
    blacklisted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    about_us: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
