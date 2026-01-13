"""
GhostReply FastAPI Routes
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Tweet, Reply, RepliedAccount

router = APIRouter(prefix="/api")


# --- Pydantic Models ---

class TweetResponse(BaseModel):
    id: str
    url: str
    text: str
    author: str
    handle: str | None
    followers: int
    likes: int
    retweets: int
    discovered_at: datetime
    replied: bool

    class Config:
        from_attributes = True


class ReplyResponse(BaseModel):
    id: int
    tweet_id: str
    tweet_url: str | None
    reply_text: str
    status: str
    generated_at: datetime
    posted_at: datetime | None

    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    total_tweets: int
    total_replies: int
    posted_replies: int
    pending_replies: int
    replies_last_hour: int
    replies_last_24h: int


# --- Tweet Routes ---

@router.get("/tweets", response_model=list[TweetResponse])
async def get_tweets(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get discovered tweets"""
    tweets = db.query(Tweet).order_by(
        Tweet.discovered_at.desc()
    ).offset(offset).limit(limit).all()
    
    return [TweetResponse(
        id=t.id,
        url=t.url,
        text=t.text,
        author=t.author,
        handle=t.author_handle,
        followers=t.followers,
        likes=t.likes,
        retweets=t.retweets,
        discovered_at=t.discovered_at,
        replied=t.replied
    ) for t in tweets]


@router.get("/tweets/{tweet_id}", response_model=TweetResponse)
async def get_tweet(tweet_id: str, db: Session = Depends(get_db)):
    """Get single tweet"""
    tweet = db.query(Tweet).filter(Tweet.id == tweet_id).first()
    if not tweet:
        raise HTTPException(status_code=404, detail="Tweet not found")
    
    return TweetResponse(
        id=tweet.id,
        url=tweet.url,
        text=tweet.text,
        author=tweet.author,
        handle=tweet.author_handle,
        followers=tweet.followers,
        likes=tweet.likes,
        retweets=tweet.retweets,
        discovered_at=tweet.discovered_at,
        replied=tweet.replied
    )


# --- Reply Routes ---

@router.get("/replies", response_model=list[ReplyResponse])
async def get_replies(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get reply drafts"""
    query = db.query(Reply)
    if status:
        query = query.filter(Reply.status == status)
    
    replies = query.order_by(Reply.generated_at.desc()).limit(limit).all()
    return replies


@router.get("/replies/pending", response_model=list[ReplyResponse])
async def get_pending_replies(db: Session = Depends(get_db)):
    """Get pending reply drafts"""
    replies = db.query(Reply).filter(
        Reply.status == "pending"
    ).order_by(Reply.generated_at.desc()).all()
    return replies


@router.post("/replies/{reply_id}/approve")
async def approve_reply(reply_id: int, db: Session = Depends(get_db)):
    """Approve a reply for posting"""
    reply = db.query(Reply).filter(Reply.id == reply_id).first()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    
    reply.status = "approved"
    db.commit()
    
    return {"status": "approved", "reply_id": reply_id}


@router.post("/replies/{reply_id}/reject")
async def reject_reply(reply_id: int, db: Session = Depends(get_db)):
    """Reject a reply draft"""
    reply = db.query(Reply).filter(Reply.id == reply_id).first()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    
    reply.status = "rejected"
    db.commit()
    
    return {"status": "rejected", "reply_id": reply_id}


@router.post("/replies/{reply_id}/regenerate")
async def regenerate_reply(reply_id: int, db: Session = Depends(get_db)):
    """Regenerate a reply using AI"""
    from openrouter import generate_reply
    
    reply = db.query(Reply).filter(Reply.id == reply_id).first()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    
    tweet = db.query(Tweet).filter(Tweet.id == reply.tweet_id).first()
    if not tweet:
        raise HTTPException(status_code=404, detail="Tweet not found")
    
    new_text, error = await generate_reply(tweet.text)
    if error:
        raise HTTPException(status_code=500, detail=error)
    
    reply.reply_text = new_text
    reply.status = "pending"
    reply.generated_at = datetime.utcnow()
    db.commit()
    
    return {"status": "regenerated", "new_text": new_text}


# --- Analytics Routes ---

@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    """Get overall statistics"""
    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)
    
    total_tweets = db.query(Tweet).count()
    total_replies = db.query(Reply).count()
    posted_replies = db.query(Reply).filter(Reply.status == "posted").count()
    pending_replies = db.query(Reply).filter(Reply.status == "pending").count()
    
    replies_last_hour = db.query(Reply).filter(
        Reply.status == "posted",
        Reply.posted_at >= hour_ago
    ).count()
    
    replies_last_24h = db.query(Reply).filter(
        Reply.status == "posted",
        Reply.posted_at >= day_ago
    ).count()
    
    return StatsResponse(
        total_tweets=total_tweets,
        total_replies=total_replies,
        posted_replies=posted_replies,
        pending_replies=pending_replies,
        replies_last_hour=replies_last_hour,
        replies_last_24h=replies_last_24h
    )


@router.get("/top-replies")
async def get_top_replies(limit: int = 10, db: Session = Depends(get_db)):
    """Get top performing replies by engagement"""
    replies = db.query(Reply).filter(
        Reply.status == "posted",
        Reply.likes_1h > 0
    ).order_by(Reply.likes_1h.desc()).limit(limit).all()
    
    return [
        {
            "id": r.id,
            "reply_text": r.reply_text,
            "likes": r.likes_1h,
            "posted_at": r.posted_at
        }
        for r in replies
    ]
