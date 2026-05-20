# routers/predictions.py
# ══════════════════════════════════════════════════════════════════════
#  ML Prediction Routes
#
#  Four endpoints:
#    POST /api/predict/diabetes       — Diabetes ML (scikit-learn)
#    POST /api/predict/ckd            — CKD ML (scikit-learn)
#    POST /api/predict/pneumonia      — Pneumonia CNN (image upload)
#    POST /api/predict/breast-cancer  — Breast Cancer CNN (image upload)
#
#  GET  /api/predict/status           — model availability health check
#
#  All endpoints require:
#    - A valid staff JWT token
#    - A valid open session_id
#
#   Every endpoint has a placeholder fallback:
#    If the model file is missing → returns a clean JSON response
#    with status='unavailable' instead of crashing with 500 error.
#    Once the model file is added → real predictions return automatically.
# ══════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
# UploadFile — FastAPI's file upload type for CNN image endpoints
# File       — used as the dependency to declare file upload fields

from sqlalchemy.orm import Session as DBSession
from database.session import get_db
from database.models import ClinicalSession, Prediction, AuditLog, User
from auth.dependencies import get_current_user

from schemas.prediction_schemas import (
    DiabetesPredictionRequest,
    CKDPredictionRequest,
    PredictionResponse
)

# ── Inference function imports ─────────────────────────────────────────
from ml_models.diabetes_inference import predict_diabetes
from ml_models.ckd_inference import predict_ckd
from ml_models.pneumonia_inference import predict_pneumonia
from ml_models.breast_cancer_inference import predict_breast_cancer

import json
import os
import shutil
import uuid
# json   — serialise patient data for storage in the database
# os     — check model file existence for the status endpoint
# shutil — save uploaded image files to a temp location
# uuid   — generate unique filenames for uploaded images

# Temporary folder for uploaded CNN images
UPLOAD_DIR = 'temp_uploads'
os.makedirs(UPLOAD_DIR, exist_ok=True)
# os.makedirs with exist_ok=True creates the folder if it does not
# exist, and does nothing if it already exists — safe to call on startup


router = APIRouter(
    prefix='/api/predict',
    tags=['Predictions']
)


# ══════════════════════════════════════════════════════════════════════
#  HELPER — validate_session()
#
#  Reusable function called by every prediction endpoint.
#  Checks three things:
#    1. The session exists in the database
#    2. The session belongs to the authenticated clinician
#    3. The session is currently open (not closed)
#
#  Returns the ClinicalSession object if all checks pass.
#  Raises HTTPException if any check fails.
# ══════════════════════════════════════════════════════════════════════

def validate_session(session_id: int, user_id: int, db: DBSession) -> ClinicalSession:
    session = db.query(ClinicalSession).filter(
        ClinicalSession.id == session_id,
        ClinicalSession.user_id == user_id
        # Both conditions — session must exist AND belong to this clinician
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Session {session_id} not found'
        )

    if session.status != 'open':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Session is closed. Open a new session to make predictions.'
            # Predictions can only be added to open sessions.
            # A closed session is a completed consultation — it cannot
            # be reopened or have new predictions added to it.
        )

    return session


# ══════════════════════════════════════════════════════════════════════
#  HELPER — save_prediction()
#
#  Reusable function that saves a prediction result to the database
#  and writes an audit log entry. Called by every prediction endpoint
#  after the inference function returns its result.
#
#  Works for both successful and unavailable results — even placeholder
#  responses are saved to the database for audit trail completeness.
# ══════════════════════════════════════════════════════════════════════

def save_prediction(
    db: DBSession,
    user_id: int,
    session_id: int,
    modelname: str,
    input_data: dict,
    result: dict,
    ip_address: str = None
) -> int:
    # Save the prediction result to the predictions table
    pred = Prediction(
        user_id=user_id,
        session_id=session_id,
        modelname=modelname,

        input_data=json.dumps(input_data),
        # json.dumps() converts the patient data dict to a JSON string
        # for storage in the Text column. Stored for audit purposes —
        # the exact input that produced this result is always traceable.

        prediction_label=result.get('prediction_label'),
        probability=result.get('probability'),
        risk_level=result.get('risk_level'),
        recommendation=result.get('recommendation')
        # All of these will be None for unavailable/error results
        # That is fine — the row still gets created for audit purposes
    )
    db.add(pred)

    # Write to audit log
    log = AuditLog(
        user_id=user_id,
        action='PREDICT',
        detail=json.dumps({
            'model': modelname,
            'session_id': session_id,
            'status': result.get('status'),
            'result': result.get('prediction_label')
        }),
        ip_address=ip_address
    )
    db.add(log)
    db.commit()
    db.refresh(pred)

    return pred.id
    # Return the auto-generated prediction ID so it can be included
    # in the response returned to the clinician


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 1 — DIABETES PREDICTION
#  POST /api/predict/diabetes
#
#  Accepts 13 clinical + engineered features.
#  Output: Low | Moderate | High risk level.
# ══════════════════════════════════════════════════════════════════════
 
