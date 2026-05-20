# ml_models/pneumonia_inference.py
# ══════════════════════════════════════════════════════════════════════
#  Pneumonia CNN Inference Function
#
#  INPUT:  image file path (chest X-ray)
#  OUTPUT CLASSES: Normal, Pneumonia
#
#  TO ACTIVATE:
#    1. Place your trained model in saved_models/pneumonia_cnn.keras
#       (or pneumonia_cnn.h5 — update MODEL_PATH below accordingly)
#    2. Replace the placeholder block with your real inference code
#       from the Pneumonia_cnn_inference notebook
# ══════════════════════════════════════════════════════════════════════

import os
import numpy as np

# ── Path to saved model and metadata ──────────────────────────────────────────
MODEL_PATH    = os.path.join('saved_models', 'chest_xray_cnn_best.keras')
METADATA_PATH = os.path.join('saved_models', 'chest_xray_metadata.json')


def predict_pneumonia(image_path: str) -> dict:
    """
    Run inference on a chest X-ray image using the EfficientNetB0-based model.

    Args:
        image_path: Absolute or relative path to the input image file.

    Returns:
        A dict with keys:
            status           – 'success' | 'unavailable' | 'error'
            prediction_label – 'PNEUMONIA' | 'NORMAL' | None
            probability      – float in [0, 1] (raw sigmoid output) | None
            risk_level       – 'Low' | 'Moderate' | 'High' | None
            recommendation   – Clinical guidance string | None
            message          – Human-readable status message
    """

    # ── Step 1: Check if model file exists ────────────────────────────────────
    if not os.path.exists(MODEL_PATH):
        return {
            'status':           'unavailable',
            'prediction_label': None,
            'probability':      None,
            'risk_level':       None,
            'recommendation':   None,
            'message': (
                'Chest X-ray model file not found in saved_models/. '
                'Please add chest_xray_cnn_best.keras to activate predictions.'
            ),
        }

    # ── Step 2: Check if the image file exists ────────────────────────────────
    if not os.path.exists(image_path):
        return {
            'status':           'error',
            'prediction_label': None,
            'probability':      None,
            'risk_level':       None,
            'recommendation':   None,
            'message':          f'Image file not found at path: {image_path}',
        }

    # ── Step 3: Load model and run inference ──────────────────────────────────
    try:
        from tensorflow.keras.models import load_model
        from tensorflow.keras.utils import load_img, img_to_array
        from tensorflow.keras.applications.efficientnet import preprocess_input

        model = load_model(MODEL_PATH)

        # ── Preprocess image (replicates training preprocessing exactly) ──────
        # Training used EfficientNetB0 preprocess_input (scales to [-1, 1]),
        # NOT a simple /255 normalisation.
        img       = load_img(image_path, target_size=(224, 224))
        img_array = img_to_array(img)                       # (224, 224, 3)
        img_array = preprocess_input(img_array)             # EfficientNet scaling
        img_array = np.expand_dims(img_array, axis=0)       # (1, 224, 224, 3)

        # ── Load tuned threshold from metadata ────────────────────────────────
        if os.path.exists(METADATA_PATH):
            import json
            with open(METADATA_PATH) as f:
                meta = json.load(f)
            threshold = meta.get('threshold', 0.6)
        else:
            threshold = 0.6   # Fall back to training-time default

        # ── Run prediction ────────────────────────────────────────────────────
        prob       = float(model.predict(img_array, verbose=0)[0][0])
        pred_class = int(prob >= threshold)   # 1 → PNEUMONIA, 0 → NORMAL

        # ── Confidence interpretation ─────────────────────────────────────────
        if pred_class == 1:   # PNEUMONIA
            confidence = (
                'High'     if prob >= 0.80 else
                'Moderate' if prob >= 0.60 else
                'Low'
            )
        else:                 # NORMAL
            confidence = (
                'High'     if prob <= 0.20 else
                'Moderate' if prob <= 0.40 else
                'Low'
            )

        # ── Clinical recommendation ───────────────────────────────────────────
        if pred_class == 0:
            recommendation = (
                'No pneumonia features detected. '
                'Chest X-ray appears normal. No immediate action needed.'
            )
        elif confidence == 'Low':
            recommendation = (
                'Borderline pneumonia features detected. '
                'Recommend radiologist review and clinical correlation.'
            )
        elif confidence == 'Moderate':
            recommendation = (
                'Pneumonia features present. '
                'This image warrants radiologist attention and follow-up.'
            )
        else:
            recommendation = (
                'Strong pneumonia features detected. '
                'Priority radiologist review and prompt clinical management recommended.'
            )

        prediction_label = 'PNEUMONIA' if pred_class == 1 else 'NORMAL'

        return {
            'status':           'success',
            'prediction_label': prediction_label,
            'probability':      round(prob, 4),
            'risk_level':       confidence,   # Low / Moderate / High
            'recommendation':   recommendation,
            'message':          'Prediction completed successfully',
        }

    except Exception as e:
        return {
            'status':           'error',
            'prediction_label': None,
            'probability':      None,
            'risk_level':       None,
            'recommendation':   None,
            'message':          f'Chest X-ray model error: {str(e)}',
        }