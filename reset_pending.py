
from database import SessionLocal, Reply, Tweet

db = SessionLocal()

# Delete all pending replies
replies = db.query(Reply).filter(Reply.status == "pending").all()
count_replies = 0
for r in replies:
    tweet = db.query(Tweet).filter(Tweet.id == r.tweet_id).first()
    if tweet:
        db.delete(tweet)
    db.delete(r)
    count_replies += 1

db.commit()
print(f"Deleted {count_replies} pending replies and their tweets.")
db.close()
