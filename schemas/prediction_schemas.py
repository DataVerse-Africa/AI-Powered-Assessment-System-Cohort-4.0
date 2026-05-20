# schemas/prediction_schemas.py
# ══════════════════════════════════════════════════════════════════════
#  Pydantic Schemas — ML/CNN Prediction Request & Response Models
#
#  Request schemas:
#    DiabetesPredictionRequest     — 13 features + session_id
#    CKDPredictionRequest          — 42 features + session_id
#    (Pneumonia and Breast Cancer use file uploads — no schema needed)
#
#  FastAPI validates all incoming request data against these schemas
#  automatically. Wrong types or missing fields return 422 before
#  the model even runs.
#
#  Response schema:
#    PredictionResponse — shared response for all four models
# ══════════════════════════════════════════════════════════════════════

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


# ══════════════════════════════════════════════════════════════════════
#  SHARED RESPONSE SCHEMA
#  Returned by all four prediction endpoints.
#  Works for both successful predictions and model-unavailable cases.
# ══════════════════════════════════════════════════════════════════════

class PredictionResponse(BaseModel):

    prediction_id: Optional[int] = None
    # Auto-generated DB row ID — None if model was unavailable

    session_id: int
    # The session this prediction belongs to

    modelname: str
    # 'diabetes' | 'ckd' | 'pneumonia' | 'breast_cancer'

    status: str
    # 'success'     → model ran and produced a result
    # 'unavailable' → model file not found, placeholder returned

    prediction_label: Optional[str] = None
    # Human-readable result — None if model unavailable

    probability: Optional[float] = None
    # Confidence score 0.0 to 1.0 — None if model unavailable

    risk_level: Optional[str] = None
    # 'Low' | 'Moderate' | 'High' | 'Critical' — None if unavailable

    recommendation: Optional[str] = None
    # Plain-language clinical recommendation — None if unavailable

    message: str
    # 'Prediction completed successfully' or
    # 'Model not available — placeholder returned'


# ══════════════════════════════════════════════════════════════════════
#  DIABETES PREDICTION REQUEST
#  Used by: POST /api/predict/diabetes
#  13 features — 8 clinical + 5 engineered during model training
# ══════════════════════════════════════════════════════════════════════

class DiabetesPredictionRequest(BaseModel):

    session_id: int = Field(..., description='ID of the open clinical session')

    # ── Core Clinical Features ────────────────────────────────────────
    Pregnancies: int = Field(..., ge=0, le=20,
        description='Number of pregnancies')

    Glucose: float = Field(..., ge=0, le=300,
        description='Plasma glucose concentration (mg/dL)')

    BloodPressure: float = Field(..., ge=0, le=200,
        description='Diastolic blood pressure (mm/Hg)')

    SkinThickness: float = Field(..., ge=0, le=100,
        description='Triceps skin fold thickness (mm)')

    Insulin: float = Field(..., ge=0, le=900,
        description='2-hour serum insulin (mu U/ml)')

    BMI: float = Field(..., ge=0, le=100,
        description='Body Mass Index (weight kg / height m²)')

    DiabetesPedigreeFunction: float = Field(..., ge=0, le=3.0,
        description='Diabetes pedigree function — genetic risk score')

    Age: int = Field(..., ge=1, le=120,
        description='Age of the patient in years')


# ══════════════════════════════════════════════════════════════════════
#  CKD PREDICTION REQUEST
#  Used by: POST /api/predict/ckd
#  42 features — mix of numeric, binary (yes/no), and categorical
#  Output classes: No_Disease, Low_Risk, Moderate_Risk, High_Risk, Severe_Disease
# ══════════════════════════════════════════════════════════════════════

