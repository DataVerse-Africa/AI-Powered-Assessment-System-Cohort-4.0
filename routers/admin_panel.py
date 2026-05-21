# routers/admin_panel.py
# ══════════════════════════════════════════════════════════════════════
#  Admin Panel Routes
#
#  Eight endpoints:
#    GET   /api/admin/users                  — all registered clinicians
#    GET   /api/admin/users/{id}             — one clinician full detail
#    PATCH /api/admin/users/{id}/suspend     — suspend a clinician account
#    PATCH /api/admin/users/{id}/activate    — reactivate a suspended account
#    GET   /api/admin/sessions               — all sessions across all clinicians
#    GET   /api/admin/predictions            — all predictions (full audit)
#    GET   /api/admin/analytics              — system-wide statistics
#    GET   /api/admin/export/{table}         — download any table as CSV
#
#  All endpoints require a valid ADMIN JWT token.
#  Admin credentials come from .env — not the database.
#  The admin can see everything. Clinicians cannot access any of these.
# ══════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
# StreamingResponse — used for CSV export
# The file is generated in memory and streamed to the client
# without saving a temp file to disk

from sqlalchemy.orm import Session as DBSession
from sqlalchemy import func, cast, Date
# func — SQLAlchemy aggregate functions e.g. func.count()
# cast — converts a column type e.g. DateTime → Date for grouping
# Date — the SQLAlchemy Date type used in cast()

from database.session import get_db
from database.models import User, ClinicalSession, Prediction, AuditLog

from auth.dependencies import require_admin
# require_admin — the admin guard from dependencies.py
# Validates the admin JWT token (signed with ADMIN_SECRET_KEY)
# Raises 401 if the token is invalid, expired, or blacklisted
# Raises 403 if a staff token is used on an admin endpoint

from datetime import datetime, timedelta
import csv
import io
import json
# csv — Python standard library for writing CSV files
# io  — in-memory string buffer — we write CSV to memory not disk
# json — parse audit log detail strings


router = APIRouter(
    prefix='/api/admin',
    tags=['Admin Panel']
)


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 1 — GET ALL CLINICIANS
#  GET /api/admin/users
#
#  Returns all registered clinician accounts with their session
#  and prediction counts. The admin uses this to see who is in
#  the system and how actively they are using it.
#
#  Optional query parameters:
#    is_active — filter by True or False
# ══════════════════════════════════════════════════════════════════════

