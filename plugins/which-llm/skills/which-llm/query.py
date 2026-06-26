"""Agent-facing CLI for LLM model selection queries.

  python query.py models                                 # top 20 by intel
  python query.py models claude                          # substring match
  python query.py models --top 5 --max-cost 500 --modality text,image
  python query.py models --intel-min 50 --sort tokens       # token-efficient
  python query.py models --pareto --max-cost 200         # Pareto frontier
  python query.py models --free                          # OR-free models
  python query.py compare claude-opus-4-7 gpt-5          # side-by-side table
  python query.py slug claude-opus-4-7                   # OpenRouter slugs
  python query.py show claude-opus-4-7                   # one model, full info
  python query.py data status                            # data freshness
  python query.py data refresh                           # re-scrape AA + OR

All `models` queries produce the same table schema (or pass `--json` for
machine output). `show` emits a multi-line profile by default, or JSON.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
ART = HERE / "artifacts"
ENRICHED_CSV = ART / "models_enriched.csv"
BASE_CSV = ART / "models.csv"

STALE_AFTER_DAYS = 7  # warn (don't refuse) if data older than this

# Canonical output columns. Both the table renderer and `--json` use these.
OUTPUT_FIELDS = [
    "slug", "name", "creator_name", "intelligence_index",
    "intelligence_index_cost_usd", "indexTokensTotal",
    "context_window_tokens",
    "price_1m_input_tokens", "price_1m_output_tokens",
    "ttft_seconds", "e2e_response_seconds",
    "openrouter_has_free", "openrouter_slug", "openrouter_free_slug",
]

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
    return (time.time() - p.stat().st_mtime) / 86400


def ensure_data() -> None:
    """If no CSV exists, run scrape.py + enrich.py."""
    if not (ENRICHED_CSV.exists() or BASE_CSV.exists()):
        print("# No cached data found, fetching from Artificial Analysis...",
              file=sys.stderr)
        _run_python("scrape.py")
        _run_python("enrich.py")


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


def _print_candidates(query: str, candidates: list[dict]) -> None:
    if candidates:
        print(f"# multiple matches for {query!r}; specify slug:", file=sys.stderr)
        print(f"# hint: python query.py models {query!r} --top 10", file=sys.stderr)
        for c in candidates[:10]:
            print(f"  {c['slug']:45s}  {c['name']}", file=sys.stderr)
    else:
        print(f"# no model matching {query!r}", file=sys.stderr)
        print(f"# hint: python query.py models {query!r} --top 10", file=sys.stderr)


def pareto_frontier(rows: list[dict]) -> list[dict]:
    """Filter to cost-min / intel-max Pareto-optimal points."""
    pts = [
        r for r in rows
        if _f(r.get("intelligence_index")) is not None
        and (_f(r.get("intelligence_index_cost_usd")) or 0) > 0
    ]
    pts.sort(key=lambda r: (_f(r["intelligence_index_cost_usd"]),
                            -_f(r["intelligence_index"])))
    front = []
    best = -math.inf
    for r in pts:
        i = _f(r["intelligence_index"])
        if i > best:
            front.append(r)
            best = i
    return front


def _speed_key(r):
    """End-to-end latency ascending (faster first); unmeasured sorts last."""
    lat = _f(r.get("e2e_response_seconds"))
    return (lat if lat is not None else math.inf,)


SORT_KEYS = {
    "intel": lambda r: (-( _f(r.get("intelligence_index")) or -math.inf),),
    "cost":  lambda r: ( _f(r.get("intelligence_index_cost_usd")) or math.inf,),
    "ctx":   lambda r: (-( _f(r.get("context_window_tokens")) or 0),),
    "tokens": lambda r: (_f(r.get("indexTokensTotal")) or math.inf,),
    "speed": _speed_key,
}


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


def _row_for_output(r: dict) -> dict:
    return {
        "slug": r.get("slug") or "",
        "name": r.get("name") or "",
        "creator": r.get("creator_name") or "-",
        "intel": _fmt_intel(r.get("intelligence_index")),
        "idx-run$": _fmt_cost(r.get("intelligence_index_cost_usd")),
        "idx-tok": _fmt_tokens(r.get("indexTokensTotal")),
        "in$/1m": _fmt_cost(r.get("price_1m_input_tokens")),
        "out$/1m": _fmt_cost(r.get("price_1m_output_tokens")),
        "ctx": r.get("context_window_tokens") or "-",
        "e2e_s": _fmt_secs(r.get("e2e_response_seconds")),
        "free": "y" if _is_true(r.get("openrouter_has_free")) else "",
        "openrouter": r.get("openrouter_slug") or "-",
    }


def _print_table(rows: list[dict]) -> None:
    cols = list(_row_for_output(rows[0] if rows else {}).keys())
    formatted = [_row_for_output(r) for r in rows]
    widths = {
        c: max(len(c), *(len(str(r[c])) for r in formatted)) if formatted else len(c)
        for c in cols
    }
    print("  ".join(f"{c:<{widths[c]}}" for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    for r in formatted:
        print("  ".join(f"{str(r[c]):<{widths[c]}}" for c in cols))


_JSON_ROUND = {
    "intelligence_index": 1,
    "intelligence_index_cost_usd": 2,
    "ttft_seconds": 1,
    "e2e_response_seconds": 1,
}

_JSON_INT = {
    "context_window_tokens",
    "display_order",
    "index_answer_tokens",
    "index_input_tokens",
    "index_output_tokens",
    "index_reasoning_tokens",
    "indexTokensTotal",
    "output_tokens",
    "representative_answer_tokens",
    "representative_input_tokens",
    "representative_output_tokens",
    "representative_query_count",
    "representative_reasoning_tokens",
}

_JSON_FLOAT = {
    "active_parameters_billions",
    "agentic_index",
    "aime",
    "aime25",
    "apex_agents",
    "briefcase_analytical_quality_elo",
    "briefcase_avg_turns_per_task",
    "briefcase_cost_answer_usd",
    "briefcase_cost_cache_read_usd",
    "briefcase_cost_cache_write_usd",
    "briefcase_cost_input_usd",
    "briefcase_cost_non_cache_input_usd",
    "briefcase_cost_output_usd",
    "briefcase_cost_reasoning_usd",
    "briefcase_cost_total_usd",
    "briefcase_elo",
    "briefcase_lower_95ci",
    "briefcase_normalized",
    "briefcase_presentation_elo",
    "briefcase_rubric_elo",
    "briefcase_rubric_pass_rate",
    "briefcase_total_tool_calls",
    "briefcase_total_tool_ms",
    "briefcase_upper_95ci",
    "cache_hit_discount_percent",
    "cache_hit_rate",
    "cache_hit_price",
    "cache_write_price",
    "canonical_answer_output_speed_median_tokens_per_second",
    "coding_index",
    "critpt",
    "estimated_intelligence_index",
    "estimated_intelligence_index_v4_1",
    "estimated_seconds_for_100_output_tokens_median",
    "fallback_price_cache_hit",
    "fallback_price_cache_write",
    "fallback_price_input",
    "fallback_price_output",
    "gdpval",
    "gdpval_normalized",
    "gdpval_v2",
    "gpqa",
    "hle",
    "humaneval",
    "ifbench",
    "index_compute",
    "index_answer_cost_per_task_usd",
    "index_answer_tokens_per_task",
    "index_cache_read_cost_per_task_usd",
    "index_cache_write_cost_per_task_usd",
    "index_cost_per_task_usd",
    "index_input_cost_per_task_usd",
    "index_output_cost_per_task_usd",
    "index_output_tokens_per_task",
    "index_reasoning_cost_per_task_usd",
    "index_reasoning_tokens_per_task",
    "intelligence_index_v4_1",
    "intelligence_index_input_cost_usd",
    "intelligence_index_output_cost_usd",
    "intelligence_index_per_m_output_tokens",
    "intelligence_index_reasoning_cost_usd",
    "intelligence_index_time_per_task_seconds",
    "inference_parameters_active_billions",
    "it_bench_sre",
    "lab_claimed_aime",
    "lab_claimed_gpqa",
    "lab_claimed_hle",
    "lab_claimed_humaneval",
    "lab_claimed_livecodebench",
    "lab_claimed_math_500",
    "lab_claimed_mmlu_pro",
    "lcr",
    "livecodebench",
    "math_500",
    "math_index",
    "mmlu_pro",
    "mmmu_pro",
    "multilingual_average",
    "multilingual_average_global_mmlu_lite",
    "multilingual_average_mgsm",
    "multilingual_average_mmlu",
    "omniscience",
    "openness_data_posttrain_access",
    "openness_data_posttrain_license",
    "openness_data_pretrain_access",
    "openness_data_pretrain_license",
    "openness_index",
    "openness_model_availability",
    "openness_model_transparency",
    "parameters_billions",
    "price_1m_blended_0_100_1",
    "price_1m_blended_0_1_1",
    "price_1m_blended_0_3_1",
    "price_1m_blended_100_1_1",
    "price_1m_blended_7_2_1",
    "price_1m_input_tokens",
    "price_1m_output_tokens",
    "price_per_1k_1mp_images",
    "prompt_100k_e2e_response_seconds",
    "prompt_100k_output_speed_tokens_per_second",
    "prompt_100k_ttfc_seconds",
    "prompt_100k_ttft_seconds",
    "prompt_long_e2e_response_seconds",
    "prompt_long_output_speed_tokens_per_second",
    "prompt_long_ttfc_seconds",
    "prompt_long_ttft_seconds",
    "prompt_medium_coding_e2e_response_seconds",
    "prompt_medium_coding_output_speed_tokens_per_second",
    "prompt_medium_coding_ttfc_seconds",
    "prompt_medium_coding_ttft_seconds",
    "prompt_medium_e2e_response_seconds",
    "prompt_medium_output_speed_tokens_per_second",
    "prompt_medium_ttfc_seconds",
    "prompt_medium_ttft_seconds",
    "prompt_vision_single_image_e2e_response_seconds",
    "prompt_vision_single_image_output_speed_tokens_per_second",
    "prompt_vision_single_image_ttfc_seconds",
    "prompt_vision_single_image_ttft_seconds",
    "output_speed_median_tokens_per_second",
    "output_speed_p05_tokens_per_second",
    "output_speed_p25_tokens_per_second",
    "output_speed_p75_tokens_per_second",
    "output_speed_p95_tokens_per_second",
    "scicode",
    "tau2",
    "tau_banking",
    "terminalbench_hard",
    "terminalbench_v2_1",
    "training_tokens_trillions",
    "ttfc_median_seconds",
    "ttfc_p05_seconds",
    "ttfc_p25_seconds",
    "ttfc_p75_seconds",
    "ttfc_p95_seconds",
    "ttfrc_median_seconds",
}

_JSON_BOOL = {
    "commercial_allowed",
    "deprecated",
    "deleted",
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
    "reasoning_pass_back_reasoning",
    "reasoning_starts_thinking_by_default",
    "reasoning_varied",
    "show_host_model_evals",
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


def _emit_models(rows: list[dict], as_json: bool) -> None:
    if as_json:
        out = []
        for r in rows:
            out.append({k: _typed(k, r.get(k)) for k in OUTPUT_FIELDS})
        json.dump(out, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        _print_table(rows)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_models(args) -> int:
    if args.cmd == "frontier":
        args.pareto = True
    if args.cmd == "free":
        args.free = True
    modalities = _parse_modalities(args.modality)
    rows = load_rows(
        modalities=modalities,
        free_only=args.free,
        min_cost=args.min_cost,
        max_cost=args.max_cost if args.max_cost is not None else math.inf,
        intel_min=args.intel_min,
        context_min=args.context_min,
        max_index_tokens=args.max_index_tokens,
        min_index_tokens=args.min_index_tokens,
        max_latency=args.max_latency,
        reasoning=args.reasoning,
        open_weights=args.open_weights,
    )
    rows = apply_pattern(rows, args.pattern)
    if args.pareto:
        rows = pareto_frontier(rows)
        rows.sort(key=SORT_KEYS["cost"])  # Pareto reads naturally cost-ascending
    else:
        rows.sort(key=SORT_KEYS[args.sort])
    if args.top is not None and args.top > 0:
        rows = rows[: args.top]
    if not rows:
        print("# no models match", file=sys.stderr)
        return 1
    _emit_models(rows, args.json)
    return 0


def cmd_show(args) -> int:
    rows = load_rows(modalities=set(), include_deprecated=True)
    r, candidates = resolve_model(rows, args.slug)
    if not r:
        _print_candidates(args.slug, candidates)
        return 1

    if args.json:
        json.dump(r, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    intel = _f(r["intelligence_index"])
    cost = _f(r["intelligence_index_cost_usd"])
    per_m = _f(r.get("intelligence_index_per_m_output_tokens"))
    print(f"{r['name']}")
    print(f"  slug:            {r['slug']}")
    print(f"  creator:         {r.get('creator_name') or '-'} ({r.get('creator_slug') or '-'})")
    print(f"  family:          {r.get('model_family_slug') or '-'}")
    print(f"  release:         {r.get('release_date') or '-'}")
    print(f"  knowledge cut:   {r.get('knowledge_cutoff_date') or '-'}")
    print(f"  deprecated:      {r.get('deprecated')}")
    print(f"  size class:      {r.get('size_class') or '-'}  "
          f"(params: {r.get('parameters_billions') or '-'}B, "
          f"active: {r.get('active_parameters_billions') or '-'}B)")
    print(f"  context window:  {r.get('context_window_tokens') or '-'}")
    print(f"  reasoning:       {r.get('reasoning_model')}")
    print(f"  open weights:    {r.get('is_open_weights')}")
    mods = [m for m, col in MODALITY_TO_COLUMN.items() if _is_true(r.get(col))]
    print(f"  input modality:  {'+'.join(mods) or '-'}")
    print()
    print(f"  intelligence index:   {_fmt_intel(intel)}")
    print(f"  cost to run index:    {_fmt_cost(cost)}  (idx-run$, not a per-call price)")
    print(f"  tokens to run index:  {_fmt_tokens(r.get('indexTokensTotal'))}")
    print(f"  index per 1M output:  {_fmt_cost(per_m)}")
    ttft = _f(r.get("ttft_seconds"))
    e2e = _f(r.get("e2e_response_seconds"))
    print(f"  response latency:     ttft {_fmt_secs(ttft)}s / end-to-end "
          f"{_fmt_secs(e2e)}s  (AA run; reasoning models include think time)")
    print()
    print(f"  pricing per 1M tokens:")
    print(f"    input:   {_fmt_cost(r.get('price_1m_input_tokens'))}")
    print(f"    output:  {_fmt_cost(r.get('price_1m_output_tokens'))}")
    print(f"    cached:  {_fmt_cost(r.get('cache_hit_price'))}")
    print()
    bench_keys = [
        ("gpqa", "GPQA Diamond"), ("hle", "HLE"), ("mmlu_pro", "MMLU-Pro"),
        ("mmmu_pro", "MMMU-Pro"), ("livecodebench", "LiveCodeBench"),
        ("math_500", "MATH-500"), ("aime", "AIME"), ("aime25", "AIME-25"),
        ("scicode", "SciCode"), ("humaneval", "HumanEval"),
        ("tau2", "tau2"), ("terminalbench_hard", "TerminalBench-hard"),
        ("ifbench", "IFBench"), ("coding_index", "[Coding Index]"),
        ("math_index", "[Math Index]"), ("agentic_index", "[Agentic Index]"),
    ]
    print(f"  benchmarks:")
    for k, label in bench_keys:
        v = _f(r.get(k))
        if v is not None:
            if v < 1 and "index" not in k:
                print(f"    {label:20s} {v*100:5.1f}%")
            else:
                print(f"    {label:20s} {v:5.1f}")
    if "openrouter_slug" in r:
        print()
        print(f"  OpenRouter:")
        print(f"    paid: {r.get('openrouter_slug') or '(no match found)'}")
        print(f"    free: {r.get('openrouter_free_slug') or '(not available)'}")
        if _is_true(r.get("openrouter_has_free")):
            print("          (:free is rate-limited promo, possibly different "
                  "quant; prototyping only)")
    return 0


def cmd_compare(args) -> int:
    rows = load_rows(modalities=set(), include_deprecated=True)
    picked = []
    seen = set()
    for query in args.models:
        r, candidates = resolve_model(rows, query)
        if not r:
            _print_candidates(query, candidates)
            return 1
        key = r.get("slug")
        if key not in seen:
            picked.append(r)
            seen.add(key)

    _emit_models(picked, args.json)
    return 0


def cmd_slug(args) -> int:
    rows = load_rows(modalities=set(), include_deprecated=True)
    r, candidates = resolve_model(rows, args.model, prefer_openrouter=True)
    if not r:
        _print_candidates(args.model, candidates)
        return 1

    payload = {
        "slug": r.get("slug") or "",
        "name": r.get("name") or "",
        "openrouter_slug": r.get("openrouter_slug") or None,
        "openrouter_free_slug": r.get("openrouter_free_slug") or None,
        "free_caveat": (
            ":free endpoints are rate-limited prototype options and can differ from the paid listing"
            if _is_true(r.get("openrouter_has_free"))
            else None
        ),
    }
    if args.json:
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return 0

    print(payload["name"])
    print(f"  slug:       {payload['slug']}")
    print(f"  openrouter: {payload['openrouter_slug'] or '(no match found)'}")
    free = payload["openrouter_free_slug"]
    print(f"  free:       {free or '(not available)'}")
    if free:
        print("              (:free is rate-limited; prototype only)")
    return 0


def cmd_data(args) -> int:
    if args.action == "status":
        p = _csv_path()
        if not p.exists():
            print("no data cached. run: python query.py data refresh",
                  file=sys.stderr)
            return 1
        age = _data_age_days() or 0
        print(f"data file:   {p}")
        print(f"data age:    {age:.1f} days")
        if age > STALE_AFTER_DAYS:
            print(
                f"WARN: data older than {STALE_AFTER_DAYS} days. "
                f"Run: python query.py data refresh",
                file=sys.stderr,
            )
        enriched = "yes" if p == ENRICHED_CSV else "no (run enrich.py)"
        print(f"openrouter:  {enriched}")
        rows = load_rows(modalities=set(), include_deprecated=True)
        print(f"model count: {len(rows)}")
        return 0
    if args.action == "refresh":
        _run_python("scrape.py", "--refresh")
        _run_python("enrich.py", "--refresh")
        return 0
    return 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--modality", default="text",
                   help="CSV of required input modalities (text,image,video,audio). "
                        "Default 'text'. Use 'any' or empty string to disable.")
    p.add_argument("--free", action="store_true",
                   help="Only include models with a :free OpenRouter variant.")
    p.add_argument("--intel-min", type=float, default=None,
                   help="Minimum intelligence_index.")
    p.add_argument("--max-cost", type=float, default=None,
                   help="Maximum idx-run$ (cost to run AA's index, USD).")
    p.add_argument("--min-cost", type=float, default=0.0,
                   help="Minimum idx-run$ (USD).")
    p.add_argument("--context-min", type=int, default=None,
                   help="Minimum context window in tokens.")
    p.add_argument("--max-index-tokens", type=float, default=None,
                   help="Maximum total tokens to run AA's Intelligence Index.")
    p.add_argument("--min-index-tokens", type=float, default=0.0,
                   help="Minimum total tokens to run AA's Intelligence Index.")
    p.add_argument("--max-latency", type=float, default=None,
                   help="Maximum end-to-end response latency in seconds "
                        "(AA's measured run). Drops models with no measurement.")
    p.add_argument("--reasoning", action=argparse.BooleanOptionalAction,
                   default=None,
                   help="Filter to reasoning (or --no-reasoning) models. "
                        "Default: no filter.")
    p.add_argument("--open-weights", action=argparse.BooleanOptionalAction,
                   default=None,
                   help="Filter to open-weights (or --no-open-weights) models. "
                        "Default: no filter.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Query current LLM intelligence/cost/capabilities data.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser(
        "models",
        aliases=["find", "list", "recommend", "frontier", "free"],
        help="Query / filter / rank models.",
    )
    sp.add_argument("pattern", nargs="?",
                    help="Optional substring; matched against name/slug/creator.")
    sp.add_argument("--top", type=int, default=20,
                    help="Max rows to return (default 20). 0 = unlimited.")
    sp.add_argument("--sort", choices=list(SORT_KEYS), default="intel",
                    help="Primary sort key: intel desc, cost asc, ctx desc, "
                         "speed asc, tokens asc.")
    sp.add_argument("--pareto", action="store_true",
                    help="Filter to cost-vs-intel Pareto frontier; ignores --sort.")
    sp.add_argument("--json", action="store_true",
                    help="Emit JSON array instead of a table.")
    _add_filter_args(sp)
    sp.set_defaults(func=cmd_models)

    sp = sub.add_parser("show", help="Full per-model profile (benchmarks, "
                                     "pricing, OR slugs, modalities).",
                        aliases=["info"])
    sp.add_argument("slug", help="Exact slug, or unambiguous name substring.")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("compare", help="Compare exact or fuzzy model names.")
    sp.add_argument("models", nargs="+",
                    help="Model slugs, names, or OpenRouter slugs. Quote names with spaces.")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_compare)

    sp = sub.add_parser("slug", help="Return OpenRouter paid and free slugs.")
    sp.add_argument("model", help="Exact slug, OpenRouter slug, or unambiguous name substring.")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_slug)

    sp = sub.add_parser("data", help="Data management (status, refresh).")
    sp.add_argument("action", choices=["status", "refresh"])
    sp.set_defaults(func=cmd_data)

    sp = sub.add_parser("status", help="Alias for: data status")
    sp.set_defaults(func=cmd_data, action="status")

    sp = sub.add_parser("refresh", help="Alias for: data refresh")
    sp.set_defaults(func=cmd_data, action="refresh")

    args = ap.parse_args()
    # `data refresh` is the only path that's allowed to run without cached data.
    if not (getattr(args, "action", None) == "refresh"):
        ensure_data()
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
