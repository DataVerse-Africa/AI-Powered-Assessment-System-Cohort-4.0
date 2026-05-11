# auth/security.py
# ══════════════════════════════════════════════════════════════════════
#  Security Utilities — Password Hashing and JWT Token Management
#
#  This file is the security engine of the entire system.
#  It is imported by the router (to hash passwords and create tokens)
#  and by dependencies.py (to decode and verify tokens).
#
#  Functions:
#    hash_password(plain)              → hashed string (bcrypt)
#    verify_password(plain, hashed)    → True or False
#    create_token(data)                → signed JWT for clinical staff
#    decode_token(token)               → payload dict or None
#    create_admin_token(data)          → signed JWT for admin
#    decode_admin_token(token)         → payload dict or None
# ══════════════════════════════════════════════════════════════════════

from datetime import datetime, timedelta
# datetime.utcnow() — current UTC time, used when setting token expiry
# timedelta        — represents a duration e.g. timedelta(minutes=60)
#                    used to calculate when the token expires

from jose import JWTError, jwt
# jose is the library that handles JWT encoding and decoding
# jwt.encode() — creates a signed JWT string from a payload dict
# jwt.decode() — verifies a JWT string and returns the payload dict
# JWTError     — the exception raised when a token is invalid or expired

from passlib.context import CryptContext
# passlib is the library that handles password hashing
# CryptContext lets us define which hashing algorithm to use (bcrypt)
# and provides the hash() and verify() methods

import os
from dotenv import load_dotenv

load_dotenv()
# Loads all key=value pairs from .env into os.environ
# Must be called before any os.getenv() calls below


# ── Hashing Configuration ─────────────────────────────────────────────

pwd_context = CryptContext(
    schemes=['bcrypt'],   # use bcrypt as our hashing algorithm
                          # bcrypt is the industry standard for password hashing
                          # it is slow by design — makes brute-force attacks expensive
    deprecated='auto'     # automatically handle older hash formats if we ever
                          # switch algorithms in the future
)


# ── JWT Configuration ─────────────────────────────────────────────────

SECRET_KEY = os.getenv('SECRET_KEY')
# The secret key used to SIGN staff JWT tokens.
# If someone has this key they can forge tokens — keep it secret.
# Read from .env — never hardcode it in the source code.

ADMIN_SECRET_KEY = os.getenv('ADMIN_SECRET_KEY')
# A SEPARATE secret key used to sign admin JWT tokens.
# Keeping admin tokens on a different secret means:
#   - a leaked staff token cannot be used to access admin endpoints
#   - the two token types are completely isolated from each other

ALGORITHM_KEY = os.getenv('ALGORITHM_KEY')
# HS256 = HMAC with SHA-256
# This is the signing algorithm — it uses our SECRET_KEY to create
# a unique signature on each token. The signature is verified on
# every protected request to confirm the token was not tampered with.

TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 60))
# How long a token stays valid after it is issued.
# Read from .env — defaults to 60 minutes if not set.
# After expiry the user must log in again to get a new token.


# ══════════════════════════════════════════════════════════════════════
#  PASSWORD FUNCTIONS
# ══════════════════════════════════════════════════════════════════════

def hash_password(plain: str) -> str:
    # Takes a plain text password string.
    # Returns a bcrypt hash string — 60 characters long.
    # This hash is what we save to the database.
    #
    # Example:
    #   hash_password('mypassword123')
    #   → '$2b$12$XkP9bF3yMn7cK2eRwHtJuOzDvAsTqLiNpWmYsVkRj1CeHgBxFdOu'
    #
    # The hash is different every time even for the same input
    # because bcrypt adds a random 'salt' before hashing.
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    # Takes the plain text password the user just typed at login,
    # and the hashed password we stored in the database.
    # Returns True if they match, False if they do not.
    #
    # bcrypt re-hashes the plain password using the salt embedded
    # in the stored hash and compares the results.
    # We never reverse the hash — we only compare hashes.
    #
    # Example:
    #   verify_password('mypassword123', '$2b$12$Xk...')  → True
    #   verify_password('wrongpassword', '$2b$12$Xk...')  → False
    return pwd_context.verify(plain, hashed)


