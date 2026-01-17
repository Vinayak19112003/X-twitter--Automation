"""
Browser Operator Agent - Playwright
Controls browser for X/Twitter actions with human-like behavior
"""
import time
import random
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext
import sys
sys.path.insert(0, '..')
from config import settings
from db import SessionLocal, ActionLog, get_today_stats


class BrowserOperator:
    """Controls browser for X/Twitter interactions"""
    
    def __init__(self):
        self.playwright = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.auth_path = Path(settings.auth_dir).absolute()
        self.auth_path.mkdir(parents=True, exist_ok=True)
        
        # Session tracking
        self.session_actions = 0
        self.session_target = random.randint(
            settings.session_min_actions, 
            settings.session_max_actions
        )
    
    def start(self, headless: bool = False):
        """Start browser with persistent context"""
        self.playwright = sync_playwright().start()
        
        self.context = self.playwright.firefox.launch_persistent_context(
            user_data_dir=str(self.auth_path),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York"
        )
        
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
        
        # Increase timeouts
        self.page.set_default_timeout(60000)
        self.page.set_default_navigation_timeout(60000)
        
        return self
    
    def close(self):
        """Close browser"""
        if self.context:
            self.context.close()
        if self.playwright:
            self.playwright.stop()
    
    def is_logged_in(self) -> bool:
        """Check if logged into X"""
        try:
            self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(8)  # Wait longer for page to fully load
            
            url = self.page.url
            print(f"  Navigated to: {url}")
            
            # Check for login redirect
            if "login" in url or "i/flow" in url:
                return False
            
            # Try multiple selectors to confirm logged in
            home_indicator = self.page.query_selector('[data-testid="primaryColumn"]')
            if home_indicator:
                return True
            
            # Fallback: check for "What's happening" or compose box
            compose = self.page.query_selector('[data-testid="tweetTextarea_0RichTextInputContainer"]')
            if compose:
                return True
            
            # Check for user avatar/menu
            avatar = self.page.query_selector('[data-testid="SideNav_AccountSwitcher_Button"]')
            if avatar:
                return True
            
            # If URL is /home and no login redirect, assume logged in
            if "/home" in url:
                return True
            
            return False
        except Exception as e:
            print(f"  Login check error: {e}")
            return False
    
    def human_delay(self, action: str = "small"):
        """Add human-like delay"""
        if action == "small":
            delay = random.uniform(settings.min_action_delay, settings.max_action_delay)
        elif action == "post":
            delay = random.uniform(settings.min_post_delay, settings.max_post_delay)
        else:
            delay = random.uniform(2, 5)
        
        print(f"⏳ Waiting {delay:.1f}s...")
        time.sleep(delay)
    
    def check_session_break(self):
        """Check if we need a human break"""
        if self.session_actions >= self.session_target:
            break_time = random.randint(
                settings.break_min_minutes, 
                settings.break_max_minutes
            )
            print(f"☕ Human break! ({self.session_actions} actions). Sleeping {break_time} mins...")
            time.sleep(break_time * 60)
            
            # Reset session
            self.session_actions = 0
            self.session_target = random.randint(
                settings.session_min_actions,
                settings.session_max_actions
            )
            print(f"👣 Back! New session target: {self.session_target}")
    
    def _log_action(self, action_type: str, target_url: str = None, 
                    content: str = None, success: bool = True, error: str = None):
        """Log action to database"""
        db = SessionLocal()
        try:
            log = ActionLog(
                action_type=action_type,
                target_url=target_url,
                content=content,
                status="success" if success else "failed",
                error_message=error,
                timestamp=datetime.utcnow()
            )
            db.add(log)
            
            # Update daily stats
            stats = get_today_stats(db)
            if success:
                if action_type == "reply":
                    stats.replies_count += 1
                elif action_type == "like":
                    stats.likes_count += 1
                elif action_type == "retweet":
                    stats.retweets_count += 1
                elif action_type == "post":
                    stats.posts_count += 1
                elif action_type == "thread":
                    stats.threads_count += 1
                elif action_type == "quote":
                    stats.quote_tweets_count += 1
            
            db.commit()
        finally:
            db.close()
    
    def post_tweet(self, text: str) -> bool:
        """Post a new tweet"""
        try:
            print(f"📝 Posting tweet: {text[:50]}...")
            self.human_delay("post")
            
            self.page.goto("https://x.com/compose/tweet", wait_until="domcontentloaded")
            time.sleep(3)
            
            # Find compose box
            compose = self.page.query_selector('[data-testid="tweetTextarea_0"]')
            if not compose:
                self._log_action("post", content=text, success=False, error="Compose box not found")
                return False
            
            compose.click()
            time.sleep(1)
            self.page.keyboard.type(text, delay=15)
            time.sleep(2)
            
            # Post
            self.page.keyboard.press("Control+Enter")
            time.sleep(5)
            
            self.session_actions += 1
            self._log_action("post", content=text, success=True)
            print("✅ Tweet posted!")
            
            self.check_session_break()
            return True
            
        except Exception as e:
            self._log_action("post", content=text, success=False, error=str(e))
            print(f"❌ Post error: {e}")
            return False
    
    def reply_to_tweet(self, tweet_url: str, reply_text: str) -> bool:
        """Reply to a tweet"""
        try:
            print(f"💬 Replying to: {tweet_url[:50]}...")
            self.human_delay("post")
            
            self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(10)
            
            # Find reply input
            reply_input = self.page.query_selector('[data-testid="tweetTextarea_0"]')
            
            if not reply_input:
                # Try clicking reply button
                reply_btn = self.page.query_selector('[data-testid="reply"]')
                if reply_btn:
                    reply_btn.click(force=True)
                    time.sleep(3)
                    reply_input = self.page.query_selector('[data-testid="tweetTextarea_0"]')
            
            if not reply_input:
                self._log_action("reply", tweet_url, reply_text, False, "Reply input not found")
                return False
            
            reply_input.click(force=True)
            time.sleep(1)
            reply_input.fill("")
            self.page.keyboard.type(reply_text, delay=15)
            time.sleep(1)
            
            # Post via keyboard
            self.page.keyboard.press("Control+Enter")
            time.sleep(5)
            
            self.session_actions += 1
            self._log_action("reply", tweet_url, reply_text, True)
            print(f"✅ Reply posted!")
            
            self.check_session_break()
            return True
            
        except Exception as e:
            self._log_action("reply", tweet_url, reply_text, False, str(e))
            print(f"❌ Reply error: {e}")
            return False
    
    def like_tweet(self, tweet_url: str) -> bool:
        """Like a tweet"""
        try:
            self.human_delay("small")
            
            self.page.goto(tweet_url, wait_until="domcontentloaded")
            time.sleep(5)
            
            like_btn = self.page.query_selector('[data-testid="like"]')
            if like_btn:
                like_btn.click()
                time.sleep(2)
                self.session_actions += 1
                self._log_action("like", tweet_url, success=True)
                print("❤️ Liked!")
                return True
            
            return False
            
        except Exception as e:
            self._log_action("like", tweet_url, success=False, error=str(e))
            return False
    
    def retweet(self, tweet_url: str) -> bool:
        """Retweet a tweet"""
        try:
            self.human_delay("small")
            
            self.page.goto(tweet_url, wait_until="domcontentloaded")
            time.sleep(5)
            
            rt_btn = self.page.query_selector('[data-testid="retweet"]')
            if rt_btn:
                rt_btn.click()
                time.sleep(2)
                
                # Confirm retweet
                confirm = self.page.query_selector('[data-testid="retweetConfirm"]')
                if confirm:
                    confirm.click()
                    time.sleep(2)
                
                self.session_actions += 1
                self._log_action("retweet", tweet_url, success=True)
                print("🔁 Retweeted!")
                return True
            
            return False
            
        except Exception as e:
            self._log_action("retweet", tweet_url, success=False, error=str(e))
            return False
    
    def quote_tweet(self, tweet_url: str, quote_text: str) -> bool:
        """Quote tweet"""
        try:
            print(f"📝 Quote tweeting: {tweet_url[:40]}...")
            self.human_delay("post")
            
            self.page.goto(tweet_url, wait_until="domcontentloaded")
            time.sleep(5)
            
            # Click retweet button to get menu
            rt_btn = self.page.query_selector('[data-testid="retweet"]')
            if rt_btn:
                rt_btn.click()
                time.sleep(2)
                
                # Click Quote
                quote_option = self.page.query_selector('[href*="compose/post"]')
                if quote_option:
                    quote_option.click()
                    time.sleep(3)
                    
                    # Type quote
                    compose = self.page.query_selector('[data-testid="tweetTextarea_0"]')
                    if compose:
                        compose.click()
                        self.page.keyboard.type(quote_text, delay=15)
                        time.sleep(2)
                        
                        self.page.keyboard.press("Control+Enter")
                        time.sleep(5)
                        
                        self.session_actions += 1
                        self._log_action("quote", tweet_url, quote_text, True)
                        print("✅ Quote tweet posted!")
                        return True
            
            return False
            
        except Exception as e:
            self._log_action("quote", tweet_url, quote_text, False, str(e))
            return False
    
    def get_feed_tweets(self, max_tweets: int = 10) -> list[dict]:
        """Get tweets from feed"""
        try:
            print("📡 Scanning feed...")
            self.page.goto("https://x.com/home", wait_until="domcontentloaded")
            time.sleep(5)
            
            # Scroll to load more
            for _ in range(3):
                self.page.mouse.wheel(0, 800)
                time.sleep(2)
            
            tweets = []
            articles = self.page.query_selector_all('article[data-testid="tweet"]')
            
            for article in articles[:max_tweets]:
                try:
                    # Extract text
                    text_el = article.query_selector('[data-testid="tweetText"]')
                    text = text_el.inner_text() if text_el else ""
                    
                    # Extract author
                    author_el = article.query_selector('[data-testid="User-Name"]')
                    author = author_el.inner_text().split("\n")[0] if author_el else ""
                    
                    # Extract link
                    link_el = article.query_selector('a[href*="/status/"]')
                    url = f"https://x.com{link_el.get_attribute('href')}" if link_el else ""
                    
                    # Extract handle
                    handle = ""
                    if author_el:
                        spans = author_el.query_selector_all("span")
                        for span in spans:
                            t = span.inner_text()
                            if t.startswith("@"):
                                handle = t[1:]
                                break
                    
                    if text and url:
                        tweets.append({
                            "text": text,
                            "url": url,
                            "author": author,
                            "handle": handle
                        })
                except:
                    continue
            
            print(f"📋 Found {len(tweets)} tweets")
            return tweets
            
        except Exception as e:
            print(f"❌ Feed error: {e}")
            return []


def interactive_login():
    """Interactive login flow"""
    print("\n🔐 Starting Login Flow...")
    print("A browser will open. Please log in manually.")
    print("Once logged in, close the browser to save the session.\n")
    
    browser = BrowserOperator()
    browser.start(headless=False)
    
    browser.page.goto("https://x.com/login")
    
    print("⏳ Waiting for you to log in...")
    print("Close the browser when done.\n")
    
    try:
        while True:
            time.sleep(5)
            if browser.is_logged_in():
                print("✅ Login successful! Session saved.")
                break
    except:
        pass
    finally:
        browser.close()


if __name__ == "__main__":
    import sys
    if "--login" in sys.argv:
        interactive_login()
    else:
        print("Usage: python browser_operator.py --login")
