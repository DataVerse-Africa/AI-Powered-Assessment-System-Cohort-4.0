# database/session.py
# ══════════════════════════════════════════════════════════════════════
#  DATABASE CONNECTION — Engine, Session Factory, and Request Dependency
#
#  This file does three things:
#    1. Creates the ENGINE — the single connection to the database file
#    2. Creates the SESSION FACTORY — a blueprint for making DB sessions
#    3. Defines get_db() — a FastAPI dependency that gives each API
#       request its own clean database session, then closes it after
# ══════════════════════════════════════════════════════════════════════

from sqlalchemy import create_engine
# create_engine() opens the connection to the database.
# Think of it as the main pipe connecting our Python app to the database file.

from sqlalchemy.orm import sessionmaker
# sessionmaker() creates a factory (a blueprint) for making Session objects.
# A Session is the object we use to run queries — db.query(...), db.add(...), etc.

import os
# os.getenv() reads environment variables from our .env file

from dotenv import load_dotenv
# load_dotenv() loads the key=value pairs from our .env file into os.environ
# so os.getenv() can read them. Must be called before any os.getenv() calls.


# ── Step 1: Load .env variables ───────────────────────────────────────

load_dotenv()
# After this line, everything defined in .env is available via os.getenv().
# e.g.  os.getenv('DATABASE_URL')  →  'sqlite:///./patient_assessment.db'


# ── Step 2: Read the database URL from .env ───────────────────────────

DATABASE_URL = os.getenv(
    'DATABASE_URL',                          # the key to look up in .env
    #'sqlite:///./patient_assessment.db'      # fallback default if key is missing
    # This fallback means: if DATABASE_URL is not in .env, use SQLite
    # and create the database file at ./patient_assessment.db
    # (right inside the project folder, next to main.py)
)

# DATABASE_URL format examples:
#   SQLite (development, no server needed):
#     sqlite:///./patient_assessment.db
#   PostgreSQL (production):
#     postgresql://username:password@localhost:5432/patient_assessment_db


# ── Step 3: Create the Engine ─────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,

    connect_args=(
        {'check_same_thread': False}   # SQLite-specific setting
        if 'sqlite' in DATABASE_URL    # only applied when using SQLite
        else {}                        # empty dict for PostgreSQL (not needed)
    )
    # check_same_thread=False is required for SQLite when using FastAPI.
    # By default SQLite only allows one thread to use a connection.
    # FastAPI handles requests across multiple threads, so we must disable
    # this restriction. PostgreSQL does not have this limitation.
)


# ── Step 4: Create the Session Factory ────────────────────────────────

SessionLocal = sessionmaker(
    autocommit=False,   # we control commits manually — changes are not
                        # saved to the database until we call db.commit()
                        # this gives us control and lets us roll back on errors

    autoflush=False,    # SQLAlchemy will not automatically sync pending changes
                        # to the database before each query
                        # we control this manually for predictability

    bind=engine         # every session created by this factory will use
                        # the engine (database connection) we defined above
)
# SessionLocal is NOT a session itself — it is a factory.
# We call SessionLocal() to create a new session object when needed.


# ── Step 5: Define the get_db Dependency ──────────────────────────────

def get_db():
    # This function is a FastAPI dependency.
    # FastAPI calls it automatically for every endpoint that declares it.
    # It provides a fresh database session for each incoming request,
    # then closes the session cleanly when the request is done.

    db = SessionLocal()
    # Create a new session from our factory.
    # This opens a connection to the database for this request.

    try:
        yield db
        # yield hands the session to the endpoint function.
        # The endpoint uses it to run queries:
        #   db.query(User).all()
        #   db.add(new_user)
        #   db.commit()
        # Code after yield runs AFTER the endpoint returns its response.

    finally:
        db.close()
        # Always close the session when done — whether the request
        # succeeded or raised an exception.
        # This releases the database connection back to the pool
        # and prevents connection leaks.
