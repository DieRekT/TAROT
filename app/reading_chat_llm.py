"""LLM integration for reading chat with fallback."""

from __future__ import annotations

import os
import re
from typing import List, Dict, Any, Optional

from openai import OpenAI

def _detect_intent(message: str) -> Dict[str, Any]:
    """Detect user intent and required formatting."""
    message_lower = message.lower()
    
    # One-line enforcement
    one_line_patterns = ["one line", "one-line", "single sentence", "one sentence"]
    is_one_line = any(pattern in message_lower for pattern in one_line_patterns)
    
    # Explain better
    is_explain = "explain" in message_lower and ("better" in message_lower or "that" in message_lower)
    
    # Action-oriented - check for more specific patterns first
    is_action = (
        "what should i do" in message_lower or 
        "what should i" in message_lower or 
        "how should i" in message_lower or
        "now what" in message_lower
    )
    
    return {
        "one_line": is_one_line,
        "explain": is_explain,
        "action": is_action
    }

def _build_fallback_response(cards: List[Dict[str, Any]], overlay: Optional[str], 
                         history: List[Dict[str, str]], message: str, intent: Dict[str, Any]) -> str:
    """Generate natural fallback response without LLM."""
    
    if intent["one_line"]:
        # One sentence summary
        if len(cards) == 1:
            card = cards[0]
            return f"{card['animal']} ({card['mode']}) suggests {card['key_message'].lower()}."
        else:
            key_messages = [c['key_message'].lower() for c in cards]
            return f"Your cards indicate {', '.join(key_messages[:-1])} and {key_messages[-1]}."
    
    elif intent["explain"]:
        # Explain better with example
        if len(cards) == 1:
            card = cards[0]
            example = f"For example, if {card['animal'].lower()} appears, you might need to {card['key_message'].lower()}."
            return f"{card['animal']} ({card['mode']}) teaches {card['key_message'].lower()}. {example} What specific situation are you facing?"
        else:
            primary = cards[0]
            return f"Your primary card {primary['animal']} ({primary['mode']}) emphasizes {primary['key_message'].lower()}. Consider how this applies to your current circumstances. What aspect feels most relevant?"
    
    elif intent["action"]:
        # Action-oriented steps
        steps = []
        for i, card in enumerate(cards[:3], 1):
            steps.append(f"{i}. {card['key_message'].lower()}")
        
        if len(cards) == 1:
            card = cards[0]
            return f"Based on your {card['animal'].lower()}: {card['key_message'].lower()}. How can you apply this today?"
        elif steps:
            return f"Based on your {cards[0]['animal'].lower()} card: {' '.join(steps)}. Which step feels most urgent right now?"
        else:
            return f"Consider {cards[0]['key_message'].lower()} as your immediate focus with {cards[0]['animal'].lower()}. How can you apply this today?"
    
    else:
        # Natural conversational response
        if len(cards) == 1:
            card = cards[0]
            return f"{card['animal']} ({card['mode']}) brings clarity about {card['key_message'].lower()}. How does this resonate with what you're experiencing?"
        else:
            modes = [c['mode'] for c in cards]
            if "Storm" in modes and "Clear" in modes:
                return f"You have both challenges and opportunities with {cards[0]['animal'].lower()}. The Storm cards suggest areas needing attention, while Clear cards show where you can move forward confidently. What feels most pressing?"
            elif all(m == "Storm" for m in modes):
                return f"Your {cards[0]['animal'].lower()} cards suggest a time for reflection and boundary-setting. Consider what needs to be addressed before taking action. What's calling for your attention?"
            else:
                return f"Your {cards[0]['animal'].lower()} cards show alignment and forward momentum. Trust your instincts and proceed with confidence. What opportunity are you most excited about?"

def generate_chat_response(cards: List[Dict[str, Any]], overlay: Optional[str],
                        history: List[Dict[str, str]], message: str) -> str:
    """Generate chat response using LLM or fallback."""
    
    intent = _detect_intent(message)
    
    # Try LLM if API key is available and not empty
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and api_key.strip() and api_key != "":
        try:
            return _generate_with_openai(cards, overlay, history, message, intent)
        except Exception as e:
            print(f"OpenAI API failed, using fallback: {e}")
    
    # Fallback to deterministic response
    return _build_fallback_response(cards, overlay, history, message, intent)

def _generate_with_openai(cards: List[Dict[str, Any]], overlay: Optional[str],
                       history: List[Dict[str, str]], message: str, intent: Dict[str, Any]) -> str:
    """Generate response using OpenAI API."""
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Build card context
    card_context = []
    for card in cards:
        card_info = f"{card['animal']} ({card['mode']}): {card['key_message']}"
        if card.get('overlay_line'):
            card_info += f" [{card['overlay_line']}]"
        card_context.append(card_info)
    
    # Build conversation history
    history_text = ""
    if history:
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-6:]])
    
    # Build system prompt
    system_prompt = f"""You are a natural, intuitive tarot reader. Respond conversationally and concisely.

Cards in play: {"; ".join(card_context)}
Overlay: {overlay or "None"}
Conversation so far: {history_text or "None"}

Rules:
- NEVER include headings like "Cards in play:" or "This answer is generated..."
- NEVER echo the user's question
- Ground every response in the cards provided
- If user asks for "one line", respond with EXACTLY one sentence
- If user asks to "explain", provide practical example and end with ONE follow-up question
- Keep responses natural and human-like
- Maximum 3 short paragraphs"""

    user_prompt = message
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=300,
        temperature=0.7
    )
    
    return response.choices[0].message.content.strip()