@router.post('/diabetes', response_model=PredictionResponse)
def diabetes_prediction(
    request: DiabetesPredictionRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    req: Request = None
):
    # ── Step 1: Validate the session ──────────────────────────────────
    session = validate_session(request.session_id, current_user.id, db)

    # ── Step 2: Extract patient features (exclude session_id) ─────────
    patient_data = request.model_dump(exclude={'session_id'})
    # model_dump() converts the Pydantic schema to a plain Python dict.
    # exclude={'session_id'} removes session_id from the dict —
    # session_id is metadata, not a model input feature.

    # ── Step 3: Run inference ─────────────────────────────────────────
    result = predict_diabetes(patient_data)
    # result is always a dict — either a real prediction or a placeholder.
    # The inference function never raises an unhandled exception.

    # ── Step 4: Save to database ──────────────────────────────────────
    pred_id = save_prediction(
        db=db,
        user_id=current_user.id,
        session_id=session.id,
        modelname='diabetes',
        input_data=patient_data,
        result=result,
        ip_address=req.client.host if req else None
    )

    # ── Step 5: Return response ───────────────────────────────────────
    return PredictionResponse(
        prediction_id=pred_id,
        session_id=session.id,
        modelname='diabetes',
        status=result.get('status', 'unavailable'),
        prediction_label=result.get('prediction_label'),
        probability=result.get('probability'),
        risk_level=result.get('risk_level'),
        recommendation=result.get('recommendation'),
        message=result.get('message', 'Prediction completed successfully')
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 2 — CKD PREDICTION
#  POST /api/predict/ckd
#
#  Accepts 42 clinical features.
#  Output: No_Disease | Low_Risk | Moderate_Risk | High_Risk | Severe_Disease
# ══════════════════════════════════════════════════════════════════════

@router.post('/ckd', response_model=PredictionResponse)
def ckd_prediction(
    request: CKDPredictionRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    req: Request = None
):
    # ── Step 1: Validate the session ──────────────────────────────────
    session = validate_session(request.session_id, current_user.id, db)

    # ── Step 2: Extract patient features ──────────────────────────────
    patient_data = request.model_dump(exclude={'session_id'})

    # ── Step 3: Run inference ─────────────────────────────────────────
    result = predict_ckd(patient_data)

    # ── Step 4: Save to database ──────────────────────────────────────
    pred_id = save_prediction(
        db=db,
        user_id=current_user.id,
        session_id=session.id,
        modelname='ckd',
        input_data=patient_data,
        result=result,
        ip_address=req.client.host if req else None
    )

    # ── Step 5: Return response ───────────────────────────────────────
    return PredictionResponse(
        prediction_id=pred_id,
        session_id=session.id,
        modelname='ckd',
        status=result.get('status', 'unavailable'),
        prediction_label=result.get('prediction_label'),
        probability=result.get('probability'),
        risk_level=result.get('risk_level'),
        recommendation=result.get('recommendation'),
        message=result.get('message', 'Prediction completed successfully')
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 3 — PNEUMONIA PREDICTION (CNN)
#  POST /api/predict/pneumonia
#
#  Accepts a chest X-ray image file upload + session_id as a form field.
#  Output: Normal | Pneumonia
#
#  Note: CNN endpoints use Form + File upload instead of JSON body.
#  This is because HTTP cannot mix JSON and file uploads in one request.
#  session_id is sent as a form field alongside the image file.
# ══════════════════════════════════════════════════════════════════════

@router.post('/pneumonia', response_model=PredictionResponse)
def pneumonia_prediction(
    session_id: int = Form( ...),
    # session_id comes as a query parameter for CNN endpoints
    # Example URL: POST /api/predict/pneumonia?session_id=7

    image: UploadFile = File(...),
    # UploadFile is FastAPI's file upload type.
    # File(...) means the file field is required.
    # The clinician selects a chest X-ray image file to upload.

    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    req: Request = None
):
    # ── Step 1: Validate the session ──────────────────────────────────
    session = validate_session(session_id, current_user.id, db)

    # ── Step 2: Save the uploaded image to a temp file ────────────────
    # We save the image to disk temporarily because the CNN inference
    # function expects a file path, not raw bytes.
    # A unique filename prevents collisions between concurrent uploads.
    file_extension = os.path.splitext(image.filename)[1]
    # os.path.splitext('xray.jpg') → ('xray', '.jpg')
    # [1] gets the extension part '.jpg'

    temp_filename = f"{uuid.uuid4()}{file_extension}"
    # uuid.uuid4() generates a random unique ID e.g. 'a3f7c2d1-...'
    # Combined with the extension: 'a3f7c2d1-....jpg'

    temp_path = os.path.join(UPLOAD_DIR, temp_filename)
    # Full path: 'temp_uploads/a3f7c2d1-....jpg'

    with open(temp_path, 'wb') as f:
        shutil.copyfileobj(image.file, f)
    # shutil.copyfileobj copies the uploaded file contents to disk.
    # 'wb' = write binary — image files are binary data.

    # ── Step 3: Run inference ─────────────────────────────────────────
    try:
        result = predict_pneumonia(temp_path)
    finally:
        # Always delete the temp file after inference — whether
        # the prediction succeeded or failed. Temp files must not
        # accumulate on the server.
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # ── Step 4: Save to database ──────────────────────────────────────
    pred_id = save_prediction(
        db=db,
        user_id=current_user.id,
        session_id=session.id,
        modelname='pneumonia',
        input_data={'filename': image.filename},
        # We store the original filename instead of pixel data —
        # storing a full image as JSON would be impractical
        result=result,
        ip_address=req.client.host if req else None
    )

    # ── Step 5: Return response ───────────────────────────────────────
    return PredictionResponse(
        prediction_id=pred_id,
        session_id=session.id,
        modelname='pneumonia',
        status=result.get('status', 'unavailable'),
        prediction_label=result.get('prediction_label'),
        probability=result.get('probability'),
        risk_level=result.get('risk_level'),
        recommendation=result.get('recommendation'),
        message=result.get('message', 'Prediction completed successfully')
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 4 — BREAST CANCER PREDICTION (CNN)
#  POST /api/predict/breast-cancer
#
#  Accepts a histology patch image file upload + session_id.
#  Output: IDC Negative | IDC Positive
#  Confidence: Low | Moderate | High (based on your notebook logic)
# ══════════════════════════════════════════════════════════════════════

@router.post('/breast-cancer', response_model=PredictionResponse)
def breast_cancer_prediction(
    session_id: int = Form(...),
    image: UploadFile = File(...),
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    req: Request = None
):
    # ── Step 1: Validate the session ──────────────────────────────────
    session = validate_session(session_id, current_user.id, db)

    # ── Step 2: Save uploaded image to temp file ──────────────────────
    file_extension = os.path.splitext(image.filename)[1]
    temp_filename = f"{uuid.uuid4()}{file_extension}"
    temp_path = os.path.join(UPLOAD_DIR, temp_filename)

    with open(temp_path, 'wb') as f:
        shutil.copyfileobj(image.file, f)

    # ── Step 3: Run inference ─────────────────────────────────────────
    try:
        result = predict_breast_cancer(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # ── Step 4: Save to database ──────────────────────────────────────
    pred_id = save_prediction(
        db=db,
        user_id=current_user.id,
        session_id=session.id,
        modelname='breast_cancer',
        input_data={'filename': image.filename},
        result=result,
        ip_address=req.client.host if req else None
    )

    # ── Step 5: Return response ───────────────────────────────────────
    return PredictionResponse(
        prediction_id=pred_id,
        session_id=session.id,
        modelname='breast_cancer',
        status=result.get('status', 'unavailable'),
        prediction_label=result.get('prediction_label'),
        probability=result.get('probability'),
        risk_level=result.get('risk_level'),
        recommendation=result.get('recommendation'),
        message=result.get('message', 'Prediction completed successfully')
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 5 — MODEL STATUS CHECK
#  GET /api/predict/status
#
#  Returns the availability status of all four model files.
#  The admin or developer can hit this endpoint to quickly see which
#  models are loaded and which are missing from saved_models/.
#  No authentication required — this is a health check endpoint.
# ══════════════════════════════════════════════════════════════════════

@router.get('/status')
def model_status():
    # Check whether each model file exists on disk
    base = os.path.join(os.path.dirname(__file__), '..', 'saved_models')
    # Build the path to the saved_models folder relative to this file

    models = {
        'diabetes':     os.path.join(base, 'diabetes_rf_model.joblib'),
        'ckd':          os.path.join(base, 'kidney_disease_nn_model.h5'),
        'pneumonia':    os.path.join(base, 'chest_xray_cnn_best.keras'),
        'breast_cancer':os.path.join(base, 'breast_cancer.keras'),
    }

    status_report = {}
    for modelname, model_path in models.items():
        exists = os.path.exists(model_path)
        status_report[modelname] = {
            'available': exists,
            # True if the file exists, False if missing
            'file': os.path.basename(model_path),
            # Just the filename for display e.g. 'diabetes.pkl'
            'status': 'ready' if exists else 'missing'
            # 'ready'   → file found, predictions will work
            # 'missing' → file not found, placeholder will be returned
        }

    all_ready = all(v['available'] for v in status_report.values())
    # True only if ALL four model files are present

    return {
        'all_models_ready': all_ready,
        'models': status_report
    }
