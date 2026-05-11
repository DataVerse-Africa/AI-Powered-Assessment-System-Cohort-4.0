# schemas/prediction_schemas.py
# ══════════════════════════════════════════════════════════════════════
#  Pydantic Schemas — ML Prediction Request Models
#
#  DiabetesPredictionRequest       — 8 clinical features + session_id
#  CardiovascularPredictionRequest — 13 clinical features + session_id
#  CKDPredictionRequest            — key kidney disease features + session_id
#  KidneyImageRequest              — session_id only (image sent as file upload)
#
#  FastAPI validates all incoming request data against these schemas
#  automatically. Wrong types or missing fields return 422 before
#  the model even runs.
#
#  ⚠️  DO NOT EDIT YET — we will build this together in Step 4
# ══════════════════════════════════════════════════════════════════════

from pydantic import BaseModel, Field
from typing import Optional

# TODO: Step 4 — we will define prediction schemas here