class CKDPredictionRequest(BaseModel):

    session_id: int = Field(..., description='ID of the open clinical session')

    # ── Demographics ──────────────────────────────────────────────────
    age: float = Field(..., ge=0, le=120, description='Age of the patient')

    # ── Urine Analysis ────────────────────────────────────────────────
    blood_pressure: float = Field(..., ge=0, le=300,
        description='Blood pressure (mm/Hg)')
    specific_gravity: float = Field(..., ge=1.000, le=1.040,
        description='Specific gravity of urine')
    albumin: float = Field(..., ge=0, le=5,
        description='Albumin in urine (0-5 scale)')
    sugar: float = Field(..., ge=0, le=5,
        description='Sugar in urine (0-5 scale)')
    red_blood_cells: str = Field(...,
        description='Red blood cells in urine — normal or abnormal')
    pus_cell: str = Field(...,
        description='Pus cells in urine — normal or abnormal')
    pus_cell_clumps: str = Field(...,
        description='Pus cell clumps in urine — present or not present')
    bacteria: str = Field(...,
        description='Bacteria in urine — present or not present')

    # ── Blood Chemistry ───────────────────────────────────────────────
    blood_glucose_random: float = Field(..., ge=0,
        description='Random blood glucose (mg/dl)')
    blood_urea: float = Field(..., ge=0,
        description='Blood urea (mg/dl)')
    serum_creatinine: float = Field(..., ge=0,
        description='Serum creatinine (mg/dl)')
    sodium: float = Field(...,
        description='Sodium level (mEq/L)')
    potassium: float = Field(...,
        description='Potassium level (mEq/L)')
    haemoglobin: float = Field(...,
        description='Hemoglobin level (gms)')
    packed_cell_volume: float = Field(...,
        description='Packed cell volume (%)')
    white_blood_cell_count: float = Field(...,
        description='White blood cell count (cells/cumm)')
    red_blood_cell_count: float = Field(...,
        description='Red blood cell count (millions/cumm)')

    # ── Medical History ───────────────────────────────────────────────
    hypertension: str = Field(..., description='Hypertension — yes or no')
    diabetes_mellitus: str = Field(..., description='Diabetes mellitus — yes or no')
    coronary_artery_disease: str = Field(..., description='Coronary artery disease — yes or no')
    appetite: str = Field(..., description='Appetite — good or poor')
    pedal_edema: str = Field(..., description='Pedal edema — yes or no')
    anemia: str = Field(..., description='Anemia — yes or no')

    # ── Advanced Clinical Markers ─────────────────────────────────────
    egfr: float = Field(..., ge=0,
        description='Estimated Glomerular Filtration Rate (eGFR)')
    urine_protein_creatinine_ratio: float = Field(..., ge=0,
        description='Urine protein-to-creatinine ratio')
    urine_output: float = Field(..., ge=0,
        description='Urine output (ml/day)')
    serum_albumin: float = Field(...,
        description='Serum albumin level')
    cholesterol: float = Field(...,
        description='Cholesterol level')
    parathyroid_hormone: float = Field(...,
        description='Parathyroid hormone (PTH) level')
    serum_calcium: float = Field(...,
        description='Serum calcium level')
    serum_phosphate: float = Field(...,
        description='Serum phosphate level')

    # ── Lifestyle & History ───────────────────────────────────────────
    family_history: str = Field(...,
        description='Family history of CKD — yes or no')
    smoking_status: str = Field(...,
        description='Smoking status — yes or no')
    bmi: float = Field(..., ge=0, le=100,
        description='Body Mass Index (BMI)')
    physical_activity: str = Field(...,
        description='Physical activity level — low, moderate, or high')
    duration_diabetes: float = Field(..., ge=0,
        description='Duration of diabetes mellitus (years)')
    duration_hypertension: float = Field(..., ge=0,
        description='Duration of hypertension (years)')

    # ── Additional Lab Results ────────────────────────────────────────
    cystatin_c: float = Field(...,
        description='Cystatin C level')
    urinary_sediment: str = Field(...,
        description='Urinary sediment microscopy results — normal or abnormal')
    crp_level: float = Field(...,
        description='C-reactive protein (CRP) level')
    il6_level: float = Field(...,
        description='Interleukin-6 (IL-6) level')