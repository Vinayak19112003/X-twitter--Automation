
from playwright.sync_api import sync_playwright
import time
from pathlib import Path

def debug():
    auth_path = Path("auth").absolute()
    
    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.firefox.launch_persistent_context(
            user_data_dir=str(auth_path),
            headless=False,
            viewport={"width": 1280, "height": 900}
        )
        
        page = browser.pages[0]
        
        print("Navigating to status page...")
        # A recent popular tweet or generic one
        page.goto("https://x.com/ElonMusk/status/1742686888494792942", wait_until="domcontentloaded")
        time.sleep(8)
        
        # print("Opening first tweet...")
        # articles = page.query_selector_all('article[data-testid="tweet"]')
        # if articles:
        #     # Click the timestamp to go to status page
        #     time_el = articles[0].query_selector('time')
        #     if time_el:
        #         time_el.click()
        #         print("Clicked timestamp, waiting for navigation...")
        #         time.sleep(8)

        
        print(f"Current URL: {page.url}")
        
        # Screenshot
        print("Taking screenshot...")
        page.screenshot(path="debug_tweet.png")
        
        # Dump HTML
        print("Dumping HTML...")
        with open("debug_tweet.html", "w", encoding="utf-8") as f:
            f.write(page.content())
            
        # Inspect Selectors
        print("\n--- INSPECTION ---")
        
        # Check Reply Buttons
        replies = page.query_selector_all('[data-testid="reply"]')
        print(f"Found {len(replies)} reply buttons")
        
        # Check Input Area
        inputs = page.query_selector_all('[data-testid="tweetTextarea_0"]')
        print(f"Found {len(inputs)} input areas (tweetTextarea_0)")
        
        inputs_labels = page.query_selector_all('[data-testid="tweetTextarea_0_label"]')
        print(f"Found {len(inputs_labels)} input labels")
        
        # Try to find the MAIN answer button (often 'Post your reply')
        placeholder = page.get_by_text("Post your reply")
        if placeholder.count() > 0:
            print(f"Found 'Post your reply' text: {placeholder.count()} times")
            
        print("\nDone. Check debug_tweet.png")
        
        browser.close()

if __name__ == "__main__":
    debug()
