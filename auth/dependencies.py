# auth/dependencies.py
# ══════════════════════════════════════════════════════════════════════
#  FastAPI Dependencies — Guard Functions for Protected Routes
#
#  What is a FastAPI dependency?
#  A dependency is a function that FastAPI calls AUTOMATICALLY before
#  the endpoint function runs. Think of it as a security guard at
#  the door. Every request must pass the guard before it gets in.
#
#  We declare a dependency in an endpoint like this:
#    def my_endpoint(user: User = Depends(get_current_user)):
#  FastAPI sees Depends(get_current_user), calls get_current_user(),
#  and passes the result as the 'user' argument to the endpoint.
#  If the guard raises an HTTPException, the endpoint never runs.
#
#  Guards in this file:
#    get_current_user  → validates staff JWT, checks blacklist, returns User object : returns the authenticated patient User object
#    require_admin     → validates admin JWT, checks blacklist, returns the admin email 
#
#  UPDATED for logout support:
#    Both guard functions now check the token_blacklist table.
#    If the token was logged out, the request is rejected with 401
#    even if the token has not naturally expired yet.
# ══════════════════════════════════════════════════════════════════════

from fastapi import Depends, HTTPException, status
# Depends        — declares a dependency in an endpoint signature
# HTTPException  — raises an HTTP error response e.g. 401 or 403
# status         — provides named HTTP status code constants
#                  e.g. status.HTTP_401_UNAUTHORIZED instead of 401
# Request        — gives access to the raw HTTP request
#                  ADDED: we now need the raw token string from the
#                  request to check against the blacklist table

from fastapi.security import OAuth2PasswordBearer
# OAuth2PasswordBearer tells FastAPI where to look for the token.
# It reads the Authorization header and extracts the Bearer token.
# It also makes the 'Authorize' button appear in the /docs UI.

from sqlalchemy.orm import Session
# Session is the type hint for the database session parameter

from database.session import get_db
# get_db is the database dependency from session.py
# We use it here to look up the user in the database

from database.models import User, TokenBlacklist
# The User model — we query this table to find the authenticated user
# TokenBlacklist — ADDED: we query this to check if the token was
#                  logged out before allowing the request through

from auth.security import decode_token, decode_admin_token
# decode_token       — verifies and decodes a staff JWT
# decode_admin_token — verifies and decodes an admin JWT




# ── OAuth2 Scheme ─────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl='/api/auth/login'
    # tokenUrl tells the /docs UI which endpoint to use for the
    # 'Authorize' button. When you click Authorize in /docs and
    # enter your credentials, it hits this URL to get a token.
    # This does NOT change how the actual login endpoint works —
    # it is only used by the /docs interface.
)

# oauth2_scheme is itself a dependency.
# When used in an endpoint, it automatically:
#   1. Reads the Authorization header from the request
#   2. Checks it starts with 'Bearer '
#   3. Extracts and returns the token string
#   4. Returns 401 if the header is missing entirely

# ══════════════════════════════════════════════════════════════════════
#  HELPER — is_token_blacklisted()
#
#  ADDED for logout support.
#  Checks whether a given token string exists in the token_blacklist
#  table. Called by both guard functions below before allowing access.
# ══════════════════════════════════════════════════════════════════════
 
def is_token_blacklisted(token: str, db: Session) -> bool:
    # Queries the token_blacklist table for this exact token string.
    # Returns True if found (token was logged out) → request should be blocked.
    # Returns False if not found (token is still valid) → request can proceed.
 
    blacklisted = db.query(TokenBlacklist).filter(
        TokenBlacklist.token == token
        # exact string match — we look for this specific token
    ).first()
 
    return blacklisted is not None
    # .first() returns the row if found, or None if not found
    # 'is not None' converts that to True/False



# ══════════════════════════════════════════════════════════════════════
#  STAFF GUARD — get_current_user
#
#  Used by all clinical staff endpoints.
#  Flow:
#    1. Extract Bearer token from Authorization header
#    2. Verify JWT signature and expiry
#    3. CHECK BLACKLIST — reject if token was logged out  ← ADDED
#    4. Look up user in database
#    5. Check account is active
#    6. Return the User object to the endpoint
# ══════════════════════════════════════════════════════════════════════
 