# ══════════════════════════════════════════════════════════════════════
#  STAFF JWT FUNCTIONS
#  Used for clinical staff login tokens.
# ══════════════════════════════════════════════════════════════════════

def create_token(data: dict) -> str:
    # Takes a payload dict — typically {'sub': email, 'role': 'clinician'}
    # Adds an expiry time to the payload.
    # Signs the payload with SECRET_KEY using the HS256 algorithm.
    # Returns the signed JWT as a string.
    #
    # The 'sub' (subject) field is the standard JWT field for
    # identifying who the token belongs to — we use the email.

    payload = data.copy()
    # Copy the data dict so we do not mutate the original

    payload['exp'] = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    # 'exp' is the standard JWT expiry claim.
    # After this time the token is invalid and the user must log in again.
    # Example: if TOKEN_EXPIRE_MINUTES=60 and it is now 14:00,
    # the token expires at 15:00.

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM_KEY)
    # jwt.encode() creates the final JWT string.
    # Format: header.payload.signature  (three base64 parts separated by dots)
    # Only someone with SECRET_KEY can create a valid signature.


def decode_token(token: str) -> dict | None:
    # Takes a JWT string received from the client's Authorization header.
    # Verifies the signature using SECRET_KEY.
    # Checks the token has not expired.
    # Returns the payload dict if valid, None if invalid or expired.
    #
    # We return None instead of raising an exception so the caller
    # (dependencies.py) can decide how to handle an invalid token.
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM_KEY])
        # jwt.decode() does three things automatically:
        #   1. Verifies the signature (was this token signed by us?)
        #   2. Checks the 'exp' claim (has the token expired?)
        #   3. Returns the payload dict if both checks pass
    except JWTError:
        # JWTError is raised for any problem:
        #   - invalid signature (token was tampered with)
        #   - token expired
        #   - malformed token string
        return None


# ══════════════════════════════════════════════════════════════════════
#  ADMIN JWT FUNCTIONS
#  Used for admin login tokens — completely separate from staff tokens.
#  Admin tokens are signed with ADMIN_SECRET_KEY, not SECRET_KEY.
#  This means a staff token cannot be used on admin endpoints,
#  even if someone tries.
# ══════════════════════════════════════════════════════════════════════

def create_admin_token(data: dict) -> str:
    # Same logic as create_token() but uses ADMIN_SECRET_KEY.
    payload = data.copy()
    payload['exp'] = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, ADMIN_SECRET_KEY, algorithm=ALGORITHM_KEY)


def decode_admin_token(token: str) -> dict | None:
    # Same logic as decode_token() but verifies against ADMIN_SECRET_KEY.
    # A staff token passed here will FAIL verification because it was
    # signed with SECRET_KEY, not ADMIN_SECRET_KEY.
    try:
        return jwt.decode(token, ADMIN_SECRET_KEY, algorithms=[ALGORITHM_KEY])
    except JWTError:
        return None
    
    
# ══════════════════════════════════════════════════════════════════════
#  TOKEN UTILITY — ADDED for logout support
# ══════════════════════════════════════════════════════════════════════
 
def get_token_expiry(token: str, is_admin: bool = False):
    # Decodes a token and returns its expiry datetime object.
    # Used when saving a token to the blacklist — we store the expiry
    # so we know when it is safe to clean up old blacklist entries.
    #
    # is_admin=True  → decode with ADMIN_SECRET_KEY
    # is_admin=False → decode with SECRET_KEY
    #
    # Returns a datetime object or None if the token cannot be decoded.
    import datetime as dt
    try:
        if is_admin:
            payload = decode_admin_token(token)
        else:
            payload = decode_token(token)
 
        if not payload or 'exp' not in payload:
            return None
 
        # payload['exp'] is a Unix timestamp (integer seconds since epoch)
        # We convert it to a datetime object for storage in the database
        return dt.datetime.utcfromtimestamp(payload['exp'])
    except Exception:
        return None
    
    