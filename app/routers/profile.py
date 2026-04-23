"""Profile-related API routes."""

import json
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ProfileInterest, ProfilePrerequisite, User, UserProfile, UserRoadmap, UserRoadmapStep
from app.profile_matching import persist_catalog_match_scores_for_user
from app.roadmap_ai import generate_personalized_roadmap
from app.schemas import (
    InterestsOut,
    InterestsReplaceIn,
    MajorDemandSkillsOut,
    OnboardingIn,
    RoadmapStepCompletionUpdateIn,
    RoadmapOut,
    SelectedPrerequisitesOut,
    SelectedPrerequisitesReplaceIn,
    SkillPrerequisitesOut,
    UserProfileOut,
)

router = APIRouter(tags=["profile"])
_DEMAND_BY_MAJOR_PATH = Path(__file__).resolve().parents[2] / "data" / "skills" / "demand_by_major.json"
_REASON_PER_SKILL_PATH = Path(__file__).resolve().parents[2] / "data" / "skills" / "reason_per_skill.json"
_PREREQ_BY_SKILL_PATH = Path(__file__).resolve().parents[2] / "data" / "skills" / "prereq_by_skill.json"


@lru_cache(maxsize=1)
def _load_demand_by_major() -> dict[str, list[str]]:
    with _DEMAND_BY_MAJOR_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return {str(k).strip().lower(): list(v) for k, v in raw.items()}


@lru_cache(maxsize=1)
def _load_reason_per_skill() -> dict[str, dict[str, str | None]]:
    with _REASON_PER_SKILL_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    out: dict[str, dict[str, str | None]] = {}
    for major, skills_map in raw.items():
        major_key = str(major).strip().lower()
        if not isinstance(skills_map, dict):
            out[major_key] = {}
            continue
        out[major_key] = {str(skill).strip(): (None if reason is None else str(reason)) for skill, reason in skills_map.items()}
    return out


@lru_cache(maxsize=1)
def _load_prereq_by_skill() -> dict[str, tuple[str, list[str]]]:
    with _PREREQ_BY_SKILL_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    out: dict[str, tuple[str, list[str]]] = {}
    if not isinstance(raw, list):
        return out
    for major_block in raw:
        if not isinstance(major_block, dict):
            continue
        for skill_map in major_block.values():
            if not isinstance(skill_map, dict):
                continue
            for skill, prereqs in skill_map.items():
                skill_name = str(skill).strip()
                if not skill_name:
                    continue
                if not isinstance(prereqs, list):
                    out[skill_name.lower()] = (skill_name, [])
                    continue
                out[skill_name.lower()] = (skill_name, [str(item).strip() for item in prereqs if str(item).strip()])
    return out


def _get_profile(db: Session, user: User) -> UserProfile | None:
    return db.scalar(select(UserProfile).where(UserProfile.user_id == user.id))


def _require_profile(db: Session, user: User) -> UserProfile:
    profile = _get_profile(db, user)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Complete onboarding first.",
        )
    return profile


def _best_effort_recompute_profile_match_scores(db: Session, user: User) -> None:
    """Compute scores automatically after onboarding/interests changes; never block request on failures."""
    try:
        persist_catalog_match_scores_for_user(db, user)
        print(f"[profile-match] trigger=profile_update success user_id={user.id}", flush=True)
    except Exception as exc:
        print(
            f"[profile-match] trigger=profile_update failed user_id={user.id} error={exc}",
            flush=True,
        )


def _roadmap_response_from_db(roadmap: UserRoadmap, db: Session) -> RoadmapOut:
    step_rows = list(
        db.scalars(
            select(UserRoadmapStep)
            .where(UserRoadmapStep.roadmap_id == roadmap.id)
            .order_by(UserRoadmapStep.step_order)
        ).all()
    )
    out_steps = [
        {
            "id": row.id,
            "main": row.main,
            "technicalComplement": row.technical_complement,
            "toolOrSoftSkill": row.tool_or_soft_skill,
            "completed": row.completed,
        }
        for row in step_rows
    ]
    return RoadmapOut(
        roadmap_id=roadmap.id,
        goal_skill=roadmap.goal_skill,
        steps_count=len(out_steps),
        all_completed=all(row["completed"] for row in out_steps) if out_steps else False,
        roadmap=out_steps,
    )


