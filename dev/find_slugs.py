import csv
rows = list(csv.DictReader(open("artifacts/models.csv", encoding="utf-8")))
patterns = [
    "Grok 4.3",
    "DeepSeek V4 Pro",
    "DeepSeek V4 Flash",
    "Gemma 4 31B",
    "MiMo-V2-Flash",
    "gpt-oss-120b",
    "gpt-oss-20B",
    "Ling 2.6 Flash",
]
for p in patterns:
    print(f"\n=== {p} ===")
    for r in rows:
        if p in (r["name"] or ""):
            print(f"  {r['slug']:50s}  {r['name']}")