@router.get('/users')
def get_all_users(
    is_active: bool = None,
    # Optional filter — True = active accounts, False = suspended
    # Example: GET /api/admin/users?is_active=false

    db: DBSession = Depends(get_db),
    admin_email: str = Depends(require_admin)
    # require_admin validates the admin JWT and returns the admin email.
    # If the token is missing, invalid, or a staff token → 401 or 403.
    # admin_email is available if we want to log who performed this action.
):
    query = db.query(User)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    users = query.order_by(User.created_at.desc()).all()

    return {
        'total_users': len(users),
        'active_users': sum(1 for u in users if u.is_active),
        'suspended_users': sum(1 for u in users if not u.is_active),
        'users': [
            {
                'id': u.id,
                'full_name': u.full_name,
                'email': u.email,
                'role': u.role,
                'is_active': u.is_active,
                'created_at': u.created_at.isoformat(),
                'last_login': u.last_login.isoformat() if u.last_login else None,
                'total_sessions': len(u.sessions),
                # Uses the SQLAlchemy relationship — no extra query needed
                'total_predictions': len(u.predictions),
            }
            for u in users
        ]
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 2 — GET ONE CLINICIAN DETAIL
#  GET /api/admin/users/{user_id}
#
#  Returns the full record of one clinician including all their
#  sessions and a summary of their prediction history.
#  Useful when investigating a specific clinician's activity.
# ══════════════════════════════════════════════════════════════════════

@router.get('/users/{user_id}')
def get_user_detail(
    user_id: int,
    db: DBSession = Depends(get_db),
    admin_email: str = Depends(require_admin)
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'User {user_id} not found'
        )

    return {
        'id': user.id,
        'full_name': user.full_name,
        'email': user.email,
        'role': user.role,
        'is_active': user.is_active,
        'created_at': user.created_at.isoformat(),
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'total_sessions': len(user.sessions),
        'total_predictions': len(user.predictions),
        'sessions': [
            {
                'session_id': s.id,
                'patient_name': s.patient_name,
                'status': s.status,
                'total_predictions': len(s.predictions),
                'created_at': s.created_at.isoformat(),
                'closed_at': s.closed_at.isoformat() if s.closed_at else None,
            }
            for s in sorted(user.sessions, key=lambda s: s.created_at, reverse=True)
            # sorted() orders sessions newest first
            # key=lambda s: s.created_at uses the created_at field for sorting
            # reverse=True gives descending order (newest first)
        ]
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 3 — SUSPEND A CLINICIAN
#  PATCH /api/admin/users/{user_id}/suspend
#
#  Sets is_active=False on a clinician account.
#  A suspended clinician cannot log in even with the correct password.
#  Their existing sessions and predictions are preserved.
# ══════════════════════════════════════════════════════════════════════

@router.patch('/users/{user_id}/suspend')
def suspend_user(
    user_id: int,
    db: DBSession = Depends(get_db),
    admin_email: str = Depends(require_admin)
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'User {user_id} not found'
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Account is already suspended'
        )

    user.is_active = False
    # SQLAlchemy tracks this change.
    # It will be committed to the database below.

    # Write to audit log
    log = AuditLog(
        user_id=None,
        # Admin is not in the users table — no user_id to link
        action='SUSPEND_USER',
        detail=json.dumps({
            'admin': admin_email,
            'suspended_user_id': user_id,
            'suspended_email': user.email
        }),
        ip_address=None
    )
    db.add(log)
    db.commit()

    return {
        'message': f'Account for {user.email} has been suspended',
        'user_id': user_id,
        'is_active': user.is_active
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 4 — ACTIVATE A CLINICIAN
#  PATCH /api/admin/users/{user_id}/activate
#
#  Sets is_active=True on a previously suspended account.
#  The clinician can log in again immediately after activation.
# ══════════════════════════════════════════════════════════════════════

@router.patch('/users/{user_id}/activate')
def activate_user(
    user_id: int,
    db: DBSession = Depends(get_db),
    admin_email: str = Depends(require_admin)
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'User {user_id} not found'
        )

    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Account is already active'
        )

    user.is_active = True

    log = AuditLog(
        user_id=None,
        action='ACTIVATE_USER',
        detail=json.dumps({
            'admin': admin_email,
            'activated_user_id': user_id,
            'activated_email': user.email
        }),
        ip_address=None
    )
    db.add(log)
    db.commit()

    return {
        'message': f'Account for {user.email} has been reactivated',
        'user_id': user_id,
        'is_active': user.is_active
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 5 — GET ALL SESSIONS
#  GET /api/admin/sessions
#
#  Returns all sessions across ALL clinicians — not filtered by user.
#  The admin sees everything. Useful for monitoring clinical workload
#  and identifying unusual patterns.
#
#  Optional filters:
#    user_id    — filter by specific clinician
#    status     — filter by 'open' or 'closed'
# ══════════════════════════════════════════════════════════════════════

@router.get('/sessions')
def get_all_sessions(
    user_id: int = None,
    # Filter by specific clinician — e.g. ?user_id=3
    status: str = None,
    # Filter by status — e.g. ?status=open
    db: DBSession = Depends(get_db),
    admin_email: str = Depends(require_admin)
):
    query = db.query(ClinicalSession)
    # No user_id filter here — admin sees ALL sessions by default

    if user_id:
        query = query.filter(ClinicalSession.user_id == user_id)
    if status:
        query = query.filter(ClinicalSession.status == status)

    sessions = query.order_by(ClinicalSession.created_at.desc()).all()

    return {
        'total_sessions': len(sessions),
        'open_sessions': sum(1 for s in sessions if s.status == 'open'),
        'closed_sessions': sum(1 for s in sessions if s.status == 'closed'),
        'sessions': [
            {
                'session_id': s.id,
                'clinician_id': s.user_id,
                'clinician_name': s.user.full_name,
                # s.user uses the SQLAlchemy relationship to get the User
                'clinician_email': s.user.email,
                'patient_name': s.patient_name,
                'patient_age': s.patient_age,
                'status': s.status,
                'total_predictions': len(s.predictions),
                'created_at': s.created_at.isoformat(),
                'closed_at': s.closed_at.isoformat() if s.closed_at else None,
            }
            for s in sessions
        ]
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 6 — GET ALL PREDICTIONS
#  GET /api/admin/predictions
#
#  Returns every prediction ever made across all clinicians and sessions.
#  Full clinical audit trail. Filterable by model, risk level, or clinician.
#
#  Optional filters:
#    model_name — filter by model type
#    risk_level — filter by risk level
#    user_id    — filter by specific clinician
# ══════════════════════════════════════════════════════════════════════

@router.get('/predictions')
def get_all_predictions(
    modelname: str = None,
    risk_level: str = None,
    user_id: int = None,
    db: DBSession = Depends(get_db),
    admin_email: str = Depends(require_admin)
):
    query = db.query(Prediction)
    # No filter by default — admin sees ALL predictions

    if modelname:
        query = query.filter(Prediction.model_name == modelname)
    if risk_level:
        query = query.filter(Prediction.risk_level == risk_level)
    if user_id:
        query = query.filter(Prediction.user_id == user_id)

    predictions = query.order_by(Prediction.created_at.desc()).all()

    return {
        'total_predictions': len(predictions),
        'predictions': [
            {
                'prediction_id': p.id,
                'clinician_name': p.user.full_name,
                'clinician_email': p.user.email,
                'session_id': p.session_id,
                'patient_name': p.session.patient_name,
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


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 7 — ANALYTICS DASHBOARD
#  GET /api/admin/analytics
#
#  Returns system-wide statistics in one call.
#  Powers the admin dashboard — gives a complete picture of how the
#  system is being used across all clinicians and all models.
# ══════════════════════════════════════════════════════════════════════

@router.get('/analytics')
def get_analytics(
    db: DBSession = Depends(get_db),
    admin_email: str = Depends(require_admin)
):
    # ── User statistics ───────────────────────────────────────────────
    total_users = db.query(func.count(User.id)).scalar()
    # func.count(User.id) → SELECT COUNT(id) FROM users
    # .scalar() → returns the single integer result

    active_users = db.query(func.count(User.id)).filter(
        User.is_active == True
    ).scalar()

    # ── Session statistics ────────────────────────────────────────────
    total_sessions = db.query(func.count(ClinicalSession.id)).scalar()

    open_sessions = db.query(func.count(ClinicalSession.id)).filter(
        ClinicalSession.status == 'open'
    ).scalar()

    # ── Prediction statistics ─────────────────────────────────────────
    total_predictions = db.query(func.count(Prediction.id)).scalar()

    # Predictions grouped by model name
    modelcounts = db.query(
        Prediction.modelname,
        func.count(Prediction.id).label('count')
    ).group_by(Prediction.modelname).all()
    # GROUP BY modelname — returns one row per model with its count
    # .label('count') gives the count column a readable name

    # Predictions grouped by risk level
    risk_counts = db.query(
        Prediction.risk_level,
        func.count(Prediction.id).label('count')
    ).group_by(Prediction.risk_level).all()

    # ── Daily activity — last 30 days ─────────────────────────────────
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    # timedelta(days=30) creates a duration of 30 days
    # Subtracting from now() gives us the date 30 days ago

    daily_activity = db.query(
        cast(Prediction.created_at, Date).label('date'),
        # cast(Prediction.created_at, Date) strips the time component
        # e.g. '2026-05-01T14:30:00' → '2026-05-01'
        # This lets us group predictions by day
        func.count(Prediction.id).label('count')
    ).filter(
        Prediction.created_at >= thirty_days_ago
    ).group_by(
        cast(Prediction.created_at, Date)
    ).order_by('date').all()

    # ── Top 5 most active clinicians ──────────────────────────────────
    top_clinicians = db.query(
        User.full_name,
        User.email,
        func.count(Prediction.id).label('prediction_count')
    ).join(
        Prediction, User.id == Prediction.user_id
        # JOIN users ON users.id = predictions.user_id
    ).group_by(User.id).order_by(
        func.count(Prediction.id).desc()
        # ORDER BY prediction_count DESC — most active first
    ).limit(5).all()
    # .limit(5) → top 5 only

    # ── Audit log summary ─────────────────────────────────────────────
    recent_logins = db.query(func.count(AuditLog.id)).filter(
        AuditLog.action == 'LOGIN',
        AuditLog.created_at >= thirty_days_ago
    ).scalar()

    failed_logins = db.query(func.count(AuditLog.id)).filter(
        AuditLog.action == 'LOGIN_FAILED',
        AuditLog.created_at >= thirty_days_ago
    ).scalar()

    return {
        'summary': {
            'total_clinicians':   total_users,
            'active_clinicians':  active_users,
            'suspended_clinicians': total_users - active_users,
            'total_sessions':     total_sessions,
            'open_sessions':      open_sessions,
            'total_predictions':  total_predictions,
        },
        'model_usage': [
            {'model': m, 'count': c}
            for m, c in modelcounts
        ],
        'risk_distribution': [
            {'risk_level': r, 'count': c}
            for r, c in risk_counts
        ],
        'daily_activity_last_30_days': [
            {'date': str(d), 'predictions': c}
            for d, c in daily_activity
        ],
        'top_5_clinicians': [
            {'name': n, 'email': e, 'total_predictions': c}
            for n, e, c in top_clinicians
        ],
        'login_activity_last_30_days': {
            'successful_logins': recent_logins,
            'failed_logins':     failed_logins,
        }
    }


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 8 — CSV EXPORT
#  GET /api/admin/export/{table}
#
#  Downloads any database table as a CSV file.
#  Four tables available: users, sessions, predictions, audit_logs
#
#  FastAPI returns a StreamingResponse — the CSV is generated in memory
#  and streamed directly to the client without saving a temp file.
#  The browser automatically prompts the user to download the file.
# ══════════════════════════════════════════════════════════════════════

@router.get('/export/{table_name}')
def export_csv(
    table_name: str,
    # Path parameter — one of: users, sessions, predictions, audit_logs
    # Example: GET /api/admin/export/predictions

    db: DBSession = Depends(get_db),
    admin_email: str = Depends(require_admin)
):
    output = io.StringIO()
    # io.StringIO() creates an in-memory string buffer.
    # We write CSV content to this buffer instead of a file on disk.
    # This is more efficient and avoids temp file cleanup issues.

    writer = csv.writer(output)
    # csv.writer() takes the buffer and provides writerow() method
    # writerow(['col1', 'col2']) writes one CSV row with a newline

    # ── Users export ──────────────────────────────────────────────────
    if table_name == 'users':
        writer.writerow([
            'id', 'full_name', 'email', 'role',
            'is_active', 'created_at', 'last_login',
            'total_sessions', 'total_predictions'
        ])
        # First row is the header row — column names

        for u in db.query(User).order_by(User.created_at.desc()).all():
            writer.writerow([
                u.id, u.full_name, u.email, u.role,
                u.is_active, u.created_at, u.last_login,
                len(u.sessions), len(u.predictions)
            ])

    # ── Sessions export ───────────────────────────────────────────────
    elif table_name == 'sessions':
        writer.writerow([
            'session_id', 'clinician_id', 'clinician_email',
            'patient_name', 'patient_age', 'patient_gender',
            'reason_for_visit', 'status',
            'total_predictions', 'created_at', 'closed_at'
        ])
        for s in db.query(ClinicalSession).order_by(
            ClinicalSession.created_at.desc()
        ).all():
            writer.writerow([
                s.id, s.user_id, s.user.email,
                s.patient_name, s.patient_age, s.patient_gender,
                s.reason_for_visit, s.status,
                len(s.predictions), s.created_at, s.closed_at
            ])

    # ── Predictions export ────────────────────────────────────────────
    elif table_name == 'predictions':
        writer.writerow([
            'prediction_id', 'clinician_id', 'clinician_email',
            'session_id', 'patient_name', 'modelname',
            'prediction_label', 'probability',
            'risk_level', 'recommendation', 'created_at'
        ])
        for p in db.query(Prediction).order_by(
            Prediction.created_at.desc()
        ).all():
            writer.writerow([
                p.id, p.user_id, p.user.email,
                p.session_id, p.session.patient_name,
                p.modelname, p.prediction_label,
                p.probability, p.risk_level,
                p.recommendation, p.created_at
            ])

    # ── Audit logs export ─────────────────────────────────────────────
    elif table_name == 'audit_logs':
        writer.writerow([
            'id', 'user_id', 'user_email',
            'action', 'detail', 'ip_address', 'created_at'
        ])
        for l in db.query(AuditLog).order_by(
            AuditLog.created_at.desc()
        ).all():
            email = l.user.email if l.user else 'N/A'
            # l.user is None for failed login attempts (user_id is NULL)
            # We default to 'N/A' to avoid an AttributeError
            writer.writerow([
                l.id, l.user_id, email,
                l.action, l.detail,
                l.ip_address, l.created_at
            ])

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Unknown table: {table_name}. Choose from: users, sessions, predictions, audit_logs'
        )

    output.seek(0)
    # Rewind the buffer to the beginning before streaming.
    # After all the writerow() calls, the cursor is at the end.
    # We must move it back to position 0 before reading starts.

    filename = f'{table_name}_export_{datetime.utcnow().strftime("%Y%m%d_%H%M")}.csv'
    # Generates a timestamped filename e.g. 'predictions_export_20260501_1430.csv'
    # strftime formats the datetime: %Y=year, %m=month, %d=day, %H=hour, %M=minute

    return StreamingResponse(
        iter([output.getvalue()]),
        # iter([...]) wraps the string in an iterable — required by StreamingResponse
        # output.getvalue() reads the entire CSV string from the buffer
        media_type='text/csv',
        # Tells the browser this is a CSV file
        headers={
            'Content-Disposition': f'attachment; filename={filename}'
            # 'attachment' tells the browser to download the file
            # rather than displaying it in the browser window
        }
    )
