
from database import SessionLocal, Reply, Tweet

db = SessionLocal()
replies = db.query(Reply).filter(Reply.status == "pending").all()

print(f"Found {len(replies)} pending replies:")
for r in replies:
    print(f"ID: {r.id} | Tweet ID: {r.tweet_id}")
    print(f"Text: '{r.reply_text}'")
    print("-" * 20)

db.close()
