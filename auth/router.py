# auth/router.py
# ══════════════════════════════════════════════════════════════════════
#  Authentication Routes
#
#  Three endpoints:
#    POST /api/auth/register     — create a new clinical staff account
#    POST /api/auth/login        — staff login, returns JWT
#    POST /api/auth/admin-login  — admin login using .env credentials,
#                                  returns a separate admin JWT
#    POST /api/auth/user-logout
#    POST /api/auth/admin-logout
# ══════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, status, Request
# APIRouter  — creates a group of related routes
#              all routes in this file will share the prefix /api/auth
# Depends    — declares a dependency (e.g. get the database session)
# HTTPException — raises HTTP error responses with a status code and detail
# status     — named HTTP status code constants e.g. status.HTTP_400_BAD_REQUEST
# Request    — gives us access to the raw HTTP request object
#              we use it to read the client's IP address for audit logging

from sqlalchemy.orm import Session
# Session is the type hint for the database session

from database.session import get_db
# get_db — the dependency that provides a database session per request

from database.models import User, AuditLog
# User     — the users table model, used to create and query accounts
# AuditLog — the audit_logs table model, used to record every auth event

from auth.security import (
    hash_password,        # converts plain password → bcrypt hash
    verify_password,      # checks plain password against stored hash
    create_token,         # creates a signed JWT for clinical staff
    create_admin_token,   # creates a signed JWT for the admin
)

from schemas.auth_schemas import (
    RegisterRequest,      # request body schema for /register
    LoginRequest,         # request body schema for /login
    AdminLoginRequest,    # request body schema for /admin-login
    TokenResponse,        # response schema for login endpoints
    UserResponse          # response schema for register endpoint
)

from datetime import datetime
# Used to update the last_login timestamp on the User record

import os
import json
# os   — reads ADMIN_EMAIL and ADMIN_PASSWORD from environment
# json — serialises the audit log detail dict into a JSON string

from dotenv import load_dotenv
load_dotenv()


# ── Router Setup ──────────────────────────────────────────────────────

router = APIRouter(
    prefix='/api/auth',
    # Every route in this file automatically starts with /api/auth
    # So @router.post('/register') becomes POST /api/auth/register

    tags=['Authentication']
    # Groups all these endpoints under 'Authentication' in the /docs UI
)


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 1 — REGISTER
#  POST /api/auth/register
#
#  Creates a new clinical staff account.
#  Role is always set to 'clinician' — the user cannot choose their role.
#  Password is hashed before storage — never saved as plain text.
# ══════════════════════════════════════════════════════════════════════

