import os, json
import numpy as np
import cv2
import base64
import io
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.app.models import ReadingRequest, ReadingResponse, ChatRequest, ChatResponse, ScanResponse
from backend.app.scan import SigilMatcher
from backend.app import storage as legacy_storage
from backend.app.reading import fallback_reading
from backend.app.ai import generate_reading_ai, chat_about_reading_ai
from backend.app.routes.deck42_routes import router as deck42_router
from backend.app.routes.reading_routes import router as reading_router
from backend.app.routes.reading_chat import router as reading_chat_router
from backend.app.deck42 import deck_for_legacy_api
from backend.app.deck42 import get_card as deck42_get_card
from backend.app.deck42 import get_overlay as deck42_get_overlay
from backend.app.deck42 import render_interpretation as deck42_render_interpretation
from backend.app.deck42 import card_id_for_legacy_asset_id

app = FastAPI(title="Tarot42 Sigil Scanner", version="0.1.0")

app.include_router(deck42_router)
app.include_router(reading_router)
app.include_router(reading_chat_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

REPO_ROOT = str(Path(__file__).resolve().parents[2])
SIGIL_DIR = os.getenv("SIGIL_DIR", os.path.join(REPO_ROOT, "deck", "sigils"))
if SIGIL_DIR and not os.path.isabs(SIGIL_DIR):
    SIGIL_DIR = os.path.join(REPO_ROOT, SIGIL_DIR)
SCAN_MIN_MATCHES = int(os.getenv("SCAN_MIN_MATCHES", "18"))
SCAN_RATIO_TEST = float(os.getenv("SCAN_RATIO_TEST", "0.75"))

try:
    matcher = SigilMatcher(SIGIL_DIR, ratio_test=SCAN_RATIO_TEST, min_matches=SCAN_MIN_MATCHES)
except Exception:
    matcher = None

# Static serving: deck assets + frontend
app.mount("/deck-assets", StaticFiles(directory=os.path.join(REPO_ROOT, "deck")), name="deck_assets")
app.mount("/static", StaticFiles(directory=os.path.join(REPO_ROOT, "frontend")), name="frontend_static")

@app.get("/")
def index():
    return FileResponse(os.path.join(REPO_ROOT, "frontend", "index.html"))

@app.get("/app.js")
def app_js():
    return FileResponse(os.path.join(REPO_ROOT, "frontend", "app.js"))

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/debug/env")
def debug_env():
    """Debug endpoint to check environment variables"""
    return {
        "openai_api_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "openai_api_key_prefix": os.getenv("OPENAI_API_KEY", "")[:10] + "..." if os.getenv("OPENAI_API_KEY") else None,
        "env_file_loaded": True
    }

@app.get("/deck")
def deck():
    return deck_for_legacy_api()


@app.post("/interpret")
def interpret(req: dict):
    overlay_id = (req.get("overlay_id") or os.getenv("DECK42_OVERLAY") or "WIND")
    try:
        overlay = deck42_get_overlay(overlay_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Unknown overlay_id: {overlay_id}")

    positions = req.get("positions") or []
    out_positions = []
    for p in positions:
        card_id = p.get("card_id")
        if not card_id:
            raise HTTPException(status_code=400, detail="Missing card_id")
        try:
            card = deck42_get_card(card_id)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Unknown card_id: {card_id}")
        out_positions.append(
            deck42_render_interpretation(
                slot_label=p.get("slot_label") or "Position",
                card=card,
                overlay=overlay,
                reversed_mode=bool(p.get("reversed")),
            )
        )

    return {
        "spread": req.get("spread") or "legacy",
        "overlay": overlay,
        "positions": out_positions,
        "key_message": " / ".join([pos["key_message"] for pos in out_positions if pos.get("key_message")]),
    }

@app.post("/scan", response_model=ScanResponse)
async def scan(image: UploadFile = File(...)):
    if matcher is None:
        raise HTTPException(status_code=503, detail="Sigil matcher unavailable")
    raw = await image.read()
    arr = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image")

    raw_id, conf, matches, debug = matcher.match(frame)
    card_id = raw_id
    if raw_id:
        try:
            card_id = card_id_for_legacy_asset_id(raw_id)
        except Exception:
            card_id = raw_id
    ok = card_id is not None
    return ScanResponse(card_id=card_id, confidence=conf, matches=matches, ok=ok, debug=debug)

@app.post("/reading", response_model=ReadingResponse)
def reading(req: ReadingRequest):
    deck = deck_for_legacy_api()
    sid = legacy_storage.new_session()
    placements = [p.model_dump() for p in req.placements]
    style = req.style
    try:
        result = generate_reading_ai(deck, placements, req.spread_type, style, req.question, req.overlay_id)
    except Exception as e:
        # Fail safe: never break the app if AI is down/misconfigured
        result = fallback_reading(deck, placements, style)

    legacy_storage.set_reading(sid, {
        "spread_type": req.spread_type,
        "style": style,
        "question": req.question,
        "placements": placements,
        "result": result
    })

    return ReadingResponse(
        session_id=sid,
        summary=result["summary"],
        card_notes=result["card_notes"],
        advice=result["advice"]
    )

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        s = legacy_storage.load_session(req.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    legacy_storage.append_chat(req.session_id, "user", req.message)

    reading = s.get("reading") or {}
    style = (req.style or reading.get("style") or "seer")
    chat_history = s.get("chat") or []

    try:
        reply = chat_about_reading_ai(deck_for_legacy_api(), reading, chat_history, style, req.message)
    except Exception as e:
        # Enhanced fail safe: more contextual and helpful
        result = (reading.get("result") or {})
        card_notes = result.get("card_notes") or []
        advice = result.get("advice") or []
        
        # Try to provide card-specific fallback
        message_lower = req.message.lower()
        card_specific_response = None
        
        for note in card_notes:
            if (note.get("card_id", "").lower() in message_lower or 
                note.get("slot_label", "").lower() in message_lower):
                card_specific_response = (
                    f"Regarding the {note.get('slot_label', 'Card')}:\n\n"
                    f"{note.get('note', 'This card offers guidance for your current situation.')}\n\n"
                    "How does this resonate with what you're experiencing?"
                )
                break
        
        if card_specific_response:
            reply = card_specific_response
        else:
            reply = (
                "Let's explore your reading more deeply.\n\n"
                "You can ask about:\n"
                "- Specific cards in your spread\n"
                "- How cards interact with each other\n"
                "- Practical guidance from the reading\n"
                "- Personal reflections on the patterns\n\n"
                "What aspect of your reading would you like to explore?"
            )


    legacy_storage.append_chat(req.session_id, "assistant", reply)
    return ChatResponse(session_id=req.session_id, reply=reply)

@app.post("/clarify")
async def clarify_card(req: dict):
    try:
        deck = deck_for_legacy_api()
        original_card = None
        clarifier_card = None
        
        # Find cards in deck
        for card in deck["cards"]:
            if card["id"] == req.get("original_card_id"):
                original_card = card
            if card["id"] == req.get("clarifier_card_id"):
                clarifier_card = card
        
        if not original_card or not clarifier_card:
            raise HTTPException(status_code=400, detail="Invalid card IDs")
        
        # Use AI if available, otherwise fallback
        try:
            from backend.app.ai import generate_reading_ai
            
            # Create a mini-spread for clarifier reading
            clarifier_placements = [
                {"slot_index": 0, "slot_label": "Original Card", "card_id": req.get("original_card_id"), "reversed": False},
                {"slot_index": 1, "slot_label": "Clarifier Card", "card_id": req.get("clarifier_card_id"), "reversed": False}
            ]
            
            result = generate_reading_ai(deck, clarifier_placements, "clarifier", req.get("style", "seer"))
            interpretation = result["summary"]
            
        except Exception:
            # Fallback interpretation
            interpretation = f"""The {clarifier_card['name']} clarifies the {original_card['name']} by bringing focus to {clarifier_card.get('keywords', ['specific aspects'])[0] if clarifier_card.get('keywords') else 'key details'}. 

This suggests that the original energy of {original_card['name']} can be understood through the lens of {clarifier_card['name']}, highlighting {clarifier_card.get('teaches', 'new perspectives')}.

Consider how this relationship between the cards offers practical guidance for your situation."""
        
        return {
            "original_card": req.get("original_card_id"),
            "clarifier_card": req.get("clarifier_card_id"),
            "interpretation": interpretation,
            "position": req.get("original_position")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clarifier reading failed: {str(e)}")

@app.post("/voice/synthesize")
async def synthesize_voice(req: dict):
    """
    Synthesize speech from text using OpenAI TTS.
    Returns base64-encoded audio data.
    """
    try:
        text = req.get("text", "").strip()
        voice = req.get("voice", "nova")  # Default to nova (natural, female)
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        # Validate voice choice
        valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        if voice not in valid_voices:
            voice = "nova"
        
        # Check OpenAI availability
        if not os.getenv("OPENAI_API_KEY"):
            raise HTTPException(status_code=503, detail="Voice synthesis not available - OpenAI API key not configured")
        
        client = OpenAI()
        
        # Generate speech
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text[:4096]  # Limit text length
        )
        
        # Convert to base64 for JSON response
        audio_buffer = io.BytesIO()
        for chunk in response.iter_bytes(chunk_size=1024):
            audio_buffer.write(chunk)
        
        audio_data = audio_buffer.getvalue()
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
        
        return {
            "audio_base64": audio_base64,
            "format": "mp3",
            "voice": voice,
            "text_length": len(text)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice synthesis failed: {str(e)}")

@app.get("/voice/voices")
async def get_available_voices():
    """
    Return list of available TTS voices with descriptions.
    """
    return {
        "voices": [
            {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced voice"},
            {"id": "echo", "name": "Echo", "description": "Male voice, suitable for reflective content"},
            {"id": "fable", "name": "Fable", "description": "British accent, storytelling style"},
            {"id": "onyx", "name": "Onyx", "description": "Deep male voice, authoritative"},
            {"id": "nova", "name": "Nova", "description": "Natural female voice, default choice"},
            {"id": "shimmer", "name": "Shimmer", "description": "Bright, expressive female voice"}
        ],
        "default": "nova"
    }

@app.post("/voice/transcribe")
async def transcribe_voice(audio: UploadFile = File(...)):
    """Transcribe uploaded audio to text using OpenAI Whisper."""
    try:
        if not os.getenv("OPENAI_API_KEY"):
            raise HTTPException(status_code=503, detail="Transcription not available - OpenAI API key not configured")

        raw = await audio.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Empty audio upload")

        # OpenAI SDK expects a file-like object with a name
        buf = io.BytesIO(raw)
        buf.name = audio.filename or "audio.webm"

        client = OpenAI()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
        )

        text = (getattr(transcript, "text", None) or "").strip()
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
