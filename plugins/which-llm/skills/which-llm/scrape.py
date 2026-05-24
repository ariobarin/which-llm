"""Scrape Artificial Analysis model leaderboard data.

Fetches https://artificialanalysis.ai/models, extracts the embedded RSC
payload, locates the full model array (the `defaultData` prop), and dumps:

  artifacts/models.html          raw HTML (cached for re-runs)
  artifacts/models.json          full normalized model list
  artifacts/models.csv           flat per-model rows for quick analysis

Run:
  uv run python scrape.py            use cached HTML if present
  uv run python scrape.py --refresh  re-download HTML
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import requests

URL = "https://artificialanalysis.ai/models"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

ART = Path(__file__).parent / "artifacts"
HTML_PATH = ART / "models.html"
JSON_PATH = ART / "models.json"
CSV_PATH = ART / "models.csv"


def fetch_html(refresh: bool) -> str:
    if HTML_PATH.exists() and not refresh:
        return HTML_PATH.read_text(encoding="utf-8")
    ART.mkdir(parents=True, exist_ok=True)
    print(f"GET {URL}")
    r = requests.get(URL, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    HTML_PATH.write_text(r.text, encoding="utf-8")
    print(f"  saved {len(r.text):,} chars -> {HTML_PATH}")
    return r.text


_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[(\d+),\s*"((?:[^"\\]|\\.)*)"\]\)', re.DOTALL)


def extract_rsc_stream(html: str) -> str:
    """Concatenate every kind=1 __next_f.push chunk into the raw RSC stream."""
    parts: list[str] = []
    for m in _CHUNK_RE.finditer(html):
        if m.group(1) != "1":
            continue
        parts.append(json.loads('"' + m.group(2) + '"'))
    if not parts:
        raise RuntimeError("No __next_f.push chunks found — page format changed?")
    return "".join(parts)


def find_default_data(stream: str) -> list[dict]:
    """Locate '"defaultData":[' in the RSC stream and JSON-parse the array."""
    needle = '"defaultData":['
    idx = stream.find(needle)
    if idx < 0:
        raise RuntimeError("defaultData marker not found in RSC stream")
    start = idx + len(needle) - 1  # position of '['
    decoder = json.JSONDecoder()
    arr, _end = decoder.raw_decode(stream, start)
    if not isinstance(arr, list):
        raise RuntimeError(f"defaultData is not a list (got {type(arr).__name__})")
    return arr


# Flat per-model columns for the CSV. The JSON file keeps every original field.
CSV_FIELDS = [
    # Identity
    "name",
    "short_name",
    "slug",
    "model_family_slug",
    "creator_name",
    "creator_slug",
    "release_date",
    "knowledge_cutoff_date",
    "deprecated",
    # The two chart axes
    "intelligence_index",
    "intelligence_index_cost_usd",
    # Companion intelligence-index fields
    "intelligence_index_is_estimated",
    "estimated_intelligence_index",
    "intelligence_index_per_m_output_tokens",
    "intelligence_index_input_cost_usd",
    "intelligence_index_output_cost_usd",
    "intelligence_index_reasoning_cost_usd",
    # Composite sub-indexes
    "coding_index",
    "math_index",
    "agentic_index",
    # Individual benchmarks
    "gpqa",
    "hle",
    "mmlu_pro",
    "mmmu_pro",
    "livecodebench",
    "math_500",
    "aime",
    "aime25",
    "scicode",
    "humaneval",
    "tau2",
    "terminalbench_hard",
    "ifbench",
    "apex_agents",
    "lcr",
    "critpt",
    "gdpval",
    "omniscience",
    # Pricing per 1M tokens, USD. AA publishes several blends; the
    # "_X_Y_1" names are AA-internal ratio identifiers, see their site.
    "price_1m_input_tokens",
    "price_1m_output_tokens",
    "price_1m_blended_0_100_1",
    "price_1m_blended_0_1_1",
    "price_1m_blended_0_3_1",
    "price_1m_blended_100_1_1",
    "price_1m_blended_7_2_1",
    "cache_hit_price",
    # Capability flags
    "reasoning_model",
    "frontier_model",
    "is_open_weights",
    "commercial_allowed",
    "input_modality_text",
    "input_modality_image",
    "input_modality_speech",
    "input_modality_video",
    "output_modality_text",
    "output_modality_image",
    "output_modality_speech",
    "output_modality_video",
    # Size & context
    "context_window_tokens",
    "parameters_billions",
    "active_parameters_billions",
    "size_class",
]


def _clean(v):
    """Coerce RSC sentinels ('$undefined', '$null', '$<hex>') to None.

    These appear because the React Server Component stream uses '$N' to mark
    references and '$undefined'/'$null' for missing values. None of our target
    fields legitimately start with '$', so this is safe.
    """
    if isinstance(v, str) and v.startswith("$"):
        return None
    return v


def _f(m: dict, key: str):
    return _clean(m.get(key))


def flatten(m: dict) -> dict:
    creators = m.get("model_creators") or {}
    cost = _clean(m.get("intelligence_index_cost")) or {}
    if not isinstance(cost, dict):
        cost = {}
    # The "_3_1" blended ratio isn't directly exposed; price_1m_blended_7_2_1
    # is the closest standard ratio AA publishes. Keep the raw fields they expose.
    return {
        "name": _f(m, "name"),
        "short_name": _f(m, "short_name"),
        "slug": _f(m, "slug"),
        "model_family_slug": _f(m, "model_family_slug"),
        "creator_name": _clean(creators.get("name")),
        "creator_slug": _clean(creators.get("slug")),
        "release_date": _f(m, "release_date"),
        "knowledge_cutoff_date": _f(m, "knowledge_cutoff_date"),
        "deprecated": _f(m, "deprecated"),

        "intelligence_index": _f(m, "intelligence_index"),
        "intelligence_index_cost_usd": _clean(cost.get("total_cost")),
        "intelligence_index_is_estimated": _f(m, "intelligence_index_is_estimated"),
        "estimated_intelligence_index": _f(m, "estimated_intelligence_index"),
        "intelligence_index_per_m_output_tokens": _f(m, "intelligence_index_per_m_output_tokens"),
        "intelligence_index_input_cost_usd": _clean(cost.get("input_cost")),
        "intelligence_index_output_cost_usd": _clean(cost.get("output_cost")),
        "intelligence_index_reasoning_cost_usd": _clean(cost.get("reasoning_cost")),

        "coding_index": _f(m, "coding_index"),
        "math_index": _f(m, "math_index"),
        "agentic_index": _f(m, "agentic_index"),

        "gpqa": _f(m, "gpqa"),
        "hle": _f(m, "hle"),
        "mmlu_pro": _f(m, "mmlu_pro"),
        "mmmu_pro": _f(m, "mmmu_pro"),
        "livecodebench": _f(m, "livecodebench"),
        "math_500": _f(m, "math_500"),
        "aime": _f(m, "aime"),
        "aime25": _f(m, "aime25"),
        "scicode": _f(m, "scicode"),
        "humaneval": _f(m, "humaneval"),
        "tau2": _f(m, "tau2"),
        "terminalbench_hard": _f(m, "terminalbench_hard"),
        "ifbench": _f(m, "ifbench"),
        "apex_agents": _f(m, "apex_agents"),
        "lcr": _f(m, "lcr"),
        "critpt": _f(m, "critpt"),
        "gdpval": _f(m, "gdpval"),
        "omniscience": _f(m, "omniscience"),

        "price_1m_input_tokens": _f(m, "price_1m_input_tokens"),
        "price_1m_output_tokens": _f(m, "price_1m_output_tokens"),
        "price_1m_blended_0_100_1": _f(m, "price_1m_blended_0_100_1"),
        "price_1m_blended_0_1_1": _f(m, "price_1m_blended_0_1_1"),
        "price_1m_blended_0_3_1": _f(m, "price_1m_blended_0_3_1"),
        "price_1m_blended_100_1_1": _f(m, "price_1m_blended_100_1_1"),
        "price_1m_blended_7_2_1": _f(m, "price_1m_blended_7_2_1"),
        "cache_hit_price": _f(m, "cache_hit_price"),

        "reasoning_model": _f(m, "reasoning_model"),
        "frontier_model": _f(m, "frontier_model"),
        "is_open_weights": _f(m, "is_open_weights"),
        "commercial_allowed": _f(m, "commercial_allowed"),
        "input_modality_text": _f(m, "input_modality_text"),
        "input_modality_image": _f(m, "input_modality_image"),
        "input_modality_speech": _f(m, "input_modality_speech"),
        "input_modality_video": _f(m, "input_modality_video"),
        "output_modality_text": _f(m, "output_modality_text"),
        "output_modality_image": _f(m, "output_modality_image"),
        "output_modality_speech": _f(m, "output_modality_speech"),
        "output_modality_video": _f(m, "output_modality_video"),

        "context_window_tokens": _f(m, "context_window_tokens"),
        "parameters_billions": _f(m, "parameters"),
        "active_parameters_billions": _f(m, "activeParams"),
        "size_class": _f(m, "size_class"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch the HTML")
    args = ap.parse_args()

    html = fetch_html(args.refresh)
    stream = extract_rsc_stream(html)
    models = find_default_data(stream)
    print(f"Parsed {len(models)} models from defaultData")

    # Catastrophic-drop guard: if we already have a known-good snapshot and the
    # new parse comes back with <80% of that count, refuse to overwrite. Almost
    # always means AA changed page structure and we're parsing garbage.
    if JSON_PATH.exists():
        try:
            prev = json.loads(JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(prev, list) and len(prev) > 0:
                ratio = len(models) / len(prev)
                if ratio < 0.8:
                    print(
                        f"ABORT: parsed {len(models)} models, previous snapshot "
                        f"had {len(prev)} ({ratio:.0%}). Refusing to overwrite. "
                        f"Investigate before re-running.",
                        file=sys.stderr,
                    )
                    return 2
        except (json.JSONDecodeError, OSError):
            pass  # corrupt or missing previous snapshot — proceed

    ART.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(models, indent=2), encoding="utf-8")
    print(f"  wrote {JSON_PATH} ({JSON_PATH.stat().st_size:,} bytes)")

    rows = [flatten(m) for m in models]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {CSV_PATH} ({CSV_PATH.stat().st_size:,} bytes)")

    # Spot-check a few chart-visible models against the screenshot.
    print("\n--- Spot checks against the Intelligence-vs-Cost chart ---")
    targets = [
        "claude-opus-4-7",
        "gpt-5-4-xhigh",
        "gpt-5-5-xhigh",
        "deepseek-v3-2",
        "gemini-3-5-flash",
    ]
    by_slug = {r["slug"]: r for r in rows if r.get("slug")}
    for slug in targets:
        r = by_slug.get(slug)
        if not r:
            print(f"  {slug}: NOT FOUND")
            continue
        print(
            f"  {r['name']:55s}  index={r['intelligence_index']!s:>6}  "
            f"cost=${r['intelligence_index_cost_usd']!s:>10}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
