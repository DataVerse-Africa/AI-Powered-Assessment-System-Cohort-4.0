# database/models.py
# ══════════════════════════════════════════════════════════════════════
#  Database Models — SQLAlchemy ORM Table Definitions
#  Four tables:
#    1. users            — patient accounts (role always = 'patient')
#    2. clinical_sessions — one consultation per patient visit
#    3. predictions       — every ML model result, linked to a session
#    4. audit_logs        — every significant action in the system
#    5. blacklist         — this stores any token that has been trigged logout
# ══════════════════════════════════════════════════════════════════════

# ── Imports ───────────────────────────────────────────────────────────

from sqlalchemy import (
    Column,       # used to define a column inside a table
    Integer,      # whole number column type  e.g. 1, 42, 100
    String,       # text column with a max length  e.g. String(100)
    Float,        # decimal number column type  e.g. 0.87, 3.14
    Boolean,      # True / False column type
    DateTime,     # date + time column type
    Text,         # long text column with no length limit (for notes, JSON strings)
    ForeignKey    # links one table to another  e.g. ForeignKey('users.id')
)

from sqlalchemy.ext.declarative import declarative_base
# declarative_base() gives us the Base class that all our models inherit from.
# It is what tells SQLAlchemy "this Python class represents a database table".

from sqlalchemy.orm import relationship
# relationship() lets us access related records directly in Python
# without writing SQL JOIN queries.
# e.g.  user.sessions  →  returns all sessions belonging to that user

from datetime import datetime
# datetime.utcnow is used as the default value for timestamp columns.
# utcnow means "current time in UTC" — always store time in UTC,
# convert to local time only when displaying to users.


# ── Base ──────────────────────────────────────────────────────────────

Base = declarative_base()
# All our model classes must inherit from Base.
# This is the contract that connects our Python class to SQLAlchemy.


# ══════════════════════════════════════════════════════════════════════
#  TABLE 1 — users
#
#  Stores every clinical staff account.
#  Role is always 'clinical' — we never let users set their own role.
#  Admin access is handled separately via the .env file, not this table.
# ══════════════════════════════════════════════════════════════════════

class User(Base):

    __tablename__ = 'users'
    # __tablename__ tells SQLAlchemy the exact name of the table in the database.
    # Python class is called User (singular), table in the DB is called users (plural).
    # This is a standard naming convention.

    # ── Primary Key ───────────────────────────────────────────────────
    id = Column(
        Integer,          # stored as a whole number
        primary_key=True, # every table needs exactly one primary key column
                          # the primary key uniquely identifies each row
        index=True        # creates a database index on this column
                          # an index makes lookups by id very fast
    )

    # ── Patient Name ──────────────────────────────────────────────────
    full_name = Column(
        String(100),      # text, max 100 characters
        nullable=False    # this column MUST have a value — cannot be empty
    )

    # ── Email Address ─────────────────────────────────────────────────
    email = Column(
        String(120),      # text, max 120 characters
        unique=True,      # no two users can share the same email address
                          # the database enforces this — not just our code
        index=True,       # we look up users by email on every login
                          # the index makes this fast
        nullable=False    # email is required
    )

    # ── Role ──────────────────────────────────────────────────────────
    role = Column(
        String(20),           # text, max 20 characters
        default='clinician'   # every new account gets role='clinician' automatically
                              # we never let a user set their own role
                              # admin access is handled via .env, not this column
    )

    # ── Password ──────────────────────────────────────────────────────
    hashed_password = Column(
        String,           # no length limit — bcrypt hashes are always 60 chars
                          # but we leave it unlimited to be safe
        nullable=False    # a password is always required
        # ⚠️  We NEVER store the plain text password here.
        # Before saving, we run the password through bcrypt which converts it
        # into an irreversible 60-character hash string.
        # e.g. 'mypassword123' → '$2b$12$XkP9bF3yMn7cK2eRwHtJuO...'
        # Even if someone steals the database, they cannot reverse the hash.
    )

    # ── Account Status ────────────────────────────────────────────────
    is_active = Column(
        Boolean,          # True or False
        default=True      # all new accounts are active by default
                          # admin can set this to False to suspend an account
                          # a suspended user cannot log in even with correct password
    )

    # ── Timestamps ────────────────────────────────────────────────────
    created_at = Column(
        DateTime,
        default=datetime.utcnow   # automatically set to the current UTC time
                                  # when the row is first inserted
                                  # we do not pass datetime.utcnow() with brackets
                                  # — without brackets means SQLAlchemy calls it
                                  # at insert time, not at class definition time
    )

    last_login = Column(
        DateTime,
        nullable=True     # nullable=True means this column CAN be empty (NULL)
                          # a new account has never logged in yet, so this starts NULL
                          # we update it every time the user successfully logs in
    )

    # ── Relationships ─────────────────────────────────────────────────
    # These are NOT database columns.
    # They are Python-side shortcuts that let us access related records easily.

    sessions = relationship(
        'ClinicalSession',        # the name of the related model class (as a string)
        back_populates='user'     # on the ClinicalSession side, the matching
                                  # relationship is called 'user'
        # Usage example:
        #   user = db.query(User).first()
        #   user.sessions  →  returns a list of all ClinicalSession rows for this user
    )

    predictions = relationship(
        'Prediction',
        back_populates='user'
        # user.predictions  →  returns all Prediction rows made by this user
    )

    audit_logs = relationship(
        'AuditLog',
        back_populates='user'
        # user.audit_logs  →  returns all AuditLog rows for this user
    )
    
    blacklisted_tokens = relationship(
        'TokenBlacklist',
        back_populates='user'
    )