@router.post(
    '/register',
    response_model=UserResponse,
    # response_model=UserResponse tells FastAPI to validate and filter
    # the response through the UserResponse schema before sending.
    # This ensures we never accidentally return hashed_password
    # or any other sensitive field in the response.

    status_code=status.HTTP_201_CREATED
    # 201 Created is the correct HTTP status for a successful resource creation.
    # 200 OK would also work but 201 is more semantically correct.
)
def register(
    request: RegisterRequest,
    # FastAPI reads the JSON request body and validates it against
    # RegisterRequest. If full_name, email, or password is missing
    # or invalid, FastAPI returns 422 before this function runs.

    db: Session = Depends(get_db),
    # Injects a fresh database session for this request.

    req: Request = None
    # The raw HTTP request — used to read the client's IP address
    # for the audit log. Made optional (= None) so tests can call
    # this endpoint without providing a full request object.
):
    # ── Step 1: Check if email already exists ─────────────────────────
    existing_user = db.query(User).filter(User.email == request.email).first()
    # db.query(User)              → SELECT * FROM users
    # .filter(User.email == ...) → WHERE email = 'john@clinic.com'
    # .first()                   → LIMIT 1 — returns one row or None

    if existing_user:
        # The email is already registered — reject the request.
        # 400 Bad Request is appropriate here — the client sent data
        # that violates a business rule (unique email).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='An account with this email address already exists'
        )

    # ── Step 2: Create the new user ───────────────────────────────────
    new_user = User(
        full_name=request.full_name,
        email=request.email,
        role='clinician',
        # Role is hardcoded here — the client's request body has no role field.
        # Every account created through this endpoint is a clinician.
        # Admin access is handled through /admin-login, not registration.

        hashed_password=hash_password(request.password)
        # hash_password() converts the plain text password to a bcrypt hash.
        # The plain text password is discarded — only the hash is saved.
    )

    db.add(new_user)
    # Stages the new User object — tells SQLAlchemy to INSERT this row
    # on the next commit. Nothing is written to the database yet.

    db.commit()
    # Writes the INSERT statement to the database.
    # The new row now exists in the users table.

    db.refresh(new_user)
    # Reloads the new_user object from the database.
    # This populates the auto-generated fields like id and created_at
    # which were set by the database during the INSERT.

    # ── Step 3: Write to audit log ────────────────────────────────────
    log = AuditLog(
        user_id=new_user.id,
        action='REGISTER',
        detail=json.dumps({
            'email': new_user.email,
            'full_name': new_user.full_name
        }),
        ip_address=req.client.host if req else None
        # req.client.host reads the IP address from the request.
        # The 'if req else None' guard handles cases where req is None
        # (e.g. during automated testing).
    )
    db.add(log)
    db.commit()

    # ── Step 4: Return the response ───────────────────────────────────
    return UserResponse(
        id=new_user.id,
        full_name=new_user.full_name,
        email=new_user.email,
        role=new_user.role,
        message='Account created successfully'
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 2 — STAFF LOGIN
#  POST /api/auth/login
#
#  Authenticates a clinical staff member.
#  Verifies email and password against the users table.
#  Returns a signed JWT token on success.
# ══════════════════════════════════════════════════════════════════════

@router.post(
    '/login',
    response_model=TokenResponse
    # Returns access_token, token_type, and role on success
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
    req: Request = None
):
    # ── Step 1: Look up the user by email ─────────────────────────────
    user = db.query(User).filter(User.email == request.email).first()

    # ── Step 2: Verify password ───────────────────────────────────────
    if not user or not verify_password(request.password, user.hashed_password):
        # We check both conditions in one if statement intentionally.
        # If we returned 'email not found' vs 'wrong password' separately,
        # an attacker could use that information to enumerate valid emails.
        # By giving the same error for both cases, we reveal nothing.

        # Log the failed attempt before raising the error
        log = AuditLog(
            user_id=None,
            # user_id is None because we either could not find the user
            # or the password was wrong — we do not link to any account
            action='LOGIN_FAILED',
            detail=json.dumps({'email': request.email}),
            ip_address=req.client.host if req else None
        )
        db.add(log)
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect email or password',
            headers={'WWW-Authenticate': 'Bearer'}
        )

    # ── Step 3: Check account is active ──────────────────────────────
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Account is suspended — contact your administrator'
        )

    # ── Step 4: Update last login timestamp ──────────────────────────
    user.last_login = datetime.utcnow()
    # SQLAlchemy tracks that this field was changed.
    # The change is written to the database on the next commit.

    # ── Step 5: Write to audit log ────────────────────────────────────
    log = AuditLog(
        user_id=user.id,
        action='LOGIN',
        detail=json.dumps({'email': user.email}),
        ip_address=req.client.host if req else None
    )
    db.add(log)
    db.commit()
    # This single commit saves both the last_login update and the audit log.

    # ── Step 6: Create and return the JWT token ───────────────────────
    token = create_token({
        'sub': user.email,
        # 'sub' (subject) is the standard JWT claim for identifying the user.
        # We use email because it is unique and human-readable.

        'role': user.role
        # We embed the role in the token so the frontend can read it
        # without making another API call after login.
    })

    return TokenResponse(
        access_token=token,
        token_type='bearer',
        role=user.role
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 3 — ADMIN LOGIN
#  POST /api/auth/admin-login
#
#  Authenticates the admin using credentials from the .env file.
#  The admin is NOT in the database — no database query is made.
#  Returns a separate admin JWT signed with ADMIN_SECRET_KEY.
# ══════════════════════════════════════════════════════════════════════

@router.post(
    '/admin-login',
    response_model=TokenResponse
)
def admin_login(
    request: AdminLoginRequest,
    req: Request = None
    # No db dependency — the admin is not in the database
):
    # ── Step 1: Read admin credentials from .env ──────────────────────
    admin_email = os.getenv('ADMIN_EMAIL')
    admin_password = os.getenv('ADMIN_PASSWORD')
    # These are plain text values from .env — we compare directly.
    # Unlike staff passwords (which are hashed), the admin password
    # in .env is stored as plain text. This is acceptable because:
    #   - .env is never committed to git
    #   - the admin sets this value themselves
    #   - it is protected by server-level access controls

    # ── Step 2: Validate credentials ─────────────────────────────────
    if request.email != admin_email or request.password != admin_password:
        # Direct string comparison — no hashing needed here
        # because we are comparing against a .env value, not a DB hash.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid admin credentials',
            headers={'WWW-Authenticate': 'Bearer'}
        )

    # ── Step 3: Create and return admin JWT ───────────────────────────
    token = create_admin_token({
        'sub': admin_email,
        # 'sub' identifies who the token belongs to
        'role': 'admin'
        # 'role' is verified in require_admin() in dependencies.py
    })

    return TokenResponse(
        access_token=token,
        token_type='bearer',
        role='admin'
    )
    
    
