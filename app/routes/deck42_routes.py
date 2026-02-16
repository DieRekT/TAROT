"""FastAPI routes for the Tarot42 AU Fauna deck.

Endpoints:
- GET /deck42/meta
- GET /deck42/cards
- GET /deck42/cards/{card_id}
- GET /deck42/overlays
- POST /deck42/interpret

Designed to be imported and included from your main FastAPI app.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..deck42 import get_deck, get_card, get_overlay, get_overlays, render_interpretation

router = APIRouter(prefix="/deck42", tags=["deck42"])


class InterpretPos(BaseModel):
    slot_label: str = Field(..., description="Position label, e.g. 'Past', 'Present', 'Future'.")
    card_id: str = Field(..., description="Card ID like 'SOVEREIGN-1'.")
    reversed: bool = Field(False, description="If true, interpret in Storm mode.")


class InterpretRequest(BaseModel):
    spread: str = Field("single", description="Spread name identifier")
    overlay_id: str = Field(..., description="Overlay ID like 'WIND' or 'RAIN'")
    positions: List[InterpretPos]


@router.get("/meta")
def meta() -> Dict[str, Any]:
    d = get_deck()
    return {
        "schema_version": d.get("schema_version"),
        "mode": d.get("mode"),
        "suits": d.get("suits"),
        "ranks": d.get("ranks"),
        "overlay_count": len(d.get("overlays", [])),
        "card_count": len(d.get("cards", [])),
    }


@router.get("/cards")
def cards() -> Dict[str, Any]:
    d = get_deck()
    return {"cards": d.get("cards", [])}


@router.get("/cards/{card_id}")
def card(card_id: str) -> Dict[str, Any]:
    c = get_card(card_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"Unknown card_id: {card_id}")
    return {"card": c}


@router.get("/overlays")
def overlays() -> Dict[str, Any]:
    return {"overlays": get_overlays()}


@router.post("/interpret")
def interpret(req: InterpretRequest) -> Dict[str, Any]:
    overlay = get_overlay(req.overlay_id)
    if not overlay:
        raise HTTPException(status_code=400, detail=f"Unknown overlay_id: {req.overlay_id}")

    out_positions: List[Dict[str, Any]] = []
    for p in req.positions:
        c = get_card(p.card_id)
        if not c:
            raise HTTPException(status_code=400, detail=f"Unknown card_id: {p.card_id}")
        out_positions.append(
            render_interpretation(
                slot_label=p.slot_label,
                card=c,
                overlay=overlay,
                reversed_mode=bool(p.reversed),
            )
        )

    return {
        "spread": req.spread,
        "overlay": overlay,
        "positions": out_positions,
        "key_message": " / ".join([pos["key_message"] for pos in out_positions if pos.get("key_message")]),
    }
