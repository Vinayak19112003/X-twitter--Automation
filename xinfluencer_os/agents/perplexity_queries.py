"""
Perplexity Query Agent - Dynamic Search Query Generation
Generates 8-15 X search queries daily focused on AI + VibeCoding
"""
import os
import json
import httpx
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv

# Load env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
CACHE_FILE = Path(__file__).parent.parent / "storage" / "daily_queries.json"

QUERY_GENERATION_PROMPT = """You are an AI trend researcher focused on AI development tools and VibeCoding.

Generate 10-15 X/Twitter search queries to find high-quality tweets about:

CORE TOPICS (focus here):
- VibeCoding / vibe coding / vibe-coding
- Cursor IDE / Cursor editor
- Claude Code / Claude artifacts
- AI coding assistants
- OpenAI updates (GPT, Codex, ChatGPT for developers)
- Gemini / Google AI for developers
- AI agent frameworks (LangChain, CrewAI, AutoGPT)
- Build-in-public AI products
- AI developer workflows
- Windsurf, Codeium, Copilot, Tabnine

QUERY RULES:
- Use X search operators: min_faves:10
- Use quotes for exact phrases: "cursor ide"
- Mix broad and specific queries
- Target active builders sharing real work
- Do NOT use min_retweets (too restrictive)

OUTPUT FORMAT (JSON only, no markdown):
{
  "date": "YYYY-MM-DD",
  "queries": [
    {"q": "vibecoding min_faves:10", "topic": "vibecoding"},
    {"q": "\\"cursor\\" coding min_faves:20", "topic": "ai_dev_tools"},
    {"q": "\\"claude code\\" min_faves:10", "topic": "ai_dev_tools"},
    {"q": "building with AI min_faves:30", "topic": "build_in_public"}
  ]
}

Generate queries for today. Output ONLY valid JSON."""


def get_api_key() -> str:
    """Get Perplexity API key"""
    key = os.getenv("PERPLEXITY_API_KEY")
    if not key:
        raise ValueError("PERPLEXITY_API_KEY not set")
    return key


def get_model() -> str:
    """Get Perplexity model"""
    return os.getenv("PERPLEXITY_MODEL", "sonar-pro")


def generate_queries() -> dict:
    """Generate fresh queries from Perplexity"""
    api_key = get_api_key()
    model = get_model()
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a trend research assistant. Output only valid JSON."},
            {"role": "user", "content": QUERY_GENERATION_PROMPT}
        ],
        "max_tokens": 1500,
        "temperature": 0.4
    }
    
    try:
        print("🔍 Generating daily search queries from Perplexity...")
        
        with httpx.Client(timeout=60) as client:
            response = client.post(PERPLEXITY_URL, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Clean JSON from potential markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            result = json.loads(content.strip())
            
            # Ensure date is set
            if "date" not in result:
                result["date"] = str(date.today())
            
            print(f"✅ Generated {len(result.get('queries', []))} queries")
            return result
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        return get_fallback_queries()
    except Exception as e:
        print(f"❌ Perplexity error: {e}")
        return get_fallback_queries()


def get_fallback_queries() -> dict:
    """Fallback queries if Perplexity fails"""
    return {
        "date": str(date.today()),
        "queries": [
            {"q": "vibecoding min_faves:50", "topic": "vibecoding"},
            {"q": "\"cursor\" coding min_faves:80", "topic": "ai_dev_tools"},
            {"q": "\"claude code\" min_faves:30", "topic": "ai_dev_tools"},
            {"q": "building with AI min_faves:100", "topic": "build_in_public"},
            {"q": "\"AI agent\" framework min_faves:50", "topic": "ai_agents"},
            {"q": "copilot workflow min_faves:50", "topic": "ai_dev_tools"},
            {"q": "\"windsurf\" OR \"codeium\" min_faves:30", "topic": "ai_dev_tools"},
            {"q": "shipped with AI min_faves:40", "topic": "build_in_public"}
        ]
    }


def save_cache(data: dict):
    """Save queries to cache file"""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"💾 Cached queries to {CACHE_FILE}")


def load_cache() -> dict | None:
    """Load cached queries if valid for today"""
    if not CACHE_FILE.exists():
        return None
    
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        
        # Check if cache is from today
        cache_date = data.get("date", "")
        if cache_date == str(date.today()):
            print(f"📂 Using cached queries from {cache_date}")
            return data
        else:
            print(f"🔄 Cache expired ({cache_date})")
            return None
    except:
        return None


def get_daily_queries() -> list[dict]:
    """Get today's search queries (from cache or generate fresh)"""
    # Try cache first
    cached = load_cache()
    if cached:
        return cached.get("queries", [])
    
    # Generate fresh
    data = generate_queries()
    save_cache(data)
    return data.get("queries", [])


def print_queries():
    """Print current queries"""
    queries = get_daily_queries()
    print(f"\n📋 Today's Search Queries ({len(queries)}):")
    for i, q in enumerate(queries, 1):
        print(f"  {i}. [{q.get('topic', 'general')}] {q.get('q', '')}")


if __name__ == "__main__":
    print_queries()
