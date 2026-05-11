# routers/user_panel.py
# ══════════════════════════════════════════════════════════════════════
#  Patient / User Panel Routes
#
#  GET  /api/user/profile      — my account info
#  GET  /api/user/sessions     — my sessions summary
#  GET  /api/user/predictions  — my full prediction history
#  PUT  /api/user/profile      — update my name or password
#
#  All endpoints require a valid patient JWT token.
#  Patients can only see their OWN data.
#
#  ⚠️  DO NOT EDIT YET — we will build this together in Step 5
# ══════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.session import get_db

router = APIRouter(prefix='/api/user', tags=['User Panel'])

# TODO: Step 5 — we will implement user panel endpoints here
