# routers/user_panel.py
# ══════════════════════════════════════════════════════════════════════
#  User Panel Routes
#
#  Four endpoints:
#    GET /api/user/profile      — view my account details
#    PUT /api/user/profile      — update my name or password
#    GET /api/user/sessions     — view all my sessions with summaries
#    GET /api/user/predictions  — view my full prediction history
#
#  All endpoints require a valid staff JWT token.
#  A clinician can only see and manage their OWN data.
#  They cannot access another clinician's profile, sessions,
#  or predictions through these endpoints.
# ══════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func

from database.session import get_db
from database.models import User, ClinicalSession, Prediction
from auth.dependencies import get_current_user
from auth.security import hash_password, verify_password
from schemas.user_schemas import UpdateProfileRequest, UserProfileResponse

# func   — SQLAlchemy aggregate functions e.g. func.count()
# hash_password    — from security.py — hashes new password before saving
# verify_password  — from security.py — checks current password before allowing change


router = APIRouter(
    prefix='/api/user',
    tags=['User Panel']
    # All routes in this file start with /api/user
    # Groups endpoints under 'User Panel' in the /docs UI
)


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 1 — GET MY PROFILE
#  GET /api/user/profile
#
#  Returns the authenticated clinician's account details.
#  hashed_password is never returned — filtered by UserProfileResponse.
# ══════════════════════════════════════════════════════════════════════

@router.get('/profile', response_model=UserProfileResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user)
    # get_current_user validates the JWT and returns the User object.
    # We do not even need a db session here — the User object already
    # has all the profile data we need from the JWT validation step.
):
    return UserProfileResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
        last_login=current_user.last_login.isoformat() if current_user.last_login else None
        # last_login is nullable — a brand new account has never logged in
        # .isoformat() converts datetime to string e.g. '2026-05-01T14:30:00'
        # We check 'if current_user.last_login' before calling .isoformat()
        # to avoid calling it on None which would raise an AttributeError
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 2 — UPDATE MY PROFILE
#  PUT /api/user/profile
#
#  Allows the clinician to update their full name and/or password.
#  All request fields are optional — only provided fields are updated.
#  To change password: both current_password and new_password required.
# ══════════════════════════════════════════════════════════════════════

