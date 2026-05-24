"""Inspect names with 'Opus' and look at a few cost-ref examples."""
import json
from pathlib import Path

models = json.loads(Path("artifacts/models.json").read_text(encoding="utf-8"))

print("--- All names containing 'Opus' ---")
for m in models:
    if "Opus" in (m.get("name") or ""):
        print(f"  {m['name']!r}  slug={m.get('slug')!r}  intel={m.get('intelligence_index')}  cost={m.get('intelligence_index_cost')}")

print("\n--- 5 rsc_ref values for intelligence_index_cost ---")
shown = 0
for m in models:
    v = m.get("intelligence_index_cost")
    if isinstance(v, str):
        print(f"  {m['name']!r} -> {v!r}")
        shown += 1
        if shown >= 5:
            break

print("\n--- top-level keys on the first model (so I see exactly what exists) ---")
first = models[0]
for k in sorted(first):
    v = first[k]
    if isinstance(v, (dict, list)):
        print(f"  {k}: <{type(v).__name__} len={len(v)}>")
    else:
        s = repr(v)
        if len(s) > 80:
            s = s[:77] + "..."
        print(f"  {k}: {s}")
