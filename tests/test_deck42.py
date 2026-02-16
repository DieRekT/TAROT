import json
from pathlib import Path


def test_deck_json_has_42_cards():
    p = Path(__file__).resolve().parents[1] / "app" / "data" / "deck42_au.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert len(data["cards"]) == 42
    assert len(data["suits"]) == 6
    assert len(data["ranks"]) == 7
    assert len(data["overlays"]) == 8


def test_card_ids_unique():
    p = Path(__file__).resolve().parents[1] / "app" / "data" / "deck42_au.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    ids = [c["id"] for c in data["cards"]]
    assert len(ids) == len(set(ids))
