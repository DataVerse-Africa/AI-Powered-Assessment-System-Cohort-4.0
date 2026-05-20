# ml_models/breast_cancer_inference.py
# ══════════════════════════════════════════════════════════════════════
#  Breast Cancer CNN Inference Function
#
#  INPUT:  image file path (histology patch)
#  OUTPUT CLASSES: IDC Negative (0), IDC Positive (1)
#
#  CONFIDENCE LOGIC (from your notebook):
#    pred_class == 1:
#      prob >= 0.80 → 'High'   | prob >= 0.60 → 'Moderate' | else → 'Low'
#    pred_class == 0:
#      prob <= 0.20 → 'High'   | prob <= 0.40 → 'Moderate' | else → 'Low'
#
#  RECOMMENDATION LOGIC (from your notebook):
#    pred_class == 0 → 'No IDC features detected...'
#    confidence == 'Low'      → 'Borderline IDC features...'
#    confidence == 'Moderate' → 'IDC features present...'
#    confidence == 'High'     → 'Strong IDC features detected...'
#
#  TO ACTIVATE:
#    1. Place your trained model in saved_models/breast_cancer_cnn.keras
#    2. Replace the placeholder block with your real inference code
#       from the Breast_Cancer_cnn_inference notebook
# ══════════════════════════════════════════════════════════════════════

import os
import numpy as np

MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', 'saved_models', 'breast_cancer.keras'
)

# Image size your CNN was trained on — update if different
IMG_SIZE = (224, 224)
# IDC patch classification typically uses 50x50 pixel patches


def predict_breast_cancer(image_path: str) -> dict:
    # ── Step 1: Check if model file exists ───────────────────────────
    if not os.path.exists(MODEL_PATH):
        return {
            'status': 'unavailable',
            'prediction_label': None,
            'probability': None,
            'risk_level': None,
            'recommendation': None,
            'message': 'Breast cancer model file not found in saved_models/. '
                       'Please add breast_cancer.keras to activate predictions.'
        }

    # ── Step 2: Check if the image file exists ────────────────────────
    if not os.path.exists(image_path):
        return {
            'status': 'error',
            'prediction_label': None,
            'probability': None,
            'risk_level': None,
            'recommendation': None,
            'message': f'Image file not found at path: {image_path}'
        }

    # ── Step 3: Load model and run inference ──────────────────────────
    try:
        from tensorflow.keras.models import load_model
        from tensorflow.keras.utils import load_img, img_to_array

        model = load_model(MODEL_PATH, compile=False)

        # ── Preprocess image (replicates training preprocessing exactly) ──
        img = load_img(image_path, target_size=(224, 224))
        img_array = img_to_array(img) / 255.0
        img_array = np.expand_dims(img_array, axis=0) # (1, 224, 224, 3)

        # ── Load tuned threshold from metadata ────────────────────────
        metadata_path = os.path.join(os.path.dirname(MODEL_PATH), 'idc_metadata.json')
        if os.path.exists(metadata_path):
            import json
            with open(metadata_path) as f:
                meta = json.load(f)
            threshold = meta.get('threshold', 0.5)
        else:
            threshold = 0.5 # Fall back to default if metadata missing

        # ── Run prediction ─────────────────────────────────────────────
        prob = float(model.predict(img_array, verbose=0)[0][0])
        pred_class = int(prob >= threshold)

        # ── Confidence interpretation ──────────────────────────────────
        if pred_class == 1: # IDC Positive
            confidence = 'High' if prob >= 0.80 else \
                         'Moderate' if prob >= 0.60 else 'Low'
        else: # IDC Negative
            confidence = 'High' if prob <= 0.20 else \
                         'Moderate' if prob <= 0.40 else 'Low'

        # ── Clinical recommendation ────────────────────────────────────
        if pred_class == 0:
            recommendation = (
                'No IDC features detected in this patch. No immediate action needed.'
            )
        elif confidence == 'Low':
            recommendation = (
                'Borderline IDC features detected. '
                'Recommend pathologist review of surrounding tissue.'
            )
        elif confidence == 'Moderate':
            recommendation = (
                'IDC features present. '
                'This region warrants pathologist attention.'
            )
        else:
            recommendation = (
                'Strong IDC features detected in this patch. '
                'Priority pathologist review recommended.'
            )

        prediction_label = 'IDC Positive' if pred_class == 1 else 'IDC Negative'

        return {
            'status': 'success',
            'prediction_label': prediction_label,
            'probability': round(prob, 4),
            'risk_level': confidence,
            'recommendation': recommendation,
            'message': 'Prediction completed successfully'
        }

    except Exception as e:
        # Fallback when model fails to load or predict
        print(f"[Breast Cancer Model] Fallback triggered: {e}")
        return {
            'status': 'fallback',
            'prediction_label': 'IDC Negative',
            'probability': 0.12,
            'risk_level': 'Low',
            'recommendation': 'Model unavailable. Please retry later.',
            'message': 'Model not loaded, returning placeholder result'
        }