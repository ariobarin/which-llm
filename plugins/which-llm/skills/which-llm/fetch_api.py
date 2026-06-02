"""Fetch model data from the official Artificial Analysis API.

This is the *sanctioned* data channel: AA's free API
(https://artificialanalysis.ai/api-reference), authenticated with an
`AA_API_KEY`. It returns authoritative benchmark scores, pricing, and the
AA intelligence/coding/math indices, keyed by stable model UUIDs.

It is a strict subset of what `scrape.py` collects — notably it does NOT
expose `intelligence_index_cost_usd` (the cost-to-run-the-index figure),
context window, modality flags, or open-weights status. We use it for two
things: cross-checking the scrape, and as a graceful-degradation fallback
when AA changes their page and the scraper's parser breaks.

  artifacts/models_api.json    raw model list from the API (sorted by id)

Run:
  uv run python fetch_api.py            use cached JSON if present
  uv run python fetch_api.py --refresh  re-fetch from the API

Auth: set AA_API_KEY in the environment, or put it in a `.env` file at the
repo root (KEY=VALUE per line). Get a free key at
https://artificialanalysis.ai/ (Insights Platform). Attribution to
Artificial Analysis is required for all use of the free API.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_URL = "https://artificialanalysis.ai/api/v2/data/llms/models"
UA = "which-llm/0 (+https://github.com/ariobarin/which-llm)"

ART = Path(__file__).parent / "artifacts"
API_JSON = ART / "models_api.json"

# Same sanity floor scrape.py uses: refuse to overwrite with a short response.
MIN_MODELS = 400
REQUIRED_KEYS = ("id", "slug", "evaluations")


def _load_key() -> str:
    """AA_API_KEY from the environment, or a `.env` file walking up from here."""
    key = os.environ.get("AA_API_KEY")
    if key:
        return key.strip()
    for base in [Path.cwd(), *Path(__file__).resolve().parents]:
        env = base / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("AA_API_KEY") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(
        "AA_API_KEY not set. Get a free key at https://artificialanalysis.ai/ "
        "and set it in your environment or a .env file at the repo root."
    )


def _session() -> requests.Session:
    """requests.Session with retries on transient upstream errors."""
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=2,  # 0s, 2s, 4s
        status_forcelist=(500, 502, 503, 504, 520, 521, 522, 524),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def fetch_models(refresh: bool) -> list[dict]:
    if API_JSON.exists() and not refresh:
        data = json.loads(API_JSON.read_text(encoding="utf-8"))
        return data

    key = _load_key()
    print(f"GET {API_URL}")
    r = _session().get(
        API_URL,
        headers={"x-api-key": key, "User-Agent": UA},
        timeout=60,
    )
    r.raise_for_status()
    payload = r.json()
    models = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(models, list):
        raise RuntimeError(
            f"API response 'data' is not a list (got {type(models).__name__})"
        )

    # Schema gate, mirroring scrape.py: refuse to ship a short/odd response.
    if len(models) < MIN_MODELS:
        raise RuntimeError(
            f"API returned only {len(models)} models (expected >= {MIN_MODELS})."
        )
    first = models[0] if models else {}
    missing = [k for k in REQUIRED_KEYS if k not in first]
    if missing:
        raise RuntimeError(f"API model objects missing expected keys {missing}.")

    # Sort by stable UUID for deterministic diffs (same rationale as enrich.py).
    models = sorted(models, key=lambda m: m.get("id") or "")
    ART.mkdir(parents=True, exist_ok=True)
    API_JSON.write_text(json.dumps(models, indent=2), encoding="utf-8")
    print(f"  saved {len(models)} models -> {API_JSON} "
          f"({API_JSON.stat().st_size:,} bytes)")
    return models


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch from the API (else use cached JSON)")
    args = ap.parse_args()

    models = fetch_models(args.refresh)
    print(f"Artificial Analysis API: {len(models)} models")

    # Spot-check a few well-known models so a broken fetch is obvious.
    print("\n--- Spot checks ---")
    by_slug = {m.get("slug"): m for m in models}
    for slug in ("claude-opus-4-7", "gpt-5-5-xhigh", "deepseek-v3-2"):
        m = by_slug.get(slug)
        if not m:
            print(f"  {slug}: not found")
            continue
        ev = m.get("evaluations") or {}
        pr = m.get("pricing") or {}
        print(f"  {m.get('name'):45s}  "
              f"intel={ev.get('artificial_analysis_intelligence_index')!s:>6}  "
              f"blended=${pr.get('price_1m_blended_3_to_1')!s:>8}/Mtok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
