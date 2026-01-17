"""
Reply Generator Agent - OpenRouter
Generates high-quality replies for discovered tweets
Uses centralized openrouter_client for API calls
"""
from agents.openrouter_client import generate_reply, call_openrouter


def batch_generate_replies(tweets: list[dict]) -> list[dict]:
    """Generate replies for multiple tweets
    
    Args:
        tweets: List of dicts with 'id', 'text', 'url' keys
        
    Returns:
        List of dicts with 'tweet', 'reply', 'error' keys
    """
    results = []
    
    for tweet in tweets:
        reply, error = generate_reply(tweet.get("text", ""))
        results.append({
            "tweet": tweet,
            "reply": reply,
            "error": error
        })
    
    return results


if __name__ == "__main__":
    # Test
    test_tweet = "Bitcoin just broke $100k. The institutions are finally here."
    print(f"Tweet: {test_tweet}")
    reply, error = generate_reply(test_tweet)
    if reply:
        print(f"Reply: {reply}")
    else:
        print(f"Error: {error}")
