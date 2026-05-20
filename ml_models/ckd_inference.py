# ══════════════════════════════════════════════════════════════════════
# ml_models/ckd_inference.py
# ══════════════════════════════════════════════════════════════════════
#  CKD ML Inference Function
#
#  OUTPUT CLASSES: No_Disease, Low_Risk, Moderate_Risk, High_Risk, Severe_Disease
#
#  TO ACTIVATE:
#    1. Place your trained model file in saved_models/ckd.pkl
#    2. Replace the placeholder block below with your real inference code
#       from the CKD_ml_inference notebook
# ══════════════════════════════════════════════════════════════════════

"""
Kidney Disease Risk Prediction — Inference Pipeline
====================================================
Extracted from: Kidney_Disease_PRED.ipynb

Model : Logistic Regression (best_logistic_regression_model.joblib)
        Saved as a sklearn Pipeline (scaler + logreg in one object)
        — no separate scaler file needed.

Preprocessing pipeline (must replicate training exactly):
  1. Encode categorical columns (binary + ordinal mappings)
  2. Generate polynomial features (degree=2, include_bias=False)
  3. Scale + predict (handled inside the saved Pipeline)

Output classes:
  0 → No_Disease
  1 → Low_Risk
  2 → Moderate_Risk
  3 → High_Risk
  4 → Severe_Disease

Required files (in saved_models/):
    - best_logistic_regression_model.joblib

Dependencies:
    pip install scikit-learn joblib numpy pandas
"""

import os
import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import PolynomialFeatures


# =============================================================================
# CONFIGURATION
# =============================================================================
 
MODEL_PATH = "saved_models/kidney_disease_nn_model.h5"
 
# ── Categorical encodings (from notebook) ────────────────────────────────────
BINARY_MAPPINGS = {
    'Red blood cells in urine':                {'normal': 0, 'abnormal': 1},
    'Pus cells in urine':                      {'normal': 0, 'abnormal': 1},
    'Pus cell clumps in urine':                {'not present': 0, 'present': 1},
    'Bacteria in urine':                       {'not present': 0, 'present': 1},
    'Hypertension (yes/no)':                   {'no': 0, 'yes': 1},
    'Diabetes mellitus (yes/no)':              {'no': 0, 'yes': 1},
    'Coronary artery disease (yes/no)':        {'no': 0, 'yes': 1},
    'Appetite (good/poor)':                    {'poor': 0, 'good': 1},
    'Pedal edema (yes/no)':                    {'no': 0, 'yes': 1},
    'Anemia (yes/no)':                         {'no': 0, 'yes': 1},
    'Family history of chronic kidney disease':{'no': 0, 'yes': 1},
    'Smoking status':                          {'no': 0, 'yes': 1},
    'Urinary sediment microscopy results':     {'normal': 0, 'abnormal': 1},
}
 
ORDINAL_MAPPINGS = {
    'Physical activity level': {'low': 0, 'moderate': 1, 'high': 2},
}
 
# ── Exact column order from the dataset (must match training order) ───────────
FEATURE_ORDER = [
    'Age of the patient',
    'Blood pressure (mm/Hg)',
    'Specific gravity of urine',
    'Albumin in urine',
    'Sugar in urine',
    'Red blood cells in urine',
    'Pus cells in urine',
    'Pus cell clumps in urine',
    'Bacteria in urine',
    'Random blood glucose level (mg/dl)',
    'Blood urea (mg/dl)',
    'Serum creatinine (mg/dl)',
    'Sodium level (mEq/L)',
    'Potassium level (mEq/L)',
    'Hemoglobin level (gms)',
    'Packed cell volume (%)',
    'White blood cell count (cells/cumm)',
    'Red blood cell count (millions/cumm)',
    'Hypertension (yes/no)',
    'Diabetes mellitus (yes/no)',
    'Coronary artery disease (yes/no)',
    'Appetite (good/poor)',
    'Pedal edema (yes/no)',
    'Anemia (yes/no)',
    'Estimated Glomerular Filtration Rate (eGFR)',
    'Urine protein-to-creatinine ratio',
    'Urine output (ml/day)',
    'Serum albumin level',
    'Cholesterol level',
    'Parathyroid hormone (PTH) level',
    'Serum calcium level',
    'Serum phosphate level',
    'Family history of chronic kidney disease',
    'Smoking status',
    'Body Mass Index (BMI)',
    'Physical activity level',
    'Duration of diabetes mellitus (years)',
    'Duration of hypertension (years)',
    'Cystatin C level',
    'Urinary sediment microscopy results',
    'C-reactive protein (CRP) level',
    'Interleukin-6 (IL-6) level',
]
 
