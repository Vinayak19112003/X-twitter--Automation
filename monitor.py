"""
GhostReply Monitor - Background task for tweet discovery and reply generation
Uses synchronous Playwright API to avoid Windows asyncio issues
"""
import sys
import time
import random
import httpx
from datetime import datetime, timedelta
from database import SessionLocal, Tweet, Reply, RepliedAccount, init_db
from browser import TwitterBrowser
from config import settings


# OpenRouter settings
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = """You are a Twitter user who understands AI, crypto, and markets.
Write short, sharp replies.
No emojis.
No hype.
No marketing tone.
No em-dashes (—). Use hyphens or simple punctuation.
Do not explain basic concepts.
Never start with "I" or "This".
Be slightly contrarian or add a unique angle."""

USER_PROMPT_TEMPLATE = """Tweet:
"{tweet_text}"

Write a 1–2 sentence reply that adds a thoughtful or insider-style perspective."""

# Strict filtering keywords
RELEVANT_KEYWORDS = [
    "web3", "crypto", "trading", "ai", "bitcoin", "solana", "eth", 
    "ethereum", "blockchain", "defi", "nft", "token", "market",
    "pump", "dump", "alpha", "gem", "bull", "bear", "analysis"
]


def generate_reply_sync(tweet_text: str) -> tuple[str | None, str | None]:
    """Generate a reply using OpenRouter (synchronous)"""
    if not settings.openrouter_api_key:
        return None, "OpenRouter API key not configured in .env"
    
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
        "max_tokens": 1000,
        "temperature": 0.8
    }
    
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(OPENROUTER_URL, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            # DEBUG RESPONSE
            print(f"  🔍 Raw API Response: {data}")
            
            reply_text = data["choices"][0]["message"]["content"]
            if reply_text:
                reply_text = reply_text.strip()
            else:
                reply_text = ""
            
            # Remove surrounding quotes if present
            if reply_text.startswith('"') and reply_text.endswith('"'):
                reply_text = reply_text[1:-1]
            
            # Basic validation
            if not reply_text:
                return None, "Empty reply generated"

            if len(reply_text) > 240:
                return None, "Reply too long"
            
            return reply_text, None
            
    except httpx.HTTPError as e:
        return None, f"API error: {str(e)}"
    except Exception as e:
        return None, f"Error: {str(e)}"


class GhostReplyMonitor:
    """Main monitoring loop for tweet discovery and reply generation"""
    
    def __init__(self):
        self.browser: TwitterBrowser | None = None
        self.running = False
        self.replies_this_hour = 0
        self.hour_start = datetime.now()
        self.auto_post = False
    
    def start(self, headless: bool = False):
        """Start the monitor"""
        init_db()
        
        self.browser = TwitterBrowser()
        self.browser.start(headless=headless)
        
        # Check login
        if not self.browser.navigate_home():
            print("❌ Not logged in. Run: python browser.py")
            return False
        
        print("✅ Logged in and ready!")
        self.running = True
        return True
    
    def stop(self):
        """Stop the monitor"""
        self.running = False
        if self.browser:
            self.browser.close()
    
    def discover_tweets(self) -> list[dict]:
        """Discover new tweets from feed only"""
        all_tweets = []
        
        # Get from feed
        print("📡 Scanning For You feed...")
        feed_tweets = self.browser.get_feed_tweets()
        all_tweets.extend(feed_tweets)
        
        # Search disabled as requested
        # search_queries = ["AI", "crypto", "bitcoin", "web3", "trading"]
        # query = random.choice(search_queries)
        # print(f"🔍 Searching: {query}...")
        # search_tweets = self.browser.search_tweets(query)
        # all_tweets.extend(search_tweets)
        
        # Deduplicate
        seen_ids = set()
        unique_tweets = []
        for tweet in all_tweets:
            if tweet["id"] and tweet["id"] not in seen_ids:
                seen_ids.add(tweet["id"])
                unique_tweets.append(tweet)
        
        return unique_tweets
    
    def _should_skip_account(self, db, username: str) -> bool:
        """Check if we've replied to this account in last 24h"""
        if not username:
            return False
            
        account = db.query(RepliedAccount).filter(
            RepliedAccount.username == username
        ).first()
        
        if account:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            if account.last_replied > cutoff:
                return True
        
        return False
    
    def _can_reply(self) -> bool:
        """Check if we can reply based on rate limits"""
        if self.replies_this_hour >= settings.max_replies_per_hour:
            return False
        return True

    def _is_relevant(self, text: str) -> bool:
        """Check if tweet contains relevant keywords"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in RELEVANT_KEYWORDS)

    def process_tweet(self, tweet: dict, db) -> Reply | None:
        """Process a single tweet - generate reply draft"""
        # strict relevancy check
        if not self._is_relevant(tweet["text"]):
            print(f"⏩ Variable filtered (irrelevant): {tweet['text'][:40]}...")
            return None        
            
        # Check if already in DB
        existing = db.query(Tweet).filter(Tweet.id == tweet["id"]).first()
        if existing:
            return None
        
        # Check 24h account cooldown
        if self._should_skip_account(db, tweet.get("handle")):
            print(f"⏭️ Skipping @{tweet.get('handle')} (24h cooldown)")
            return None
        
        # Save tweet to DB
        db_tweet = Tweet(
            id=tweet["id"],
            url=tweet["url"],
            text=tweet["text"],
            author=tweet.get("author", ""),
            author_handle=tweet.get("handle", ""),
            followers=tweet.get("followers", 0),
            likes=tweet.get("likes", 0),
            retweets=tweet.get("retweets", 0)
        )
        db.add(db_tweet)
        db.commit()
        
        # Generate reply
        print(f"🤖 Generating reply for: {tweet['text'][:60]}...")
        
        reply_text, error = generate_reply_sync(tweet["text"])
            
        if error:
            print(f"⚠️ Generation failed: {error}")
            return None
        
        # Save reply draft
        reply = Reply(
            tweet_id=tweet["id"],
            tweet_url=tweet["url"],
            reply_text=reply_text,
            status="pending"
        )
        db.add(reply)
        db.commit()
        
        print(f"✅ Draft: {reply_text}")
        return reply
    
    def post_approved_reply(self, reply: Reply, db) -> bool:
        """Post an approved reply"""
        if not self._can_reply():
            print("⏸️ Rate limit reached")
            return False
        
        self.browser.random_delay()
        
        success = self.browser.post_reply(reply.tweet_url, reply.reply_text)
        
        if success:
            reply.status = "posted"
            reply.posted_at = datetime.utcnow()
            self.replies_this_hour += 1
            
            tweet = db.query(Tweet).filter(Tweet.id == reply.tweet_id).first()
            if tweet and tweet.author_handle:
                account = db.query(RepliedAccount).filter(
                    RepliedAccount.username == tweet.author_handle
                ).first()
                if account:
                    account.last_replied = datetime.utcnow()
                else:
                    db.add(RepliedAccount(
                        username=tweet.author_handle,
                        last_replied=datetime.utcnow()
                    ))
            
            db.commit()
            return True
        else:
            reply.status = "failed"
            db.commit()
            return False
    
    def run_cycle(self):
        """Run one discovery and processing cycle"""
        db = SessionLocal()
        
        try:
            tweets = self.discover_tweets()
            print(f"📋 Found {len(tweets)} eligible tweets")
            
            for tweet in tweets:
                if not self.running:
                    break
                    
                reply = self.process_tweet(tweet, db)
                
                if reply and self.auto_post and self._can_reply():
                    self.post_approved_reply(reply, db)
                
                time.sleep(2)
                
        except Exception as e:
            print(f"❌ Cycle error: {e}")
        finally:
            db.close()
    
    def run_loop(self, interval_minutes: int = 5):
        """Run continuous monitoring loop"""
        print(f"🚀 Starting monitor (every {interval_minutes} min)...")
        
        while self.running:
            self.run_cycle()
            
            if self.running:
                print(f"💤 Sleeping {interval_minutes} minutes...")
                time.sleep(interval_minutes * 60)


def run_monitor(headless: bool = False, auto_post: bool = False):
    """Start the GhostReply monitor"""
    monitor = GhostReplyMonitor()
    monitor.auto_post = auto_post
    
    if monitor.start(headless=headless):
        try:
            monitor.run_loop(interval_minutes=1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping...")
        finally:
            monitor.stop()


if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 GhostReply Monitor Starting...")
    print("="*50 + "\n")
    
    auto_post = "--auto-post" in sys.argv
    
    run_monitor(headless=False, auto_post=auto_post)
