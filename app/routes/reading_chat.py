from __future__ import annotations

import json
import logging
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Literal

from ..deck42 import get_deck
from ..reading_memory import append_message, get_history, reset_reading
from ..reading_chat_llm import generate_chat_response

log = logging.getLogger("tarot42.reading_chat")
router = APIRouter()
deck = get_deck()

OverlayId = Literal["WIND","RAIN","THUNDER","LIGHTNING","FIRE","FOG","DROUGHT","TIDE"]

class ReadingCard(BaseModel):
    id: str
    reversed: bool = False

class ReadingContext(BaseModel):
    cards: List[ReadingCard] = Field(..., min_length=1, max_length=10)
    overlay: Optional[OverlayId] = None

class ReadingChatRequest(BaseModel):
    reading_id: str = Field(..., min_length=1, max_length=100)
    reading: ReadingContext
    message: str = Field(..., min_length=1, max_length=2000)

class ReadingChatResponse(BaseModel):
    answer: str
    reading_id: str
    used_cards: List[Dict[str, Any]]
    history: List[Dict[str, str]]

@router.post("/reading/ask", response_model=ReadingChatResponse)
def ask_about_reading(req: ReadingChatRequest):
    log.info("reading/ask payload=%s", json.dumps(req.model_dump(), ensure_ascii=False))

    # validate overlay
    if req.reading.overlay is not None:
        valid = {o["id"] for o in deck["overlays"]}
        if req.reading.overlay not in valid:
            raise HTTPException(status_code=400, detail=f"Unknown overlay: {req.reading.overlay}")

    # interpret cards
    interpreted: List[Dict[str, Any]] = []
    for rc in req.reading.cards:
        try:
            c = None
            for card in deck["cards"]:
                if card.get("id") == rc.id:
                    c = card
                    break
            if c is None:
                raise HTTPException(status_code=404, detail=f"Unknown card_id: {rc.id}")
        except Exception:
            raise HTTPException(status_code=404, detail=f"Unknown card_id: {rc.id}")

        mode = "Storm" if rc.reversed else "Clear"
        body = c["storm"] if rc.reversed else c["clear"]
        overlay_line = c.get("overlays", {}).get(req.reading.overlay) if req.reading.overlay else None

        interpreted.append({
            "id": c["id"],
            "animal": c["animal"],
            "title": c["title"],
            "suit": c["suit"],
            "rank": c["rank"],
            "mode": mode,
            "key_message": c.get("key_message"),
            "overlay": req.reading.overlay,
            "overlay_line": overlay_line,
            "body": body,
        })

    # get conversation history
    history = get_history(req.reading_id, limit=20)
    
    # generate response using LLM or fallback
    answer = generate_chat_response(interpreted, req.reading.overlay, history, req.message)
    
    # store user message
    append_message(req.reading_id, "user", req.message, interpreted, req.reading.overlay)
    
    # store assistant response
    append_message(req.reading_id, "assistant", answer, interpreted, req.reading.overlay)

    return {
        "answer": answer,
        "reading_id": req.reading_id,
        "used_cards": interpreted,
        "history": history + [{"role": "user", "content": req.message}, {"role": "assistant", "content": answer}]
    }

@router.post("/reading/reset")
def reset_reading_endpoint(req: Dict[str, str]):
    reading_id = req.get("reading_id")
    if not reading_id:
        raise HTTPException(status_code=400, detail="reading_id required")
    
    reset_reading(reading_id)
    return {"ok": True}
