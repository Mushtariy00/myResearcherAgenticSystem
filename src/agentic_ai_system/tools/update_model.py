import os
import re
from pathlib import Path
import subprocess

def get_best_model():
    try:
        result = subprocess.run(
            ["python3", "src/agentic_ai_system/tools/model_checker.py", "--best"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Error finding best model: {e}")
        return None

def update_agents_yaml(new_model):
    if not new_model:
        return False
    
    project_root = Path(__file__).resolve().parents[3]
    config_path = project_root / "src" / "agentic_ai_system" / "config" / "agents.yaml"
    
    if not config_path.exists():
        print(f"Error: {config_path} not found.")
        return False

    content = config_path.read_text(encoding="utf-8")
    
    # Replace any llm: line with the new model
    # We use regex to find lines like "llm: openai/gpt-oss-120b:free" or similar
    new_content = re.sub(r"llm: .*", f"llm: {new_model}", content)
    
    if content == new_content:
        print(f"Model is already set to {new_model} or no 'llm:' entries found.")
        return False

    config_path.write_text(new_content, encoding="utf-8")
    print(f"Successfully updated {config_path} to use model: {new_model}")
    return True

def main():
    print("Searching for the best available free model...")
    best_model = get_best_model()
    if best_model:
        print(f"Found best model: {best_model}")
        update_agents_yaml(best_model)
    else:
        print("Could not find any available free models.")

if __name__ == "__main__":
    main()
