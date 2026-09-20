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
from agents.perplexity_queries import get_daily_queries
from agents.quality_safety import (
    validate_content, should_skip_random, can_reply_to_account,
    check_daily_limits, load_recent_replies
)
from agents.browser_operator import BrowserOperator, interactive_login
from agents.analytics_agent import print_daily_report
from agents.jev_decision_gate import evaluate_tweet, should_skip_posting
from agents.jev_client import JevSettings


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
        self.jev_settings = JevSettings.from_env()
    
    def _jev_shadow(self) -> bool:
        """Shadow mode is the default. No X mutations while it is on."""
        return bool(self.jev_settings.shadow_mode)

    def _apply_jev_gate(self, tweet: dict, source_label: str = "") -> str:
        """Classify with Jev before any reply generation. Never posts to X.

        Routed actions:
          IGNORE / SAVE / RESEARCH / REVIEW / SKIP / WATCH_CLUSTER / RESEARCH_CA
            -> skip posting; never buy
          PREPARE_NOTE -> research note only, never a buy, never an X post
          PREPARE_REPLY -> draft only, queue Telegram stub, still do not post
        """
        label = f" [{source_label}]" if source_label else ""
        preview = (tweet.get("text") or "")[:50]
        print(f"🧠 Jev classifying{label}: {preview}...")
        try:
            decision = evaluate_tweet(tweet, generate_draft=True, run_research=False)
        except Exception as exc:
            print(f"⚠️ Jev gate error ({exc.__class__.__name__}); fail-closed REVIEW, skip X")
            return "REVIEW"

        print(
            f"   Jev recommended={decision.recommended_action or '-'} "
            f"routed={decision.final_routed_action} ({decision.reason})"
        )
        if decision.errors:
            print(f"   Jev errors: {'; '.join(decision.errors)}")
        if decision.final_routed_action == "PREPARE_NOTE" and decision.research_note:
            print(f"   FOMO research note (never a buy): {decision.research_note[:80]}")
        if decision.final_routed_action == "PREPARE_REPLY" and decision.draft_reply:
            print(f"   Draft queued for Telegram approval (not posted): {decision.draft_reply[:80]}")
        if should_skip_posting(decision):
            print("   X action skipped (shadow / approval required / non-reply route)")
        return decision.final_routed_action
    
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
            
            if self._jev_shadow():
                print("🧠 Jev shadow mode: content draft kept local, not posting to X")
                return

            # Post (disabled while JEV_SHADOW_MODE=true, the default)
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
        classified = 0
        
        for tweet in tweets:
            if classified >= max_replies_per_cycle:
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
            
            # Jev decision gate: classify before reply generation.
            # If not PREPARE_REPLY, if shadow, or if REVIEW: skip posting.
            routed = self._apply_jev_gate(tweet, "feed")
            classified += 1
            if routed != "PREPARE_REPLY" or self._jev_shadow() or routed == "REVIEW":
                continue

            # PREPARE_REPLY outside shadow would still require Telegram approval.
            # Live X reply posting is not enabled by this integration.
            print("📝 Prepared reply held for Telegram approval; not posting to X")
        
        print(f"\n✅ Cycle complete: {classified} classified, {replies_posted} replies posted (X posting disabled)")
    
    def run_search_reply_cycle(self):
        """Discover tweets via Perplexity-generated search queries and reply"""
        print("\n" + "-"*40)
        print("🔍 SEARCH REPLY CYCLE (AI/VibeCoding)")
        print("-"*40)
        
        # Check limits
        can_reply, reason = check_daily_limits("reply")
        if not can_reply:
            print(f"⏸️ Daily limit: {reason}")
            return
        
        if self.replies_this_hour >= self.hourly_target:
            print(f"⏸️ Hourly limit: {self.replies_this_hour}/{self.hourly_target}")
            return
        
        # Get daily search queries from Perplexity
        queries = get_daily_queries()
        if not queries:
            print("📭 No search queries available")
            return
        
        # Pick random queries for this cycle
        selected_queries = random.sample(queries, min(3, len(queries)))
        
        replies_posted = 0
        max_replies_per_cycle = 3
        classified = 0
        
        for query_data in selected_queries:
            if classified >= max_replies_per_cycle:
                break
            
            if not self.running:
                break
            
            query = query_data.get("q", "")
            topic = query_data.get("topic", "general")
            
            if not query:
                continue
            
            # Discover tweets from search
            tweets = self.browser.discover_from_search(
                query=query,
                topic=topic,
                min_likes=50,
                max_tweets=5
            )
            
            if not tweets:
                continue
            
            # Small delay between queries
            time.sleep(random.uniform(2, 5))
            
            for tweet in tweets:
                if classified >= max_replies_per_cycle:
                    break
                
                if not self.running:
                    break
                
                # Account cooldown check
                can_reply_acc, reason = can_reply_to_account(tweet.get("handle", ""))
                if not can_reply_acc:
                    print(f"⏸️ Account cooldown: {tweet.get('handle', '')}")
                    continue
                
                # Random skip
                skip, prob = should_skip_random()
                if skip:
                    print(f"🎲 Skipped (random {prob:.0%}) [{topic}]")
                    continue
                
                # Jev decision gate: classify before reply generation.
                # If not PREPARE_REPLY, if shadow, or if REVIEW: skip posting.
                routed = self._apply_jev_gate(tweet, f"search:{topic}")
                classified += 1
                if routed != "PREPARE_REPLY" or self._jev_shadow() or routed == "REVIEW":
                    continue

                print("📝 Prepared reply held for Telegram approval; not posting to X")
        
        print(f"\n✅ Search cycle complete: {classified} classified, {replies_posted} replies posted (X posting disabled)")
    
    def run_engagement_cycle(self):
        """Light engagement: likes and retweets"""
        if self._jev_shadow():
            print("🧠 Jev shadow mode: skipping likes/retweets (no X mutations)")
            return

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
                
                # 3. Reply Cycle (main activity) - alternate between feed and search
                if cycle_count % 2 == 1:
                    # Odd cycles: Search-based discovery (AI/VibeCoding)
                    self.run_search_reply_cycle()
                else:
                    # Even cycles: Feed-based discovery
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

    if "--shadow-jev" in sys.argv:
        from scripts.shadow_jev import run as run_shadow_jev
        raise SystemExit(run_shadow_jev(sys.argv[2:]))
    
    # Default: run orchestrator
    orchestrator = Orchestrator()
    try:
        orchestrator.run()
    except KeyboardInterrupt:
        orchestrator.stop()


if __name__ == "__main__":
    main()
