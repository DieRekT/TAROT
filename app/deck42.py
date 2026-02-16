"""Tarot42 Australian Fauna Deck (6x7) loader + helpers.

Drop-in module.
- Loads deck JSON from backend/app/data/deck42_au.json
- Provides: get_deck(), get_card(card_id), get_overlays(), get_overlay(overlay_id)

No external deps.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


DATA_PATH = Path(__file__).resolve().parent / "data" / "deck42_au.json"


class Deck42Error(RuntimeError):
    pass


def _load_json() -> Dict[str, Any]:
    try:
        raw = DATA_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise Deck42Error(f"Deck42 data file not found at: {DATA_PATH}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Deck42Error(f"Invalid JSON in {DATA_PATH}: {e}") from e

    if "cards" not in data or not isinstance(data["cards"], list) or len(data["cards"]) != 42:
        raise Deck42Error("Deck42 data must contain exactly 42 cards.")
    return data


_DECK_CACHE: Optional[Dict[str, Any]] = None


def get_deck() -> Dict[str, Any]:
    global _DECK_CACHE
    if _DECK_CACHE is None:
        _DECK_CACHE = _load_json()
    return _DECK_CACHE


def get_cards() -> List[Dict[str, Any]]:
    return list(get_deck()["cards"])


def get_card(card_id: str) -> Dict[str, Any]:
    for c in get_deck()["cards"]:
        if c.get("id") == card_id:
            return c
    raise Deck42Error(f"Unknown card id: {card_id}")


def get_overlays() -> List[Dict[str, Any]]:
    return list(get_deck()["overlays"])


def get_overlay(overlay_id: str) -> Dict[str, Any]:
    oid = overlay_id.upper()
    for o in get_deck()["overlays"]:
        if o.get("id") == oid:
            return o
    raise Deck42Error(f"Unknown overlay id: {overlay_id}")


def validate_deck() -> None:
    data = get_deck()
    ids = [c.get("id") for c in data["cards"]]
    if len(ids) != len(set(ids)):
        raise Deck42Error("Duplicate card ids detected.")

    suits = {s["id"] for s in data.get("suits", [])}
    for c in data["cards"]:
        if c.get("suit") not in suits:
            raise Deck42Error(f"Card {c.get('id')} has unknown suit {c.get('suit')}")
        r = c.get("rank")
        if not isinstance(r, int) or r < 1 or r > 7:
            raise Deck42Error(f"Card {c.get('id')} has invalid rank {r}")


def render_interpretation(
    *,
    slot_label: str,
    card: Dict[str, Any],
    overlay: Dict[str, Any],
    reversed_mode: bool,
) -> Dict[str, Any]:
    """Deterministic renderer for an interpreted position.

    Returns a compact object intended for API use.
    """

    orientation = "storm" if reversed_mode else "clear"
    base_text = card.get("storm") if reversed_mode else card.get("clear")
    overlay_id = (overlay.get("id") or "").upper()
    overlay_text = (card.get("overlays") or {}).get(overlay_id)

    key_message = card.get("key_message") or card.get("essence") or ""
    if reversed_mode and key_message:
        key_message = f"Storm: {key_message}"

    out: Dict[str, Any] = {
        "slot_label": slot_label,
        "card_id": card.get("id"),
        "suit": card.get("suit"),
        "rank": card.get("rank"),
        "animal": card.get("animal"),
        "title": card.get("title"),
        "orientation": orientation,
        "base": base_text,
        "key_message": key_message,
        "overlay": overlay,
        "overlay_effect": overlay_text,
    }

    # Optional fields (keep stable keys when present)
    if "essence" in card:
        out["essence"] = card.get("essence")
    if "when" in card:
        out["when"] = card.get("when")
    if "shadow" in card:
        out["shadow"] = card.get("shadow")
    if "boundary_note" in card:
        out["boundary_note"] = card.get("boundary_note")

    return out


def deck_for_legacy_api() -> Dict[str, Any]:
    """Compatibility deck object for existing `/deck` consumers.

    Old app expects:
    - `deck_id` == "tarot42"
    - `cards`: list of objects with `id`, `name`, `upright`, `reversed`
    """

    d = get_deck()
    cards: List[Dict[str, Any]] = []
    for c in d.get("cards", []):
        cards.append(
            {
                "id": c.get("id"),
                "name": c.get("animal"),
                "upright": c.get("clear"),
                "reversed": c.get("storm"),
                "animal": c.get("animal"),
                "title": c.get("title"),
                "essence": c.get("essence"),
                "key_message": c.get("key_message"),
                "clear": c.get("clear"),
                "storm": c.get("storm"),
                "suit": c.get("suit"),
                "rank": c.get("rank"),
                "overlays": c.get("overlays"),
            }
        )

    return {
        "deck_id": "tarot42",
        "schema_version": d.get("schema_version"),
        "mode": d.get("mode"),
        "suits": d.get("suits"),
        "ranks": d.get("ranks"),
        "overlays": d.get("overlays"),
        "cards": cards,
    }


def legacy_asset_id_for_card_id(card_id: str) -> str:
    cards = get_cards()
    for i, c in enumerate(cards, start=1):
        if c.get("id") == card_id:
            return f"t42_{i:02d}"
    raise Deck42Error(f"Unknown card id: {card_id}")


def card_id_for_legacy_asset_id(asset_id: str) -> str:
    s = (asset_id or "").strip().lower()
    if not s.startswith("t42_"):
        raise Deck42Error(f"Invalid legacy asset id: {asset_id}")
    try:
        n = int(s.split("_")[-1])
    except Exception as e:
        raise Deck42Error(f"Invalid legacy asset id: {asset_id}") from e
    cards = get_cards()
    if n < 1 or n > len(cards):
        raise Deck42Error(f"Legacy asset id out of range: {asset_id}")
    return cards[n - 1].get("id")


def resolve_card_id(card_id: str, cards_by_id: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """Resolve card_id to canonical deck42 ID for lookup.

    Handles both deck42 IDs (THRESHOLD-1) and legacy asset IDs (t42_01).
    Returns the canonical ID if found, else None.
    """
    if not card_id:
        return None
    if card_id in cards_by_id:
        return card_id
    s = (card_id or "").strip().lower()
    if s.startswith("t42_"):
        try:
            return card_id_for_legacy_asset_id(card_id)
        except Deck42Error:
            return None
    return None
