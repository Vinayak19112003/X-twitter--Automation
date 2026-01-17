"""
XInfluencerOS Database Models
SQLite storage for trends, content, actions, and analytics
"""
from datetime import datetime, date
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Date, Boolean, Float, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings
import os

# Ensure storage directory exists
os.makedirs(os.path.dirname(settings.db_path), exist_ok=True)

Base = declarative_base()
engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class Trend(Base):
    """Stored trend briefs from Perplexity"""
    __tablename__ = "trends"
    
    id = Column(Integer, primary_key=True)
    topic = Column(String(255), nullable=False)
    why_trending = Column(Text)
    key_points = Column(JSON)  # List of strings
    sources = Column(JSON)     # List of URLs
    fetched_at = Column(DateTime, default=datetime.utcnow)
    used = Column(Boolean, default=False)


class ContentDraft(Base):
    """Generated content drafts"""
    __tablename__ = "content_drafts"
    
    id = Column(Integer, primary_key=True)
    content_type = Column(String(50))  # tweet, thread, quote
    text = Column(Text, nullable=False)
    thread_items = Column(JSON)  # For threads: list of tweet texts
    trend_id = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")  # pending, posted, rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    posted_at = Column(DateTime, nullable=True)


class ActionLog(Base):
    """Log of all browser actions"""
    __tablename__ = "action_log"
    
    id = Column(Integer, primary_key=True)
    action_type = Column(String(50))  # post, reply, like, retweet, quote
    target_url = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, success, failed
    error_message = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class DailyStats(Base):
    """Daily analytics summary"""
    __tablename__ = "daily_stats"
    
    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, default=date.today)
    replies_count = Column(Integer, default=0)
    likes_count = Column(Integer, default=0)
    retweets_count = Column(Integer, default=0)
    posts_count = Column(Integer, default=0)
    threads_count = Column(Integer, default=0)
    quote_tweets_count = Column(Integer, default=0)


class RepliedAccount(Base):
    """Tracks accounts we've replied to (24h cooldown)"""
    __tablename__ = "replied_accounts"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(255), unique=True, nullable=False)
    last_replied = Column(DateTime, default=datetime.utcnow)


class ReplyHistory(Base):
    """Stores recent replies for similarity checking"""
    __tablename__ = "reply_history"
    
    id = Column(Integer, primary_key=True)
    reply_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(engine)
    print("✅ Database initialized")


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Caller must close


def get_today_stats(db) -> DailyStats:
    """Get or create today's stats record"""
    today = date.today()
    stats = db.query(DailyStats).filter(DailyStats.date == today).first()
    if not stats:
        stats = DailyStats(date=today)
        db.add(stats)
        db.commit()
    return stats


if __name__ == "__main__":
    init_db()
