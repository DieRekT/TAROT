from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_deck():
    r = client.get("/deck")
    assert r.status_code == 200
    j = r.json()
    assert j["deck_id"] == "tarot42"
    assert len(j["cards"]) == 42