# ══════════════════════════════════════════════════════════════════════
#  TABLE 2 — clinical_sessions
#
#  Represents a single patient consultation.
#  A session MUST be opened before any prediction can be made.
#  One session can contain many predictions (diabetes + CKD in same visit).
#  Sessions can be CLOSED (record kept) or DELETED (record removed).
# ══════════════════════════════════════════════════════════════════════

class ClinicalSession(Base):

    __tablename__ = 'clinical_sessions'

    # ── Primary Key ───────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True)

    # ── Foreign Key — links session to the patient who owns it ────────
    user_id = Column(
        Integer,
        ForeignKey('users.id'),   # this value must match an id in the users table
                                  # if the user is deleted, this becomes invalid
                                  # (SQLAlchemy handles cascade behaviour)
        nullable=False            # every session must belong to a user
    )

    # ── Patient Information ───────────────────────────────────────────
    # Note: this is the patient being assessed, not the account holder.
    # In this system they are the same person, but the fields are kept
    # separate for clarity and future flexibility.

    patient_name = Column(
        String(100),
        nullable=False    # we always need a name for the session record
    )

    patient_age = Column(
        Integer,
        nullable=True     # age is helpful context but not strictly required
    )

    patient_gender = Column(
        String(10),       # 'Male', 'Female', 'Other'
        nullable=True     # optional — not all assessments require this
    )

    # ── Clinical Notes ────────────────────────────────────────────────
    reason_for_visit = Column(
        Text,             # Text has no length limit — free-form clinical note
        nullable=True     # optional — the patient can describe their symptoms
    )

    notes = Column(
        Text,
        nullable=True     # any additional observations added during the session
    )

    # ── Session Status ────────────────────────────────────────────────
    status = Column(
        String(10),
        default='open'    # 'open'   = consultation is in progress
                          # 'closed' = consultation has ended, record is preserved
                          # Deletion removes the row entirely (different from closing)
    )

    # ── Timestamps ────────────────────────────────────────────────────
    created_at = Column(
        DateTime,
        default=datetime.utcnow   # when the session was opened
    )

    closed_at = Column(
        DateTime,
        nullable=True     # NULL while the session is still open
                          # set to current time when PATCH /sessions/{id}/close is called
    )

    # ── Relationships ─────────────────────────────────────────────────
    user = relationship(
        'User',
        back_populates='sessions'
        # session.user  →  returns the User object who owns this session
    )

    predictions = relationship(
        'Prediction',
        back_populates='session',
        cascade='all, delete-orphan'
        # cascade='all, delete-orphan' means:
        # if this session is deleted, ALL its linked predictions are also deleted
        # automatically. We never have predictions floating with no session.
        # session.predictions  →  returns all Prediction rows in this session
    )


