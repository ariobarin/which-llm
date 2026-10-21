"""Shared snapshot loading, filtering, and formatting for the which-llm commands.

Maintainers can run `python query.py data refresh` to re-scrape AA and OpenRouter.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
ART = HERE / "artifacts"
ENRICHED_CSV = ART / "models_enriched.csv"
BASE_CSV = ART / "models.csv"

STALE_AFTER_DAYS = 2
BLENDED_PRICE_PREFIX = "price_1m_blended_"
COST_CONTEXT = (
    "# cost context: token prices are rates, not workload costs. Workload cost "
    "also depends on token volume, caching, tools, and retries. Task-cost fields "
    "are benchmark-specific evidence, not application spend estimates."
)


def print_cost_context() -> None:
    print(COST_CONTEXT, file=sys.stderr)

# Modality vocabulary: what the user types -> the CSV column name.
MODALITY_TO_COLUMN = {
    "text": "input_modality_text",
    "image": "input_modality_image",
    "video": "input_modality_video",
    "audio": "input_modality_speech",  # AA calls it 'speech'; we expose 'audio'
}


def _csv_path() -> Path:
    return ENRICHED_CSV if ENRICHED_CSV.exists() else BASE_CSV


def _is_true(v) -> bool:
    return (v or "").strip().lower() == "true"


def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _data_age_days() -> float | None:
    p = _csv_path()
    if not p.exists():
        return None
    try:
        with p.open(encoding="utf-8", newline="") as handle:
            row = next(csv.DictReader(handle), None)
        stamp = (row or {}).get("snapshot_updated_at_utc")
        if not stamp:
            return None
        updated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds() / 86400
    except (OSError, csv.Error, ValueError, StopIteration):
        return None


def ensure_data() -> None:
    """Use fresh local data; otherwise fetch the published, validated snapshot."""
    from data import refresh_file, validate_csv

    age = _data_age_days()
    if age is not None and -1 / 24 <= age <= STALE_AFTER_DAYS:
        return
    print("# Fetching the current which-llm snapshot...", file=sys.stderr)
    try:
        refresh_file(ENRICHED_CSV, validate_csv)
    except RuntimeError as exc:
        raise SystemExit(f"{exc}. Cached data was preserved. Maintainers can run: python query.py data refresh") from exc


def _run_python(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(HERE / script), *args], cwd=HERE, check=True)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def _parse_modalities(spec: str | None) -> set[str]:
    """'text,image' -> {'text','image'}. 'any' or '' or None -> set() (no filter)."""
    if not spec or spec.strip().lower() == "any":
        return set()
    tokens = {t.strip().lower() for t in spec.split(",") if t.strip()}
    unknown = tokens - set(MODALITY_TO_COLUMN)
    if unknown:
        raise SystemExit(
            f"unknown modality {sorted(unknown)}; "
            f"valid: {sorted(MODALITY_TO_COLUMN)} or 'any'"
        )
    return tokens


def load_rows(
    modalities: set[str] | None = None,
    free_only: bool = False,
    include_deprecated: bool = False,
    min_cost: float = 0.0,
    max_cost: float = math.inf,
    intel_min: float | None = None,
    context_min: int | None = None,
    max_index_tokens: float | None = None,
    min_index_tokens: float = 0.0,
    max_latency: float | None = None,
    reasoning: bool | None = None,
    open_weights: bool | None = None,
) -> list[dict]:
    if modalities is None:
        modalities = {"text"}
    rows = []
    with _csv_path().open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not include_deprecated and _is_true(r.get("deprecated")):
                continue
            if modalities and not all(
                _is_true(r.get(MODALITY_TO_COLUMN[m])) for m in modalities
            ):
                continue
            if free_only and not _is_true(r.get("openrouter_has_free")):
                continue
            cost = _f(r.get("intelligence_index_cost_usd"))
            if (min_cost > 0 or max_cost < math.inf) and cost is None:
                continue
            if cost is not None and (cost < min_cost or cost > max_cost):
                continue
            if intel_min is not None and (_f(r.get("intelligence_index")) or -1) < intel_min:
                continue
            if context_min is not None and (_f(r.get("context_window_tokens")) or 0) < context_min:
                continue
            index_tokens = _f(r.get("indexTokensTotal"))
            if (min_index_tokens > 0 or max_index_tokens is not None) and index_tokens is None:
                continue
            if index_tokens is not None and (
                index_tokens < min_index_tokens
                or (max_index_tokens is not None and index_tokens > max_index_tokens)
            ):
                continue
            if max_latency is not None:
                lat = _f(r.get("e2e_response_seconds"))
                if lat is None or lat > max_latency:  # unmeasured can't be confirmed fast
                    continue
            if reasoning is not None and _is_true(r.get("reasoning_model")) != reasoning:
                continue
            if open_weights is not None and _is_true(r.get("is_open_weights")) != open_weights:
                continue
            rows.append(r)
    return rows


def apply_pattern(rows: list[dict], pattern: str | None) -> list[dict]:
    if not pattern:
        return rows
    pat = pattern.lower()
    return [
        r for r in rows
        if pat in (r.get("name") or "").lower()
        or pat in (r.get("slug") or "").lower()
        or pat in (r.get("creator_name") or "").lower()
    ]


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _model_matches(r: dict, pat: str) -> bool:
    p = pat.lower()
    return (
        p in (r.get("slug") or "").lower()
        or p in (r.get("name") or "").lower()
        or p in (r.get("openrouter_slug") or "").lower()
        or p in (r.get("openrouter_free_slug") or "").lower()
    )


def resolve_model(
    rows: list[dict],
    query: str,
    prefer_openrouter: bool = False,
) -> tuple[dict | None, list[dict]]:
    """Resolve exact or fuzzy model input. Returns (match, candidates)."""
    q = query.strip()
    qn = _norm(q)
    if not q:
        return None, []

    exact = [
        r for r in rows
        if q.lower() in {
            (r.get("slug") or "").lower(),
            (r.get("name") or "").lower(),
            (r.get("openrouter_slug") or "").lower(),
            (r.get("openrouter_free_slug") or "").lower(),
        }
        or qn in {
            _norm(r.get("slug")),
            _norm(r.get("name")),
            _norm(r.get("openrouter_slug")),
            _norm(r.get("openrouter_free_slug")),
        }
    ]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        if prefer_openrouter:
            ql = q.lower()
            same_endpoint = [
                r for r in exact
                if ql in {
                    (r.get("openrouter_slug") or "").lower(),
                    (r.get("openrouter_free_slug") or "").lower(),
                }
            ]
            if same_endpoint:
                same_endpoint.sort(
                    key=lambda r: -(_f(r.get("intelligence_index")) or -math.inf)
                )
                return same_endpoint[0], []
        return None, exact

    candidates = [r for r in rows if _model_matches(r, q)]
    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _fmt_cost(v) -> str:
    f = _f(v)
    if f is None:
        return "-"
    return f"${f:,.2f}" if f < 1000 else f"${f:,.0f}"


def _fmt_intel(v) -> str:
    f = _f(v)
    return f"{f:.1f}" if f is not None else "-"


def _fmt_secs(v) -> str:
    f = _f(v)
    return f"{f:.1f}" if f is not None else "-"


def _fmt_tokens(v) -> str:
    f = _f(v)
    if f is None:
        return "-"
    if f >= 1_000_000_000:
        return f"{f / 1_000_000_000:.2f}B"
    if f >= 1_000_000:
        return f"{f / 1_000_000:.1f}M"
    if f >= 1_000:
        return f"{f / 1_000:.1f}K"
    return f"{f:.0f}"


_JSON_ROUND = {
    "intelligence_index": 1,
    "intelligence_index_cost_usd": 2,
    "intelligence_index_cost_per_task_usd": 4,
    "agentic_index_cost_per_task_usd": 4,
    "ttft_seconds": 1,
    "e2e_response_seconds": 1,
}

_JSON_INT = {
    "context_window_tokens",
    "indexTokensTotal",
}

_JSON_FLOAT = {
    "active_parameters_billions",
    "agentic_index",
    "aime",
    "aime25",
    "apex_agents",
    "cache_hit_price",
    "coding_index",
    "critpt",
    "estimated_intelligence_index",
    "gdpval",
    "gpqa",
    "hle",
    "humaneval",
    "ifbench",
    "intelligence_index_input_cost_usd",
    "intelligence_index_output_cost_usd",
    "intelligence_index_per_m_output_tokens",
    "intelligence_index_reasoning_cost_usd",
    "lcr",
    "livecodebench",
    "math_500",
    "math_index",
    "mmlu_pro",
    "mmmu_pro",
    "omniscience",
    "parameters_billions",
    "price_1m_blended_0_100_1",
    "price_1m_blended_0_1_1",
    "price_1m_blended_0_3_1",
    "price_1m_blended_100_1_1",
    "price_1m_blended_7_2_1",
    "price_1m_input_tokens",
    "price_1m_output_tokens",
    "scicode",
    "tau2",
    "terminalbench_hard",
}

_JSON_BOOL = {
    "commercial_allowed",
    "deprecated",
    "frontier_model",
    "input_modality_image",
    "input_modality_speech",
    "input_modality_text",
    "input_modality_video",
    "intelligence_index_is_estimated",
    "is_open_weights",
    "openrouter_has_free",
    "output_modality_image",
    "output_modality_speech",
    "output_modality_text",
    "output_modality_video",
    "reasoning_model",
}


def _typed(k: str, v: str | None):
    """Parse CSV string to native type for JSON output, rounding where appropriate."""
    if v is None or v == "":
        return None
    if k in _JSON_ROUND:
        f = _f(v)
        return round(f, _JSON_ROUND[k]) if f is not None else None
    if k in _JSON_INT:
        return int(float(v)) if v else None
    if k in _JSON_FLOAT:
        return _f(v)
    if k in _JSON_BOOL:
        return v.strip().lower() == "true"
    return v


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Maintainer data tools.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("data", help="Re-scrape AA and OpenRouter.")
    sp.add_argument("action", choices=["refresh"])
    ap.parse_args()
    _run_python("scrape.py", "--refresh")
    _run_python("enrich.py", "--refresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
