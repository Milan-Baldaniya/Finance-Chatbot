"""
User profile persistence and prompt-summary helpers.
"""

from datetime import date
from random import shuffle
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


def build_profile_suggestions(profile: Dict[str, Any] | None) -> List[str]:
    """
    Build fast profile-aware starter questions without waiting on an LLM call.
    These are dynamic questions derived from the user's saved profile signals.
    """
    generic_suggestions = [
        "What insurance cover should I prioritize right now?",
        "Which documents and disclosures matter before buying a policy?",
        "How should I compare term, health, and savings plans?",
        "Which waiting periods or exclusions should I check first?",
        "Which policy exclusions could create claim problems later?",
        "How should I compare premium, coverage, waiting periods, and exclusions?",
        "What should I ask an insurer before paying the first premium?",
        "How do I avoid common insurance mis-selling traps?",
        "Which claim rejection risks should I understand before buying?",
        "What policy features matter most beyond low premium?",
    ]

    if not profile:
        shuffle(generic_suggestions)
        return generic_suggestions[:4]

    profile_suggestions: List[str] = []
    goals = parse_primary_insurance_goals(profile.get("primary_insurance_goal"))
    age_band = str(profile.get("age_band") or "")
    dependents = profile.get("life_stage_dependents") or []
    residency = str(profile.get("residential_status") or "")
    occupation = str(profile.get("occupation_type") or "")
    income = str(profile.get("annual_income_band") or "")
    vehicle_status = profile.get("vehicle_status")

    for goal in goals[:3]:
        normalized_goal = goal.lower()
        profile_suggestions.extend(
            [
                f"What should I check before choosing {normalized_goal}?",
                f"How does my profile change the suitability of {normalized_goal}?",
                f"What risks should I compare before buying {normalized_goal}?",
            ]
        )

    if any(item in dependents for item in ["Married", "Kids", "Senior Parents"]):
        profile_suggestions.extend(
            [
                "How should I balance my cover with my family dependents?",
                "Should I prioritize term cover, family health, or both?",
                "How much protection should I consider for my dependents?",
            ]
        )

    if profile.get("is_smoker"):
        profile_suggestions.extend(
            [
                "How will smoker status affect my premium and underwriting?",
                "Which disclosures matter most for a smoker buying insurance?",
                "Can I reduce insurance costs despite smoker-rated premiums?",
            ]
        )

    if profile.get("has_preexisting_conditions"):
        profile_suggestions.extend(
            [
                "Which waiting periods apply to my pre-existing conditions?",
                "How should I compare health plans with my medical history?",
                "What medical disclosures should I prepare before applying?",
            ]
        )

    if "NRI" in residency:
        profile_suggestions.extend(
            [
                "Which insurance rules should an NRI check before buying?",
                "How do NRE or NRO payments affect insurance purchases?",
                "Which policy documents should an NRI verify before applying?",
            ]
        )

    if age_band in {"60-75", "75+"}:
        profile_suggestions.extend(
            [
                "Which senior health policy features should I compare first?",
                "How do waiting periods affect senior citizen health insurance?",
                "What sub-limits should I check in senior health plans?",
            ]
        )
    elif age_band in {"56-59"}:
        profile_suggestions.extend(
            [
                "What should I buy before senior citizen pricing starts?",
                "Should I lock health cover before premiums rise with age?",
                "Which insurance gaps should I close before turning sixty?",
            ]
        )

    if occupation == "Business Owner":
        profile_suggestions.extend(
            [
                "Do I need key-man, liability, or business health cover?",
                "How should a business owner structure insurance protection?",
                "Which personal and business risks should I insure separately?",
            ]
        )

    if "Above Rs 10 Lakh" in income:
        profile_suggestions.extend(
            [
                "How much term cover is suitable for my income profile?",
                "Should I consider higher cover or wealth-linked insurance plans?",
                "How do I balance tax saving with adequate insurance cover?",
            ]
        )

    if vehicle_status:
        profile_suggestions.extend(
            [
                "What motor cover should I choose for my vehicle status?",
                "Do I need own-damage cover or only third-party cover?",
                "Which motor exclusions could cause claim rejection later?",
            ]
        )

    unique: List[str] = []
    for suggestion in [*profile_suggestions, *generic_suggestions]:
        if suggestion not in unique:
            unique.append(suggestion)

    profile_unique = [suggestion for suggestion in unique if suggestion in profile_suggestions]
    generic_unique = [suggestion for suggestion in unique if suggestion not in profile_suggestions]

    shuffle(profile_unique)
    shuffle(generic_unique)

    selected = profile_unique[:3]
    selected.extend(generic_unique[: max(0, 4 - len(selected))])

    if len(selected) < 4:
        selected.extend(profile_unique[3 : 3 + (4 - len(selected))])

    shuffle(selected)
    return selected[:4]


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
