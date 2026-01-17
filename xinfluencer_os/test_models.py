"""Quick test for OpenRouter models"""
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "mistralai/devstral-2512:free",
    "tngtech/deepseek-r1t2-chimera:free", 
    "xiaomi/mimo-v2-flash:free",
    "google/gemma-2-9b-it:free"  # Fallback
]

def test_model(model: str) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say 'test ok' in 3 words"}],
        "max_tokens": 20
    }
    
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(URL, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                reply = data["choices"][0]["message"]["content"][:50]
                return f"✅ WORKS - Response: {reply}"
            else:
                return f"❌ FAILED - {response.status_code}: {response.text[:100]}"
    except Exception as e:
        return f"❌ ERROR - {str(e)[:50]}"

print("Testing OpenRouter Models...\n")
print(f"API Key: {API_KEY[:20]}...{API_KEY[-10:]}\n")

for model in MODELS:
    print(f"Testing: {model}")
    result = test_model(model)
    print(f"  {result}\n")
