"""Tests for reading determinism and persistence."""

import pytest
import tempfile
import os

from backend.app.readings_storage.readings_db import init_db, create_reading, get_reading, save_positions
from backend.app.utils.rng import seeded_random, shuffle_deck, draw_cards


class TestRNGDeterminism:
    """Test deterministic RNG behavior."""
    
    def test_seeded_random_deterministic(self):
        """Same seed and salt should produce same sequence."""
        rng1 = seeded_random("test_seed", "test_salt")
        rng2 = seeded_random("test_seed", "test_salt")
        
        # Generate sequences
        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]
        
        assert seq1 == seq2, "Same seed+salt should produce identical sequences"
    
    def test_seeded_random_different_seeds(self):
        """Different seeds should produce different sequences."""
        rng1 = seeded_random("seed1", "salt")
        rng2 = seeded_random("seed2", "salt")
        
        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]
        
        assert seq1 != seq2, "Different seeds should produce different sequences"
    
    def test_seeded_random_different_salts(self):
        """Different salts should produce different sequences."""
        rng1 = seeded_random("seed", "salt1")
        rng2 = seeded_random("seed", "salt2")
        
        seq1 = [rng1.random() for _ in range(10)]
        seq2 = [rng2.random() for _ in range(10)]
        
        assert seq1 != seq2, "Different salts should produce different sequences"
    
    def test_shuffle_deck_deterministic(self):
        """Deck shuffling should be deterministic."""
        deck = ["card1", "card2", "card3", "card4", "card5"]
        
        shuffled1 = shuffle_deck(deck, "seed", "salt")
        shuffled2 = shuffle_deck(deck, "seed", "salt")
        
        assert shuffled1 == shuffled2, "Shuffle should be deterministic"
        assert sorted(shuffled1) == sorted(deck), "All cards should be present"
    
    def test_draw_cards_deterministic(self):
        """Card drawing should be deterministic."""
        deck = [f"card_{i}" for i in range(20)]
        
        drawn1 = draw_cards(deck, 5, "seed", "salt", allow_reversed=True)
        drawn2 = draw_cards(deck, 5, "seed", "salt", allow_reversed=True)
        
        assert drawn1 == drawn2, "Drawing should be deterministic"
        assert len(drawn1) == 5, "Should draw correct number of cards"
        
        # Check no duplicates
        card_ids = [card["card_id"] for card in drawn1]
        assert len(card_ids) == len(set(card_ids)), "No duplicate cards should be drawn"


class TestReadingPersistence:
    """Test reading storage and retrieval."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        original_db_path = os.path.join(os.path.dirname(__file__), "..", "app", "storage", "readings_db.py")
        original_db = os.path.join(os.path.dirname(__file__), "..", "app", "storage", "readings_db.py")
        
        # Create temp database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            temp_db_path = tmp.name
        
        # Temporarily override DB path
        import backend.app.storage.readings_db as db_module
        original_path = db_module.DB_PATH
        db_module.DB_PATH = temp_db_path
        
        # Initialize the temp database
        init_db()
        
        yield temp_db_path
        
        # Cleanup
        db_module.DB_PATH = original_path
        os.unlink(temp_db_path)
    
    def test_create_and_get_reading(self, temp_db):
        """Test creating and retrieving a reading."""
        # Create reading
        reading_data = create_reading(
            mode="digital",
            spread_id="three-card",
            seed="test_seed_123"
        )
        
        assert "reading_id" in reading_data
        assert reading_data["mode"] == "digital"
        assert reading_data["spread_id"] == "three-card"
        assert reading_data["seed"] == "test_seed_123"
        
        # Retrieve reading
        retrieved = get_reading(reading_data["reading_id"])
        
        assert retrieved is not None
        assert retrieved["reading_id"] == reading_data["reading_id"]
        assert retrieved["mode"] == "digital"
        assert retrieved["spread_id"] == "three-card"
        assert retrieved["seed"] == "test_seed_123"
        assert "created_at" in retrieved
        assert retrieved["positions"] == []  # No positions yet
    
    def test_save_and_get_positions(self, temp_db):
        """Test saving and retrieving positions."""
        # Create reading
        reading = create_reading("digital", "single", "seed123")
        
        # Save positions
        positions = [
            {"slot": "card_1", "card_id": "test_card_1", "reversed": False},
            {"slot": "card_2", "card_id": "test_card_2", "reversed": True}
        ]
        
        save_positions(reading["reading_id"], positions)
        
        # Retrieve reading with positions
        retrieved = get_reading(reading["reading_id"])
        
        assert len(retrieved["positions"]) == 2
        assert retrieved["positions"][0]["slot"] == "card_1"
        assert retrieved["positions"][0]["card_id"] == "test_card_1"
        assert retrieved["positions"][0]["reversed"] is False
        assert retrieved["positions"][1]["slot"] == "card_2"
        assert retrieved["positions"][1]["card_id"] == "test_card_2"
        assert retrieved["positions"][1]["reversed"] is True
    
    def test_force_redraw(self, temp_db):
        """Test force_redraw functionality."""
        # Create reading
        reading = create_reading("digital", "single", "seed123")
        
        # Save initial positions
        positions1 = [{"slot": "card_1", "card_id": "card_a", "reversed": False}]
        save_positions(reading["reading_id"], positions1)
        
        # Try to save again without force - should fail
        positions2 = [{"slot": "card_1", "card_id": "card_b", "reversed": True}]
        with pytest.raises(ValueError, match="Positions already exist"):
            save_positions(reading["reading_id"], positions2)
        
        # Save with force - should succeed
        save_positions(reading["reading_id"], positions2, force_redraw=True)
        
        # Verify new positions
        retrieved = get_reading(reading["reading_id"])
        assert retrieved["positions"][0]["card_id"] == "card_b"
        assert retrieved["positions"][0]["reversed"] is True
    
    def test_get_nonexistent_reading(self, temp_db):
        """Test getting a non-existent reading."""
        result = get_reading("nonexistent_id")
        assert result is None


class TestIntegration:
    """Integration tests combining RNG and storage."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            temp_db_path = tmp.name
        
        import backend.app.storage.readings_db as db_module
        original_path = db_module.DB_PATH
        db_module.DB_PATH = temp_db_path
        
        init_db()
        
        yield temp_db_path
        
        db_module.DB_PATH = original_path
        os.unlink(temp_db_path)
    
    def test_deterministic_reading_workflow(self, temp_db):
        """Test that the same reading workflow produces identical results."""
        # Create two readings with same parameters
        reading1 = create_reading("digital", "three-card", "same_seed")
        reading2 = create_reading("digital", "three-card", "same_seed")
        
        # Use deterministic card drawing
        deck_ids = [f"card_{i}" for i in range(42)]
        
        drawn1 = draw_cards(
            deck_ids=deck_ids,
            count=3,
            seed="same_seed",
            salt=reading1["reading_id"],
            allow_reversed=True
        )
        
        drawn2 = draw_cards(
            deck_ids=deck_ids,
            count=3,
            seed="same_seed",
            salt=reading2["reading_id"],
            allow_reversed=True
        )
        
        # Results should be different because reading_id (salt) is different
        assert drawn1 != drawn2, "Different reading_ids should produce different draws"
        
        # But same reading_id should produce same draw
        drawn1_again = draw_cards(
            deck_ids=deck_ids,
            count=3,
            seed="same_seed",
            salt=reading1["reading_id"],
            allow_reversed=True
        )
        
        assert drawn1 == drawn1_again, "Same reading_id should produce identical draws"
