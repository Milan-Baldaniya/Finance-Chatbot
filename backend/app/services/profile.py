"""
User profile persistence and prompt-summary helpers.
"""

from datetime import date
from typing import Any, Dict, List

from app.core.db import get_db
from app.schemas.profile import UserProfilePayload


def calculate_age(date_of_birth: date) -> int:
    today = date.today()
    return today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )

def calculate_age_band(date_of_birth: date) -> str:
    age = calculate_age(date_of_birth)

    if age <= 17:
        return "0-17"
    if age <= 55:
        return "18-55"
    if age <= 59:
        return "56-59"
    if age <= 75:
        return "60-75"
    return "75+"


def build_profile_row(user_id: str, payload: UserProfilePayload) -> Dict[str, Any]:
    data = payload.model_dump(mode="json")
    data.update(
        {
            "user_id": user_id,
            "exact_age": calculate_age(payload.date_of_birth),
            "age_band": calculate_age_band(payload.date_of_birth),
            "onboarding_completed": True,
        }
    )
    return data


def upsert_profile(user_id: str, payload: UserProfilePayload) -> Dict[str, Any]:
    db = get_db()
    row = build_profile_row(user_id, payload)

    response = (
        db.table("user_profiles")
        .upsert(row, on_conflict="user_id")
        .execute()
    )

    if not response.data:
        return row
    return response.data[0]


def get_profile(user_id: str) -> Dict[str, Any] | None:
    db = get_db()
    response = (
        db.table("user_profiles")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None
    return response.data[0]


def parse_primary_insurance_goals(value: Any) -> List[str]:
    """
    Profiles currently store up to 3 selected goals as a comma-separated string.
    Keep this tolerant so older rows and future array-shaped values both work.
    """
    if not value:
        return []
    if isinstance(value, list):
        return [str(goal).strip() for goal in value if str(goal).strip()]
    return [goal.strip() for goal in str(value).split(",") if goal.strip()]


def get_profile_primary_goals(user_id: str) -> List[str]:
    profile = get_profile(user_id)
    if not profile:
        return []
    return parse_primary_insurance_goals(profile.get("primary_insurance_goal"))


def get_profile_summary(user_id: str) -> str:
    profile = get_profile(user_id)
    if not profile:
        return ""

    parts = []
    fields = [
        ("Age band", "age_band"),
        ("Gender", "gender"),
        ("Residency", "residential_status"),
        ("Annual income", "annual_income_band"),
        ("Occupation", "occupation_type"),
        ("Vehicle status", "vehicle_status"),
    ]

    for label, key in fields:
        value = profile.get(key)
        if value:
            parts.append(f"{label}: {value}")

    primary_goals = parse_primary_insurance_goals(profile.get("primary_insurance_goal"))
    if primary_goals:
        parts.append(f"Selected primary insurance goals ({len(primary_goals)}): {', '.join(primary_goals)}")

    exact_age = profile.get("exact_age")
    if exact_age:
        parts.append(f"Exact age: {exact_age}")

    if profile.get("is_smoker") is not None:
        parts.append(f"Tobacco/smoker: {'Yes' if profile['is_smoker'] else 'No'}")

    if profile.get("has_preexisting_conditions"):
        conditions = profile.get("preexisting_conditions") or []
        condition_text = ", ".join(conditions) if conditions else "Yes"
        parts.append(f"Pre-existing conditions: {condition_text}")

    dependents = profile.get("life_stage_dependents") or []
    if dependents:
        parts.append(f"Life stage/dependents: {', '.join(dependents)}")

    if profile.get("has_existing_long_term_tp_policy") is not None:
        value = "Yes" if profile["has_existing_long_term_tp_policy"] else "No"
        parts.append(f"Existing long-term third-party policy: {value}")

    return "User Profile: " + " | ".join(parts) if parts else ""
