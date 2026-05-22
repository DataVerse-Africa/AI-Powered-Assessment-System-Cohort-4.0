# routers/chat.py
# ══════════════════════════════════════════════════════════════════════
#  AI Chatbot Routes — Groq LLM Integration
#
#  Three endpoints:
#    POST   /api/user/chat/{session_id} — send message, get AI response
#    GET    /api/user/chat/{session_id} — get full conversation history
#    DELETE /api/user/chat/{session_id} — clear conversation for session
#
#  Design principles:
#    - Session-based: every conversation is tied to a clinical session
#    - Context-aware: all predictions from the session are injected
#      into the LLM system prompt automatically
#    - Memory: full conversation history is passed on every request
#      so the LLM remembers what was said earlier
#    - Safety: system prompt enforces recommendation-only framing
#      and always reminds the clinician to consult a professional
#    - Audit: every message is saved to the chat_messages table
#
#  Requirements:
#    pip install groq
#    Add GROQ_API_KEY to your .env file
# ══════════════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from database.session import get_db
from database.models import ClinicalSession, ChatMessage, Prediction, User
from auth.dependencies import get_current_user

from schemas.chat_schemas import (
    ChatMessageRequest,
    ChatResponse,
    ChatHistoryResponse,
    ChatMessageResponse,
)

from groq import Groq
# Groq is the official Python client for the Groq API.
# Install with: pip install groq
# Import it here — if GROQ_API_KEY is not set, the client will raise
# an error when the first request is made, not at import time.

import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
# Read the Groq API key from .env
# If this is None, the chatbot endpoints will return a clear error
# rather than crashing with an unhandled exception

GROQ_MODEL = os.getenv('GROQ_MODEL')
# The Groq model to use.
# Options available on Groq free tier:
#   llama3-8b-8192   → fast, good quality, 8k context window
#   llama3-70b-8192  → slower, better quality, 8k context window
#   mixtral-8x7b-32768 → good quality, 32k context window (more history)
# We use llama3-8b-8192 as the default — fast and reliable.
# Change this value to switch models with no other code changes needed.


router = APIRouter(
    prefix='/api/user/chat',
    tags=['AI Chatbot']
)


# ══════════════════════════════════════════════════════════════════════
#  HELPER — build_system_prompt()
#
#  Builds the LLM system prompt for a specific session.
#  This is injected as the first message in every Groq API call.
#
#  The system prompt does three things:
#    1. Defines the chatbot's role and safety boundaries
#    2. Provides patient context (name, age, gender, reason for visit)
#    3. Lists all prediction results from this session
#
#  The system prompt is NEVER stored in the database — it is rebuilt
#  fresh on every request from live database data. This ensures that
#  if a new prediction is added to the session, the chatbot
#  immediately has access to it without any extra logic.
# ══════════════════════════════════════════════════════════════════════

def build_system_prompt(session: ClinicalSession) -> str:

    # ── Patient context ───────────────────────────────────────────────
    patient_info = f"""Patient Name: {session.patient_name}
Patient Age: {session.patient_age or 'Not provided'}
Patient Gender: {session.patient_gender or 'Not provided'}
Reason for Visit: {session.reason_for_visit or 'Not provided'}
Session Status: {session.status}
Session Date: {session.created_at.strftime('%B %d, %Y')}"""

    # ── Prediction results ────────────────────────────────────────────
    if session.predictions:
        prediction_lines = []
        for p in session.predictions:
            line = (
                f"  - Model: {p.modelname.upper()}\n"
                f"    Result: {p.prediction_label or 'Unavailable'}\n"
                f"    Risk Level: {p.risk_level or 'Unavailable'}\n"
                f"    Confidence: {f'{p.probability:.0%}' if p.probability else 'Unavailable'}\n"
                f"    Recommendation: {p.recommendation or 'Unavailable'}"
            )
            prediction_lines.append(line)
        predictions_text = '\n'.join(prediction_lines)
    else:
        predictions_text = '  No predictions have been run in this session yet.'

    # ── Build the full system prompt ──────────────────────────────────
    system_prompt = f"""You are a clinical decision support assistant for the Patient Assessment System. Your role is to help clinical staff understand and act on AI-generated disease risk assessments.

IMPORTANT SAFETY RULES — YOU MUST ALWAYS FOLLOW THESE:
1. You are a RECOMMENDATION ENGINE, not a diagnostic tool. Never make a definitive diagnosis.
2. Always remind the clinician to consult a qualified medical professional for any final diagnosis, treatment decision, or urgent health concern.
3. Base your responses primarily on the prediction results provided below.
4. Be compassionate, clear, and clinically appropriate in your language.
5. If asked something outside clinical guidance (politics, personal advice, etc.), politely redirect to the clinical context.
6. Respond in English only.

CURRENT PATIENT CONTEXT:
{patient_info}

PREDICTION RESULTS FROM THIS SESSION:
{predictions_text}

Use the above patient data and prediction results as the basis for your responses. When a clinician asks a question, interpret it in the context of this specific patient and these specific results. Always conclude sensitive recommendations with a reminder to seek professional medical consultation."""

    return system_prompt


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 1 — SEND MESSAGE AND GET AI RESPONSE
#  POST /api/user/chat/{session_id}
#
#  Flow:
#    1. Validate session belongs to this clinician
#    2. Load full conversation history from database
#    3. Build system prompt from session + predictions
#    4. Send to Groq API: system prompt + history + new message
#    5. Save both user message and AI reply to database
#    6. Return the AI reply
# ══════════════════════════════════════════════════════════════════════

