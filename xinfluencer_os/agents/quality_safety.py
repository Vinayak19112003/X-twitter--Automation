"""
Quality & Safety Agent - Content Validation
Validates content before posting, enforces anti-spam rules
"""
import random
from datetime import datetime, timedelta
from collections import deque
import sys
sys.path.insert(0, '..')
from config import settings
from db import SessionLocal, RepliedAccount, ReplyHistory, DailyStats, get_today_stats


# In-memory cache for fast similarity checks
_recent_replies = deque(maxlen=30)

# Banned phrases that sound AI-generated
BANNED_PHRASES = [
    "as an ai", "certainly", "in conclusion", "i can help",
    "interesting tweet", "great point", "this is huge",
    "delve", "crucial", "it's important to", "firstly",
    "absolutely", "definitely", "game changer", "paradigm shift",
    "let me explain", "here's why", "here's the thing"
]

# Obvious AI emoji patterns
BANNED_EMOJIS = [
    "🚀", "📈", "💎", "🔥", "🧵", "👇", "🤖", "🧠", 
    "😅", "🙏", "👀", "💯", "🎯", "⚡", "🌙", "📊"
]

# Generic replies to reject
GENERIC_STARTERS = [
    "great", "amazing", "love this", "so true", "facts",
    "couldn't agree more", "exactly", "100%", "this is the way"
]


def validate_content(text: str, content_type: str = "reply") -> tuple[bool, str]:
    """
    Validate content before posting
    
    Args:
        text: Content to validate
        content_type: "reply", "tweet", "thread", "quote"
        
    Returns:
        tuple: (is_valid, rejection_reason)
    """
    if not text:
        return False, "Empty content"
    
    text_lower = text.lower().strip()
    
    # Length check
    max_length = 280 if content_type in ["tweet", "quote"] else 240
    if len(text) > max_length:
        return False, f"Too long ({len(text)} > {max_length})"
    
    # Hashtag check
    if "#" in text:
        return False, "Contains hashtag"
    
    # Question check (for replies)
    if content_type == "reply" and text.rstrip().endswith("?"):
        return False, "Ends with question"
    
    # Banned phrases
    for phrase in BANNED_PHRASES:
        if phrase in text_lower:
            return False, f"Banned phrase: {phrase}"
    
    # Emoji check
    for emoji in BANNED_EMOJIS:
        if emoji in text:
            return False, f"Banned emoji: {emoji}"
    
    # Generic starter check
    for starter in GENERIC_STARTERS:
        if text_lower.startswith(starter):
            return False, f"Generic starter: {starter}"
    
    # Em-dash check
    if "—" in text:
        return False, "Contains em-dash"
    
    # Similarity check against recent replies
    for past_reply in _recent_replies:
        if text_lower == past_reply.lower():
            return False, "Duplicate reply"
        if len(text_lower) > 20 and text_lower[:20] == past_reply.lower()[:20]:
            return False, "Similar starting phrase"
    
    return True, "OK"


def should_skip_random() -> tuple[bool, float]:
    """
    Apply random skip chance for human-like behavior
    
    Returns:
        tuple: (should_skip, skip_probability_used)
    """
    probability = random.uniform(settings.skip_chance_min, settings.skip_chance_max)
    skip = random.random() < probability
    return skip, probability


def can_reply_to_account(username: str) -> tuple[bool, str]:
    """
    Check if we can reply to this account (24h cooldown)
    
    Returns:
        tuple: (can_reply, reason)
    """
    if not username:
        return True, "No username"
    
    db = SessionLocal()
    try:
        account = db.query(RepliedAccount).filter(
            RepliedAccount.username == username
        ).first()
        
        if account:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            if account.last_replied > cutoff:
                hours_ago = (datetime.utcnow() - account.last_replied).total_seconds() / 3600
                return False, f"Replied {hours_ago:.1f}h ago"
        
        return True, "OK"
    finally:
        db.close()


def check_daily_limits(action_type: str) -> tuple[bool, str]:
    """
    Check if we've hit daily limits for an action type
    
    Args:
        action_type: "reply", "like", "retweet", "post"
        
    Returns:
        tuple: (within_limits, reason)
    """
    db = SessionLocal()
    try:
        stats = get_today_stats(db)
        
        limits = {
            "reply": (stats.replies_count, settings.max_replies_per_day),
            "like": (stats.likes_count, settings.max_likes_per_day),
            "retweet": (stats.retweets_count, settings.max_retweets_per_day),
            "post": (stats.posts_count, settings.max_posts_per_day)
        }
        
        if action_type not in limits:
            return True, "Unknown action type"
        
        current, limit = limits[action_type]
        
        if current >= limit:
            return False, f"Daily limit reached ({current}/{limit})"
        
        return True, f"OK ({current}/{limit})"
    finally:
        db.close()


def record_reply(reply_text: str):
    """Record a reply for similarity tracking"""
    _recent_replies.append(reply_text)
    
    # Also persist to DB
    db = SessionLocal()
    try:
        db.add(ReplyHistory(reply_text=reply_text))
        db.commit()
    finally:
        db.close()


def record_account_reply(username: str):
    """Record that we replied to an account"""
    if not username:
        return
    
    db = SessionLocal()
    try:
        account = db.query(RepliedAccount).filter(
            RepliedAccount.username == username
        ).first()
        
        if account:
            account.last_replied = datetime.utcnow()
        else:
            db.add(RepliedAccount(
                username=username,
                last_replied=datetime.utcnow()
            ))
        
        db.commit()
    finally:
        db.close()


def load_recent_replies():
    """Load recent replies from DB into memory"""
    global _recent_replies
    db = SessionLocal()
    try:
        recent = db.query(ReplyHistory).order_by(
            ReplyHistory.created_at.desc()
        ).limit(30).all()
        
        for r in reversed(recent):
            _recent_replies.append(r.reply_text)
        
        print(f"📚 Loaded {len(_recent_replies)} recent replies for similarity check")
    finally:
        db.close()


if __name__ == "__main__":
    # Test validation
    test_cases = [
        ("Great insights on the market! 🚀", "reply"),
        ("The market is overheated right now.", "reply"),
        ("As an AI, I think this is interesting.", "reply"),
        ("Certainly! Here's what you need to know—", "reply"),
        ("Bitcoin's correlation with risk assets remains high despite the narrative shift.", "reply"),
    ]
    
    print("Testing Quality Agent:\n")
    for text, ctype in test_cases:
        valid, reason = validate_content(text, ctype)
        status = "✅" if valid else "❌"
        print(f"{status} '{text[:50]}...' -> {reason}")
