import os
import requests
import json
from pathlib import Path
from dotenv import load_dotenv

def get_free_models():
    """
    Fetch all available models from OpenRouter and filter for free ones.
    """
    # Load .env
    project_root = Path(__file__).resolve().parents[3]
    env_file = project_root / ".env"
    load_dotenv(dotenv_path=env_file)
    
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY or OPENAI_API_KEY not found in .env")
        return []

    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        models = response.json().get("data", [])
        
        free_models = []
        for model in models:
            pricing = model.get("pricing", {})
            # A model is usually free if prompt/completion pricing is 0
            is_free = (
                float(pricing.get("prompt", 0)) == 0 and 
                float(pricing.get("completion", 0)) == 0
            )
            
            if is_free:
                free_models.append({
                    "id": model.get("id"),
                    "name": model.get("name"),
                    "context_length": model.get("context_length"),
                    "description": model.get("description")
                })
        
        return free_models
    except Exception as e:
        print(f"Error fetching models: {e}")
        return []

def test_model_availability(model_id):
    """
    Test if a specific model is responding correctly.
    """
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Say 'hello'"}],
        "max_tokens": 10
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            return True, "Available"
        else:
            error_data = response.json().get("error", {})
            return False, error_data.get("message", f"Status Code {response.status_code}")
    except Exception as e:
        return False, str(e)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Check free models on OpenRouter")
    parser.add_argument("--test", action="store_true", help="Test availability of each model (slow)")
    parser.add_argument("--best", action="store_true", help="Find and print only the first available free model")
    args = parser.parse_args()

    if args.best:
        # Silently find the first working model
        free_models = get_free_models()
        for model in free_models:
            available, _ = test_model_availability(model["id"])
            if available:
                print(model["id"])
                return
        return

    print("Fetching free models from OpenRouter...")
    free_models = get_free_models()
    
    if not free_models:
        print("No free models found or error occurred.")
        return

    print(f"\nFound {len(free_models)} free models:\n")
    print(f"{'ID':<60} | {'Context':<8} | {'Status' if args.test else ''}")
    print("-" * (90 if args.test else 75))
    
    for model in free_models:
        model_id = model["id"]
        status_str = ""
        if args.test:
            available, msg = test_model_availability(model_id)
            status_str = f"| {msg}"
        
        print(f"{model_id:<60} | {model['context_length']:<8} {status_str}")

if __name__ == "__main__":
    main()
