
from database import SessionLocal, Reply, Tweet

db = SessionLocal()

# Delete empty replies
replies = db.query(Reply).filter(Reply.reply_text == "").all()
count_replies = 0
for r in replies:
    # Also delete the tweet so it gets rediscovered
    tweet = db.query(Tweet).filter(Tweet.id == r.tweet_id).first()
    if tweet:
        db.delete(tweet)
    db.delete(r)
    count_replies += 1

db.commit()
print(f"Deleted {count_replies} empty replies and their tweets.")
db.close()
