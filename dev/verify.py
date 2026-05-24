"""Sanity-check scraped values against the chart screenshot."""
import csv
from pathlib import Path

rows = list(csv.DictReader(Path("artifacts/models.csv").open(encoding="utf-8")))
print(f"{len(rows)} rows in CSV")

print("\n--- All GPT-5.* model slugs/names ---")
for r in rows:
    if "GPT-5" in (r["name"] or "") or (r["slug"] or "").startswith("gpt-5"):
        print(f"  {r['slug']:40s}  {r['name']}")

print("\n--- Chart-visible models (from screenshot), sorted by cost ---")
chart_slug_substrings = [
    "claude-opus-4-7", "claude-sonnet-4-6", "gpt-5", "gemini-3-5-flash",
    "gemini-3-1-pro", "qwen3-7-max", "qwen3-5-397b", "grok-4-3-high",
    "kimi-k2-6", "deepseek-v3-2", "deepseek-v4", "minimax-m2-7",
    "mimo-v2-5-pro", "nvidia-nemotron-3-super", "gpt-oss-120b-high",
    "gpt-oss-20b", "claude-4-5-haiku", "nova-2-pro", "mistral-medium-3-5",
]

picked = []
for r in rows:
    slug = r["slug"] or ""
    for sub in chart_slug_substrings:
        if sub in slug:
            picked.append(r)
            break

picked.sort(key=lambda r: float(r["intelligence_index_cost_usd"]) if r["intelligence_index_cost_usd"] else 0)
print(f"{'slug':40s} {'name':55s} {'intel':>7s} {'cost USD':>11s}")
for r in picked:
    intel = r["intelligence_index"] or ""
    cost = r["intelligence_index_cost_usd"] or ""
    print(f"{r['slug']:40s} {(r['name'] or '')[:55]:55s} {intel[:7]:>7s} {cost[:11]:>11s}")
