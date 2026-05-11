# routers/sessions.py
# ══════════════════════════════════════════════════════════════════════
#  Clinical Session Routes
#
#  POST   /api/sessions/          — open a new session (before any prediction)
#  GET    /api/sessions/mine      — list all my sessions
#  GET    /api/sessions/{id}      — get one session + all its predictions
#  PATCH  /api/sessions/{id}/close — mark session closed (record kept)
#  DELETE /api/sessions/{id}      — permanently delete session + predictions
#
#  ⚠️  DO NOT EDIT YET — we will build this together in Step 3
# ══════════════════════════════════════════════════════════════════════

#from fastapi import APIRouter, Depends, HTTPException, Request
#from sqlalchemy.orm import Session as DBSession
#from database.session import get_db

# TODO: Step 3 — we will implement all session endpoints here

#  All endpoints require a valid staff JWT token.
#  A clinician can only see and manage their OWN sessions —
#  they cannot access another clinician's sessions.
#  The admin can see ALL sessions — that is handled in admin_panel.py
# ══════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, status, Request
# APIRouter     — groups all session routes under the /api/sessions prefix
# Depends       — declares dependencies (db session, current user)
# HTTPException — raises HTTP error responses
# status        — named HTTP status code constants
# Request       — raw HTTP request — used to read client IP for audit log

from sqlalchemy.orm import Session as DBSession
# DBSession is the SQLAlchemy database session type.
# We alias it as DBSession to avoid confusion with the clinical
# 'session' concept we use throughout this file.

from database.session import get_db
# Provides a fresh database session per request

from database.models import ClinicalSession, AuditLog, User, Prediction
# ClinicalSession — the sessions table model
# AuditLog        — we write a log entry for every significant action
# User            — the type returned by get_current_user
# Prediction      — needed to count predictions per session

from auth.dependencies import get_current_user
# get_current_user — the staff guard from Step 2
# Validates the JWT token and returns the authenticated User object
# If the token is missing, invalid, expired, or blacklisted → 401

from schemas.session_schemas import (
    SessionCreateRequest,   # body for POST /api/sessions/
    SessionUpdateRequest,   # body for PATCH /api/sessions/{id}/close
    SessionResponse,        # response for POST /api/sessions/
    SessionDetailResponse,  # response for GET /api/sessions/{id}
    PredictionSummary,       # used inside SessionDetailResponse
    SessionDeleteResponse    # the response gotten after a delete is made
)

from datetime import datetime
import json
# datetime — used to set closed_at timestamp when closing a session
# json     — used to serialise audit log detail dict to a JSON string


# ── Router Setup ──────────────────────────────────────────────────────

router = APIRouter(
    prefix='/api/sessions',
    # Every route in this file starts with /api/sessions
    # So @router.post('/') becomes POST /api/sessions/
    # And @router.get('/mine') becomes GET /api/sessions/mine

    tags=['Clinical Sessions']
    # Groups all endpoints under 'Clinical Sessions' in the /docs UI
)


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 1 — CREATE SESSION
#  POST /api/sessions/
#
#  Opens a new clinical session for a patient consultation.
#  This MUST be called before any prediction endpoint.
#  The session_id returned here is required by all prediction endpoints.
#
#  On success: returns session_id, patient_name, status, created_at
# ══════════════════════════════════════════════════════════════════════

