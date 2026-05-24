"""Cross-reference AA scrape with the OpenRouter model catalog.

Reads `artifacts/models.csv` (from scrape.py) and `artifacts/openrouter.json`
(fetched on demand). Writes `artifacts/models_enriched.csv` with three new
columns:

  openrouter_slug          primary paid OR slug we matched (e.g. anthropic/claude-opus-4.7)
  openrouter_free_slug     :free OR slug, if one exists for the same model
  openrouter_has_free      true / false

Matching is best-effort via name normalization. Mismatches are printed at
the end so the schema drift can be tracked over time.

  uv run py enrich.py
  uv run py enrich.py --refresh   re-fetches openrouter.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import requests

ART = Path(__file__).parent / "artifacts"
AA_CSV = ART / "models.csv"
OR_JSON = ART / "openrouter.json"
OUT_CSV = ART / "models_enriched.csv"

OR_URL = "https://openrouter.ai/api/v1/models"
UA = "Mozilla/5.0 (compatible; aa-scrape/1.0)"

# AA-only suffixes we strip from a slug to get a "base" model name.
# Order matters — longer first.
SUFFIX_STRIPS = [
    "-non-reasoning",
    "-adaptive",
    "-reasoning",
    "-thinking",
    "-minimal",
    "-xhigh",
    "-medium",
    "-high",
    "-low",
    "-max",
    "-pro",  # only strip after others; risky, but pairs (e.g., -reasoning-pro) get -reasoning first
]
# Same idea but for matching against OR names (which use 'Reasoning'/'Non-reasoning' in display name).
NAME_NOISE = re.compile(
    r"\((?:Adaptive\s+|Non-)?[Rr]easoning(?:,\s*[A-Za-z]+\s+Effort)?\)"
    r"|\(Non-[Rr]easoning\)"
    r"|\([A-Za-z]+\s+Effort\)"
    r"|\([Mm]edium\)|\([Hh]igh\)|\([Ll]ow\)|\([Mm]ax\)|\(xhigh\)|\([Mm]inimal\)"
)


def fetch_openrouter(refresh: bool) -> list[dict]:
    if OR_JSON.exists() and not refresh:
        data = json.loads(OR_JSON.read_text(encoding="utf-8"))
    else:
        print(f"GET {OR_URL}")
        r = requests.get(OR_URL, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        data = r.json()
        OR_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  saved {OR_JSON} ({len(json.dumps(data)):,} bytes)")
    return data["data"] if isinstance(data, dict) else data


def _norm(s: str) -> str:
    """Lowercase, strip non-alphanumerics. 'Claude-Opus-4.7' -> 'claudeopus47'."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _norm_tokens(s: str) -> str:
    """Sort alphanumeric tokens to be word-order-insensitive.

    'llama-3.3-70b-instruct' and 'llama-3-3-instruct-70b' both become
    '3370binstructllama'. Token multisets are stable across the
    'instruct-70b' / '70b-instruct' style permutations AA and OR disagree on.
    """
    tokens = re.findall(r"[a-z0-9]+", (s or "").lower())
    return "".join(sorted(tokens))


def _aa_base_slug(slug: str) -> str:
    """Strip reasoning/effort suffixes from an AA slug to get a base model slug."""
    s = slug
    while True:
        cut = None
        for suf in SUFFIX_STRIPS:
            if s.endswith(suf) and len(s) > len(suf) + 1:
                cut = suf
                break
        if cut is None:
            return s
        s = s[: -len(cut)]


def _aa_clean_name(name: str) -> str:
    """Strip reasoning/effort parenthetical bits from a display name."""
    return NAME_NOISE.sub("", name or "").strip()


