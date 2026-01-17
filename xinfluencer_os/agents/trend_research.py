"""
Trend Research Agent - Perplexity API
Finds daily trending topics in AI/Web3/crypto
"""
import httpx
import json
from datetime import datetime
import sys
sys.path.insert(0, '..')
from config import settings
from db import SessionLocal, Trend, init_db


PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

TREND_RESEARCH_PROMPT = """You are a research agent tracking AI, Web3, and crypto trends.

Find the TOP 5-7 trending topics RIGHT NOW in these areas:
- AI: model releases, OpenAI/Google/Anthropic news, AI agents, GPU/compute
- Web3: protocol updates, token launches, DeFi narratives
- Crypto: Bitcoin/ETH price moves, whale activity, market sentiment

For each topic, provide:
1. Topic name (short)
2. Why it's trending (1 sentence)
3. 3 key points
4. 2 source URLs (real, recent articles)

Respond ONLY with valid JSON array:
[
  {
    "topic": "...",
    "why_trending": "...",
    "key_points": ["...", "...", "..."],
    "sources": ["url1", "url2"]
  }
]
"""


def fetch_trends() -> list[dict]:
    """Fetch trending topics from Perplexity API"""
    if not settings.perplexity_api_key:
        print("❌ Perplexity API key not configured")
        return []
    
    headers = {
        "Authorization": f"Bearer {settings.perplexity_api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": settings.perplexity_model,
        "messages": [
            {"role": "system", "content": "You are a trend research assistant. Always respond with valid JSON only."},
            {"role": "user", "content": TREND_RESEARCH_PROMPT}
        ],
        "max_tokens": 2000,
        "temperature": 0.3
    }
    
    try:
        print("🔍 Fetching trends from Perplexity...")
        with httpx.Client(timeout=60) as client:
            response = client.post(PERPLEXITY_URL, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            # Handle potential markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            trends = json.loads(content.strip())
            print(f"✅ Found {len(trends)} trends")
            return trends
            
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(f"Raw content: {content[:500]}")
        return []
    except httpx.HTTPError as e:
        print(f"❌ API error: {e}")
        return []
    except Exception as e:
        print(f"❌ Error: {e}")
        return []


def save_trends(trends: list[dict]) -> int:
    """Save trends to database"""
    db = SessionLocal()
    saved = 0
    
    try:
        for trend in trends:
            db_trend = Trend(
                topic=trend.get("topic", "Unknown"),
                why_trending=trend.get("why_trending", ""),
                key_points=trend.get("key_points", []),
                sources=trend.get("sources", []),
                fetched_at=datetime.utcnow(),
                used=False
            )
            db.add(db_trend)
            saved += 1
        
        db.commit()
        print(f"💾 Saved {saved} trends to database")
        return saved
        
    except Exception as e:
        print(f"❌ DB error: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


def get_unused_trends(limit: int = 5) -> list[Trend]:
    """Get unused trends for content generation"""
    db = SessionLocal()
    try:
        trends = db.query(Trend).filter(Trend.used == False).order_by(Trend.fetched_at.desc()).limit(limit).all()
        return trends
    finally:
        db.close()


def mark_trend_used(trend_id: int):
    """Mark a trend as used"""
    db = SessionLocal()
    try:
        trend = db.query(Trend).filter(Trend.id == trend_id).first()
        if trend:
            trend.used = True
            db.commit()
    finally:
        db.close()


def run_trend_research():
    """Main entry point for trend research"""
    print("\n" + "="*50)
    print("🔬 TREND RESEARCH AGENT")
    print("="*50 + "\n")
    
    trends = fetch_trends()
    
    if trends:
        save_trends(trends)
        
        print("\n📊 Today's Trends:")
        for i, t in enumerate(trends, 1):
            print(f"\n{i}. {t.get('topic', 'N/A')}")
            print(f"   Why: {t.get('why_trending', 'N/A')}")
    else:
        print("⚠️ No trends fetched")
    
    return trends


if __name__ == "__main__":
    init_db()
    run_trend_research()
