from pydantic import BaseModel, Field
from typing import List, Optional, Literal

ReaderStyle = Literal["seer", "counselor", "strategist", "shadow"]

class Card(BaseModel):
    id: str
    name: str
    keywords: List[str] = Field(default_factory=list)
    upright: str
    reversed: str
    lore: str = ""

class SpreadPlacement(BaseModel):
    slot_index: int
    slot_label: str
    card_id: str
    reversed: bool = False

class ReadingRequest(BaseModel):
    spread_type: str
    style: ReaderStyle = "seer"
    question: Optional[str] = None
    overlay_id: Optional[str] = None
    placements: List[SpreadPlacement]

class ReadingResponse(BaseModel):
    session_id: str
    summary: str
    card_notes: List[dict]
    advice: List[str]
    theme: Optional[str] = None
    energy: Optional[str] = None
    synthesis: Optional[str] = None
    reflection_prompt: Optional[str] = None

class ChatRequest(BaseModel):
    session_id: str
    message: str
    style: Optional[ReaderStyle] = None  # optional override; usually use session style

class ChatResponse(BaseModel):
    session_id: str
    reply: str

class ScanResponse(BaseModel):
    card_id: Optional[str] = None
    confidence: float = 0.0
    matches: int = 0
    ok: bool = False
    debug: Optional[dict] = None
