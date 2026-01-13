
from database import SessionLocal, Reply, Tweet

db = SessionLocal()

# Get all tweet IDs that have a reply
reply_tweet_ids = [r.tweet_id for r in db.query(Reply.tweet_id).all()]

# Get all tweets
tweets = db.query(Tweet).all()
deleted_count = 0

for t in tweets:
    if t.id not in reply_tweet_ids:
        db.delete(t)
        deleted_count += 1

db.commit()
print(f"Deleted {deleted_count} tweets with no replies.")
db.close()
