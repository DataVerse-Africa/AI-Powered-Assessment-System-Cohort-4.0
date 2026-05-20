# main.py
# ══════════════════════════════════════════════════════════════════════
#  Patient Assessment System — API Entry Point
#
#  This is the root file that:
#    1. Creates the FastAPI app instance
#    2. Adds CORS middleware (so the frontend can talk to the API)
#    3. Creates all database tables on startup
#    4. Registers all routers (auth, sessions, predictions, user, admin)
#    5. Exposes a health check endpoint at GET /api/health
#
#  To run the server:
#    uvicorn main:app --reload --port 8000
#
#  Interactive API docs (auto-generated):
#    http://localhost:8000/docs
#
# -------------- importing the necessary libraries ----------------------------
#
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Database imports (Step 1) ──────────────────────────────────────────
from database.session import engine
# engine is the connection to our database file.
# We pass it to Base.metadata.create_all() below to create the tables.

from database.models import Base
# Base knows about all four of our model classes (User, ClinicalSession,
# Prediction, AuditLog) because they all inherit from it.
# Base.metadata.create_all() reads those classes and creates the tables.

# ── Router imports — uncomment as we build each step ──────────────────
from auth.router import router as auth_router        # Step 2 ✅
from routers.sessions  import router as sessions_router    # Step 3 ✅
from routers.predictions import router as predictions_router # Step ✅
# from routers.user_panel  import router as user_router      # Step 5
# from routers.admin_panel import router as admin_router     # Step 6

# ── Create all database tables on startup ─────────────────────────────
Base.metadata.create_all(bind=engine)
# This line runs when the server starts.
# SQLAlchemy looks at every model class that inherits from Base,
# compares them to what already exists in the database,
# and creates any tables that are missing.
# If the tables already exist, this does nothing — it is safe to run repeatedly.


# ── Create the FastAPI app instance ───────────────────────────────────
app = FastAPI(
    title='Patient Assessment System API',
    description='AI-powered clinical decision support — Diabetes, Breast Cancer, Chest Pneumonia, Kidney CNN',
    version='1.0.0'
)


# ── CORS Middleware ────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:3000'],  # the frontend's address
                                             # update this when deploying to production
    allow_credentials=True,   # allows cookies and auth headers to be sent cross-origin
    allow_methods=['*'],      # allow all HTTP methods: GET, POST, PATCH, DELETE, etc.
    allow_headers=['*'],      # allow all headers including our Authorization header
)


# ── Register routers — uncomment as we build each step ────────────────
app.include_router(auth_router)         # Step 2 ✅
app.include_router(sessions_router)     # Step 3 ✅
app.include_router(predictions_router)  # Step 4 ✅
# app.include_router(user_router)         # Step 5
# app.include_router(admin_router)        # Step 6


# ── Health Check Endpoint ─────────────────────────────────────────────
@app.get('/api/health')
#@app.get('/api/health') registers this function as a GET endpoint.
# Visiting http://localhost:8000/api/health will call this function.
def health_check():
    # This endpoint has one job: confirm the server is running.
    # Monitoring tools ping this URL to know if the app is alive.
    return {
        'status': 'ok',
        'version': '1.0.0',
        'message': 'Patient Assessment System API is running Please continue no cause of alarm'
    }


# ── To run the server ──────────────────────────────────────────────────
# uvicorn main:app --reload --port 8000
#
# main      → the filename (main.py)
# app       → the FastAPI instance defined above
# --reload  → auto-restart when any file changes (development only)
# --port    → listen on port 8000

# TODO: Add CORS middleware here
# TODO: Register all routers here
# TODO: Add health check endpoint here
# TODO: Create all DB tables on startup here
