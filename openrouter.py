"""
OpenRouter AI Client - Generate human-like replies
"""
import httpx
import re
from config import settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are a Twitter user who understands AI, crypto, and markets.
Write short, sharp replies.
No emojis.
No hype.
No marketing tone.
Do not explain basic concepts.
Never start with "I" or "This".
Never use words like "actually", "honestly", "literally".
Be slightly contrarian or add a unique angle."""

USER_PROMPT_TEMPLATE = """Tweet:
"{tweet_text}"

Write a 1–2 sentence reply that adds a thoughtful or insider-style perspective."""


def validate_reply(text: str) -> tuple[bool, str]:
    """
    Validate AI-generated reply.
    Returns (is_valid, rejection_reason)
    """
    if len(text) > 240:
        return False, "Too long (>240 chars)"
    
    # Check for emojis (basic check)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    if emoji_pattern.search(text):
        return False, "Contains emojis"
    
    # Check for generic phrases
    generic_phrases = [
        "great point",
        "so true",
        "couldn't agree more",
        "this is huge",
        "love this",
        "amazing",
        "incredible",
        "game changer",
        "to the moon"
    ]
    text_lower = text.lower()
    for phrase in generic_phrases:
        if phrase in text_lower:
            return False, f"Generic phrase: {phrase}"
    
    # Check for promotional language
    promo_words = ["check out", "click here", "follow me", "my newsletter", "subscribe"]
    for word in promo_words:
        if word in text_lower:
            return False, f"Promotional: {word}"
    
    return True, ""


async def generate_reply(tweet_text: str, max_retries: int = 2) -> tuple[str | None, str | None]:
    """
    Generate a reply for the given tweet.
    Returns (reply_text, error_message)
    """
    if not settings.openrouter_api_key:
        return None, "OpenRouter API key not configured"
    
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://ghostreply.local",
        "X-Title": "GhostReply"
    }
    
    payload = {
        "model": settings.ai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(tweet_text=tweet_text)}
        ],
        "max_tokens": 100,
        "temperature": 0.8
    }
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                reply_text = data["choices"][0]["message"]["content"].strip()
                
                # Remove surrounding quotes if present
                if reply_text.startswith('"') and reply_text.endswith('"'):
                    reply_text = reply_text[1:-1]
                
                # Validate
                is_valid, reason = validate_reply(reply_text)
                if is_valid:
                    return reply_text, None
                
                # If last attempt, return anyway with warning
                if attempt == max_retries - 1:
                    return None, f"Validation failed: {reason}"
                    
        except httpx.HTTPError as e:
            if attempt == max_retries - 1:
                return None, f"API error: {str(e)}"
        except Exception as e:
            if attempt == max_retries - 1:
                return None, f"Error: {str(e)}"
    
    return None, "Max retries exceeded"
