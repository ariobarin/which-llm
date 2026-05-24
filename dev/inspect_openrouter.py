"""Look up specific OR slugs to figure out matching gaps."""
import json
from pathlib import Path

models = json.loads(Path("artifacts/openrouter.json").read_text(encoding="utf-8"))["data"]

queries = ["llama-3", "llama-4", "claude-haiku", "claude-4-5", "gemma-4", "gemini-3",
           "magistral", "mistral-large", "devstral", "ministral", "kimi", "mimo",
           "minimax", "gemma-3", "qwen3-7", "qwen3-5", "qwen3-6"]

for q in queries:
    print(f"\n=== '{q}' ===")
    for m in models:
        sid = m.get("id", "")
        if q in sid:
            print(f"  {sid}")
