"""
GhostReply Database - SQLite with SQLAlchemy
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

Base = declarative_base()


class Tweet(Base):
    """Discovered tweets"""
    __tablename__ = "tweets"
    
    id = Column(String, primary_key=True)
    url = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    author = Column(String, nullable=False)
    author_handle = Column(String)
    followers = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    retweets = Column(Integer, default=0)
    discovered_at = Column(DateTime, default=datetime.utcnow)
    replied = Column(Boolean, default=False)
    ignored = Column(Boolean, default=False)


class Reply(Base):
    """Generated and posted replies"""
    __tablename__ = "replies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tweet_id = Column(String, nullable=False)
    tweet_url = Column(String)
    reply_text = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
    posted_at = Column(DateTime)
    status = Column(String, default="pending")  # pending, approved, posted, rejected
    likes_1h = Column(Integer, default=0)
    rejection_reason = Column(String)


class RepliedAccount(Base):
    """Track accounts we've replied to (24h cooldown)"""
    __tablename__ = "replied_accounts"
    
    username = Column(String, primary_key=True)
    last_replied = Column(DateTime, default=datetime.utcnow)


class AppSettings(Base):
    """Application settings stored in DB"""
    __tablename__ = "settings"
    
    key = Column(String, primary_key=True)
    value = Column(String)


# Database connection
engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create all tables"""
    Base.metadata.create_all(engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