@router.post(
    '/',
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED
    # 201 Created — a new session resource was created in the database
)
def create_session(
    request: SessionCreateRequest,
    # FastAPI validates the request body against SessionCreateRequest.
    # patient_name is required. All other fields are optional.

    db: DBSession = Depends(get_db),
    # Injects a fresh database session for this request

    current_user: User = Depends(get_current_user),
    # get_current_user runs first — validates the JWT token.
    # If the token is invalid or missing, this raises 401 and the
    # endpoint function never runs.
    # If valid, current_user is the authenticated clinician's User object.

    req: Request = None
    # Raw HTTP request — used to read the client IP address
):
    # ── Step 1: Create the session record ─────────────────────────────
    new_session = ClinicalSession(
        user_id=current_user.id,
        # Links this session to the authenticated clinician.
        # current_user.id comes from the JWT token via get_current_user.

        patient_name=request.patient_name,
        patient_age=request.patient_age,
        patient_gender=request.patient_gender,
        reason_for_visit=request.reason_for_visit,
        notes=request.notes,
        status='open'
        # Every new session starts as 'open'.
        # It becomes 'closed' when PATCH /{id}/close is called.
    )

    db.add(new_session)
    # Stages the new ClinicalSession object for insertion.
    # Nothing is written to the database yet.

    db.commit()
    # Executes the INSERT statement — the row now exists in the database.

    db.refresh(new_session)
    # Reloads the object from the database to populate:
    #   - new_session.id        (auto-generated primary key)
    #   - new_session.created_at (auto-generated timestamp)

    # ── Step 2: Write to audit log ────────────────────────────────────
    log = AuditLog(
        user_id=current_user.id,
        action='CREATE_SESSION',
        detail=json.dumps({
            'session_id': new_session.id,
            'patient': request.patient_name,
            'clinician': current_user.email
        }),
        ip_address=req.client.host if req else None
    )
    db.add(log)
    db.commit()

    # ── Step 3: Return the response ───────────────────────────────────
    return SessionResponse(
        session_id=new_session.id,
        patient_name=new_session.patient_name,
        status=new_session.status,
        created_at=new_session.created_at.isoformat(),
        # .isoformat() converts the datetime object to a readable string:
        # datetime(2026, 5, 1, 14, 30) → '2026-05-01T14:30:00'
        message='Session opened successfully'
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 2 — GET MY SESSIONS
#  GET /api/sessions/mine
#
#  Returns a summary list of ALL sessions created by the currently
#  authenticated clinician — across all their patients, all dates.
#
#  A clinician only sees their OWN sessions — not other clinicians'.
#  The admin sees all sessions — that is in admin_panel.py.
# ══════════════════════════════════════════════════════════════════════

@router.get('/mine')
def get_my_sessions(
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sessions = db.query(ClinicalSession).filter(
        ClinicalSession.user_id == current_user.id
        # WHERE user_id = current_user.id
        # This filter ensures clinicians only see their own sessions.
        # Even if a clinician manipulates the request, they cannot
        # access another clinician's sessions through this endpoint.
    ).order_by(
        ClinicalSession.created_at.desc()
        # Most recent session first — descending order by date
    ).all()
    # .all() returns a list of ClinicalSession objects

    # Build the response — a list of session summaries
    return {
        'total_sessions': len(sessions),
        # Total count of all sessions for this clinician

        'open_sessions': sum(1 for s in sessions if s.status == 'open'),
        # Count of sessions still open (consultation in progress)
        # sum(1 for s in sessions if s.status == 'open') is a generator
        # expression — it counts how many sessions have status='open'

        'closed_sessions': sum(1 for s in sessions if s.status == 'closed'),
        # Count of completed sessions

        'sessions': [
            {
                'session_id': s.id,
                'patient_name': s.patient_name,
                'patient_age': s.patient_age,
                'patient_gender': s.patient_gender,
                'reason_for_visit': s.reason_for_visit,
                'status': s.status,
                'total_predictions': len(s.predictions),
                # len(s.predictions) uses the relationship we defined
                # in models.py — no extra query needed
                'created_at': s.created_at.isoformat(),
                'closed_at': s.closed_at.isoformat() if s.closed_at else None
                # closed_at is None for open sessions
            }
            for s in sessions
            # Python list comprehension — builds a dict for each session
        ]
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 3 — GET ONE SESSION DETAIL
#  GET /api/sessions/{id}
#
#  Returns the full record of one specific session including every
#  prediction made during that consultation.
#  Used when a clinician reviews a past patient visit.
#
#  {id} is a path parameter — it becomes the session_id integer.
#  A clinician can only view their OWN sessions.
# ══════════════════════════════════════════════════════════════════════

@router.get('/{session_id}', response_model=SessionDetailResponse)
def get_session_detail(
    session_id: int,
    # FastAPI reads {session_id} from the URL path and passes it here.
    # Example: GET /api/sessions/7 → session_id = 7

    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ── Find the session ──────────────────────────────────────────────
    session = db.query(ClinicalSession).filter(
        ClinicalSession.id == session_id,
        # WHERE id = session_id (the ID from the URL)
        ClinicalSession.user_id == current_user.id
        # AND user_id = current_user.id
        # Both conditions must be true — this prevents a clinician
        # from accessing another clinician's session by guessing its ID.
    ).first()

    if not session:
        # Either the session does not exist, OR it belongs to a
        # different clinician. We return the same 404 error for both
        # cases — we do not reveal whether the session exists at all.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Session {session_id} not found'
        )

    # ── Build the predictions list ────────────────────────────────────
    predictions_list = [
        PredictionSummary(
            id=p.id,
            model_name=p.model_name,
            prediction_label=p.prediction_label,
            probability=p.probability,
            risk_level=p.risk_level,
            recommendation=p.recommendation,
            created_at=p.created_at.isoformat()
        )
        for p in session.predictions
        # session.predictions uses the SQLAlchemy relationship defined
        # in models.py — returns all Prediction rows linked to this session
    ]

    # ── Return the full session detail ────────────────────────────────
    return SessionDetailResponse(
        session_id=session.id,
        patient_name=session.patient_name,
        patient_age=session.patient_age,
        patient_gender=session.patient_gender,
        reason_for_visit=session.reason_for_visit,
        notes=session.notes,
        status=session.status,
        created_at=session.created_at.isoformat(),
        closed_at=session.closed_at.isoformat() if session.closed_at else None,
        total_predictions=len(predictions_list),
        predictions=predictions_list
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 4 — CLOSE SESSION
#  PATCH /api/sessions/{id}/close
#
#  Marks a session as closed when the consultation ends.
#  The record is PRESERVED — all predictions remain accessible.
#  This is the correct action at the end of every consultation.
#
#  CLOSE vs DELETE:
#    CLOSE  → status becomes 'closed', row stays in database forever
#    DELETE → row and all its predictions are permanently removed
#
#  Only open sessions can be closed — calling this on an already
#  closed session returns 400 Bad Request.
# ══════════════════════════════════════════════════════════════════════

@router.patch('/{session_id}/close')
def close_session(
    session_id: int,
    request: SessionUpdateRequest,
    # Optional — clinician can add final notes when closing.
    # If no body is sent, notes stays as whatever it was before.

    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    req: Request = None
):
    # ── Find the session ──────────────────────────────────────────────
    session = db.query(ClinicalSession).filter(
        ClinicalSession.id == session_id,
        ClinicalSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Session {session_id} not found'
        )

    # ── Check session is still open ───────────────────────────────────
    if session.status == 'closed':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Session is already closed'
            # Cannot close a session that is already closed.
            # The clinician should open a new session for a new visit.
        )

    # ── Close the session ─────────────────────────────────────────────
    session.status = 'closed'
    # SQLAlchemy tracks this change automatically.
    # It will be saved to the database on the next db.commit().

    session.closed_at = datetime.utcnow()
    # Records exactly when the consultation ended.
    # Used in session history and admin analytics.

    if request.notes:
        session.notes = request.notes
        # Only update notes if the clinician provided them.
        # If request.notes is None, the existing notes are preserved.

    # ── Write to audit log ────────────────────────────────────────────
    log = AuditLog(
        user_id=current_user.id,
        action='CLOSE_SESSION',
        detail=json.dumps({
            'session_id': session_id,
            'patient': session.patient_name,
            'total_predictions': len(session.predictions)
        }),
        ip_address=req.client.host if req else None
    )
    db.add(log)
    db.commit()
    # Saves both the session status update and the audit log in one commit

    return {
        'message': 'Session closed successfully',
        'session_id': session_id,
        'patient_name': session.patient_name,
        'status': session.status,
        'closed_at': session.closed_at.isoformat(),
        'total_predictions': len(session.predictions)
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 5 — DELETE SESSION
#  DELETE /api/sessions/{id}
#
#  PERMANENTLY removes a session and ALL its predictions from the database.
#  This action is IRREVERSIBLE — use only for sessions created by mistake.
#
#  ⚠️  The cascade='all, delete-orphan' we set on the
#  ClinicalSession.predictions relationship in models.py means SQLAlchemy
#  automatically deletes all linked Prediction rows when the session
#  row is deleted. No orphaned predictions are left behind.
#
#  Returns 204 No Content — no response body on successful deletion.
# ══════════════════════════════════════════════════════════════════════

@router.delete('/{session_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    req: Request = None
):
    # ── Find the session ──────────────────────────────────────────────
    session = db.query(ClinicalSession).filter(
        ClinicalSession.id == session_id,
        ClinicalSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Session {session_id} not found'
        )

    # ── Write to audit log BEFORE deleting ───────────────────────────
    # We must log this BEFORE db.delete(session) because after deletion
    # we can no longer read session.patient_name from the object.
    log = AuditLog(
        user_id=current_user.id,
        action='DELETE_SESSION',
        detail=json.dumps({
            'session_id': session_id,
            'patient': session.patient_name,
            'total_predictions_deleted': len(session.predictions)
        }),
        ip_address=req.client.host if req else None
    )
    db.add(log)

    # ── Delete the session ────────────────────────────────────────────
    db.delete(session)
    # db.delete(session) marks the session row for deletion.
    # Because of cascade='all, delete-orphan' on the predictions
    # relationship, all linked Prediction rows are also marked
    # for deletion automatically by SQLAlchemy.

    db.commit()
    # Executes the DELETE statements for the session AND all its
    # predictions in a single database transaction.
    # Also saves the audit log entry.

    # ── Return 204 No Content ─────────────────────────────────────────
    # 204 means success but there is no response body to return.
    # The resource has been deleted — there is nothing to send back.
    # FastAPI handles this automatically when status_code=204.
    return SessionDeleteResponse(
        msg=f'you just deleted a session called {session_id}'

    )