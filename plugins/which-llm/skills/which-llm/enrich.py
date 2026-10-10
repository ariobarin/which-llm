"""Cross-reference AA scrape with the OpenRouter model catalog.

Reads `artifacts/models.csv` from a fresh scrape, or the tracked enriched CSV
when re-matching only. Fetches OpenRouter on demand. Writes
`artifacts/models_enriched.csv` with three OpenRouter columns:

  openrouter_slug          primary paid OR slug we matched (e.g. anthropic/claude-opus-4.7)
  openrouter_free_slug     :free OR slug, if one exists for the same model
  openrouter_has_free      true / false

Matching is best-effort via name normalization. Mismatches are printed at
the end so the schema drift can be tracked over time.

  python enrich.py
  python enrich.py --refresh   re-fetches openrouter.json
"""
from __future__ import annotations

import argparse
import csv
import json
import io
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ART = Path(__file__).parent / "artifacts"
AA_CSV = ART / "models.csv"
OR_JSON = ART / "openrouter.json"
OUT_CSV = ART / "models_enriched.csv"
UNMATCHED_TXT = ART / "unmatched.txt"
OR_FIELDS = ["openrouter_slug", "openrouter_free_slug", "openrouter_has_free", "openrouter_data_status"]
TIMESTAMP_FIELD = "snapshot_updated_at_utc"

OR_URL = "https://openrouter.ai/api/v1/models"
UA = "Mozilla/5.0 (compatible; aa-scrape/1.0)"

# AA-only suffixes we strip from a slug to get a "base" model name.
# Order matters: longer first.
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


def _get_json(url: str, timeout: int = 60):
    """Fetch JSON with a small retry loop for transient upstream failures."""
    transient_status = {429, 500, 502, 503, 504, 520, 521, 522, 524}
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except urllib.error.HTTPError as exc:
            if exc.code not in transient_status:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        if attempt < 3:
            time.sleep(2 ** attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"failed to fetch {url}")


def fetch_openrouter(refresh: bool) -> list[dict]:
    if OR_JSON.exists() and not refresh:
        data = json.loads(OR_JSON.read_text(encoding="utf-8"))
    else:
        print(f"GET {OR_URL}")
        data = _get_json(OR_URL)
    models = data.get("data") if isinstance(data, dict) else data
    if not isinstance(models, list) or len(models) < 100 or not all(
        isinstance(model, dict) and isinstance(model.get("id"), str) and model["id"]
        for model in models
    ):
        raise RuntimeError("OpenRouter returned an empty or invalid model catalog")
    # Never overwrite a previously valid cache with a partial/error API response.
    if refresh or not OR_JSON.exists():
        from data import atomic_write
        atomic_write(OR_JSON, json.dumps(data, indent=2))
        print(f"  saved {OR_JSON} ({len(json.dumps(data)):,} bytes)")
    return sorted(models, key=lambda m: m["id"])


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


def load_aa_rows() -> list[dict]:
    source = AA_CSV if AA_CSV.exists() else OUT_CSV
    if not source.exists():
        raise FileNotFoundError(
            "No AA snapshot found. Run: python scrape.py --refresh"
        )
    rows = list(csv.DictReader(source.open(encoding="utf-8")))
    if source == OUT_CSV:
        return [
            {key: value for key, value in row.items() if key not in OR_FIELDS}
            for row in rows
        ]
    return rows


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid snapshot source timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"snapshot source timestamp must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def _rows_by_slug(rows: list[dict]) -> dict[str, dict]:
    by_slug = {row.get("slug"): row for row in rows}
    if any(not row.get("slug") for row in rows) or len(by_slug) != len(rows):
        raise RuntimeError("snapshot rows must have unique slugs")
    return by_slug


def _source_timestamp(rows: list[dict]) -> tuple[str, datetime]:
    stamps = {row.get(TIMESTAMP_FIELD) or "" for row in rows}
    if len(stamps) != 1:
        raise RuntimeError("snapshot rows must carry one consistent source timestamp")
    stamp = stamps.pop()
    if not stamp:
        raise RuntimeError("snapshot source timestamp is missing")
    return stamp, _timestamp(stamp)


