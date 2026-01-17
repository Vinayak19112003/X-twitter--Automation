"""
Content Writer Agent - Perplexity + OpenRouter
Generates original tweets, threads, and quote tweets
"""
import httpx
import random
import sys
sys.path.insert(0, '..')
from config import settings
from db import SessionLocal, ContentDraft, Trend
from pathlib import Path


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Load prompts
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load prompt from file"""
    path = PROMPTS_DIR / f"{name}.txt"
    if path.exists():
        return path.read_text()
    return ""


def generate_tweet(trend_brief: str) -> list[str]:
    """Generate tweet options from a trend brief"""
    
    system_prompt = """You are an AI/Web3 trader-builder writing tweets.
Voice: short, confident, slightly skeptical.
No emojis. No hashtags. No motivational tone.
No questions. No "I think" or "I believe".
Sound like a real insider with knowledge."""
    
    user_prompt = f"""Trend brief:
{trend_brief}

Write 3 tweet options.
Each must be 1-2 lines MAX and sound like a real person with insider knowledge.
Do not use em-dashes. Use simple punctuation.
Output ONLY the 3 tweets, numbered 1-3."""
    
    return _call_openrouter(system_prompt, user_prompt, max_tokens=300)


def generate_thread(trend_brief: str) -> list[str]:
    """Generate a thread from a trend brief"""
    
    system_prompt = """You are an AI/Web3 expert writing Twitter threads.
Style: sharp, informed, slightly contrarian.
No emojis. No hashtags. No motivational fluff.
Each tweet must stand alone but connect to the next."""
    
    user_prompt = f"""Trend brief:
{trend_brief}

Write a 5-tweet thread:
1. Hook (attention-grabbing observation)
2-4. Key insights (one per tweet)
5. Closing (sharp takeaway)

Output ONLY the 5 tweets, numbered 1-5.
Each tweet should be 1-2 lines max."""
    
    return _call_openrouter(system_prompt, user_prompt, max_tokens=600)


def generate_quote_tweet(original_tweet: str) -> str:
    """Generate a quote tweet"""
    
    system_prompt = """You are quoting a tweet with your own take.
Add insight, not just agreement.
No emojis. No hashtags. No questions.
Sound like someone who knows more than the original poster."""
    
    user_prompt = f"""Original tweet:
"{original_tweet}"

Write a 1-sentence quote tweet that adds a unique insight or contrarian angle.
Output ONLY the quote text."""
    
    result = _call_openrouter(system_prompt, user_prompt, max_tokens=100)
    return result[0] if result else ""


def _call_openrouter(system: str, user: str, max_tokens: int = 200) -> list[str]:
    """Call OpenRouter API"""
    if not settings.openrouter_api_key:
        print("❌ OpenRouter API key not configured")
        return []
    
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://xinfluenceros.local",
        "X-Title": "XInfluencerOS"
    }
    
    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7
    }
    
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(OPENROUTER_URL, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            
            # Parse numbered list
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            # Remove numbering
            results = []
            for line in lines:
                # Strip "1. ", "1) ", etc.
                if line and line[0].isdigit():
                    line = line.lstrip("0123456789.)-: ")
                if line:
                    results.append(line)
            
            return results
            
    except Exception as e:
        print(f"❌ OpenRouter error: {e}")
        return []


def create_daily_content():
    """Generate daily content from available trends"""
    print("\n" + "="*50)
    print("✍️ CONTENT WRITER AGENT")
    print("="*50 + "\n")
    
    db = SessionLocal()
    
    try:
        # Get unused trends
        trends = db.query(Trend).filter(Trend.used == False).order_by(Trend.fetched_at.desc()).limit(3).all()
        
        if not trends:
            print("⚠️ No unused trends available. Run trend research first.")
            return []
        
        drafts = []
        
        # Generate 1-2 original tweets
        for trend in trends[:2]:
            brief = f"Topic: {trend.topic}\nWhy: {trend.why_trending}\nPoints: {', '.join(trend.key_points or [])}"
            
            print(f"📝 Generating tweet for: {trend.topic}")
            options = generate_tweet(brief)
            
            if options:
                # Pick best option (first one for now)
                selected = options[0]
                
                draft = ContentDraft(
                    content_type="tweet",
                    text=selected,
                    trend_id=trend.id,
                    status="pending"
                )
                db.add(draft)
                drafts.append(draft)
                
                print(f"✅ Draft: {selected[:60]}...")
                
                # Mark trend as used
                trend.used = True
        
        db.commit()
        print(f"\n💾 Created {len(drafts)} content drafts")
        return drafts
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        return []
    finally:
        db.close()


def get_pending_drafts(content_type: str = None) -> list[ContentDraft]:
    """Get pending content drafts"""
    db = SessionLocal()
    try:
        query = db.query(ContentDraft).filter(ContentDraft.status == "pending")
        if content_type:
            query = query.filter(ContentDraft.content_type == content_type)
        return query.order_by(ContentDraft.created_at.desc()).all()
    finally:
        db.close()


if __name__ == "__main__":
    from db import init_db
    init_db()
    create_daily_content()
