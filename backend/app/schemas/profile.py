"""
Schemas for authenticated user insurance profile data.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class UserProfilePayload(BaseModel):
    """Incoming profile payload from onboarding and profile edit forms."""

    date_of_birth: date
    gender: str = Field(..., min_length=1)
    residential_status: str = Field(..., min_length=1)
    annual_income_band: str = Field(..., min_length=1)
    occupation_type: str = Field(..., min_length=1)
    is_smoker: bool
    has_preexisting_conditions: bool
    preexisting_conditions: List[str] = Field(default_factory=list)
    primary_insurance_goal: str = Field(..., min_length=1)
    life_stage_dependents: List[str] = Field(default_factory=list)
    vehicle_status: Optional[str] = None
    has_existing_long_term_tp_policy: Optional[bool] = None

    @field_validator("preexisting_conditions", "life_stage_dependents", mode="before")
    @classmethod
    def normalize_list(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        return value


class UserProfileResponse(UserProfilePayload):
    user_id: str
    age_band: str
    onboarding_completed: bool = True
