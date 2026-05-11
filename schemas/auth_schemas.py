# schemas/auth_schemas.py
# ══════════════════════════════════════════════════════════════════════
#  Pydantic Schemas — Authentication Request & Response Models
#
#  What is Pydantic?
#  Pydantic is a data validation library. We define a class that
#  describes the shape of an incoming request body. FastAPI
#  automatically validates every incoming request against that class.
#  If a required field is missing or the wrong type, FastAPI returns
#  a 422 error before our code even runs.
#
#  Schemas in this file:
#    RegisterRequest   — body for POST /api/auth/register
#    LoginRequest      — body for POST /api/auth/login
#    AdminLoginRequest — body for POST /api/auth/admin-login
#    TokenResponse     — response body returned after a successful login
#    UserResponse      — response body returned after a successful register
# ══════════════════════════════════════════════════════════════════════

from pydantic import BaseModel, EmailStr, Field
# BaseModel  — every schema class inherits from this
#              it is what makes the class a Pydantic schema
# EmailStr   — a special string type that validates email format
#              e.g. 'notanemail' would be rejected automatically
# Field      — lets us add extra rules to a field
#              e.g. minimum length, maximum length, description

from typing import Optional
# Optional[X] means the field can be X or None (not required)


# ══════════════════════════════════════════════════════════════════════
#  REGISTER REQUEST
#  Used by: POST /api/auth/register
#  Who sends this: a new clinical staff member signing up
# ══════════════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):

    full_name: str = Field(
        ...,               # ... means this field is REQUIRED — cannot be omitted
        min_length=2,      # name must be at least 2 characters
        max_length=100,    # name cannot exceed 100 characters
        description='Full name of the clinical staff member'
    )

    email: EmailStr = Field(
        ...,               # required
        description='Email address — used as login username'
        # EmailStr automatically checks that the value looks like an email
        # e.g. 'john@clinic.com' passes, 'john' or 'john@' fails with 422
    )

    password: str = Field(
        ...,               # required
        min_length=6,      # password must be at least 6 characters
        description='Password — will be hashed before storage, never stored plain'
    )
    # ⚠️  We receive the plain text password here in the request body
    # but we NEVER save it to the database as plain text.
    # In the router, we immediately pass it through bcrypt before saving.


# ══════════════════════════════════════════════════════════════════════
#  LOGIN REQUEST
#  Used by: POST /api/auth/login
#  Who sends this: a clinical staff member logging in
# ══════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):

    email: EmailStr = Field(
        ...,
        description='Registered email address'
    )

    password: str = Field(
        ...,
        description='Account password'
    )


# ══════════════════════════════════════════════════════════════════════
#  ADMIN LOGIN REQUEST
#  Used by: POST /api/auth/admin-login
#  Who sends this: the admin logging into the admin panel
#
#  Note: the admin is NOT in the database.
#  Their credentials live in the .env file (ADMIN_EMAIL, ADMIN_PASSWORD).
#  This schema looks identical to LoginRequest but it is kept separate
#  for clarity — the two endpoints have completely different logic.
# ══════════════════════════════════════════════════════════════════════

class AdminLoginRequest(BaseModel):

    email: str = Field(
        ...,
        description='Admin email — must match ADMIN_EMAIL in .env'
    )

    password: str = Field(
        ...,
        description='Admin password — must match ADMIN_PASSWORD in .env'
    )


# ══════════════════════════════════════════════════════════════════════
#  TOKEN RESPONSE
#  Returned by: POST /api/auth/login and POST /api/auth/admin-login
#  This is what the frontend receives after a successful login.
#  The access_token is the JWT the client must include in every
#  subsequent request inside the Authorization header.
# ══════════════════════════════════════════════════════════════════════

class TokenResponse(BaseModel):

    access_token: str
    # The signed JWT string.
    # Example: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
    # The frontend stores this and sends it with every protected request.

    token_type: str = 'bearer'
    # 'bearer' is the standard token type for JWT authentication.
    # The client sends it in the header like:
    #   Authorization: Bearer eyJhbGci...

    role: str
    # 'clinician' for staff, 'admin' for the admin user.
    # The frontend uses this to decide which UI to show after login.


# ══════════════════════════════════════════════════════════════════════
#  USER RESPONSE
#  Returned by: POST /api/auth/register
#  What the client receives after a successful registration.
#  We never send back the hashed_password — only safe fields.
# ══════════════════════════════════════════════════════════════════════

class UserResponse(BaseModel):

    id: int
    # The auto-generated database ID of the new account.

    full_name: str
    # The name that was registered.

    email: str
    # The email that was registered.

    role: str
    # Always 'clinician' for newly registered staff.

    message: str
    # A confirmation message e.g. 'Account created successfully'