# ── Additional import needed for logout ───────────────────────────────
from database.models import TokenBlacklist
from auth.security import get_token_expiry
from auth.dependencies import get_current_user, oauth2_scheme, admin_oauth2_scheme
from fastapi import Depends
 
 
# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 4 — STAFF LOGOUT
#  POST /api/auth/logout
#
#  ADDED for logout support.
#
#  Logs out the currently authenticated clinical staff member by
#  adding their token to the token_blacklist table.
#  After this call, the token is immediately invalid even if it
#  has not naturally expired yet.
#
#  Requires: valid staff JWT in Authorization header
# ══════════════════════════════════════════════════════════════════════
 
@router.post('/logout', status_code=status.HTTP_200_OK)
def logout(
    token: str = Depends(oauth2_scheme),
    # oauth2_scheme extracts the raw Bearer token string from the
    # Authorization header. We need the raw string to save to the
    # blacklist table — not just the payload inside it.
 
    current_user: User = Depends(get_current_user),
    # get_current_user validates the token and returns the User object.
    # If the token is already invalid or blacklisted, this raises 401
    # before we even reach the logout logic below.
 
    db: Session = Depends(get_db),
    req: Request = None
):
    # ── Step 1: Save the token to the blacklist ───────────────────────
    blacklisted = TokenBlacklist(
        token=token,
        # The raw JWT string — stored so we can check it on future requests
 
        token_type='staff',
        # Marks this as a staff token (vs admin token)
 
        user_id=current_user.id,
        # Links the blacklist entry to the staff member who logged out
        # Useful for admin panel: "when did this clinician last log out?"
 
        expires_at=get_token_expiry(token, is_admin=False)
        # Stores the token's natural expiry time.
        # Once this time has passed, the token would be rejected by JWT
        # verification anyway — so the blacklist entry can be safely
        # cleaned up after this date.
    )
    db.add(blacklisted)
 
    # ── Step 2: Write to audit log ────────────────────────────────────
    log = AuditLog(
        user_id=current_user.id,
        action='LOGOUT',
        detail=json.dumps({'email': current_user.email}),
        ip_address=req.client.host if req else None
    )
    db.add(log)
    db.commit()
 
    # ── Step 3: Return confirmation ───────────────────────────────────
    return {
        'message': 'Logged out successfully',
        'detail': 'Your token has been invalidated. Please log in again to continue.'
    }
 
 
# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 5 — ADMIN LOGOUT
#  POST /api/auth/admin-logout
#
#  ADDED for logout support.
#
#  Logs out the admin by adding their token to the token_blacklist.
#  The admin is not in the database, so user_id is stored as None.
#
#  Requires: valid admin JWT in Authorization header
# ══════════════════════════════════════════════════════════════════════
 
@router.post('/admin-logout', status_code=status.HTTP_200_OK)
def admin_logout(
    token: str = Depends(admin_oauth2_scheme),
    # Extracts the raw admin Bearer token from the Authorization header.
    # Uses admin_oauth2_scheme (tokenUrl='/api/auth/admin-login') so
    # the /docs UI uses the correct login URL for this endpoint.
 
    db: Session = Depends(get_db),
    req: Request = None
):
    # We import require_admin inline here to avoid circular import issues
    # Instead we decode the admin token directly to validate it
    from auth.security import decode_admin_token
    from auth.dependencies import is_token_blacklisted
 
    # ── Step 1: Validate the admin token ─────────────────────────────
    payload = decode_admin_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired admin token'
        )
 
    # ── Step 2: Check it is not already blacklisted ───────────────────
    if is_token_blacklisted(token, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token is already logged out'
        )
 
    # ── Step 3: Add to blacklist ──────────────────────────────────────
    blacklisted = TokenBlacklist(
        token=token,
        token_type='admin',
        # Marks this as an admin token
 
        user_id=None,
        # Admin is not in the users table — no user_id to link
 
        expires_at=get_token_expiry(token, is_admin=True)
        # Token's natural expiry — used for cleanup
    )
    db.add(blacklisted)
    db.commit()
 
    # ── Step 4: Return confirmation ───────────────────────────────────
    return {
        'message': 'Admin logged out successfully',
        'detail': 'Admin token has been invalidated. Please log in again to continue.'
    }
 
    