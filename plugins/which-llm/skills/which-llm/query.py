"""Agent-facing CLI for LLM model selection queries.

  uv run python query.py models                                 # top 20 by intel
  uv run python query.py models claude                          # substring match
  uv run python query.py models --top 5 --max-cost 500 --modality text,image
  uv run python query.py models --pareto --max-cost 200         # Pareto frontier
  uv run python query.py models --free                          # OR-free models
  uv run python query.py show claude-opus-4-7                   # one model, full info
  uv run python query.py data status                            # data freshness
  uv run python query.py data refresh                           # re-scrape AA + OR

All `models` queries produce the same table schema (or pass `--json` for
machine output). `show` emits a multi-line profile by default, or JSON.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
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
    "intelligence_index_cost_usd", "context_window_tokens",
    "openrouter_has_free", "openrouter_slug", "openrouter_free_slug",
]

# Modality vocabulary — what the user types -> the CSV column name.
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
        subprocess.run(["uv", "run", "python", "scrape.py"], cwd=HERE, check=True)
        subprocess.run(["uv", "run", "python", "enrich.py"], cwd=HERE, check=True)


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
            if cost is not None and (cost < min_cost or cost > max_cost):
                continue
            if intel_min is not None and (_f(r.get("intelligence_index")) or -1) < intel_min:
                continue
            if context_min is not None and (_f(r.get("context_window_tokens")) or 0) < context_min:
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


SORT_KEYS = {
    "intel": lambda r: (-( _f(r.get("intelligence_index")) or -math.inf),),
    "cost":  lambda r: ( _f(r.get("intelligence_index_cost_usd")) or math.inf,),
    "ctx":   lambda r: (-( _f(r.get("context_window_tokens")) or 0),),
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


def _row_for_output(r: dict) -> dict:
    return {
        "slug": r.get("slug") or "",
        "name": r.get("name") or "",
        "creator": r.get("creator_name") or "-",
        "intel": _fmt_intel(r.get("intelligence_index")),
        "idx-run$": _fmt_cost(r.get("intelligence_index_cost_usd")),
        "ctx": r.get("context_window_tokens") or "-",
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
}


def _typed(k: str, v: str | None):
    """Parse CSV string to native type for JSON output, rounding where appropriate."""
    if v is None or v == "":
        return None
    if k in _JSON_ROUND:
        f = _f(v)
        return round(f, _JSON_ROUND[k]) if f is not None else None
    if k == "context_window_tokens":
        return int(float(v)) if v else None
    if k in ("openrouter_has_free",):
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
    modalities = _parse_modalities(args.modality)
    rows = load_rows(
        modalities=modalities,
        free_only=args.free,
        min_cost=args.min_cost,
        max_cost=args.max_cost if args.max_cost is not None else math.inf,
        intel_min=args.intel_min,
        context_min=args.context_min,
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
    by_slug = {r["slug"]: r for r in rows}
    r = by_slug.get(args.slug)
    if not r:
        pat = args.slug.lower()
        candidates = [
            x for x in rows
            if pat in (x.get("slug") or "").lower()
            or pat in (x.get("name") or "").lower()
        ]
        if len(candidates) == 1:
            r = candidates[0]
        elif candidates:
            print(f"# multiple matches for {args.slug!r}; specify slug:",
                  file=sys.stderr)
            for c in candidates[:10]:
                print(f"  {c['slug']:45s}  {c['name']}", file=sys.stderr)
            return 1
        else:
            print(f"# no model matching {args.slug!r}", file=sys.stderr)
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
    print(f"  per 1M output tokens: {_fmt_cost(per_m)}")
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


def cmd_data(args) -> int:
    if args.action == "status":
        p = _csv_path()
        if not p.exists():
            print("no data cached. run: uv run python query.py data refresh",
                  file=sys.stderr)
            return 1
        age = _data_age_days() or 0
        print(f"data file:   {p}")
        print(f"data age:    {age:.1f} days")
        if age > STALE_AFTER_DAYS:
            print(
                f"WARN: data older than {STALE_AFTER_DAYS} days. "
                f"Run: uv run python query.py data refresh",
                file=sys.stderr,
            )
        enriched = "yes" if p == ENRICHED_CSV else "no (run enrich.py)"
        print(f"openrouter:  {enriched}")
        rows = load_rows(modalities=set(), include_deprecated=True)
        print(f"model count: {len(rows)}")
        return 0
    if args.action == "refresh":
        subprocess.run(["uv", "run", "python", "scrape.py", "--refresh"],
                       cwd=HERE, check=True)
        subprocess.run(["uv", "run", "python", "enrich.py", "--refresh"],
                       cwd=HERE, check=True)
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

    sp = sub.add_parser("models", help="Query / filter / rank models.")
    sp.add_argument("pattern", nargs="?",
                    help="Optional substring; matched against name/slug/creator.")
    sp.add_argument("--top", type=int, default=20,
                    help="Max rows to return (default 20). 0 = unlimited.")
    sp.add_argument("--sort", choices=list(SORT_KEYS), default="intel",
                    help="Primary sort key (default intel-desc).")
    sp.add_argument("--pareto", action="store_true",
                    help="Filter to cost-vs-intel Pareto frontier; ignores --sort.")
    sp.add_argument("--json", action="store_true",
                    help="Emit JSON array instead of a table.")
    _add_filter_args(sp)
    sp.set_defaults(func=cmd_models)

    sp = sub.add_parser("show", help="Full per-model profile (benchmarks, "
                                     "pricing, OR slugs, modalities).")
    sp.add_argument("slug", help="Exact slug, or unambiguous name substring.")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("data", help="Data management (status, refresh).")
    sp.add_argument("action", choices=["status", "refresh"])
    sp.set_defaults(func=cmd_data)

    args = ap.parse_args()
    # `data refresh` is the only path that's allowed to run without cached data.
    if not (args.cmd == "data" and args.action == "refresh"):
        ensure_data()
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
