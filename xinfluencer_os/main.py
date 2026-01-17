"""
XInfluencerOS - Multi-Agent X Automation System
Orchestrator Brain - Coordinates all agents
"""
import sys
import time
import random
from datetime import datetime

# Add parent path for imports
sys.path.insert(0, '.')

from config import settings
from db import init_db, SessionLocal, get_today_stats
from agents.trend_research import run_trend_research, get_unused_trends
from agents.content_writer import create_daily_content, get_pending_drafts
from agents.reply_generator import generate_reply
from agents.quality_safety import (
    validate_content, should_skip_random, can_reply_to_account,
    check_daily_limits, record_reply, record_account_reply, load_recent_replies
)
from agents.browser_operator import BrowserOperator, interactive_login
from agents.analytics_agent import print_daily_report


class Orchestrator:
    """Central brain coordinating all agents"""
    
    def __init__(self):
        self.browser: BrowserOperator | None = None
        self.running = False
        
        # Scheduling
        self.last_trend_research = None
        self.last_daily_post = None
        
        # Rate limiting
        self.replies_this_hour = 0
        self.hour_start = datetime.now()
        self.hourly_target = random.randint(8, 12)
    
    def start(self, headless: bool = False) -> bool:
        """Initialize system"""
        print("\n" + "="*60)
        print("🤖 XInfluencerOS - Multi-Agent System Starting...")
        print("="*60 + "\n")
        
        # Initialize database
        init_db()
        load_recent_replies()
        
        # Start browser
        print("🌐 Starting browser...")
        self.browser = BrowserOperator()
        self.browser.start(headless=headless)
        
        # Check login
        if not self.browser.is_logged_in():
            print("❌ Not logged in. Run: python main.py --login")
            return False
        
        print("✅ Logged in and ready!")
        self.running = True
        return True
    
    def stop(self):
        """Shutdown system"""
        self.running = False
        if self.browser:
            self.browser.close()
        print("\n🛑 XInfluencerOS stopped.")
    
    def _is_sleep_window(self) -> bool:
        """Check if in sleep window"""
        hour = datetime.now().hour
        return settings.sleep_window_start <= hour < settings.sleep_window_end
    
    def _reset_hourly(self):
        """Reset hourly counters"""
        now = datetime.now()
        if now.hour != self.hour_start.hour:
            self.hour_start = now
            self.replies_this_hour = 0
            self.hourly_target = random.randint(8, 12)
            print(f"🔄 Hourly reset! Target: {self.hourly_target}")
    
    def run_trend_research_cycle(self):
        """Run trend research (2x/day)"""
        now = datetime.now()
        
        # Run if not done today or if 12 hours passed
        should_run = (
            self.last_trend_research is None or
            (now - self.last_trend_research).total_seconds() > 12 * 3600
        )
        
        if should_run:
            run_trend_research()
            self.last_trend_research = now
    
    def run_content_creation_cycle(self):
        """Create and post daily content"""
        now = datetime.now()
        
        # Check daily limit
        can_post, reason = check_daily_limits("post")
        if not can_post:
            print(f"⏸️ Post limit: {reason}")
            return
        
        # Check if already posted today
        if self.last_daily_post and self.last_daily_post.date() == now.date():
            return
        
        # Create content if needed
        pending = get_pending_drafts("tweet")
        if not pending:
            create_daily_content()
            pending = get_pending_drafts("tweet")
        
        if pending:
            draft = pending[0]
            
            # Validate
            is_valid, reason = validate_content(draft.text, "tweet")
            if not is_valid:
                print(f"⚠️ Draft rejected: {reason}")
                return
            
            # Post
            if self.browser.post_tweet(draft.text):
                self.last_daily_post = now
                
                # Update draft status
                db = SessionLocal()
                try:
                    draft.status = "posted"
                    draft.posted_at = datetime.utcnow()
                    db.commit()
                except:
                    pass
                finally:
                    db.close()
    
    def run_reply_cycle(self):
        """Discover tweets and post replies"""
        print("\n" + "-"*40)
        print("💬 REPLY CYCLE")
        print("-"*40)
        
        # Check limits
        can_reply, reason = check_daily_limits("reply")
        if not can_reply:
            print(f"⏸️ Daily limit: {reason}")
            return
        
        if self.replies_this_hour >= self.hourly_target:
            print(f"⏸️ Hourly limit: {self.replies_this_hour}/{self.hourly_target}")
            return
        
        # Get tweets from feed
        tweets = self.browser.get_feed_tweets(max_tweets=15)
        
        if not tweets:
            print("📭 No tweets found")
            return
        
        replies_posted = 0
        max_replies_per_cycle = 3
        
        for tweet in tweets:
            if replies_posted >= max_replies_per_cycle:
                break
            
            if not self.running:
                break
            
            # Small delay between processing
            time.sleep(random.uniform(1.5, 4))
            
            # Account cooldown check
            can_reply_acc, reason = can_reply_to_account(tweet.get("handle", ""))
            if not can_reply_acc:
                continue
            
            # Random skip
            skip, prob = should_skip_random()
            if skip:
                print(f"🎲 Skipped (random {prob:.0%})")
                continue
            
            # Generate reply
            print(f"🤖 Generating for: {tweet['text'][:50]}...")
            reply_text, error = generate_reply(tweet['text'])
            
            if error:
                print(f"⚠️ Gen error: {error}")
                continue
            
            # Validate
            is_valid, reason = validate_content(reply_text, "reply")
            if not is_valid:
                print(f"⚠️ Rejected: {reason}")
                # Try once more
                reply_text, error = generate_reply(tweet['text'])
                if error:
                    continue
                is_valid, reason = validate_content(reply_text, "reply")
                if not is_valid:
                    print(f"⚠️ Rejected again: {reason}")
                    continue
            
            # Post reply
            if self.browser.reply_to_tweet(tweet['url'], reply_text):
                replies_posted += 1
                self.replies_this_hour += 1
                
                # Record for safety tracking
                record_reply(reply_text)
                record_account_reply(tweet.get("handle", ""))
                
                print(f"📊 Session: {self.browser.session_actions}/{self.browser.session_target} | Hour: {self.replies_this_hour}/{self.hourly_target}")
        
        print(f"\n✅ Cycle complete: {replies_posted} replies posted")
    
    def run_engagement_cycle(self):
        """Light engagement: likes and retweets"""
        # Check limits
        can_like, _ = check_daily_limits("like")
        can_rt, _ = check_daily_limits("retweet")
        
        if not can_like and not can_rt:
            return
        
        tweets = self.browser.get_feed_tweets(max_tweets=5)
        
        for tweet in tweets[:2]:
            if can_like and random.random() < 0.3:
                self.browser.like_tweet(tweet['url'])
                time.sleep(random.uniform(3, 8))
            
            if can_rt and random.random() < 0.1:
                self.browser.retweet(tweet['url'])
                time.sleep(random.uniform(5, 15))
    
    def run(self):
        """Main orchestration loop"""
        if not self.running:
            if not self.start():
                return
        
        print("\n🚀 Starting main loop...")
        print(f"🎯 Hourly target: {self.hourly_target} replies")
        
        cycle_count = 0
        
        while self.running:
            try:
                cycle_count += 1
                print(f"\n{'='*50}")
                print(f"🔄 CYCLE {cycle_count} - {datetime.now().strftime('%H:%M')}")
                print(f"{'='*50}")
                
                # Sleep window check
                if self._is_sleep_window():
                    print(f"😴 Sleep window ({settings.sleep_window_start}-{settings.sleep_window_end}). Sleeping 30min...")
                    time.sleep(30 * 60)
                    continue
                
                # Hourly reset
                self._reset_hourly()
                
                # 1. Trend Research (2x/day)
                self.run_trend_research_cycle()
                
                # 2. Content Creation (1-2x/day)
                if cycle_count % 5 == 0:  # Every 5 cycles
                    self.run_content_creation_cycle()
                
                # 3. Reply Cycle (main activity)
                self.run_reply_cycle()
                
                # 4. Light Engagement
                if random.random() < 0.3:
                    self.run_engagement_cycle()
                
                # 5. Analytics (hourly)
                if cycle_count % 10 == 0:
                    print_daily_report()
                
                # Sleep between cycles
                sleep_time = random.randint(2, 5) * 60  # 2-5 minutes
                print(f"\n💤 Next cycle in {sleep_time // 60} minutes...")
                time.sleep(sleep_time)
                
            except KeyboardInterrupt:
                print("\n\n⚠️ Interrupted by user")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                time.sleep(60)
        
        self.stop()


def main():
    """Entry point"""
    if "--login" in sys.argv:
        interactive_login()
        return
    
    if "--trends" in sys.argv:
        init_db()
        run_trend_research()
        return
    
    if "--content" in sys.argv:
        init_db()
        create_daily_content()
        return
    
    if "--report" in sys.argv:
        init_db()
        print_daily_report()
        return
    
    # Default: run orchestrator
    orchestrator = Orchestrator()
    try:
        orchestrator.run()
    except KeyboardInterrupt:
        orchestrator.stop()


if __name__ == "__main__":
    main()