# ══════════════════════════════════════════════════════════════════════
#  TABLE 3 — predictions
#
#  Every ML model result ever produced by the system.
#  Each prediction is linked to BOTH a user AND a session.
#  This double-link allows queries like:
#    "show all predictions from session 7"
#    "show all predictions made by this patient this month"
# ══════════════════════════════════════════════════════════════════════

class Prediction(Base):

    __tablename__ = 'predictions'

    # ── Primary Key ───────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True)

    # ── Foreign Keys ──────────────────────────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey('users.id'),
        nullable=False    # every prediction must be linked to a patient account
    )

    session_id = Column(
        Integer,
        ForeignKey('clinical_sessions.id'),
        nullable=False    # every prediction must belong to a session
                          # you cannot make a prediction without opening a session first
    )

    # ── Which Model Was Used ──────────────────────────────────────────
    model_name = Column(
        String(50),       # 'diabetes' | 'cardiovascular' | 'chest - Pneumonia' | 'kidney_image'
        nullable=False
    )

    # ── Input Data ────────────────────────────────────────────────────
    input_data = Column(
        Text              # the full patient data submitted, stored as a JSON string
                          # e.g. '{"glucose": 148, "bmi": 33.6, "age": 50, ...}'
                          # storing the input lets us reconstruct exactly what
                          # the model was given — important for auditing
    )

    # ── Model Output ──────────────────────────────────────────────────
    prediction = Column(
        Integer           # the raw numeric output from the model
                          # e.g.  0 = negative / no disease
                          #       1 = positive / disease detected
    )

    prediction_label = Column(
        String(50)        # human-readable version of the prediction integer
                          # e.g. 'Non-Diabetic', 'Diabetic'
                          #      'Low Risk', 'High Risk'
                          #      'Normal', 'Cyst', 'Tumor', 'Stone'
    )

    probability = Column(
        Float             # the model's confidence as a decimal between 0.0 and 1.0
                          # e.g. 0.87 means the model is 87% confident in its output
    )

    risk_level = Column(
        String(20)        # a human-friendly risk band derived from the probability
                          # 'Low' | 'Moderate' | 'High' | 'Critical'
    )

    recommendation = Column(
        Text              # a plain-language clinical recommendation string
                          # generated by the inference function alongside the prediction
                          # e.g. "Glucose levels are elevated. Recommend fasting test."
    )

    # ── Timestamp ─────────────────────────────────────────────────────
    created_at = Column(
        DateTime,
        default=datetime.utcnow   # exact time the prediction was made
    )

    # ── Relationships ─────────────────────────────────────────────────
    user = relationship(
        'User',
        back_populates='predictions'
        # prediction.user  →  returns the User who made this prediction
    )

    session = relationship(
        'ClinicalSession',
        back_populates='predictions'
        # prediction.session  →  returns the ClinicalSession this prediction belongs to
    )
    

# ══════════════════════════════════════════════════════════════════════
#  TABLE 4 — audit_logs
#
#  A complete, immutable record of every significant action in the system.
#  This table is append-only — we only ever INSERT rows, never UPDATE them.
#  The admin panel reads from this table to monitor system activity.
#
#  Actions logged:
#    LOGIN, LOGIN_FAILED, REGISTER,
#    CREATE_SESSION, CLOSE_SESSION, DELETE_SESSION,
#    PREDICT, SUSPEND_USER, ACTIVATE_USER
# ══════════════════════════════════════════════════════════════════════

