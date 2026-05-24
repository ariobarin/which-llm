"""Spot-check OR matching for chart-visible models + popular ones."""
import csv
from pathlib import Path

rows = list(csv.DictReader(Path("artifacts/models_enriched.csv").open(encoding="utf-8")))

slugs = [
    "claude-opus-4-7", "claude-opus-4-7-non-reasoning",
    "claude-sonnet-4-6", "claude-sonnet-4-6-adaptive",
    "claude-4-5-haiku", "claude-4-5-haiku-reasoning",
    "gpt-5", "gpt-5-4", "gpt-5-5",
    "gemini-3-5-flash", "gemini-3-1-pro-preview",
    "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v3-2",
    "grok-4-3", "grok-4-3-medium", "grok-4-3-low",
    "kimi-k2-6", "minimax-m2-7",
    "mimo-v2-5-pro", "mimo-v2-flash",
    "gpt-oss-120b-low", "gpt-oss-20b-low",
    "gemma-4-31b-non-reasoning",
    "ling-2-6-flash",
    "qwen3-7-max", "qwen3-5-397b-a17b",
    "mistral-medium-3-5",
    "nova-pro-2-0",
]
by = {r["slug"]: r for r in rows}
print(f"{'AA slug':45s} {'OR paid':45s} {'OR free':30s}")
for s in slugs:
    r = by.get(s)
    if not r:
        print(f"{s:45s} (AA slug not in CSV)")
        continue
    paid = r["openrouter_slug"] or "-"
    free = r["openrouter_free_slug"] or "-"
    print(f"{s:45s} {paid:45s} {free:30s}")
