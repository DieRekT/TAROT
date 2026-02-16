from typing import List, Dict, Any
import os
import json

from backend.app.deck42 import get_overlay, render_interpretation, resolve_card_id

# Optional OpenAI usage
try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception:
    _OPENAI_AVAILABLE = False

_OPENAI_AVAILABLE = False


def _card_text(card: Dict[str, Any], reversed_: bool) -> str:
    """
    Build a rich text block for a single card.
    """
    meaning = card.get("reversed") if reversed_ else card.get("upright")
    orientation = "REVERSED" if reversed_ else "UPRIGHT"

    parts = [
        f"Name: {card.get('name')}",
        f"Orientation: {orientation}",
    ]

    if card.get("keywords"):
        parts.append("Keywords: " + ", ".join(card["keywords"]))

    if meaning:
        parts.append(f"Meaning: {meaning}")

    if card.get("teaches"):
        parts.append(f"Teaches: {card['teaches']}")

    if card.get("responsibility"):
        parts.append(f"Responsibility: {card['responsibility']}")

    if card.get("boundary"):
        parts.append(f"Boundary: {card['boundary']}")

    return "\n".join(parts)


# -------------------------------------------------------------------
# FALLBACK (NO AI) — MUST NOT BE SHIT
# -------------------------------------------------------------------

def _fallback_reading(
    deck: Dict[str, Any],
    placements: List[Dict[str, Any]],
    spread_type: str,
) -> Dict[str, Any]:
    cards = {c["id"]: c for c in deck.get("cards", [])}

    summary_lines = []
    notes = []

    for p in placements:
        cid = p.get("card_id")
        if not cid:
            continue
        cid = resolve_card_id(cid, cards) or cid
        if cid not in cards:
            continue

        card = cards[cid]
        reversed_ = bool(p.get("reversed"))
        label = p.get("slot_label", "Position")

        core = card.get("reversed") if reversed_ else card.get("upright")
        keywords = ", ".join(card.get("keywords", []))

        notes.append({
            "slot_index": p.get("slot_index"),
            "slot_label": label,
            "card_id": cid,
            "note": (
                f"{label}: This card highlights {keywords or 'a central theme'}. "
                f"It suggests {core.lower() if core else 'a moment of attention and choice'}. "
                "Treat this as guidance, not a fixed outcome."
            )
        })

        if core:
            summary_lines.append(core)

    summary = (
        "This reading describes the current pattern and what it asks of you. "
        + " ".join(summary_lines[:2])
        if summary_lines
        else "This reading points to a moment of reflection and choice."
    )

    return {
        "summary": summary,
        "card_notes": notes,
        "advice": ["Reflect on how these patterns connect to your current situation."]
    }


# -------------------------------------------------------------------
# AI READING
# -------------------------------------------------------------------

def generate_reading_ai(
    deck: Dict[str, Any],
    placements: List[Dict[str, Any]],
    spread_type: str,
    reader_style: str,
    question: str | None = None,
    overlay_id: str | None = None,
) -> Dict[str, Any]:
    """
    Generate a tarot reading using OpenAI if available,
    otherwise fall back to deterministic logic.
    Returns structured JSON with enhanced card insights.
    """
    # Deterministic interpreter (Deck42). We intentionally do not call external APIs.
    overlay = None
    try:
        overlay = get_overlay(overlay_id or os.getenv("DECK42_OVERLAY", "WIND"))
    except Exception:
        overlay = {"id": "WIND", "name": "Wind", "keywords": [], "effect": ""}

    cards = {c["id"]: c for c in deck.get("cards", [])}

    out_notes: List[Dict[str, Any]] = []
    summary_bits: List[str] = []

    for p in placements:
        cid = p.get("card_id")
        if not cid or cid not in cards:
            continue
        card = cards[cid]
        reversed_mode = bool(p.get("reversed"))
        label = p.get("slot_label") or "Position"
        interp = render_interpretation(
            slot_label=label,
            card=card,
            overlay=overlay,
            reversed_mode=reversed_mode,
        )
        base = interp.get("base") or ""
        key_message = interp.get("key_message") or ""
        overlay_effect = interp.get("overlay_effect")

        note_lines = [x for x in [key_message, base, overlay_effect] if x]
        out_notes.append(
            {
                "slot_index": p.get("slot_index"),
                "slot_label": label,
                "card_id": cid,
                "note": "\n\n".join(note_lines),
            }
        )

        if key_message:
            summary_bits.append(key_message)

    if not out_notes:
        return _fallback_reading(deck, placements, spread_type)

    summary = " ".join(summary_bits[:2]).strip() or "This reading highlights a pattern that wants your attention."
    advice = [
        (overlay.get("effect") or "").strip(),
        "Treat this as guidance, not a fixed outcome.",
    ]
    advice = [a for a in advice if a]

    return {
        "summary": summary,
        "card_notes": out_notes,
        "advice": advice,
        "theme": None,
        "energy": None,
        "synthesis": None,
        "reflection_prompt": None,
    }


