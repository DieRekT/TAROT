"""Deterministic RNG utilities for reproducible card shuffling."""

import hashlib
import random
from typing import List


def seeded_random(seed: str, salt: str = "") -> random.Random:
    """Create a deterministic random.Random instance from seed and optional salt.
    
    Args:
        seed: Base seed string
        salt: Optional salt to modify the seed (e.g., reading_id)
        
    Returns:
        random.Random instance that will produce deterministic sequences
    """
    # Combine seed and salt, then hash to create deterministic integer seed
    combined = f"{seed}{salt}"
    hash_obj = hashlib.sha256(combined.encode('utf-8'))
    int_seed = int(hash_obj.hexdigest(), 16)
    
    # Mask to fit within Python's random seed range
    int_seed = int_seed & ((1 << 31) - 1)
    
    return random.Random(int_seed)


def shuffle_deck(deck_ids: List[str], seed: str, salt: str = "") -> List[str]:
    """Shuffle a deck of card IDs deterministically.
    
    Args:
        deck_ids: List of card IDs to shuffle
        seed: Base seed for shuffling
        salt: Optional salt to modify the shuffle
        
    Returns:
        New list with shuffled card IDs
    """
    rng = seeded_random(seed, salt)
    shuffled = deck_ids.copy()
    rng.shuffle(shuffled)
    return shuffled


def draw_cards(deck_ids: List[str], count: int, seed: str, salt: str = "", allow_reversed: bool = False) -> List[dict]:
    """Draw cards from deck deterministically.
    
    Args:
        deck_ids: List of available card IDs
        count: Number of cards to draw
        seed: Base seed for drawing
        salt: Optional salt to modify the draw
        allow_reversed: Whether to randomly reverse cards
        
    Returns:
        List of dicts with 'card_id' and 'reversed' keys
    """
    rng = seeded_random(seed, salt)
    
    # Shuffle deck
    shuffled = deck_ids.copy()
    rng.shuffle(shuffled)
    
    # Draw requested number of cards
    drawn_cards = shuffled[:count]
    
    # Determine reversed status if needed
    result = []
    for card_id in drawn_cards:
        reversed_card = allow_reversed and rng.choice([True, False])
        result.append({
            "card_id": card_id,
            "reversed": reversed_card
        })
    
    return result
