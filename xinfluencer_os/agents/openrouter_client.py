"""
OpenRouter Client - Centralized API client for all OpenRouter calls
"""
import os
import httpx
from pathlib import Path
from dotenv import load_dotenv

# Load .env from parent directory (xinfluencer_os)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

# Correct OpenRouter endpoint
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def get_api_key() -> str:
    """Get API key with validation"""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise ValueError("OPENROUTER_API_KEY not set in .env")
    return key


def get_model() -> str:
    """Get model from env or use fallback"""
    return os.getenv("AI_MODEL", "meta-llama/llama-3.1-8b-instruct:free")


def call_openrouter(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 80,
    temperature: float = 0.7
) -> tuple[str | None, str | None]:
    """
    Call OpenRouter API with proper error handling
    
    Returns:
        tuple: (response_text, error_message)
    """
    api_key = get_api_key()
    model = get_model()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "XInfluencerOS"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    try:
        print(f"  🔗 OpenRouter: {model}")
        
        with httpx.Client(timeout=30) as client:
            response = client.post(OPENROUTER_URL, json=payload, headers=headers)
            
            # Debug on error
            if response.status_code != 200:
                print(f"  ❌ HTTP {response.status_code}")
                print(f"  📍 URL: {OPENROUTER_URL}")
                print(f"  🤖 Model: {model}")
                print(f"  📄 Response: {response.text[:300]}")
                return None, f"API error: {response.status_code} - {response.text[:100]}"
            
            data = response.json()
            
            # Extract and clean response
            content = data["choices"][0]["message"]["content"]
            if content:
                content = content.strip()
                # Remove surrounding quotes if present
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1]
                # Remove leading newlines
                content = content.lstrip('\n')
            
            if not content:
                return None, "Empty response from API"
            
            return content, None
            
    except httpx.HTTPError as e:
        print(f"  ❌ HTTP Error: {e}")
        return None, f"HTTP error: {str(e)}"
    except KeyError as e:
        print(f"  ❌ Parse Error: Missing key {e}")
        return None, f"Parse error: {str(e)}"
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None, f"Error: {str(e)}"


def generate_reply(tweet_text: str) -> tuple[str | None, str | None]:
    """Generate a reply for a tweet"""
    system_prompt = """You are a Twitter user who understands AI, crypto, and markets.
Write short replies that add real insight.
No emojis. No hashtags. No questions.
No hype or marketing tone.
No em-dashes. Use simple punctuation.
Never start with "I" or "This".
Sound like a real insider, slightly contrarian."""

    user_prompt = f"""Tweet:
"{tweet_text}"

Write a 1-2 sentence reply that adds an insider perspective or unique angle."""

    return call_openrouter(system_prompt, user_prompt, max_tokens=80, temperature=0.8)


def generate_tweet(trend_brief: str) -> tuple[str | None, str | None]:
    """Generate a tweet from a trend brief"""
    system_prompt = """You are an AI/Web3 trader-builder writing tweets.
Voice: short, confident, slightly skeptical.
No emojis. No hashtags. No motivational tone.
No questions. No "I think" or "I believe".
Sound like a real insider with knowledge.
No em-dashes. Use simple punctuation."""

    user_prompt = f"""Trend brief:
{trend_brief}

Write a single tweet (1-2 lines max) that sounds like a real person with insider knowledge."""

    return call_openrouter(system_prompt, user_prompt, max_tokens=150, temperature=0.7)


if __name__ == "__main__":
    # Quick test
    print("Testing OpenRouter client...")
    reply, error = generate_reply("Bitcoin just hit $100k. Institutions are finally here.")
    if reply:
        print(f"✅ Reply: {reply}")
    else:
        print(f"❌ Error: {error}")