def get_current_user(
    token: str = Depends(oauth2_scheme),
    # FastAPI automatically extracts the Bearer token from the
    # Authorization header and passes it here as a plain string.
    # If no Authorization header is present → 401 before we run.
 
    db: Session = Depends(get_db)
    # Fresh database session for this request.
    # Used both for the blacklist check and the user lookup.
) -> User:
 
    # ── Step 1: Verify the JWT signature and expiry ───────────────────
    payload = decode_token(token)
    # Returns the payload dict if valid, None if invalid or expired.
    
 
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired token — please log in again',
            headers={'WWW-Authenticate': 'Bearer'}
        )
 
    # ── Step 2: Check the blacklist ───────────────────────────────────
    # ADDED for logout support.
    # Even if the token is mathematically valid and not yet expired,
    # we reject it if the user has explicitly logged out.
    if is_token_blacklisted(token, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token has been logged out — please log in again',
            headers={'WWW-Authenticate': 'Bearer'}
        )
 
    # ── Step 3: Extract the user identifier from the token ────────────
    email = payload.get('sub')
    # 'sub' (subject) is the JWT claim we set to the user's email
    # when the token was created in security.py
 
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token is missing user identifier'
        )
 
    # ── Step 4: Look up the user in the database ──────────────────────
    user = db.query(User).filter(User.email == email).first()
    # WHERE email = 'john@clinic.com' LIMIT 1
 
    if not user:
        # Email in token does not match any user — account may have
        # been deleted after the token was issued.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='User account not found'
        )
 
    # ── Step 5: Check the account is still active ─────────────────────
    if not user.is_active:
        # Account has been suspended by the admin.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Account is suspended — contact your administrator'
        )
 
    return user
    # The full User object is passed to the endpoint as its
    # 'user' or 'current_user' parameter.
 
# ══════════════════════════════════════════════════════════════════════
#  ADMIN GUARD — require_admin
#  Used by all admin panel endpoints.
#  The admin is NOT in the database — their token is verified
#  against ADMIN_SECRET_KEY from .env.
#  Returns the admin email string if the token is valid.
#  Raises 401 if the token is invalid or expired.
#  Raises 403 if a staff token is used on an admin endpoint.
# ══════════════════════════════════════════════════════════════════════

admin_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl='/api/auth/admin-login'
    # Separate OAuth2 scheme for the admin — points to the admin login URL.
    # This means the /docs 'Authorize' button for admin endpoints will
    # use /api/auth/admin-login instead of /api/auth/login.
)

def require_admin(
    token: str = Depends(admin_oauth2_scheme),
    db: Session = Depends(get_db)
    # ADDED: db session needed for the blacklist check
    # Previously require_admin had no db dependency because the admin
    # is not in the database. Now we need db to check the blacklist.
) -> str:
 
    # ── Step 1: Verify the admin JWT ──────────────────────────────────
    payload = decode_admin_token(token)
    # Verifies against ADMIN_SECRET_KEY.
    # A staff token will FAIL here — signed with a different secret.
 
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or expired admin token — please log in again',
            headers={'WWW-Authenticate': 'Bearer'}
        )
 
    # ── Step 2: Check the blacklist ───────────────────────────────────
    # ADDED for logout support.
    # Checks if this admin token was explicitly logged out.
    if is_token_blacklisted(token, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Admin token has been logged out — please log in again',
            headers={'WWW-Authenticate': 'Bearer'}
        )
 
    # ── Step 3: Verify the role claim ─────────────────────────────────
    role = payload.get('role')
 
    if role != 'admin':
        # Extra safety check — even a valid admin-scheme token must
        # carry the 'admin' role claim to access admin endpoints.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Admin access required'
        )
 
    return payload.get('sub')
    # Returns the admin email string.
    # Admin endpoints receive this as their 'admin_email' parameter.