class AuditLog(Base):

    __tablename__ = 'audit_logs'

    # ── Primary Key ───────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True)

    # ── Who Did It ────────────────────────────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey('users.id'),
        nullable=True     # nullable=True because failed login attempts have no user_id
                          # (the user does not exist or could not be identified)
    )

    # ── What They Did ─────────────────────────────────────────────────
    action = Column(
        String(50),
        nullable=False    # the action type is always required
                          # e.g. 'LOGIN', 'PREDICT', 'DELETE_SESSION'
    )

    # ── Full Context ──────────────────────────────────────────────────
    detail = Column(
        Text              # a JSON string with the full context of what happened
                          # e.g. '{"session_id": 7, "patient": "John Doe"}'
                          #      '{"model": "diabetes", "result": "Diabetic"}'
                          #      '{"email": "unknown@x.com"}' (for failed logins)
    )

    # ── Where It Came From ────────────────────────────────────────────
    ip_address = Column(
        String(45),       # max 45 chars covers both IPv4 (15 chars) and IPv6 (45 chars)
        nullable=True     # we try to capture this but it may not always be available
    )

    # ── When It Happened ──────────────────────────────────────────────
    created_at = Column(
        DateTime,
        default=datetime.utcnow   # exact timestamp — critical for security monitoring
    )

    # ── Relationship ──────────────────────────────────────────────────
    user = relationship(
        'User',
        back_populates='audit_logs'
        # audit_log.user  →  returns the User who performed this action
        # will be None for failed login attempts (user_id is NULL)
    )
    
    
# ══════════════════════════════════════════════════════════════════════
#  TABLE 5 — token_blacklist
#
#  ADDED for logout support.
#
#  Stores JWT tokens that have been explicitly invalidated via logout.
#  Why this is necessary:
#    JWT tokens are stateless — the server does not store them after
#    issuing them. A token remains mathematically valid until its
#    expiry time (60 minutes), even after the user "logs out".
#    Without a blacklist, a logged-out token could still be used to
#    make API calls for up to 60 minutes after logout.
#
#  How it works:
#    1. User calls POST /api/auth/logout
#    2. Their current token is saved to this table
#    3. get_current_user() checks this table on every protected request
#    4. If the token is found here → 401 immediately, request blocked
#    5. Expired tokens are cleaned up automatically (optional cron job)
#
#  This table serves both staff tokens and admin tokens.
#  The token_type column distinguishes between them.
#
#    This is especially important for a clinical system:
#    If an admin suspends a staff account, we also blacklist their
#    current token so they are kicked out immediately — not 60 min later.
# ══════════════════════════════════════════════════════════════════════


class TokenBlacklist(Base):
 
    __tablename__ = 'token_blacklist'
 
    # ── Primary Key ───────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True)
 
    # ── The Blacklisted Token ─────────────────────────────────────────
    token = Column(
        Text,              # JWT tokens can be long strings — use Text not String
        nullable=False,    # always required — this is the whole point of the table
        unique=True        # each token should only appear once in the blacklist
                           # prevents duplicate entries if logout is called twice
    )
 
    # ── Token Type ────────────────────────────────────────────────────
    token_type = Column(
        String(10),
        nullable=False
        # 'staff' → a clinical staff JWT (signed with SECRET_KEY)
        # 'admin' → an admin JWT (signed with ADMIN_SECRET_KEY)
        # We track this so the blacklist check uses the right secret
        # when verifying which token was invalidated.
    )
 
    # ── Who Logged Out ────────────────────────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey('users.id'),
        nullable=True      # nullable=True because admin tokens are not
                           # linked to a database user (admin is in .env)
    )
 
    # ── When the Token Was Blacklisted ────────────────────────────────
    blacklisted_at = Column(
        DateTime,
        default=datetime.utcnow    # timestamp of the logout action
    )
 
    # ── When the Token Naturally Expires ──────────────────────────────
    expires_at = Column(
        DateTime,
        nullable=True      # stores the token's natural expiry time
                           # useful for cleanup — tokens past this date
                           # can be safely deleted from this table since
                           # they would be rejected by JWT verification anyway
    )
 
    # ── Relationship ──────────────────────────────────────────────────
    user = relationship(
        'User',
        back_populates='blacklisted_tokens'
        # blacklisted_token.user → returns the User who logged out
        # Will be None for admin logouts (admin is not in the users table)
    )