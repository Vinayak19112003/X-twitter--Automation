# GhostReply - Autonomous X (Twitter) Assistant 👻

A fully automated, multimodal-enabled bot that monitors your X/Twitter feed, uses AI to generate intelligent replies, and posts them automatically.

## ✨ Key Features
- **🔍 Smart Feed Monitoring**: Scans your "For You" feed every minute for high-impact tweets.
- **🖼️ Vision Intelligence**: Uses **Gemini 2.0 Flash (Vision)** to analyze charts, memes, and images in tweets.
- **🧠 Semantic Filtering**: Strictly focuses on *Web3, Crypto, AI, Trading* content (configurable).
- **🤖 Human-Like Posting**: Bypasses bot detection by simulating human typing and interaction delays.
- **🛡️ Auto-Recovery**: Automatically detects "Something went wrong" feed errors and clicks "Retry" to resume operations.
- **📊 Local Dashboard**: Includes a Next.js dashboard for monitoring and manual queue management.

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Firefox Browser
- An **OpenRouter API Key** (or Gemini/Llama API key)

### Installation
1.  **Clone the repo**:
    ```bash
    git clone https://github.com/Vinayak19112003/X-twitter--Automation.git
    cd X-twitter--Automation
    ```
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Setup Environment**:
    Create a `.env` file:
    ```ini
    OPENROUTER_API_KEY=your_key_here
    AI_MODEL=google/gemini-2.0-flash-exp:free
    MIN_LIKES=50
    ```

### Running the Bot
1.  **First Run (Login)**:
    Open the browser controller to log in manually.
    ```bash
    python browser.py
    ```
    *Log in to X, verify the feed loads, then press ENTER in the terminal to save the session.*

2.  **Start Monitor**:
    Launch the autonomous loop.
    ```bash
    python monitor.py --auto-post
    ```
    *The bot will now run indefinitely, checking every 60 seconds.*

## 📁 Project Structure

| File/Dir | Description |
|---|---|
| `monitor.py` | **Core Bot Logic**. Handles the loop, tweet discovery, and AI generation. |
| `browser.py` | **Browser Controller**. Manages Playwright, selectors, and X interactions. |
| `config.py` | Configuration loader from `.env`. |
| `database.py` | SQLite database models (Tweets, Replies). |
| `scripts/` | Maintenance utilities (see below). |
| `frontend/` | Next.js Dashboard code. |

## 🛠️ Maintenance Scripts
Located in `scripts/`:

-   `reset_pending.py`: Clears "pending" drafts if the queue gets stuck.
-   `fix_failed.py`: Deletes failed replies so they can be retried.
-   `cleanup_orphaned.py`: Removes database entries that have no matching tweet data.
-   `clear_cache.py`: Clears Playwright temp files (use carefully).

## 🛡️ Troubleshooting
-   **"Not Logged In" Error**: Run `python browser.py`, login again, and ensure you close it via the terminal (Enter key).
-   **"TargetClosedError"**: Run `taskkill /F /IM firefox.exe` to kill zombie processes.
-   **Feed Error**: The bot auto-retries. If it fails repeatedly, check your internet connection.

---
*Built with Playwright, Python, and Agentic AI.*
