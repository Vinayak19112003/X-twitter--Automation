"""
Test OpenRouter API connection
Run: python scripts/test_openrouter.py
"""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.openrouter_client import call_openrouter, get_api_key, get_model, generate_reply

def main():
    print("=" * 50)
    print("🧪 OPENROUTER API TEST")
    print("=" * 50)
    
    # Check API key
    try:
        api_key = get_api_key()
        print(f"✅ API Key: {api_key[:15]}...{api_key[-5:]}")
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    
    # Check model
    model = get_model()
    print(f"✅ Model: {model}")
    
    print("\n" + "-" * 50)
    print("Testing API call...")
    print("-" * 50)
    
    # Test 1: Simple call
    reply, error = call_openrouter(
        system_prompt="You are a helpful assistant.",
        user_prompt="Say 'API test successful' in exactly 3 words.",
        max_tokens=20,
        temperature=0.5
    )
    
    if reply:
        print(f"✅ Response: {reply}")
    else:
        print(f"❌ Error: {error}")
        return 1
    
    print("\n" + "-" * 50)
    print("Testing reply generation...")
    print("-" * 50)
    
    # Test 2: Reply generation
    test_tweet = "Bitcoin just broke $100k. The institutions are finally here."
    print(f"Tweet: {test_tweet}")
    
    reply, error = generate_reply(test_tweet)
    
    if reply:
        print(f"✅ Generated Reply: {reply}")
        print("\n" + "=" * 50)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 50)
        return 0
    else:
        print(f"❌ Error: {error}")
        return 1


if __name__ == "__main__":
    exit(main())
