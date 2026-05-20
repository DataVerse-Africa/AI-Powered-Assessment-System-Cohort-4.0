# schemas/session_schemas.py
# ══════════════════════════════════════════════════════════════════════
#  Pydantic Schemas — Clinical Session Request Models
#
#  SessionCreateRequest — fields needed to open a new session
#  SessionUpdateRequest — fields for updating session notes
#
# 
# ══════════════════════════════════════════════════════════════════════

from pydantic import BaseModel
from typing import Optional

# TODO: Step 3 — we will define schemas here

# ══════════════════════════════════════════════════════════════════════
#  Pydantic Schemas — Clinical Session Request Models
#
#  Schemas in this file:
#    SessionCreateRequest  — body for POST /api/sessions/
#    SessionUpdateRequest  — body for PATCH /api/sessions/{id}/close
#    SessionResponse       — response after creating a session
#    PredictionSummary     — lightweight prediction inside a session detail
#    SessionDetailResponse — full session with all predictions inside
# ══════════════════════════════════════════════════════════════════════

from pydantic import BaseModel, Field
# BaseModel — every schema class inherits from this
# Field     — lets us add validation rules and descriptions to fields

from typing import Optional, List
# Optional[X] — the field can be X or None (not required)
# List[X]     — the field is a list of X items

from datetime import datetime
# datetime — used as the type hint for timestamp fields in responses


# ══════════════════════════════════════════════════════════════════════
#  SESSION CREATE REQUEST
#  Used by: POST /api/sessions/
#  Who sends this: a logged-in clinical staff member
#  What it does: opens a new consultation session for a patient
# ══════════════════════════════════════════════════════════════════════

class SessionCreateRequest(BaseModel):

    patient_name: str = Field(
        ...,               # required — cannot open a session without a patient name
        min_length=2,
        max_length=100,
        description='Full name of the patient being assessed'
    )

    patient_age: Optional[int] = Field(
        None,              # optional — defaults to None if not provided
        ge=0,              # ge = greater than or equal to — age cannot be negative
        le=150,            # le = less than or equal to — reasonable upper limit
        description='Age of the patient in years'
    )

    patient_gender: Optional[str] = Field(
        None,              # optional
        max_length=10,     # 'Male', 'Female', 'Other' all under 10 characters
        description='Gender of the patient — Male, Female, or Other'
    )

    reason_for_visit: Optional[str] = Field(
        None,              # optional — clinician may or may not add this
        description='Brief description of why the patient came in today'
        # Example: "Patient complains of increased thirst and frequent urination"
    )

    notes: Optional[str] = Field(
        None,              # optional — extra clinical notes
        description='Any additional notes about this consultation'
    )


# ══════════════════════════════════════════════════════════════════════
#  SESSION UPDATE REQUEST
#  Used by: PATCH /api/sessions/{id}/close
#  Allows the clinician to add or update notes when closing a session.
#  All fields are optional — clinician may close with no additional notes.
# ══════════════════════════════════════════════════════════════════════

class SessionUpdateRequest(BaseModel):

    notes: Optional[str] = Field(
        None,
        description='Final notes to add before closing the session'
    )


# ══════════════════════════════════════════════════════════════════════
#  SESSION RESPONSE
#  Returned by: POST /api/sessions/
#  The session_id in this response is what the clinician must include
#  in every prediction request made during this consultation.
# ══════════════════════════════════════════════════════════════════════

class SessionResponse(BaseModel):

    session_id: int
    # The auto-generated ID of the new session.
    # This is the most important field — the clinician copies this
    # and includes it in every subsequent prediction request.

    patient_name: str
    # Confirms which patient this session was opened for.

    status: str
    # Always 'open' when a session is first created.
    # Changes to 'closed' when PATCH /sessions/{id}/close is called.

    created_at: str
    # ISO format timestamp of when the session was opened.
    # Example: '2026-05-01T14:30:00'

    message: str
    # Confirmation message — 'Session opened successfully'


# ══════════════════════════════════════════════════════════════════════
#  PREDICTION SUMMARY
#  A lightweight prediction object used inside SessionDetailResponse.
#  Only the fields relevant for displaying session history are included.
# ══════════════════════════════════════════════════════════════════════

class PredictionSummary(BaseModel):

    id: int
    # Unique prediction ID

    modelname:str
    # Which ML model was used:
    # 'diabetes' | 'cardiovascular' | 'ckd' | 'kidney_image'

    prediction_label: Optional[str]
    # Human-readable result — 'Diabetic', 'High Risk', 'Normal' etc.

    probability: Optional[float]
    # Model confidence score — 0.0 to 1.0

    risk_level: Optional[str]
    # 'Low' | 'Moderate' | 'High' | 'Critical'

    recommendation: Optional[str]
    # Plain-language recommendation from the inference function

    created_at: str
    # When this prediction was made


# ══════════════════════════════════════════════════════════════════════
#  SESSION DETAIL RESPONSE
#  Returned by: GET /api/sessions/{id}
#  Returns the full session record including every prediction made
#  during that consultation — used for reviewing a past visit.
# ══════════════════════════════════════════════════════════════════════

class SessionDetailResponse(BaseModel):

    session_id: int
    patient_name: str
    patient_age: Optional[int]
    patient_gender: Optional[str]
    reason_for_visit: Optional[str]
    notes: Optional[str]
    status: str
    # 'open' or 'closed'

    created_at: str
    closed_at: Optional[str]
    # None if session is still open, ISO timestamp if closed

    total_predictions: int
    # Count of predictions made in this session

    predictions: List[PredictionSummary]
    # Full list of all predictions made during this consultation
    
class SessionDeleteResponse(BaseModel):
    msg: str
    # Session has been deleted