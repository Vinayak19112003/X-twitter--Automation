"""
Analytics Agent - Reporting & Insights
Generates daily summaries and tracks engagement
"""
from datetime import datetime, date, timedelta
import sys
sys.path.insert(0, '..')
from db import SessionLocal, DailyStats, ActionLog, get_today_stats


def get_daily_summary(target_date: date = None) -> dict:
    """
    Get summary for a specific date
    
    Args:
        target_date: Date to summarize (default: today)
        
    Returns:
        dict with stats and action breakdown
    """
    if target_date is None:
        target_date = date.today()
    
    db = SessionLocal()
    try:
        # Get stats record
        stats = db.query(DailyStats).filter(DailyStats.date == target_date).first()
        
        if not stats:
            return {
                "date": str(target_date),
                "total_actions": 0,
                "breakdown": {},
                "success_rate": 0
            }
        
        # Get action logs for the day
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())
        
        actions = db.query(ActionLog).filter(
            ActionLog.timestamp >= start,
            ActionLog.timestamp <= end
        ).all()
        
        # Calculate stats
        total = len(actions)
        successful = sum(1 for a in actions if a.status == "success")
        
        return {
            "date": str(target_date),
            "total_actions": total,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "breakdown": {
                "replies": stats.replies_count,
                "likes": stats.likes_count,
                "retweets": stats.retweets_count,
                "posts": stats.posts_count,
                "threads": stats.threads_count,
                "quote_tweets": stats.quote_tweets_count
            }
        }
    finally:
        db.close()


def get_weekly_summary() -> dict:
    """Get summary for the past 7 days"""
    summaries = []
    today = date.today()
    
    for i in range(7):
        d = today - timedelta(days=i)
        summaries.append(get_daily_summary(d))
    
    # Aggregate
    total = {
        "replies": 0,
        "likes": 0,
        "retweets": 0,
        "posts": 0
    }
    
    for s in summaries:
        for key in total:
            total[key] += s["breakdown"].get(key, 0)
    
    return {
        "period": f"{today - timedelta(days=6)} to {today}",
        "daily_summaries": summaries,
        "totals": total
    }


def get_top_actions(action_type: str = None, limit: int = 10) -> list[dict]:
    """Get recent successful actions"""
    db = SessionLocal()
    try:
        query = db.query(ActionLog).filter(ActionLog.status == "success")
        
        if action_type:
            query = query.filter(ActionLog.action_type == action_type)
        
        actions = query.order_by(ActionLog.timestamp.desc()).limit(limit).all()
        
        return [{
            "type": a.action_type,
            "url": a.target_url,
            "content": a.content[:100] if a.content else None,
            "timestamp": str(a.timestamp)
        } for a in actions]
    finally:
        db.close()


def print_daily_report():
    """Print formatted daily report"""
    summary = get_daily_summary()
    
    print("\n" + "="*50)
    print("📊 DAILY ANALYTICS REPORT")
    print(f"📅 {summary['date']}")
    print("="*50 + "\n")
    
    print(f"Total Actions: {summary['total_actions']}")
    print(f"Success Rate: {summary['success_rate']:.1f}%\n")
    
    print("📈 Breakdown:")
    for action, count in summary['breakdown'].items():
        print(f"  • {action.title()}: {count}")
    
    # Recent actions
    recent = get_top_actions(limit=5)
    if recent:
        print("\n🕐 Recent Actions:")
        for a in recent:
            print(f"  • {a['type']}: {a['content'][:40] if a['content'] else a['url'][:40]}...")
    
    print()


def print_weekly_report():
    """Print formatted weekly report"""
    summary = get_weekly_summary()
    
    print("\n" + "="*50)
    print("📊 WEEKLY ANALYTICS REPORT")
    print(f"📅 {summary['period']}")
    print("="*50 + "\n")
    
    print("📈 Weekly Totals:")
    for action, count in summary['totals'].items():
        print(f"  • {action.title()}: {count}")
    
    print("\n📅 Daily Breakdown:")
    for day in summary['daily_summaries']:
        total = sum(day['breakdown'].values())
        print(f"  {day['date']}: {total} actions")
    
    print()


if __name__ == "__main__":
    print_daily_report()
    print_weekly_report()