def build_or_index(or_models: list[dict]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Build two OR indexes: exact-normalized and token-multiset (loose).

    Loose lookups are only tried when exact ones fail. We return two separate
    indexes so the loose pass stays opt-in and false-positive risk is bounded.
    """
    exact: dict[str, list[dict]] = {}
    loose: dict[str, list[dict]] = {}
    for m in or_models:
        full_id = m.get("id") or ""
        clean_id = full_id.split(":")[0]
        slash = clean_id.split("/", 1)
        model_part = slash[1] if len(slash) == 2 else clean_id
        name = m.get("name") or ""
        name_tail = name.split(":", 1)[1] if ":" in name else name

        exact_keys = {
            _norm(model_part),
            _norm(clean_id),
            _norm(m.get("canonical_slug") or ""),
            _norm(name_tail),
            _norm(name),
        }
        loose_keys = {
            _norm_tokens(model_part),
            _norm_tokens(name_tail),
        }
        for k in filter(None, exact_keys):
            exact.setdefault(k, []).append(m)
        for k in filter(None, loose_keys):
            loose.setdefault(k, []).append(m)
    return exact, loose


def match_aa_to_or(
    aa: dict,
    exact_idx: dict[str, list[dict]],
    loose_idx: dict[str, list[dict]],
) -> list[dict]:
    """Return OR models that match this AA row (including :free variants).

    Try exact normalization first, then fall back to token-multiset matching
    against the loose index for cases where AA and OR use different word order.
    """
    slug = aa.get("slug") or ""
    base_slug = _aa_base_slug(slug)
    name = aa.get("name") or ""
    clean_name = _aa_clean_name(name)

    exact_candidates = [_norm(slug), _norm(base_slug), _norm(clean_name), _norm(name)]
    for key in exact_candidates:
        if key and (hits := exact_idx.get(key)):
            return hits
    loose_candidates = [_norm_tokens(base_slug), _norm_tokens(clean_name)]
    for key in loose_candidates:
        if key and (hits := loose_idx.get(key)):
            return hits
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Re-fetch openrouter.json before matching.")
    args = ap.parse_args()

    or_models = fetch_openrouter(args.refresh)
    print(f"OpenRouter catalog: {len(or_models)} models")

    aa_rows = list(csv.DictReader(AA_CSV.open(encoding="utf-8")))
    print(f"AA scrape:          {len(aa_rows)} models")

    exact_idx, loose_idx = build_or_index(or_models)

    matched = 0
    free_matched = 0
    unmatched: list[str] = []
    enriched: list[dict] = []
    sample_matches: list[tuple[str, str, str]] = []

    for r in aa_rows:
        hits = match_aa_to_or(r, exact_idx, loose_idx)
        paid_slug = ""
        free_slug = ""
        for h in hits:
            full = h.get("id") or ""
            if full.endswith(":free"):
                if not free_slug:
                    free_slug = full
            elif not paid_slug:
                paid_slug = full
        if paid_slug or free_slug:
            matched += 1
            if free_slug:
                free_matched += 1
            if len(sample_matches) < 8:
                sample_matches.append((r["slug"], paid_slug, free_slug))
        else:
            # Track only non-deprecated unmatched for noise reduction.
            if (r.get("deprecated") or "").lower() != "true":
                unmatched.append(f"{r['slug']:45s}  {r['name']}")
        enriched.append({
            **r,
            "openrouter_slug": paid_slug,
            "openrouter_free_slug": free_slug,
            "openrouter_has_free": "true" if free_slug else "false",
        })

    # Write the enriched CSV.
    fieldnames = list(aa_rows[0].keys()) + [
        "openrouter_slug", "openrouter_free_slug", "openrouter_has_free",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(enriched)
    print(f"  wrote {OUT_CSV}")

    print(f"\nMatched {matched}/{len(aa_rows)} AA models to OpenRouter "
          f"({100*matched/len(aa_rows):.1f}%)")
    print(f"  ...of which {free_matched} have a :free OR variant")
    print(f"  Unmatched (non-deprecated): {len(unmatched)}")
    print("\nSample matches:")
    for aa, paid, free in sample_matches:
        print(f"  {aa:45s} -> paid={paid or '-'}  free={free or '-'}")
    if unmatched:
        print(f"\nFirst 20 unmatched (non-deprecated):")
        for u in unmatched[:20]:
            print(f"  {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