def enforce_snapshot_monotonicity(enriched: list[dict], previous: list[dict]) -> bool:
    """Keep a newer tracked timestamp when a stale edge returns identical data."""
    if not enriched:
        return False
    current_by_slug = _rows_by_slug(enriched)
    current_stamp, current_time = _source_timestamp(enriched)
    if not previous:
        return False
    previous_by_slug = _rows_by_slug(previous)
    previous_stamp, previous_time = _source_timestamp(previous)
    if current_time >= previous_time:
        return False

    def without_timestamp(row: dict) -> dict:
        return {key: value for key, value in row.items() if key != TIMESTAMP_FIELD}

    unchanged = (
        current_by_slug.keys() == previous_by_slug.keys()
        and all(
            without_timestamp(current_by_slug[slug])
            == without_timestamp(previous_by_slug[slug])
            for slug in current_by_slug
        )
    )
    if not unchanged:
        raise RuntimeError(
            f"refusing changed snapshot dated {current_stamp}; "
            f"tracked snapshot is newer at {previous_stamp}"
        )
    enriched[:] = [current_by_slug[row["slug"]] for row in previous]
    for current in enriched:
        current[TIMESTAMP_FIELD] = previous_stamp
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="Re-fetch openrouter.json before matching.")
    args = ap.parse_args()

    previous_rows = (
        list(csv.DictReader(OUT_CSV.open(encoding="utf-8")))
        if OUT_CSV.exists()
        else []
    )
    aa_rows = load_aa_rows()
    print(f"AA scrape:          {len(aa_rows)} models")

    try:
        or_models = fetch_openrouter(args.refresh)
    except (OSError, ValueError, RuntimeError) as exc:
        # The AA data is still usable. Do not erase known-good slugs due to
        # a broken optional OpenRouter feed; mark each fallback explicitly.
        if not any(row.get("openrouter_slug") or row.get("openrouter_free_slug")
                   for row in previous_rows):
            raise RuntimeError("OpenRouter unavailable and no published slug mappings exist") from exc
        print(f"WARNING: OpenRouter unavailable ({exc}); retaining cached slug mappings", file=sys.stderr)
        or_models = None
    previous_by_slug = {row["slug"]: row for row in previous_rows}
    if or_models is not None:
        print(f"OpenRouter catalog: {len(or_models)} models")
        exact_idx, loose_idx = build_or_index(or_models)
        previously_matched = [
            row for row in aa_rows
            if (old := previous_by_slug.get(row["slug"]))
            and (old.get("openrouter_slug") or old.get("openrouter_free_slug"))
        ]
        still_matched = sum(
            bool(match_aa_to_or(row, exact_idx, loose_idx))
            for row in previously_matched
        )
        if len(previously_matched) >= 20 and still_matched < len(previously_matched) * 0.8:
            print(
                f"WARNING: OpenRouter match count dropped from {len(previously_matched)} "
                f"to {still_matched}; keeping cached mappings instead",
                file=sys.stderr,
            )
            or_models = None
    if or_models is None:
        exact_idx, loose_idx = {}, {}

    matched = 0
    free_matched = 0
    unmatched: list[str] = []
    enriched: list[dict] = []
    sample_matches: list[tuple[str, str, str]] = []

    for r in aa_rows:
        paid_slug = ""
        free_slug = ""
        if or_models is None:
            cached = previous_by_slug.get(r["slug"], {})
            paid_slug = cached.get("openrouter_slug") or ""
            free_slug = cached.get("openrouter_free_slug") or ""
            source_status = "cached" if paid_slug or free_slug else "unavailable"
        else:
            hits = match_aa_to_or(r, exact_idx, loose_idx)
            for h in hits:
                full = h.get("id") or ""
                if full.endswith(":free"):
                    if not free_slug:
                        free_slug = full
                elif not paid_slug:
                    paid_slug = full
            source_status = "live"

        if paid_slug or free_slug:
            matched += 1
            if free_slug:
                free_matched += 1
            if len(sample_matches) < 8:
                sample_matches.append((r["slug"], paid_slug, free_slug))
        elif (r.get("deprecated") or "").lower() != "true":
            unmatched.append(f"{r['slug']:45s}  {r['name']}")

        enriched.append({
            **r,
            "openrouter_slug": paid_slug,
            "openrouter_free_slug": free_slug,
            "openrouter_has_free": "true" if free_slug else "false",
            "openrouter_data_status": source_status,
        })

    if enforce_snapshot_monotonicity(enriched, previous_rows):
        print("  kept newer tracked source timestamp for unchanged data")

    fieldnames = list(aa_rows[0].keys()) + OR_FIELDS
    from data import atomic_write
    with io.StringIO(newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(enriched)
        atomic_write(OUT_CSV, f.getvalue())
    print(f"  wrote {OUT_CSV}")

    unmatched_sorted = sorted(unmatched)
    warning = (
        "# WARNING: OpenRouter refresh failed; cached slugs may be stale. "
        "Rows carry openrouter_data_status=cached or unavailable.\n"
        if or_models is None else ""
    )
    atomic_write(
        UNMATCHED_TXT,
        f"# Unmatched non-deprecated AA models ({len(unmatched_sorted)} total)\n"
        f"# Run: python enrich.py  (regenerates this file)\n"
        + warning + "\n".join(unmatched_sorted) + "\n",
    )

    print(f"\nMatched {matched}/{len(aa_rows)} AA models to OpenRouter "
          f"({100*matched/len(aa_rows):.1f}%)")
    print(f"  ...of which {free_matched} have a :free OR variant")
    print(f"  Unmatched (non-deprecated): {len(unmatched)}  -> {UNMATCHED_TXT.name}")
    print("\nSample matches:")
    for aa, paid, free in sample_matches:
        print(f"  {aa:45s} -> paid={paid or '-'}  free={free or '-'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
