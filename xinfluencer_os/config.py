"""
XInfluencerOS Configuration
Multi-Agent X/Twitter Automation System
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

# Load .env from this directory specifically
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=True)


class Settings(BaseSettings):
    # API Keys
    perplexity_api_key: str = Field(default="", env="PERPLEXITY_API_KEY")
    openrouter_api_key: str = Field(default="", env="OPENROUTER_API_KEY")
    
    # AI Models - Read directly from env after load_dotenv
    perplexity_model: str = Field(default="sonar-pro", env="PERPLEXITY_MODEL")
    
    @property
    def openrouter_model(self) -> str:
        return os.getenv("AI_MODEL", "meta-llama/llama-3-8b-instruct:free")
    
    # Daily Rate Limits
    max_replies_per_day: int = Field(default=70, env="MAX_REPLIES_PER_DAY")
    max_likes_per_day: int = Field(default=20, env="MAX_LIKES_PER_DAY")
    max_retweets_per_day: int = Field(default=4, env="MAX_RETWEETS_PER_DAY")
    max_posts_per_day: int = Field(default=2, env="MAX_POSTS_PER_DAY")
    
    # Hourly Limits
    max_replies_per_hour: int = Field(default=12, env="MAX_REPLIES_PER_HOUR")
    
    # Humanization - Delays
    min_action_delay: int = Field(default=2, env="MIN_ACTION_DELAY")
    max_action_delay: int = Field(default=6, env="MAX_ACTION_DELAY")
    min_post_delay: int = Field(default=30, env="MIN_POST_DELAY")
    max_post_delay: int = Field(default=180, env="MAX_POST_DELAY")
    
    # Humanization - Sessions
    session_min_actions: int = Field(default=3, env="SESSION_MIN_ACTIONS")
    session_max_actions: int = Field(default=7, env="SESSION_MAX_ACTIONS")
    break_min_minutes: int = Field(default=5, env="BREAK_MIN_MINUTES")
    break_max_minutes: int = Field(default=25, env="BREAK_MAX_MINUTES")
    
    # Sleep Window (Local Time)
    sleep_window_start: int = Field(default=2, env="SLEEP_WINDOW_START")  # 2 AM
    sleep_window_end: int = Field(default=7, env="SLEEP_WINDOW_END")      # 7 AM
    
    # Skip Chance
    skip_chance_min: float = Field(default=0.20, env="SKIP_CHANCE_MIN")
    skip_chance_max: float = Field(default=0.35, env="SKIP_CHANCE_MAX")
    
    # Paths
    auth_dir: str = "../auth"
    db_path: str = "storage/xinfluencer.db"
    
    class Config:
        env_file = Path(__file__).parent / ".env"
        extra = "ignore"


settings = Settings()
