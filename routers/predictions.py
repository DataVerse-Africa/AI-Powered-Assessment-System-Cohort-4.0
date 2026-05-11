# routers/predictions.py
# ══════════════════════════════════════════════════════════════════════
#  ML Prediction Routes
#
#  POST /api/predict/diabetes        — Diabetes risk (Scikit-learn)
#  POST /api/predict/cardiovascular  — Cardiovascular risk (Scikit-learn)
#  POST /api/predict/ckd             — Chronic Kidney Disease (Scikit-learn)
#  POST /api/predict/kidney-image    — Kidney CT scan (CNN / TensorFlow)
#
#  All endpoints require:
#    - A valid patient JWT token
#    - An open session_id
#  Prediction is refused if the session is closed or doesn't exist.
#
#  ⚠️  DO NOT EDIT YET — we will build this together in Step 4
# ══════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session as DBSession
from database.session import get_db

router = APIRouter(prefix='/api/predict', tags=['Predictions'])

# TODO: Step 4 — we will implement prediction endpoints here
