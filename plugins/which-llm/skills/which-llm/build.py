"""Build the merged model dataset from all sources.

Orchestrates the three data layers into `artifacts/models_enriched.csv`:

  1. scrape.py     AA leaderboard scrape  -> models.csv  (PRIMARY: the only
                   source for idx-run$ / cost-to-run, context, modality,
                   open-weights, params, and the AA-only long tail)
  2. fetch_api.py  AA official API        -> models_api.json  (sanctioned
                   cross-check + graceful-degradation fallback)
  3. enrich.py     OpenRouter catalog     -> models_enriched.csv  (slugs,
                   :free, context/modality cross-check)

Source selection via the WHICH_LLM_SOURCE env var:

  merged  (default)  scrape primary; if the scraper's parser breaks, fall
                     back to building the base from the API so the dataset
                     is never empty (just missing the scrape-only columns).
  scrape             scrape only; fail hard if the parser breaks.
  api                API only; never scrape. Sanctioned-source-only build,
                     for users who prefer not to scrape AA at all. Loses
                     idx-run$, context, modality, and open-weights.

  uv run python build.py            use cached inputs where present
  uv run python build.py --refresh  re-fetch every source
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import scrape  # same-dir module; importing only runs definitions

HERE = Path(__file__).parent
ART = HERE / "artifacts"
MODELS_CSV = ART / "models.csv"
MODELS_JSON = ART / "models.json"
API_JSON = ART / "models_api.json"

VALID_SOURCES = ("merged", "scrape", "api")


def _source() -> str:
    s = os.environ.get("WHICH_LLM_SOURCE", "merged").strip().lower()
    if s not in VALID_SOURCES:
        raise SystemExit(
            f"WHICH_LLM_SOURCE={s!r} invalid; choose one of {VALID_SOURCES}"
        )
    return s


def _run(script: str, refresh: bool) -> int:
    """Run a sibling pipeline script via uv; return its exit code."""
    cmd = ["uv", "run", "python", script]
    if refresh:
        cmd.append("--refresh")
    return subprocess.run(cmd, cwd=HERE).returncode


# --- API -> scrape-schema fallback ----------------------------------------

# Map the API's evaluations{} keys onto our flat CSV benchmark columns.
_API_EVAL_MAP = {
    "intelligence_index": "artificial_analysis_intelligence_index",
    "coding_index": "artificial_analysis_coding_index",
    "math_index": "artificial_analysis_math_index",
    "gpqa": "gpqa", "hle": "hle", "mmlu_pro": "mmlu_pro",
    "livecodebench": "livecodebench", "scicode": "scicode",
    "math_500": "math_500", "aime": "aime", "aime25": "aime_25",
    "tau2": "tau2", "terminalbench_hard": "terminalbench_hard",
    "ifbench": "ifbench", "lcr": "lcr",
}


def _api_to_rows(api_models: list[dict]) -> list[dict]:
    """Project API model objects onto scrape.CSV_FIELDS (blanks for the rest).

    Used only when scraping is unavailable. The scrape-only columns
    (idx-run$, context, modality, open-weights, params) stay empty —
    query.py degrades gracefully on those.
    """
    rows = []
    for m in api_models:
        ev = m.get("evaluations") or {}
        pr = m.get("pricing") or {}
        cr = m.get("model_creator") or {}
        row = {k: None for k in scrape.CSV_FIELDS}
        row["name"] = m.get("name")
        row["slug"] = m.get("slug")
        row["release_date"] = m.get("release_date")
        row["creator_name"] = cr.get("name")
        row["creator_slug"] = cr.get("slug")
        for col, api_key in _API_EVAL_MAP.items():
            row[col] = ev.get(api_key)
        row["price_1m_input_tokens"] = pr.get("price_1m_input_tokens")
        row["price_1m_output_tokens"] = pr.get("price_1m_output_tokens")
        rows.append(row)
    return rows


def _write_models_csv(rows: list[dict]) -> None:
    ART.mkdir(parents=True, exist_ok=True)
    with MODELS_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=scrape.CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _build_base_from_api() -> None:
    """Build models.csv from the cached API JSON (degraded base)."""
    if not API_JSON.exists():
        raise SystemExit(
            "API source requested but artifacts/models_api.json is missing. "
            "Run: uv run python fetch_api.py --refresh"
        )
    api_models = json.loads(API_JSON.read_text(encoding="utf-8"))
    rows = _api_to_rows(api_models)
    _write_models_csv(rows)
    MODELS_JSON.write_text(json.dumps(api_models, indent=2), encoding="utf-8")
    print(f"  built models.csv from API ({len(rows)} models, scrape-only "
          f"columns blank)")


# --- cross-check ------------------------------------------------------------


def _cross_check() -> None:
    """Report intelligence_index drift between the scrape and the API.

    A large, widespread divergence is an early signal that the scrape parser
    has silently latched onto stale or wrong data even though it didn't error.
    """
    if not (MODELS_CSV.exists() and API_JSON.exists()):
        return
    try:
        api = {m["slug"]: m for m in json.loads(API_JSON.read_text("utf-8"))}
        scraped = list(csv.DictReader(MODELS_CSV.open(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, KeyError):
        return
    checked = drift = 0
    for r in scraped:
        a = api.get(r.get("slug"))
        if not a:
            continue
        ai = (a.get("evaluations") or {}).get(
            "artificial_analysis_intelligence_index")
        try:
            si = float(r.get("intelligence_index") or "nan")
        except ValueError:
            continue
        if ai is None or si != si:  # si!=si => NaN
            continue
        checked += 1
        if abs(si - ai) > 1.0:
            drift += 1
    if checked:
        pct = 100 * drift / checked
        flag = "  <-- investigate" if pct > 10 else ""
        print(f"cross-check: {checked} models compared to API, "
              f"{drift} differ >1.0 on intelligence_index ({pct:.0f}%){flag}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch every source (else use cached inputs)")
    args = ap.parse_args()
    source = _source()
    print(f"build: source={source}")

    scrape_ok = False
    if source in ("merged", "scrape"):
        rc = _run("scrape.py", args.refresh)
        scrape_ok = rc == 0
        if not scrape_ok:
            if source == "scrape":
                print("scrape failed and source=scrape; aborting.",
                      file=sys.stderr)
                return rc or 1
            print("WARN: scrape failed; falling back to API base "
                  "(idx-run$/context/modality will be blank).", file=sys.stderr)

    # Always pull the API when possible: it's the cross-check, and the base
    # for api-source or scrape-fallback. Non-fatal in merged mode (e.g. no key).
    api_rc = _run("fetch_api.py", args.refresh)
    if source == "api" or not scrape_ok:
        if api_rc != 0 and not API_JSON.exists():
            print("ERROR: no scrape and no API data available.",
                  file=sys.stderr)
            return 1
        _build_base_from_api()

    rc = _run("enrich.py", args.refresh)
    if rc != 0:
        return rc

    _cross_check()
    print("build: done -> artifacts/models_enriched.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