# -------------------------------------------------------------------
# CHAT ABOUT A READING
# -------------------------------------------------------------------

def chat_about_reading_ai(
    deck: Dict[str, Any],
    reading: Dict[str, Any],
    chat_history: List[Dict[str, Any]],
    reader_style: str,
    message: str,
) -> str:
    return _deep_fallback_chat(deck, reading, chat_history, message)


def _deep_fallback_chat(
    deck: Dict[str, Any],
    reading: Dict[str, Any],
    chat_history: List[Dict[str, Any]],
    message: str,
) -> str:
    """
    Enhanced fallback chat that provides meaningful, card-specific conversations
    even without AI access.
    """
    placements = reading.get("placements", [])
    result = reading.get("result", {})
    cards = {c["id"]: c for c in deck.get("cards", [])}
    
    # Analyze user message for card references
    message_lower = message.lower()
    referenced_cards = []
    
    for p in placements:
        cid = p.get("card_id")
        if cid:
            cid = resolve_card_id(cid, cards) or cid
        if cid and cid in cards:
            card = cards[cid]
            if (card.get("name", "").lower() in message_lower or 
                p.get("slot_label", "").lower() in message_lower):
                referenced_cards.append((p, card))
    
    # Generate contextual response
    if referenced_cards:
        # User is asking about specific cards
        responses = []
        for p, card in referenced_cards:
            label = p.get("slot_label", "Position")
            meaning = card.get("reversed") if p.get("reversed") else card.get("upright")
            keywords = card.get("keywords", [])
            
            response = (
                f"Regarding the {card['name']} in the {label} position:\n\n"
                f"This card speaks to {meaning.lower()}. "
            )
            
            if keywords:
                response += f"The key themes here are {', '.join(keywords)}. "
            
            # Add reflective questions based on card type
            if "responsibility" in card:
                response += f"Consider what {card['responsibility'].lower()} "
                response += "in your current situation.\n\n"
            
            if "teaches" in card:
                response += f"This card asks you to learn {card['teaches'].lower()}. "
                response += "How might this lesson show up in your daily life?\n\n"
            
            response += "What resonates most strongly with you about this card?"
            responses.append(response)
        
        return "\n\n".join(responses)
    
    else:
        # General conversation about the reading
        summary = result.get("summary", "")
        card_notes = result.get("card_notes", [])
        
        response = (
            "Let's explore this reading more deeply.\n\n"
        )
        
        if summary:
            response += f"The core message is: {summary}\n\n"
        
        # Offer specific angles for exploration
        if len(placements) >= 2:
            response += (
                "You might want to explore:\n"
                "- How the cards interact with each other\n"
                "- Which card feels most relevant to your current situation\n"
                "- What patterns you notice across the positions\n\n"
            )
        
        response += (
            "Which card or aspect of this reading would you like to explore further? "
            "You can ask about specific cards, their meanings, or how they relate to your life."
        )
        
        return response