@router.post('/{session_id}', response_model=ChatResponse)
def send_message(
    session_id: int,
    request: ChatMessageRequest,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ── Step 1: Validate GROQ_API_KEY is set ─────────────────────────
    if not GROQ_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Chatbot is not configured. Add GROQ_API_KEY to your .env file.'
        )

    # ── Step 2: Validate the session ─────────────────────────────────
    session = db.query(ClinicalSession).filter(
        ClinicalSession.id == session_id,
        ClinicalSession.user_id == current_user.id
        # Clinician can only chat about their own sessions
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Session {session_id} not found'
        )

    # ── Step 3: Load conversation history from database ───────────────
    history = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()
    # Order oldest first — this is the correct order for LLM history.
    # The LLM reads the conversation from top (oldest) to bottom (newest).

    # ── Step 4: Build the Groq API messages list ──────────────────────
    # The Groq API expects a list of message dicts in this format:
    # [
    #   {"role": "system",    "content": "..."},  <- system prompt (always first)
    #   {"role": "user",      "content": "..."},  <- first clinician message
    #   {"role": "assistant", "content": "..."},  <- first LLM reply
    #   {"role": "user",      "content": "..."},  <- second clinician message
    #   ...
    #   {"role": "user",      "content": "..."},  <- current new message (last)
    # ]

    messages = [
        {
            'role': 'system',
            'content': build_system_prompt(session)
            # Built fresh on every request — always reflects latest predictions
        }
    ]

    # Add existing conversation history
    for msg in history:
        messages.append({
            'role': msg.role,         # 'user' or 'assistant'
            'content': msg.content    # the actual message text
        })

    # Add the new user message at the end
    messages.append({
        'role': 'user',
        'content': request.message
    })

    # ── Step 5: Call the Groq API ─────────────────────────────────────
    try:
        client = Groq(api_key=GROQ_API_KEY)
        # Create the Groq client with the API key from .env

        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            # The model we defined at the top of this file
            messages=messages,
            # The full conversation — system prompt + history + new message
            temperature=0.7,
            # Controls creativity vs consistency:
            # 0.0 = very deterministic, same answer every time
            # 1.0 = very creative, more varied answers
            # 0.7 = balanced — good for clinical recommendations
            max_tokens=1024,
            # Maximum length of the AI response.
            # 1024 tokens ≈ roughly 750-800 words — enough for a
            # detailed clinical recommendation.
        )

        assistant_reply = completion.choices[0].message.content
        # Extract the AI response text from the API response object.
        # completion.choices[0] → first (and only) completion choice
        # .message.content → the text of the assistant's reply

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Groq API error: {str(e)}'
            # Catches network errors, invalid API key, model errors, etc.
            # Returns a clean 503 error instead of crashing the server.
        )

    # ── Step 6: Save user message to database ─────────────────────────
    user_message = ChatMessage(
        session_id=session_id,
        user_id=current_user.id,
        role='user',
        content=request.message
    )
    db.add(user_message)

    # ── Step 7: Save assistant reply to database ──────────────────────
    assistant_message = ChatMessage(
        session_id=session_id,
        user_id=current_user.id,
        role='assistant',
        content=assistant_reply
    )
    db.add(assistant_message)
    db.commit()
    # Single commit saves both messages together.

    # ── Step 8: Return response ───────────────────────────────────────
    total_messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).count()

    return ChatResponse(
        session_id=session_id,
        assistant_reply=assistant_reply,
        total_messages=total_messages
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 2 — GET CONVERSATION HISTORY
#  GET /api/user/chat/{session_id}
#
#  Returns the full conversation history for a session.
#  Useful for the frontend to display the conversation log
#  when a clinician returns to a session they started earlier.
# ══════════════════════════════════════════════════════════════════════

@router.get('/{session_id}', response_model=ChatHistoryResponse)
def get_chat_history(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ── Validate session ──────────────────────────────────────────────
    session = db.query(ClinicalSession).filter(
        ClinicalSession.id == session_id,
        ClinicalSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Session {session_id} not found'
        )

    # ── Load all messages ─────────────────────────────────────────────
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()
    # Oldest first — chronological order for display

    return ChatHistoryResponse(
        session_id=session_id,
        patient_name=session.patient_name,
        total_messages=len(messages),
        messages=[
            ChatMessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at.isoformat()
            )
            for m in messages
        ]
    )


# ══════════════════════════════════════════════════════════════════════
#  ENDPOINT 3 — CLEAR CONVERSATION HISTORY
#  DELETE /api/user/chat/{session_id}
#
#  Permanently deletes all chat messages for a specific session.
#  Use this to start a fresh conversation about the same session
#  without losing the session's prediction data.
#
#  Note: This only deletes chat_messages rows.
#  The session and its predictions are NOT affected.
#  Returns 204 No Content on success.
# ══════════════════════════════════════════════════════════════════════

@router.delete('/{session_id}', status_code=status.HTTP_204_NO_CONTENT)
def clear_chat_history(
    session_id: int,
    db: DBSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # ── Validate session ──────────────────────────────────────────────
    session = db.query(ClinicalSession).filter(
        ClinicalSession.id == session_id,
        ClinicalSession.user_id == current_user.id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Session {session_id} not found'
        )

    # ── Delete all messages for this session ──────────────────────────
    deleted_count = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).delete()
    # .delete() returns the number of rows deleted.
    # This deletes ALL chat messages for the session in one query.

    db.commit()

    # 204 No Content — no response body needed
    return None
