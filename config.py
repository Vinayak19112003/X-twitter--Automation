"""
GhostReply Configuration
"""
import os
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # OpenRouter
    openrouter_api_key: str = Field(default="", env="OPENROUTER_API_KEY")
    ai_model: str = Field(default="meta-llama/llama-3-8b-instruct:free", env="AI_MODEL")
    
    # Rate Limiting
    max_replies_per_hour: int = Field(default=15, env="MAX_REPLIES_PER_HOUR")
    min_delay_seconds: int = Field(default=30, env="MIN_DELAY_SECONDS")
    max_delay_seconds: int = Field(default=180, env="MAX_DELAY_SECONDS")
    
    # Filtering
    min_followers: int = Field(default=5000, env="MIN_FOLLOWERS")
    min_likes: int = Field(default=50, env="MIN_LIKES")
    min_retweets: int = Field(default=10, env="MIN_RETWEETS")

    # Humanization Settings
    sleep_window_start: int = Field(default=2, env="SLEEP_WINDOW_START") # 2 AM
    sleep_window_end: int = Field(default=7, env="SLEEP_WINDOW_END")     # 7 AM
    
    session_min_replies: int = Field(default=3, env="SESSION_MIN_REPLIES")
    session_max_replies: int = Field(default=7, env="SESSION_MAX_REPLIES")
    
    break_min_minutes: int = Field(default=5, env="BREAK_MIN_MINUTES")
    break_max_minutes: int = Field(default=25, env="BREAK_MAX_MINUTES")
    
    # Keywords to monitor
    keywords: list[str] = [
        "AI", "OpenAI", "Gemini", "Claude", "GPT",
        "Web3", "crypto", "bitcoin", "BTC", "ETH", "Solana",
        "Nvidia", "trading", "startups", "markets"
    ]
    
    # Paths
    auth_dir: str = "auth"
    db_path: str = "ghostreply.db"
    
    class Config:
        env_file = ".env"


settings = Settings()