# ── Target label map (inverse — for decoding predictions) ────────────────────
LABEL_MAP = {
    0: 'No_Disease',
    1: 'Low_Risk',
    2: 'Moderate_Risk',
    3: 'High_Risk',
    4: 'Severe_Disease',
}
 
 
# =============================================================================
# INFERENCE FUNCTION
# =============================================================================
 
def predict_ckd(patient_data: dict) -> dict:
    """
    Predict kidney disease risk for a single patient.
 
    Parameters
    ----------
    patient_data : dict
        All 42 feature keys exactly as in the dataset (see feature list below).
        Categorical fields should be passed as raw strings e.g. 'yes'/'no',
        'normal'/'abnormal' — encoding is handled internally.
 
    Returns
    -------
    dict
        {
            'status':           'success' | 'unavailable' | 'error',
            'prediction_label': 'No_Disease' | 'Low_Risk' | 'Moderate_Risk'
                                | 'High_Risk' | 'Severe_Disease' | None,
            'probability':      float (0.0 – 1.0, confidence of predicted class),
            'risk_level':       'None' | 'Low' | 'Moderate' | 'High' | 'Severe',
            'recommendation':   str,
            'message':          str,
        }
    """
 
    # ── Step 1: Check model file exists ───────────────────────────────
    if not os.path.exists(MODEL_PATH):
        return {
            'status':           'unavailable',
            'prediction_label': None,
            'probability':      None,
            'risk_level':       None,
            'recommendation':   None,
            'message':          'Kidney disease model file not found in saved_models/. '
                                'Please add best_logistic_regression_model.joblib to activate predictions.'
        }
 
    try:
        # ── Step 2: Load the pipeline (scaler + model in one object) ──
        model = joblib.load(MODEL_PATH)
 
        # ── Step 3: Build a single-row DataFrame in exact training column order ──
        df = pd.DataFrame([{col: patient_data[col] for col in FEATURE_ORDER}])
 
        # ── Step 4: Encode categorical columns ────────────────────────
        for col, mapping in BINARY_MAPPINGS.items():
            if col in df.columns:
                df[col] = df[col].replace(mapping)
 
        for col, mapping in ORDINAL_MAPPINGS.items():
            if col in df.columns:
                df[col] = df[col].replace(mapping)
 
        # ── Step 5: Generate polynomial features (degree=2) ───────────
        # This replicates the PolynomialFeatures step done before training.
        # The pipeline's scaler was fitted on the polynomial-expanded data,
        # so we must expand first before passing to the pipeline.
        poly = PolynomialFeatures(degree=2, include_bias=False)
        features_poly = poly.fit_transform(df)   # (1, n_poly_features)
 
        # ── Step 6: Predict using the pipeline (scales + predicts) ────
        prediction  = int(model.predict(features_poly)[0])
        probabilities = model.predict_proba(features_poly)[0]
        probability = float(probabilities[prediction])   # confidence of predicted class
 
        prediction_label = LABEL_MAP[prediction]
 
        # ── Step 7: Map to simplified risk level ──────────────────────
        risk_level_map = {
            'No_Disease':      'None',
            'Low_Risk':        'Low',
            'Moderate_Risk':   'Moderate',
            'High_Risk':       'High',
            'Severe_Disease':  'Severe',
        }
        risk_level = risk_level_map[prediction_label]
 
        # ── Step 8: Clinical recommendation ───────────────────────────
        recommendation_map = {
            'No_Disease':     'No kidney disease detected. Continue routine health check-ups '
                              'and maintain a healthy lifestyle.',
            'Low_Risk':       'Low risk of kidney disease detected. Monitor kidney function '
                              'periodically and manage any underlying conditions.',
            'Moderate_Risk':  'Moderate kidney disease risk. Recommend consultation with a '
                              'nephrologist and closer monitoring of kidney function markers.',
            'High_Risk':      'High kidney disease risk detected. Prompt nephrology referral '
                              'and comprehensive renal assessment strongly advised.',
            'Severe_Disease': 'Severe kidney disease indicated. Immediate medical attention '
                              'and nephrology consultation required.',
        }
        recommendation = recommendation_map[prediction_label]
 
        return {
            'status':           'success',
            'prediction_label': prediction_label,
            'probability':      round(probability, 4),
            'risk_level':       risk_level,
            'recommendation':   recommendation,
            'message':          'Prediction completed successfully'
        }
 
    except KeyError as e:
        return {
            'status':           'error',
            'prediction_label': None,
            'probability':      None,
            'risk_level':       None,
            'recommendation':   None,
            'message':          f'Missing required field in patient_data: {e}'
        }
    except Exception as e:
        return {
            'status':           'error',
            'prediction_label': None,
            'probability':      None,
            'risk_level':       None,
            'recommendation':   None,
            'message':          f'Kidney disease model error: {str(e)}'
        }
