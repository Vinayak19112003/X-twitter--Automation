"""
Playwright Browser Controller - X/Twitter automation
Uses synchronous Playwright API to avoid Windows asyncio issues
"""
import time
import re
import random
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext
from config import settings


class TwitterBrowser:
    """Controls browser for X/Twitter interactions - Sync API"""
    
    def __init__(self):
        self.playwright = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.auth_path = Path(settings.auth_dir).absolute()
        self.auth_path.mkdir(exist_ok=True)
    
    def start(self, headless: bool = False):
        """Start browser"""
        self.playwright = sync_playwright().start()
        
        # Use Firefox - less likely to be detected
        self.context = self.playwright.firefox.launch_persistent_context(
            user_data_dir=str(self.auth_path),
            headless=headless,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
        
        # Increase default timeout to 60s (for slow connections)
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
        """Check if user is logged into X"""
        try:
            url = self.page.url
            if "x.com/home" in url or ("x.com" in url and "login" not in url and "i/flow" not in url):
                home_indicator = self.page.query_selector('[data-testid="primaryColumn"]')
                return home_indicator is not None
            return False
        except Exception:
            return False
    
    def navigate_home(self) -> bool:
        """Navigate to home and check if logged in"""
        try:
            self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)  # Wait longer for redirects
            
            # Check actual URL (might have redirected to login)
            url = self.page.evaluate("window.location.href")
            print(f"  Navigated to: {url}")
            
            if "login" in url or "i/flow" in url:
                return False
            
            home_el = self.page.query_selector('[data-testid="primaryColumn"]')
            
            # Auto-retry if "Something went wrong" (Feed Error)
            if not home_el:
                print("  Checking for Retry button...")
                retry_btn = self.page.query_selector('div[role="button"]:has-text("Retry")')
                if not retry_btn:
                     retry_btn = self.page.query_selector('button:has-text("Retry")')
                
                if retry_btn:
                    print("  ⚠️ Feed error detected. Clicking Retry...")
                    retry_btn.click()
                    time.sleep(5)
                    home_el = self.page.query_selector('[data-testid="primaryColumn"]')

            if home_el:
                return True
                
            return False
        except Exception as e:
            print(f"Navigation error: {e}")
            return False
    
    def wait_for_login(self, timeout: int = 300):
        """Wait for user to complete manual login"""
        print("\n" + "="*50)
        print("🔐 MANUAL LOGIN REQUIRED")
        print("="*50)
        print("\n1. Log in to X/Twitter in the browser window")
        print("2. Complete any 2FA or verification")
        print("3. Navigate to your home feed manually")
        print(f"\nTimeout: {timeout} seconds")
        print("\n⚠️  DO NOT CLOSE THIS TERMINAL\n")
        
        self.page.goto("https://x.com/login", wait_until="domcontentloaded")
        
        start = datetime.now()
        while (datetime.now() - start).seconds < timeout:
            time.sleep(8)
            
            try:
                # Force page to evaluate current URL (not cached)
                url = self.page.evaluate("window.location.href")
                print(f"  Checking... Current page: {url[:50]}...")
                
                if "home" in url and "login" not in url and "i/flow" not in url:
                    time.sleep(2)
                    # Check for home feed element
                    home_el = self.page.query_selector('[data-testid="primaryColumn"]')
                    if home_el:
                        print("\n✅ Login successful! Session saved.\n")
                        return True
                elif "login" not in url and "i/flow" not in url and "x.com" in url:
                    # User navigated somewhere else on X
                    time.sleep(2)
                    home_el = self.page.query_selector('[data-testid="primaryColumn"]')
                    if home_el:
                        print("\n✅ Login successful! Session saved.\n")
                        return True
            except Exception as e:
                print(f"  Check error: {e}")
        
        print("\n❌ Login timeout. Please try again.\n")
        return False
    
    def search_tweets(self, query: str, min_likes: int = 50) -> list[dict]:
        """Search for tweets matching query"""
        tweets = []
        
        try:
            search_url = f"https://x.com/search?q={query}%20min_faves%3A{min_likes}&src=typed_query&f=live"
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            
            for _ in range(3):
                self.page.evaluate("window.scrollBy(0, 800)")
                time.sleep(1.5)
            
            tweet_elements = self.page.query_selector_all('article[data-testid="tweet"]')
            
            for element in tweet_elements[:10]:
                try:
                    tweet_data = self._extract_tweet_data(element)
                    if tweet_data and self._passes_filters(tweet_data):
                        tweets.append(tweet_data)
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"Search error: {e}")
        
        return tweets
    
    def get_feed_tweets(self) -> list[dict]:
        """Get tweets from For You feed"""
        tweets = []
        
        try:
            self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            
            for _ in range(3):
                self.page.evaluate("window.scrollBy(0, 600)")
                time.sleep(1.5)
            
            tweet_elements = self.page.query_selector_all('article[data-testid="tweet"]')
            
            for element in tweet_elements[:15]:
                try:
                    tweet_data = self._extract_tweet_data(element)
                    if tweet_data and self._passes_filters(tweet_data):
                        tweets.append(tweet_data)
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"Feed error: {e}")
        
        return tweets
    
    def _extract_tweet_data(self, element) -> dict | None:
        """Extract tweet data from article element"""
        try:
            text_el = element.query_selector('[data-testid="tweetText"]')
            text = text_el.inner_text() if text_el else ""
            
            if not text or len(text) < 20:
                return None
            
            user_el = element.query_selector('[data-testid="User-Name"]')
            user_text = user_el.inner_text() if user_el else ""
            
            author = ""
            handle = ""
            if user_text:
                parts = user_text.split("\n")
                author = parts[0] if parts else ""
                handle = parts[1] if len(parts) > 1 else ""
                handle = handle.replace("@", "").split("·")[0].strip()
            
            tweet_url = ""
            # Find the timestamp link which is the true permalink
            time_el = element.query_selector('time')
            if time_el:
                link_el = time_el.evaluate_handle('el => el.closest("a")')
                if link_el:
                    href = link_el.get_attribute("href")
                    if href:
                        tweet_url = href
            
            # Fallback to any status link if timestamp not found
            if not tweet_url:
                link_els = element.query_selector_all('a[href*="/status/"]')
                for link in link_els:
                    href = link.get_attribute("href")
                    if href and "/analytics" not in href and "/photo/" not in href:
                        tweet_url = href
                        break
            
            if tweet_url and not tweet_url.startswith("http"):
                tweet_url = f"https://x.com{tweet_url}"
            
            tweet_id = ""
            if tweet_url:
                match = re.search(r"/status/(\d+)", tweet_url)
                if match:
                    tweet_id = match.group(1)
            
            likes = self._get_metric(element, "like")
            retweets = self._get_metric(element, "retweet")
            
            # Extract image URLs
            images = []
            try:
                img_els = element.query_selector_all('img[src*="http"]')
                for img in img_els:
                    src = img.get_attribute("src")
                    if src and "profile_images" not in src and "emoji" not in src:
                        # Convert small thumbnails to large if possible (optional)
                        images.append(src)
            except Exception:
                pass
            
            return {
                "id": tweet_id,
                "url": tweet_url,
                "text": text,
                "images": images,
                "author": author,
                "handle": handle,
                "followers": 10000,
                "likes": likes,
                "retweets": retweets
            }
            
        except Exception:
            return None
    
    def _get_metric(self, element, metric_type: str) -> int:
        """Extract engagement metric from tweet element"""
        try:
            metric_el = element.query_selector(f'[data-testid="{metric_type}"] span')
            if metric_el:
                text = metric_el.inner_text()
                return self._parse_count(text)
        except Exception:
            pass
        return 0
    
    def _parse_count(self, text: str) -> int:
        """Parse count string like '5.2K' to integer"""
        if not text:
            return 0
        text = text.strip().upper()
        try:
            if "K" in text:
                return int(float(text.replace("K", "")) * 1000)
            elif "M" in text:
                return int(float(text.replace("M", "")) * 1000000)
            else:
                return int(text.replace(",", ""))
        except Exception:
            return 0
    
    def _passes_filters(self, tweet: dict) -> bool:
        """Check if tweet passes filtering criteria"""
        has_engagement = (
            tweet.get("likes", 0) >= settings.min_likes or
            tweet.get("retweets", 0) >= settings.min_retweets
        )
        
        if not has_engagement:
            return False
        
        text_lower = tweet.get("text", "").lower()
        has_keyword = any(kw.lower() in text_lower for kw in settings.keywords)
        
        ignore_patterns = [
            "giveaway", "airdrop", "free nft", "dm me",
            "🎁", "politics", "maga", "trump", "biden"
        ]
        has_ignore = any(pattern in text_lower for pattern in ignore_patterns)
        
        return has_keyword and not has_ignore
    
    def post_reply(self, tweet_url: str, reply_text: str) -> bool:
        """Post a reply (Aggressive Mode - Keyboard Shortcut)"""
        try:
            print(f"  Navigating to: {tweet_url}")
            # Use domcontentloaded but wait longer explicitly
            self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=60000)
            print("  Waiting for page load...")
            time.sleep(10)
            
            # Method 1: Check for input area directly
            reply_input = self.page.query_selector('[data-testid="tweetTextarea_0"]')
            
            # Method 2: Click Reply Button (Force)
            if not reply_input:
                print("  Input not visible, looking for reply button...")
                reply_btn = self.page.query_selector('[data-testid="reply"]')
                if reply_btn:
                    print("  Clicking reply button (Force)...")
                    try:
                        reply_btn.click(force=True, timeout=5000)
                        time.sleep(3)
                    except:
                        pass
                    reply_input = self.page.query_selector('[data-testid="tweetTextarea_0"]')
            
            if not reply_input:
                print("❌ Reply input not found")
                return False
            
            print(f"  Typing reply ({len(reply_text)} chars)...")
            try:
                reply_input.click(force=True, timeout=5000)
                time.sleep(1)
                reply_input.fill("") # Clear first
                self.page.keyboard.type(reply_text, delay=15)
                time.sleep(1)
            except Exception as e:
                print(f"  ⚠️ Typing error: {e}")
                return False
            
            # Click Post or use Shortcut
            print("  Posting (Ctrl+Enter)...")
            self.page.keyboard.press("Control+Enter")
            time.sleep(5)
            
            # Verify success (check if input cleared or disappeared)
            remaining_input = self.page.query_selector('[data-testid="tweetTextarea_0"]')
            if remaining_input:
                val = remaining_input.input_value()
                if val and len(val) > 0:
                     print("  ⚠️ Ctrl+Enter failed, trying button...")
                     post_btn = self.page.query_selector('[data-testid="tweetButtonInline"]')
                     if not post_btn: post_btn = self.page.query_selector('[data-testid="tweetButton"]')
                     
                     if post_btn: 
                        post_btn.click(force=True, timeout=5000)
                        time.sleep(5)
            
            print(f"✅ Reply posted: {reply_text[:50]}...")
            return True
            
        except Exception as e:
            print(f"❌ Error posting reply: {e}")
            return False
    
    def random_delay(self):
        """Wait random delay between actions"""
        delay = random.randint(settings.min_delay_seconds, settings.max_delay_seconds)
        print(f"⏳ Waiting {delay} seconds...")
        time.sleep(delay)


def login_flow():
    """Interactive login flow"""
    print("\n🚀 Starting GhostReply Browser...\n")
    
    browser = TwitterBrowser()
    browser.start(headless=False)
    
    if browser.navigate_home():
        print("✅ Already logged in!")
        print("\nSession is ready. You can close this window.")
        input("\nPress Enter to close browser...")
    else:
        success = browser.wait_for_login()
        if success:
            print("\nSession saved successfully!")
            print("You can now run the monitor with: python main.py")
            input("\nPress Enter to close browser...")
        else:
            print("\nLogin failed or timed out.")
            input("\nPress Enter to close browser...")
    
    browser.close()


if __name__ == "__main__":
    login_flow()
