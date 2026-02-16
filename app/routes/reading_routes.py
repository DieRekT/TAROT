"""FastAPI routes for digital reading sessions with deterministic shuffling."""

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.readings_storage.readings_db import init_db, create_reading, get_reading, save_positions
from app.utils.rng import draw_cards
from app.deck42 import get_deck

# Initialize database on import
init_db()

router = APIRouter(prefix="/reading", tags=["reading"])


class ReadingStartRequest(BaseModel):
    mode: str = Field(..., description="Reading mode: 'physical' or 'digital'")
    spread_id: str = Field(..., description="Spread identifier: 'single', 'three-card', etc.")
    seed: Optional[str] = Field(None, description="Optional seed for deterministic shuffling")


class ReadingStartResponse(BaseModel):
    reading_id: str
    mode: str
    spread_id: str
    seed: str


class ReadingDrawRequest(BaseModel):
    reading_id: str
    count: int = Field(..., ge=1, le=10, description="Number of cards to draw (1-10)")
    allow_reversed: bool = Field(False, description="Whether cards can be drawn reversed")
    slots: Optional[List[str]] = Field(None, description="Optional slot labels for positions")
    force_redraw: bool = Field(False, description="Force redraw even if positions exist")


class Position(BaseModel):
    slot: str
    card_id: str
    reversed: bool


class ReadingDrawResponse(BaseModel):
    reading_id: str
    mode: str
    spread_id: str
    seed: str
    positions: List[Position]


class ReadingResponse(BaseModel):
    reading_id: str
    mode: str
    spread_id: str
    seed: str
    created_at: str
    positions: Optional[List[Position]] = None
    metadata: Optional[Dict[str, Any]] = None


def get_deck_card_ids() -> List[str]:
    """Get all card IDs from the deck."""
    deck = get_deck()
    return [card["id"] for card in deck.get("cards", [])]


@router.post("/start", response_model=ReadingStartResponse)
def start_reading(req: ReadingStartRequest) -> ReadingStartResponse:
    """Start a new reading session."""
    if req.mode not in ["physical", "digital"]:
        raise HTTPException(status_code=400, detail="mode must be 'physical' or 'digital'")
    
    if req.mode == "digital" and not req.seed:
        import secrets
        req.seed = secrets.token_urlsafe(16)
    
    reading = create_reading(
        mode=req.mode,
        spread_id=req.spread_id,
        seed=req.seed or "physical"
    )
    
    return ReadingStartResponse(**reading)


@router.post("/draw", response_model=ReadingDrawResponse)
def draw_cards_for_reading(req: ReadingDrawRequest) -> ReadingDrawResponse:
    """Draw cards for a reading session."""
    # Load reading
    reading = get_reading(req.reading_id)
    if not reading:
        raise HTTPException(status_code=404, detail=f"Reading not found: {req.reading_id}")
    
    if reading["mode"] != "digital":
        raise HTTPException(status_code=400, detail="Card drawing only available for digital readings")
    
    # Check if positions already exist
    if reading["positions"] and not req.force_redraw:
        return ReadingDrawResponse(
            reading_id=reading["reading_id"],
            mode=reading["mode"],
            spread_id=reading["spread_id"],
            seed=reading["seed"],
            positions=[Position(**pos) for pos in reading["positions"]]
        )
    
    # Get deck and draw cards
    deck_ids = get_deck_card_ids()
    drawn_cards = draw_cards(
        deck_ids=deck_ids,
        count=req.count,
        seed=reading["seed"],
        salt=reading["reading_id"],  # Use reading_id as salt for uniqueness
        allow_reversed=req.allow_reversed
    )
    
    # Create positions
    if req.slots:
        if len(req.slots) != len(drawn_cards):
            raise HTTPException(
                status_code=400, 
                detail=f"Number of slots ({len(req.slots)}) must match count ({req.count})"
            )
        slot_labels = req.slots
    else:
        slot_labels = [f"card_{i+1}" for i in range(len(drawn_cards))]
    
    positions = [
        Position(
            slot=slot_labels[i],
            card_id=card["card_id"],
            reversed=card["reversed"]
        )
        for i, card in enumerate(drawn_cards)
    ]
    
    # Save positions
    save_positions(
        reading_id=req.reading_id,
        positions=[pos.model_dump() for pos in positions],
        force_redraw=req.force_redraw
    )
    
    return ReadingDrawResponse(
        reading_id=reading["reading_id"],
        mode=reading["mode"],
        spread_id=reading["spread_id"],
        seed=reading["seed"],
        positions=positions
    )


@router.get("/{reading_id}", response_model=ReadingResponse)
def get_reading_by_id(reading_id: str) -> ReadingResponse:
    """Retrieve a reading by ID."""
    reading = get_reading(reading_id)
    if not reading:
        raise HTTPException(status_code=404, detail=f"Reading not found: {reading_id}")
    
    positions = [Position(**pos) for pos in reading.get("positions", [])]
    
    return ReadingResponse(
        reading_id=reading["reading_id"],
        mode=reading["mode"],
        spread_id=reading["spread_id"],
        seed=reading["seed"],
        created_at=reading["created_at"],
        positions=positions if positions else None,
        metadata=reading.get("metadata")
    )
