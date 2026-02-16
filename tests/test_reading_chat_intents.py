"""Test reading chat intent detection and response formatting."""

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_one_line_enforcement():
    """Test that one-line requests return exactly one sentence."""
    payload = {
        "reading_id": "test_one_line",
        "reading": {
            "overlay": "LIGHTNING",
            "cards": [{"id": "SOVEREIGN-2", "reversed": True}]
        },
        "message": "one line summary"
    }
    r = client.post("/reading/ask", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "answer" in data
    assert "used_cards" in data
    
    # Check that response is exactly one sentence
    answer = data["answer"].strip()
    # Remove trailing period and whitespace before counting
    clean_answer = answer.rstrip('. \n')
    sentence_count = len([s for s in clean_answer.split('.') if s.strip()])
    assert sentence_count <= 1, f"Expected 1 sentence, got {sentence_count}: {answer}"
    
    # Should not contain headings
    assert "Cards in play:" not in answer
    assert "This answer is generated" not in answer


def test_explain_better_mode():
    """Test explain better intent with example and follow-up question."""
    payload = {
        "reading_id": "test_explain",
        "reading": {
            "overlay": "WIND",
            "cards": [{"id": "THRESHOLD-1", "reversed": False}]
        },
        "message": "explain that better"
    }
    r = client.post("/reading/ask", json=payload)
    assert r.status_code == 200
    data = r.json()
    answer = data["answer"].strip()
    
    # Should include practical example
    assert "example" in answer.lower() or "for example" in answer.lower()
    
    # Should end with a question
    assert "?" in answer
    
    # Should not echo user message
    assert "explain that better" not in answer.lower()


def test_memory_continuity():
    """Test that conversation maintains continuity."""
    reading_id = "test_memory"
    
    # First message
    payload1 = {
        "reading_id": reading_id,
        "reading": {
            "overlay": "RAIN",
            "cards": [{"id": "WITNESS-1", "reversed": True}]
        },
        "message": "explain that better"
    }
    r1 = client.post("/reading/ask", json=payload1)
    assert r1.status_code == 200
    data1 = r1.json()
    
    # Second message referencing previous
    payload2 = {
        "reading_id": reading_id,
        "reading": {
            "overlay": "RAIN",
            "cards": [{"id": "WITNESS-1", "reversed": True}]
        },
        "message": "ok so what boundary do I set?"
    }
    r2 = client.post("/reading/ask", json=payload2)
    assert r2.status_code == 200
    data2 = r2.json()
    
    # Second response should reference context without repeating boilerplate
    answer2 = data2["answer"].strip()
    assert len(answer2) > 10  # Should have substantial content
    
    # Should not repeat exact same response
    assert data1["answer"] != data2["answer"]
    
    # History should be maintained
    assert len(data2["history"]) >= 4  # user1, assistant1, user2, assistant2


def test_single_card_no_interaction():
    """Test that single card responses don't mention interaction."""
    payload = {
        "reading_id": "test_single",
        "reading": {
            "overlay": None,
            "cards": [{"id": "SOVEREIGN-1", "reversed": False}]
        },
        "message": "what should I do today?"
    }
    r = client.post("/reading/ask", json=payload)
    assert r.status_code == 200
    data = r.json()
    answer = data["answer"].strip()
    
    # Should not mention "interaction between cards"
    assert "interaction" not in answer.lower()
    assert "between" not in answer.lower()
    
    # Should reference the specific card
    assert "dingo" in answer.lower() or "sovereign" in answer.lower()


def test_reset_endpoint():
    """Test reading reset functionality."""
    # First add some messages
    payload = {
        "reading_id": "test_reset",
        "reading": {
            "overlay": "FOG",
            "cards": [{"id": "TRACE-1", "reversed": False}]
        },
        "message": "test message"
    }
    r1 = client.post("/reading/ask", json=payload)
    assert r1.status_code == 200
    
    # Reset the reading
    r2 = client.post("/reading/reset", json={"reading_id": "test_reset"})
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}
    
    # Verify new message starts fresh (no history context)
    payload2 = {
        "reading_id": "test_reset",
        "reading": {
            "overlay": "FOG",
            "cards": [{"id": "TRACE-1", "reversed": False}]
        },
        "message": "new message after reset"
    }
    r3 = client.post("/reading/ask", json=payload2)
    assert r3.status_code == 200
    data3 = r3.json()
    
    # Should have minimal history (just current exchange)
    assert len(data3["history"]) == 2