@router.get(
    "/profile",
    response_model=UserProfileOut,
)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileOut:
    """Return onboarding / academic profile for the current user."""
    return _require_profile(db, current_user)


@router.post(
    "/profile/onboarding",
    response_model=UserProfileOut,
)
def save_onboarding(
    payload: OnboardingIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserProfileOut:
    """Create/update a user's onboarding profile, and flip `users.onboarded=true`."""
    if current_user.onboarded:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already onboarded")

    profile = db.scalar(select(UserProfile).where(UserProfile.user_id == current_user.id))

    if profile is None:
        profile = UserProfile(
            user_id=current_user.id,
            university=payload.university,
            major=payload.major,
            year_of_study=payload.year_of_study,
            graduation_semester=payload.graduation_semester,
            graduation_year=payload.graduation_year,
            gpa_scale=payload.gpa_scale,
            gpa_value=payload.gpa_value,
        )
        db.add(profile)
    else:
        # User is not onboarded yet, so allow updating the existing row.
        profile.university = payload.university
        profile.major = payload.major
        profile.year_of_study = payload.year_of_study
        profile.graduation_semester = payload.graduation_semester
        profile.graduation_year = payload.graduation_year
        profile.gpa_scale = payload.gpa_scale
        profile.gpa_value = payload.gpa_value

    current_user.onboarded = True
    db.commit()
    db.refresh(profile)
    return profile


@router.get(
    "/profile/interests",
    response_model=InterestsOut,
)
def get_interests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterestsOut:
    """Return saved interests so the client can skip the picker if already set."""
    profile = _get_profile(db, current_user)
    if profile is None:
        return InterestsOut(interests=[], has_interests=False)

    rows = db.scalars(
        select(ProfileInterest.interest)
        .where(ProfileInterest.user_profile_id == profile.id)
        .order_by(ProfileInterest.interest)
    ).all()
    interests = list(rows)
    return InterestsOut(interests=interests, has_interests=bool(interests))


@router.get(
    "/profile/prerequisites",
    response_model=SelectedPrerequisitesOut,
)
def get_selected_prerequisites(
    skill: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SelectedPrerequisitesOut:
    """Return saved prerequisite selections for a given skill for this profile."""
    skill_name = (skill or "").strip()
    if not skill_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="skill query parameter is required")
    profile = _get_profile(db, current_user)
    if profile is None:
        return SelectedPrerequisitesOut(skill=skill_name, prerequisites=[], has_prerequisites=False)

    rows = db.scalars(
        select(ProfilePrerequisite.prerequisite)
        .where(ProfilePrerequisite.user_profile_id == profile.id)
        .where(ProfilePrerequisite.skill == skill_name)
        .order_by(ProfilePrerequisite.prerequisite)
    ).all()
    prerequisites = list(rows)
    return SelectedPrerequisitesOut(skill=skill_name, prerequisites=prerequisites, has_prerequisites=bool(prerequisites))


@router.put(
    "/profile/prerequisites",
    response_model=SelectedPrerequisitesOut,
)
def replace_selected_prerequisites(
    payload: SelectedPrerequisitesReplaceIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SelectedPrerequisitesOut:
    """Replace selected prerequisites for one skill on this profile (empty list clears that skill)."""
    profile = _require_profile(db, current_user)
    skill_name = payload.skill.strip()

    db.execute(
        delete(ProfilePrerequisite)
        .where(ProfilePrerequisite.user_profile_id == profile.id)
        .where(ProfilePrerequisite.skill == skill_name)
    )
    for label in payload.prerequisites:
        db.add(ProfilePrerequisite(user_profile_id=profile.id, skill=skill_name, prerequisite=label))
    db.commit()

    prerequisites = sorted(payload.prerequisites)
    return SelectedPrerequisitesOut(skill=skill_name, prerequisites=prerequisites, has_prerequisites=bool(prerequisites))


@router.put(
    "/profile/interests",
    response_model=InterestsOut,
)
def replace_interests(
    payload: InterestsReplaceIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InterestsOut:
    """Replace all interests for this profile (use an empty list to clear)."""
    profile = _require_profile(db, current_user)

    db.execute(delete(ProfileInterest).where(ProfileInterest.user_profile_id == profile.id))
    for label in payload.interests:
        db.add(ProfileInterest(user_profile_id=profile.id, interest=label))
    db.commit()
    _best_effort_recompute_profile_match_scores(db, current_user)

    interests = sorted(payload.interests)
    return InterestsOut(interests=interests, has_interests=bool(interests))


@router.get(
    "/profile/major-demand-skills",
    response_model=MajorDemandSkillsOut,
)
def get_major_demand_skills(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MajorDemandSkillsOut:
    """Return top 3 in-demand skills + reason + roadmap status for the logged-in user's major, or ``null`` when unavailable."""
    profile = _require_profile(db, current_user)
    major = profile.major.strip()
    demand_by_major = _load_demand_by_major()
    reason_per_skill = _load_reason_per_skill()
    skills = demand_by_major.get(major.lower())
    if not skills:
        return MajorDemandSkillsOut(major=major, skills=None)
    top_skills = skills[:3]
    roadmap_rows = list(
        db.scalars(
            select(UserRoadmap)
            .where(
                UserRoadmap.user_id == current_user.id,
                UserRoadmap.user_profile_id == profile.id,
                UserRoadmap.goal_skill.in_(top_skills),
            )
            .order_by(UserRoadmap.created_at.desc())
        ).all()
    )
    latest_roadmap_by_skill: dict[str, UserRoadmap] = {}
    for row in roadmap_rows:
        key = row.goal_skill.strip().lower()
        if key and key not in latest_roadmap_by_skill:
            latest_roadmap_by_skill[key] = row

    completed_by_skill: dict[str, bool] = {}
    roadmap_ids = [row.id for row in latest_roadmap_by_skill.values()]
    if roadmap_ids:
        step_rows = list(
            db.scalars(
                select(UserRoadmapStep)
                .where(UserRoadmapStep.roadmap_id.in_(roadmap_ids))
                .order_by(UserRoadmapStep.step_order)
            ).all()
        )
        step_groups: dict[UUID, list[UserRoadmapStep]] = {}
        for step in step_rows:
            step_groups.setdefault(step.roadmap_id, []).append(step)
        for skill_key, roadmap in latest_roadmap_by_skill.items():
            skill_steps = step_groups.get(roadmap.id, [])
            completed_by_skill[skill_key] = all(step.completed for step in skill_steps) if skill_steps else False

    reason_map = reason_per_skill.get(major.lower(), {})
    skills_with_reasons = [
        {
            "skill": skill,
            "reason": reason_map.get(skill),
            "roadmap_generated": skill.strip().lower() in latest_roadmap_by_skill,
            "completed": completed_by_skill.get(skill.strip().lower(), False),
        }
        for skill in top_skills
    ]
    return MajorDemandSkillsOut(major=major, skills=skills_with_reasons)


@router.get(
    "/profile/skill-prerequisites",
    response_model=SkillPrerequisitesOut,
)
def get_skill_prerequisites(
    skill: str,
    _: User = Depends(get_current_user),
) -> SkillPrerequisitesOut:
    """Return prerequisites for a given skill name from the static prerequisite map."""
    normalized = (skill or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="skill query parameter is required")
    prereq_by_skill = _load_prereq_by_skill()
    matched = prereq_by_skill.get(normalized.lower())
    if matched is None:
        return SkillPrerequisitesOut(skill=normalized, prerequisites=None)
    skill_name, prereqs = matched
    return SkillPrerequisitesOut(skill=skill_name, prerequisites=prereqs)


@router.post(
    "/profile/roadmap",
    response_model=RoadmapOut,
)
def generate_profile_roadmap(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapOut:
    """
    Generate a personalized roadmap with Ollama using profile + interests + selected prerequisites.
    Requires at least one saved prerequisite row: the goal skill is the most recently saved skill.
    Persists the roadmap and steps when none exists yet for this user, profile, and goal skill.
    """
    profile = _require_profile(db, current_user)
    goal_skill_row = db.execute(
        select(
            ProfilePrerequisite.skill,
            ProfilePrerequisite.created_at,
        )
        .where(ProfilePrerequisite.user_profile_id == profile.id)
        .order_by(ProfilePrerequisite.created_at.desc(), ProfilePrerequisite.skill.asc())
        .limit(1)
    ).first()
    if goal_skill_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No saved skill prerequisites found. Save prerequisites for a skill first.",
        )
    goal_skill = str(goal_skill_row[0]).strip()
    interests = db.scalars(
        select(ProfileInterest.interest)
        .where(ProfileInterest.user_profile_id == profile.id)
        .order_by(ProfileInterest.interest)
    ).all()
    checked_prerequisites = db.scalars(
        select(ProfilePrerequisite.prerequisite)
        .where(ProfilePrerequisite.user_profile_id == profile.id)
        .where(ProfilePrerequisite.skill == goal_skill)
        .order_by(ProfilePrerequisite.prerequisite)
    ).all()
    existing_roadmap = db.scalar(
        select(UserRoadmap)
        .where(
            UserRoadmap.user_id == current_user.id,
            UserRoadmap.user_profile_id == profile.id,
            UserRoadmap.goal_skill == goal_skill,
        )
        .order_by(UserRoadmap.created_at.desc())
        .limit(1)
    )
    if existing_roadmap is not None:
        return _roadmap_response_from_db(existing_roadmap, db)

    try:
        roadmap = generate_personalized_roadmap(
            major=profile.major,
            graduation_year=profile.graduation_year,
            interests=list(interests),
            goal_skill=goal_skill,
            checked_prerequisites=list(checked_prerequisites),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Roadmap generation failed: {exc}",
        ) from exc

    user_roadmap = UserRoadmap(
        user_id=current_user.id,
        user_profile_id=profile.id,
        goal_skill=goal_skill,
    )
    db.add(user_roadmap)
    db.flush()

    for idx, step in enumerate(roadmap, start=1):
        db.add(
            UserRoadmapStep(
                roadmap_id=user_roadmap.id,
                step_order=idx,
                main=step["main"],
                technical_complement=step["technicalComplement"],
                tool_or_soft_skill=step["toolOrSoftSkill"],
                completed=False,
            )
        )
    db.commit()
    db.refresh(user_roadmap)
    out = _roadmap_response_from_db(user_roadmap, db)

    return out


@router.put(
    "/profile/roadmaps/{roadmap_id}/steps/completion",
    response_model=RoadmapOut,
)
def update_roadmap_steps_completion(
    roadmap_id: UUID,
    payload: RoadmapStepCompletionUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapOut:
    roadmap = db.scalar(
        select(UserRoadmap).where(
            UserRoadmap.id == roadmap_id,
            UserRoadmap.user_id == current_user.id,
        )
    )
    if roadmap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")

    if payload.step_ids:
        target_steps = list(
            db.scalars(
                select(UserRoadmapStep).where(
                    UserRoadmapStep.roadmap_id == roadmap.id,
                    UserRoadmapStep.id.in_(payload.step_ids),
                )
            ).all()
        )
        if len(target_steps) != len(payload.step_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more step ids were not found in this roadmap",
            )
        for step in target_steps:
            step.completed = payload.completed
        db.commit()

    return _roadmap_response_from_db(roadmap, db)

