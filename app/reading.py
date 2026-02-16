from typing import Dict, Any, List, Optional

from backend.app.deck42 import resolve_card_id


def fallback_reading(deck: Dict[str, Any], placements: List[Dict[str, Any]], style: str) -> Dict[str, Any]:
    by_id = {c["id"]: c for c in deck["cards"]}
    card_notes = []
    advice = []

    style_intro = {
        "seer": "The symbols reveal patterns speaking through time. Here's how the energies weave:",
        "counselor": "Let's approach this with gentle honesty. Here's what the spread reflects:",
        "strategist": "Here's the strategic landscape. Focus on clear actions and next moves:",
        "shadow": "This spread points to deeper patterns. What wants to be seen beneath the surface:"
    }.get(style, "Here's your spread:")

    for p in placements:
        cid = p.get("card_id")
        if not cid:
            continue
        cid = resolve_card_id(cid, by_id) or cid
        c = by_id.get(cid)
        if not c:
            continue

        orientation = "reversed" if p.get("reversed") else "upright"
        meaning = c.get("storm") if p.get("reversed") else c.get("clear")
        if not meaning:
            meaning = c.get("reversed") if p.get("reversed") else c.get("upright")
        
        # Create position-aware interpretation
        meaning_text = (meaning or "").lower()
        if not meaning_text:
            meaning_text = "a moment of attention and choice"
        if p.get("reversed"):
            interpretation = f"Reversed {c['name']} suggests {meaning_text}. This challenges your usual approach and asks you to consider what you're avoiding."
        else:
            interpretation = f"Upright {c['name']} offers {meaning_text}. This energy supports your path forward, especially when paired with clear intention."

        card_notes.append({
            "slot_index": p["slot_index"],
            "slot_label": p["slot_label"],
            "card_id": cid,
            "note": interpretation
        })
        
        # Generate practical advice based on card interactions
        if len(placements) >= 2:
            advice.append(f"Notice how {placements[0]['slot_label']} and {placements[1]['slot_label']} interact - this relationship shapes your current situation.")
        advice.append(f"The {c['name']} asks you to trust your {orientation.lower()} instincts about {p['slot_label'].lower()}.")
        
        # Style-specific closing
        if style == "strategist":
            advice.append("Prioritize the most direct path forward. Test assumptions with small, measurable steps.")
        elif style == "counselor":
            advice.append("Be gentle with yourself. This reading may touch sensitive areas - give yourself time to process.")
        elif style == "shadow":
            advice.append("Ask what pattern you might be avoiding. The discomfort you feel often points to important growth.")
        else:
            advice.append("Stay open to the symbolic messages. Your intuition is receiving valid guidance through these cards.")

    summary = f"{style_intro} {len(card_notes)} cards offer clear guidance. The patterns suggest {len(placements) >= 2 and 'interconnected dynamics' or 'a focused narrative'}. Trust the process that's unfolding."

    return {"summary": summary, "card_notes": card_notes, "advice": advice[:6]}
