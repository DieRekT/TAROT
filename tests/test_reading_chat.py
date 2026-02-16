from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_reading_ask_correlates_cards():
    payload = {
        "reading": {"overlay": "WIND", "cards": [{"id": "SOVEREIGN-1", "reversed": False}, {"id": "WITNESS-1", "reversed": True}, {"id": "THRESHOLD-1", "reversed": False}]},
        "question": "how do cards interact"
    }
    r = client.post("/reading/ask", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert "used_cards" in data
    ids = [c["id"] for c in data["used_cards"]]
    assert ids == ["SOVEREIGN-1","WITNESS-1","THRESHOLD-1"]
    # Must mention at least one title or animal to prove correlation
    assert "Dingo" in data["answer"] or "SOVEREIGN-1" in data["answer"]
