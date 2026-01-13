
from database import SessionLocal, Reply, Tweet

db = SessionLocal()

# Delete failed replies
replies = db.query(Reply).filter(Reply.status == "failed").all()
count = 0
for r in replies:
    tweet = db.query(Tweet).filter(Tweet.id == r.tweet_id).first()
    if tweet:
        db.delete(tweet)
    db.delete(r)
    count += 1

db.commit()
print(f"Deleted {count} failed replies and their tweets.")
db.close()
