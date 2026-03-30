from typing import Any

from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend
from sqladmin.fields import SelectField as AdminSelectField
from starlette.requests import Request
from wtforms.fields import PasswordField

from app.config import ADMIN_PASSWORD, ADMIN_SECRET_KEY, ADMIN_USERNAME
from app.models import (
    DEFAULT_USER_ROLE,
    USER_ROLES,
    ProfileInterest,
    ScrapedCompany,
    ScrapedJob,
    User,
    UserProfile,
)
from app.security import hash_password


class UserRoleSelectField(AdminSelectField):
    """sqladmin matches ``form_overrides`` by attribute name string (e.g. ``\"role\"``), not ``User.role``."""

    def __init__(self, label=None, validators=None, **kwargs):
        kwargs.pop("choices", None)
        if kwargs.get("default") in (None, ""):
            kwargs["default"] = DEFAULT_USER_ROLE
        super().__init__(
            label,
            validators,
            coerce=str,
            choices=[(r, r.replace("_", " ").title()) for r in USER_ROLES],
            allow_blank=kwargs.pop("allow_blank", False),
            blank_text=kwargs.pop("blank_text", None),
            **kwargs,
        )


class AdminAuth(AuthenticationBackend):
    def __init__(self) -> None:
        super().__init__(secret_key=ADMIN_SECRET_KEY)
        self._username = ADMIN_USERNAME or ""
        self._password = ADMIN_PASSWORD or ""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        if username == self._username and password == self._password:
            request.session.update({"admin_authenticated": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin_authenticated"))


def build_authentication_backend() -> AdminAuth | None:
    if ADMIN_USERNAME and ADMIN_PASSWORD:
        return AdminAuth()
    return None


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"
    column_list = [User.id, User.email, User.full_name, User.role, User.onboarded, User.created_at]
    column_searchable_list = [User.email, User.full_name]
    column_sortable_list = [User.email, User.full_name, User.role, User.onboarded, User.created_at]
    column_details_exclude_list = [User.password_hash]
    form_columns = [User.email, User.full_name, User.password_hash, User.role, User.onboarded]
    form_overrides = {
        "password_hash": PasswordField,
        "role": UserRoleSelectField,
    }
    column_labels = {User.password_hash: "Password"}

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        pwd = data.get("password_hash")
        if pwd is not None and str(pwd).strip():
            data["password_hash"] = hash_password(str(pwd))
        elif not is_created:
            data.pop("password_hash", None)
        else:
            raise ValueError("Password is required when creating a user")

        if is_created and (
            not data.get("role") or not str(data.get("role", "")).strip()
        ):
            data["role"] = DEFAULT_USER_ROLE


class UserProfileAdmin(ModelView, model=UserProfile):
    name = "User Profile"
    name_plural = "User Profiles"
    icon = "fa-solid fa-id-card"
    can_create = False
    can_edit = True

    column_list = [
        UserProfile.id,
        UserProfile.user_id,
        UserProfile.university,
        UserProfile.major,
        UserProfile.year_of_study,
        UserProfile.graduation_semester,
        UserProfile.graduation_year,
        UserProfile.gpa_scale,
        UserProfile.gpa_value,
        UserProfile.created_at,
        UserProfile.updated_at,
    ]
    column_searchable_list = [UserProfile.university, UserProfile.major]
    column_sortable_list = [UserProfile.created_at, UserProfile.updated_at, UserProfile.graduation_year]

    # Never edit `user_id` in admin: the WTForms UUID field often submits empty and
    # would set `user_id` to NULL on UPDATE (NOT NULL violation).
    form_columns = [
        UserProfile.university,
        UserProfile.major,
        UserProfile.year_of_study,
        UserProfile.graduation_semester,
        UserProfile.graduation_year,
        UserProfile.gpa_scale,
        UserProfile.gpa_value,
    ]
    column_details_list = column_list

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        data.pop("user_id", None)


class ProfileInterestAdmin(ModelView, model=ProfileInterest):
    name = "Profile interest"
    name_plural = "Profile interests"
    icon = "fa-solid fa-heart"
    can_create = True
    can_edit = True
    column_list = [
        ProfileInterest.id,
        ProfileInterest.user_profile_id,
        ProfileInterest.interest,
    ]
    column_sortable_list = [ProfileInterest.interest, ProfileInterest.user_profile_id]
    column_searchable_list = [ProfileInterest.interest]
    form_columns = [
        ProfileInterest.user_profile_id,
        ProfileInterest.interest,
    ]
    column_details_list = column_list

    async def on_model_change(
        self,
        data: dict[str, Any],
        model: Any,
        is_created: bool,
        request: Request,
    ) -> None:
        if not is_created and data.get("user_profile_id") in (None, ""):
            data.pop("user_profile_id", None)


class ScrapedJobAdmin(ModelView, model=ScrapedJob):
    name = "Job"
    name_plural = "Jobs"
    icon = "fa-solid fa-briefcase"
    can_create = False
    can_edit = False

    column_list = [
        ScrapedJob.job_id,
        ScrapedJob.job_title,
        ScrapedJob.seed_location,
        ScrapedJob.keyword,
        ScrapedJob.posted_date,
        ScrapedJob.scraped_at,
    ]
    column_details_list = [
        ScrapedJob.id,
        ScrapedJob.company_id,
        ScrapedJob.job_id,
        ScrapedJob.job_title,
        ScrapedJob.company_linkedin_url,
        ScrapedJob.posted_date,
        ScrapedJob.job_description,
        ScrapedJob.linkedin_url,
        ScrapedJob.seed_location,
        ScrapedJob.keyword,
        ScrapedJob.scraped_at,
    ]
    column_searchable_list = [
        ScrapedJob.job_id,
        ScrapedJob.job_title,
        ScrapedJob.company_linkedin_url,
        ScrapedJob.linkedin_url,
        ScrapedJob.keyword,
    ]
    column_sortable_list = [ScrapedJob.scraped_at, ScrapedJob.job_id]
    column_default_sort = [(ScrapedJob.scraped_at, True)]


class ScrapedCompanyAdmin(ModelView, model=ScrapedCompany):
    name = "Company"
    name_plural = "Companies"
    icon = "fa-solid fa-building"
    can_create = False
    can_edit = True
    # Only allow toggling blacklist from admin; other fields stay scrape-sourced.
    form_columns = [ScrapedCompany.blacklisted]

    column_list = [
        ScrapedCompany.company_name,
        ScrapedCompany.blacklisted,
        ScrapedCompany.industry,
        ScrapedCompany.company_size,
        ScrapedCompany.scraped_at,
    ]
    column_details_list = [
        ScrapedCompany.id,
        ScrapedCompany.company_name,
        ScrapedCompany.linkedin_url,
        ScrapedCompany.blacklisted,
        ScrapedCompany.industry,
        ScrapedCompany.company_size,
        ScrapedCompany.website,
        ScrapedCompany.phone,
        ScrapedCompany.about_us,
        ScrapedCompany.scraped_at,
    ]
    column_searchable_list = [
        ScrapedCompany.company_name,
        ScrapedCompany.linkedin_url,
        ScrapedCompany.industry,
    ]
    column_sortable_list = [
        ScrapedCompany.scraped_at,
        ScrapedCompany.company_name,
        ScrapedCompany.blacklisted,
    ]
    column_default_sort = [(ScrapedCompany.scraped_at, True)]
