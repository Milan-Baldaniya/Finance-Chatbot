"""
User profile persistence and prompt-summary helpers.
"""

from datetime import date
from typing import Any, Dict

from app.core.db import get_db
from app.schemas.profile import UserProfilePayload


def calculate_age_band(date_of_birth: date) -> str:
    today = date.today()
    age = today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )

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
        ("Primary goal", "primary_insurance_goal"),
        ("Vehicle status", "vehicle_status"),
    ]

    for label, key in fields:
        value = profile.get(key)
        if value:
            parts.append(f"{label}: {value}")

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
