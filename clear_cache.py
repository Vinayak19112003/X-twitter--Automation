
from database import SessionLocal, RepliedAccount

db = SessionLocal()
db.query(RepliedAccount).delete()
db.commit()
print("Cleared skipped accounts cache")
db.close()
