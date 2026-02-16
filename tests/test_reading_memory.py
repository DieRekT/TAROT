"""Test reading memory functionality."""

import json
import tempfile
import os
from pathlib import Path

from backend.app.reading_memory import append_message, get_history, reset_reading


def test_reading_memory_persistence():
    """Test that messages are stored and retrieved correctly."""
    reading_id = "test_reading_123"
    
    # Clear any existing data
    reset_reading(reading_id)
    
    # Add messages
    append_message(reading_id, "user", "What does this mean?", [{"id": "SOVEREIGN-1", "reversed": False}], "WIND")
    append_message(reading_id, "assistant", "This suggests choosing what you allow in.", [{"id": "SOVEREIGN-1", "reversed": False}], "WIND")
    append_message(reading_id, "user", "Explain that better", [{"id": "SOVEREIGN-1", "reversed": False}], "WIND")
    
    # Retrieve history
    history = get_history(reading_id)
    
    assert len(history) == 3
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "What does this mean?"
    assert history[1]["role"] == "assistant"
    assert history[2]["role"] == "user"
    assert history[2]["content"] == "Explain that better"
    
    # Reset and verify cleared
    reset_reading(reading_id)
    history_after_reset = get_history(reading_id)
    assert len(history_after_reset) == 0


def test_multiple_readings_isolation():
    """Test that different readings don't interfere."""
    reading1 = "test_reading_1"
    reading2 = "test_reading_2"
    
    # Clear data
    reset_reading(reading1)
    reset_reading(reading2)
    
    # Add messages to different readings
    append_message(reading1, "user", "Message for reading 1", [], None)
    append_message(reading2, "user", "Message for reading 2", [], None)
    
    # Verify isolation
    history1 = get_history(reading1)
    history2 = get_history(reading2)
    
    assert len(history1) == 1
    assert history1[0]["content"] == "Message for reading 1"
    
    assert len(history2) == 1
    assert history2[0]["content"] == "Message for reading 2"
    
    # Cleanup
    reset_reading(reading1)
    reset_reading(reading2)