@router.put('/profile')
def update_my_profile(
    request: UpdateProfileRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ── Update full name if provided ──────────────────────────────────
    if request.full_name:
        current_user.full_name = request.full_name
        # SQLAlchemy tracks this change automatically.
        # It will be written to the database on db.commit() below.

    # ── Update password if new_password provided ──────────────────────
    if request.new_password:

        # current_password is required when changing password
        if not request.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='current_password is required when setting a new password'
            )

        # Verify the current password before allowing the change
        if not verify_password(request.current_password, current_user.hashed_password):
            # verify_password() checks the plain text against the bcrypt hash.
            # If they do not match, we reject the request.
            # This prevents someone who finds an unlocked screen from
            # changing the password without knowing the original.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Current password is incorrect'
            )

        # Hash the new password before saving — never store plain text
        current_user.hashed_password = hash_password(request.new_password)

    # ── Check that at least one field was provided ────────────────────
    if not request.full_name and not request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No fields provided to update — send full_name or new_password'
        )

    # ── Save changes ──────────────────────────────────────────────────
    db.commit()
    # db.commit() writes all tracked changes (full_name, hashed_password)
    # to the database in a single transaction.

    return {
        'message': 'Profile updated successfully',
        'full_name': current_user.full_name,
        'email': current_user.email
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 3 — GET MY SESSIONS
#  GET /api/user/sessions
#
#  Returns a summary of all sessions created by the authenticated
#  clinician — across all their patients and all dates.
#  Includes totals, open/closed counts, and per-session prediction count.
#
#  Optional query parameters for filtering:
#    status — filter by 'open' or 'closed'
# ══════════════════════════════════════════════════════════════════════

@router.get('/sessions')
def get_my_sessions(
    status: str = None,
    # Optional filter — 'open' or 'closed'
    # If not provided, all sessions are returned
    # Example URL: GET /api/user/sessions?status=open

    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ── Build the query ───────────────────────────────────────────────
    query = db.query(ClinicalSession).filter(
        ClinicalSession.user_id == current_user.id
        # Always filter by the authenticated clinician's user_id
        # A clinician can only see their own sessions
    )

    # ── Apply optional status filter ──────────────────────────────────
    if status:
        if status not in ['open', 'closed']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='status filter must be "open" or "closed"'
            )
        query = query.filter(ClinicalSession.status == status)
        # Adds: AND status = 'open' (or 'closed') to the WHERE clause

    sessions = query.order_by(
        ClinicalSession.created_at.desc()
        # Most recent session first
    ).all()

    # ── Build the response ────────────────────────────────────────────
    return {
        'total_sessions': len(sessions),
        'open_sessions': sum(1 for s in sessions if s.status == 'open'),
        'closed_sessions': sum(1 for s in sessions if s.status == 'closed'),
        'sessions': [
            {
                'session_id': s.id,
                'patient_name': s.patient_name,
                'patient_age': s.patient_age,
                'patient_gender': s.patient_gender,
                'reason_for_visit': s.reason_for_visit,
                'status': s.status,
                'total_predictions': len(s.predictions),
                # Uses the SQLAlchemy relationship — no extra query needed
                'created_at': s.created_at.isoformat(),
                'closed_at': s.closed_at.isoformat() if s.closed_at else None
            }
            for s in sessions
        ]
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 4 — GET MY PREDICTIONS
#  GET /api/user/predictions
#
#  Returns the full prediction history for the authenticated clinician
#  across ALL their sessions and ALL model types.
#
#  Optional query parameters for filtering:
#    model_name — filter by 'diabetes', 'ckd', 'pneumonia', 'breast_cancer'
#    risk_level — filter by 'Low', 'Moderate', 'High', 'Critical'
# ══════════════════════════════════════════════════════════════════════

@router.get('/predictions')
def get_my_predictions(
    modelname: str = None,
    # Optional filter — 'diabetes' | 'ckd' | 'pneumonia' | 'breast_cancer'

    risk_level: str = None,
    # Optional filter — 'Low' | 'Moderate' | 'High' | 'Critical'

    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ── Build the query ───────────────────────────────────────────────
    query = db.query(Prediction).filter(
        Prediction.user_id == current_user.id
        # Always filter by the authenticated clinician
    )

    # ── Apply optional filters ────────────────────────────────────────
    if modelname:
        query = query.filter(Prediction.modelname == modelname)
        # Adds: AND modelname = 'diabetes' to the WHERE clause

    if risk_level:
        query = query.filter(Prediction.risk_level == risk_level)
        # Adds: AND risk_level = 'High' to the WHERE clause

    predictions = query.order_by(
        Prediction.created_at.desc()
        # Most recent prediction first
    ).all()

    # ── Build the response ────────────────────────────────────────────
    return {
        'total_predictions': len(predictions),

        # Summary counts by model type
        'by_model': {
            'diabetes':     sum(1 for p in predictions if p.modelname == 'diabetes'),
            'ckd':          sum(1 for p in predictions if p.modelname == 'ckd'),
            'pneumonia':    sum(1 for p in predictions if p.modelname == 'pneumonia'),
            'breast_cancer':sum(1 for p in predictions if p.modelname == 'breast_cancer'),
        },

        # Summary counts by risk level
        'by_risk_level': {
            'Low':      sum(1 for p in predictions if p.risk_level == 'Low'),
            'Moderate': sum(1 for p in predictions if p.risk_level == 'Moderate'),
            'High':     sum(1 for p in predictions if p.risk_level == 'High'),
            'Critical': sum(1 for p in predictions if p.risk_level == 'Critical'),
        },

        'predictions': [
            {
                'prediction_id': p.id,
                'session_id': p.session_id,
                # The frontend can use session_id to link back to the
                # full session detail via GET /api/sessions/{session_id}
                'patient_name': p.session.patient_name,
                # p.session uses the SQLAlchemy relationship to get
                # the ClinicalSession object — no extra query needed
                'modelname': p.modelname,
                'prediction_label': p.prediction_label,
                'probability': p.probability,
                'risk_level': p.risk_level,
                'recommendation': p.recommendation,
                'created_at': p.created_at.isoformat()
            }
            for p in predictions
        ]
    }
