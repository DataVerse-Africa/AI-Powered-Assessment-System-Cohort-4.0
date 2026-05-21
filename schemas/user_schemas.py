# schemas/user_schemas.py
# ══════════════════════════════════════════════════════════════════════
#  Pydantic Schemas — User Panel Request & Response Models
#
#  Schemas in this file:
#    UpdateProfileRequest — body for PUT /api/user/profile
#    UserProfileResponse  — response for GET /api/user/profile
# ══════════════════════════════════════════════════════════════════════

from pydantic import BaseModel, EmailStr, Field
from typing import Optional


# ══════════════════════════════════════════════════════════════════════
#  UPDATE PROFILE REQUEST
#  Used by: PUT /api/user/profile
#  Allows a clinician to update their full name and/or password.
#  All fields are optional — only fields provided are updated.
#  If new_password is provided, current_password must also be provided.
# ══════════════════════════════════════════════════════════════════════

class UpdateProfileRequest(BaseModel):

    full_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100,
        description='Updated full name — leave blank to keep existing name'
    )

    current_password: Optional[str] = Field(
        None,
        description='Current password — required only when changing password'
        # We require the current password before allowing a password change.
        # This prevents someone who finds an unlocked screen from
        # changing the password and locking out the real user.
    )

    new_password: Optional[str] = Field(
        None,
        min_length=6,
        description='New password — must also provide current_password'
    )


# ══════════════════════════════════════════════════════════════════════
#  USER PROFILE RESPONSE
#  Returned by: GET /api/user/profile
#  Safe fields only — hashed_password is never included.
# ══════════════════════════════════════════════════════════════════════

class UserProfileResponse(BaseModel):

    id: int
    full_name: str
    email: str
    role: str
    # Always 'clinician' for users registered through /api/auth/register

    is_active: bool
    # True = account is active, False = account is suspended

    created_at: str
    # ISO timestamp of when the account was created

    last_login: Optional[str] = None
    # ISO timestamp of the most recent successful login
    # None if the user has never logged in (brand new account)
