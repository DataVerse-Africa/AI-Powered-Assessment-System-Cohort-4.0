# ml_models/diabetes_inference.py
# ══════════════════════════════════════════════════════════════════════
#  Diabetes ML Inference Function
#
#  OUTPUT CLASSES: Low, Moderate, High
#
#  TO ACTIVATE:
#    1. Place your trained model file in saved_models/diabetes.pkl
#    2. Replace the placeholder block below with your real inference code
#    3. Ensure your function accepts a dict and returns a dict
#       matching the structure shown in the return block below
# ══════════════════════════════════════════════════════════════════════

import os
import joblib
import numpy as np

# Paths to model and scaler
MODEL_PATH  = os.path.join(
    os.path.dirname(__file__),
    '..', 'saved_models', 'diabetes_rf_model.joblib'
)

SCALER_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', 'saved_models', 'diabetes_scaler.pkl'
)


def predict_diabetes(patient_data: dict) -> dict:
    # ── Step 1: Check if model file exists ───────────────────────────
    if not os.path.exists(MODEL_PATH):
        # Model file not found — return placeholder response.
        # The API will still return a clean JSON response instead
        # of crashing with a 500 error.
        # Once diabetes.pkl is placed in saved_models/, this block
        # is skipped automatically and real predictions are returned.
        return {
            'status': 'unavailable',
            'prediction_label': None,
            'probability': None,
            'risk_level': None,
            'recommendation': None,
            'message': 'Diabetes model file not found in saved_models/. '
                       'diabetes_rf_model.joblib to activate predictions.'
        }

    # ── Step 2: Load the model and run inference ──────────────────────
    try:
        model  = joblib.load(MODEL_PATH)
        scaler = joblib.load(SCALER_PATH)

        # Original feature order (must match training column order)
        feature_order = [
            'Pregnancies', 'Glucose', 'BloodPressure', 'SkinThickness',
            'Insulin', 'BMI', 'DiabetesPedigreeFunction', 'Age'
        ]

        # Features where 0 is biologically invalid → treated as missing
        medical_features = ['Glucose', 'BloodPressure', 'SkinThickness', 'Insulin', 'BMI']

        # Imputation values computed from training set
        # (replace with exact values printed from your notebook)
        imputation_values = {
            'Glucose':       121.68,   # mean
            'BloodPressure':  72.40,   # mean
            'SkinThickness':  29.15,   # median
            'Insulin':        79.80,   # median
            'BMI':            32.46,   # mean
        }

        # Replace biologically invalid zeros with NaN and track missing flags
        raw = {feat: patient_data[feat] for feat in feature_order}
        missing_flags = {}

        for feat in medical_features:
            missing_flags[f'{feat}_missing'] = int(raw[feat] == 0)
            if raw[feat] == 0:
                raw[feat] = np.nan

        # Impute NaNs using training-set statistics
        for feat, fill_value in imputation_values.items():
            if np.isnan(raw[feat]):
                raw[feat] = fill_value

        # Assemble full feature vector (original features + missing indicators)
        original_values  = [raw[f] for f in feature_order]
        indicator_values = [missing_flags[f'{f}_missing'] for f in medical_features]
        features_array   = np.array([original_values + indicator_values])  # (1, 13)

        # Scale only the original 8 numerical columns (indicators excluded)
        features_array[:, :len(feature_order)] = scaler.transform(
            features_array[:, :len(feature_order)]
        )

        # Run prediction
        prediction  = int(model.predict(features_array)[0])
        probability = float(model.predict_proba(features_array)[0][1])  # P(diabetic)

        prediction_label = 'Diabetic'     if prediction == 1 else 'Non-Diabetic'
        risk_level       = 'High'         if prediction == 1 else 'Low'

        recommendation = (
            'High diabetes risk detected. Please consult a healthcare provider '
            'for a full clinical assessment and personalised management plan.'
            if prediction == 1 else
            'No diabetes risk detected. Maintain a healthy lifestyle, '
            'balanced diet, and regular exercise to stay low-risk.'
        )

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
            'status': 'error',
            'prediction_label': None,
            'probability': None,
            'risk_level': None,
            'recommendation': None,
            'message': f'Diabetes model error: {str(e)}'
        }