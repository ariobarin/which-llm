"""Agent-facing CLI for LLM model selection queries.

Subcommands all produce compact, structured output meant to be consumed by an
LLM agent without further parsing.

  uv run py query.py find claude          # find models by name/slug substring
  uv run py query.py info claude-opus-4-7 # full info for one model
  uv run py query.py list --limit 20      # top N by intelligence
  uv run py query.py frontier             # Pareto frontier (cost vs intel)
  uv run py query.py recommend --intel-min 50 --max-cost 2000 --image
  uv run py query.py free                 # OR-free models, sorted by intel
  uv run py query.py refresh              # re-scrape AA + cross-ref OR
  uv run py query.py status               # data freshness check
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
        subprocess.run(["uv", "run", "py", "scrape.py"], cwd=HERE, check=True)
        subprocess.run(["uv", "run", "py", "enrich.py"], cwd=HERE, check=True)


def load_rows(
    require_text: bool = True,
    require_image: bool = False,
    require_video: bool = False,
    require_audio: bool = False,
    free_only: bool = False,
    include_deprecated: bool = False,
    min_cost: float = 0.0,
    max_cost: float = math.inf,
) -> list[dict]:
    rows = []
    with _csv_path().open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not include_deprecated and _is_true(r.get("deprecated")):
                continue
            if require_text and not _is_true(r.get("input_modality_text")):
                continue
            if require_image and not _is_true(r.get("input_modality_image")):
                continue
            if require_video and not _is_true(r.get("input_modality_video")):
                continue
            if require_audio and not _is_true(r.get("input_modality_speech")):
                continue
            if free_only and not _is_true(r.get("openrouter_has_free")):
                continue
            cost = _f(r.get("intelligence_index_cost_usd"))
            if cost is not None:
                if cost < min_cost or cost > max_cost:
                    continue
            rows.append(r)
    return rows


def _fmt_cost(v) -> str:
    f = _f(v)
    if f is None:
        return "-"
    return f"${f:,.2f}" if f < 1000 else f"${f:,.0f}"


def _fmt_intel(v) -> str:
    f = _f(v)
    return f"{f:.1f}" if f is not None else "-"


def _fmt_modalities(r: dict) -> str:
    bits = []
    if _is_true(r.get("input_modality_text")):
        bits.append("text")
    if _is_true(r.get("input_modality_image")):
        bits.append("image")
    if _is_true(r.get("input_modality_video")):
        bits.append("video")
    if _is_true(r.get("input_modality_speech")):
        bits.append("audio")
    return "+".join(bits) or "-"


def _print_table(rows: list[dict], cols: list[tuple[str, str, int]]) -> None:
    """Print rows with given (column_key, header, width) layout.

    Width 0 means auto-size to the widest cell.
    """
    # Auto-size columns where width=0.
    sized: list[tuple[str, str, int]] = []
    for key, header, width in cols:
        if width == 0:
            w = max(len(header), max((len(str(r.get(key) or "")) for r in rows), default=0))
            sized.append((key, header, w))
        else:
            sized.append((key, header, width))
    header_line = "  ".join(f"{h:<{w}}" for _, h, w in sized)
    print(header_line)
    print("  ".join("-" * w for _, _, w in sized))
    for r in rows:
        line = "  ".join(f"{str(r.get(k) or '-'):<{w}}" for k, _, w in sized)
        print(line)


def _intel_sort_key(r: dict) -> float:
    return _f(r.get("intelligence_index")) or -1


def _cost_sort_key(r: dict) -> float:
    return _f(r.get("intelligence_index_cost_usd")) or math.inf


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_status(args) -> int:
    p = _csv_path()
    if not p.exists():
        print("no data cached. run: uv run py query.py refresh")
        return 1
    age = _data_age_days()
    print(f"data file:   {p}")
    print(f"data age:    {age:.1f} days")
    if age and age > STALE_AFTER_DAYS:
        print(f"WARN: data older than {STALE_AFTER_DAYS} days. "
              f"Run: uv run py query.py refresh")
    enriched = "yes" if p == ENRICHED_CSV else "no (run enrich.py)"
    print(f"openrouter:  {enriched}")
    rows = load_rows(require_text=False, include_deprecated=True)
    print(f"model count: {len(rows)}")
    return 0


def cmd_refresh(args) -> int:
    subprocess.run(["uv", "run", "py", "scrape.py", "--refresh"], cwd=HERE, check=True)
    subprocess.run(["uv", "run", "py", "enrich.py", "--refresh"], cwd=HERE, check=True)
    return 0


def cmd_find(args) -> int:
    rows = load_rows(require_text=False)
    pat = args.pattern.lower()
    matches = [
        r for r in rows
        if pat in (r.get("name") or "").lower()
        or pat in (r.get("slug") or "").lower()
        or pat in (r.get("creator_name") or "").lower()
    ]
    matches.sort(key=_intel_sort_key, reverse=True)
    if not matches:
        print(f"# no matches for '{args.pattern}'")
        return 1
    _print_table(
        [
            {
                "slug": r["slug"],
                "name": r["name"],
                "creator": r.get("creator_name") or "-",
                "intel": _fmt_intel(r.get("intelligence_index")),
                "cost": _fmt_cost(r.get("intelligence_index_cost_usd")),
            }
            for r in matches
        ],
        [("slug", "slug", 0), ("name", "name", 0), ("creator", "creator", 0),
         ("intel", "intel", 5), ("cost", "idx-run$", 10)],
    )
    print(f"\n# {len(matches)} matches")
    return 0


def cmd_info(args) -> int:
    rows = load_rows(require_text=False, include_deprecated=True)
    by_slug = {r["slug"]: r for r in rows}
    r = by_slug.get(args.slug)
    if not r:
        # try fuzzy by name
        pat = args.slug.lower()
        candidates = [x for x in rows if pat in (x["slug"] or "").lower() or pat in (x["name"] or "").lower()]
        if len(candidates) == 1:
            r = candidates[0]
        elif candidates:
            print(f"# multiple matches for '{args.slug}'; specify slug:")
            for c in candidates[:10]:
                print(f"  {c['slug']:45s}  {c['name']}")
            return 1
        else:
            print(f"# no model matching '{args.slug}'")
            return 1

    intel = _f(r["intelligence_index"])
    cost = _f(r["intelligence_index_cost_usd"])
    per_m = _f(r["intelligence_index_per_m_output_tokens"])
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
    print(f"  input modality:  {_fmt_modalities(r)}")
    print()
    print(f"  intelligence index:   {_fmt_intel(intel)}")
    print(f"  cost to run index:    {_fmt_cost(cost)}")
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
    return 0


def cmd_list(args) -> int:
    rows = load_rows(
        require_text=args.text, require_image=args.image,
        require_video=args.video, require_audio=args.audio,
        free_only=args.free, max_cost=args.max_cost or math.inf,
    )
    sort_key = _cost_sort_key if args.by_cost else _intel_sort_key
    rows.sort(key=sort_key, reverse=not args.by_cost)
    rows = rows[: args.limit]
    formatted = [
        {
            "slug": r["slug"],
            "name": r["name"],
            "creator": r.get("creator_name") or "-",
            "intel": _fmt_intel(r.get("intelligence_index")),
            "cost": _fmt_cost(r.get("intelligence_index_cost_usd")),
            "free": "y" if _is_true(r.get("openrouter_has_free")) else "",
            "or_slug": r.get("openrouter_slug") or "-",
        }
        for r in rows
    ]
    _print_table(
        formatted,
        [("slug", "slug", 0), ("name", "name", 0), ("creator", "creator", 0),
         ("intel", "intel", 5), ("cost", "idx-run$", 10), ("free", "free", 4),
         ("or_slug", "openrouter", 0)],
    )
    return 0


def cmd_frontier(args) -> int:
    rows = load_rows(
        require_text=args.text, require_image=args.image,
        require_video=args.video, require_audio=args.audio,
        free_only=args.free, min_cost=args.min_cost,
        max_cost=args.max_cost or math.inf,
    )
    valid = [r for r in rows
             if _f(r["intelligence_index"]) is not None
             and _f(r["intelligence_index_cost_usd"]) is not None
             and _f(r["intelligence_index_cost_usd"]) > 0]
    sorted_rows = sorted(valid, key=lambda r: (_cost_sort_key(r), -_intel_sort_key(r)))
    front: list[dict] = []
    best = -math.inf
    for r in sorted_rows:
        i = _f(r["intelligence_index"])
        if i > best:
            front.append(r)
            best = i
    formatted = [
        {
            "slug": r["slug"],
            "name": r["name"],
            "creator": r.get("creator_name") or "-",
            "intel": _fmt_intel(r["intelligence_index"]),
            "cost": _fmt_cost(r["intelligence_index_cost_usd"]),
            "free": "y" if _is_true(r.get("openrouter_has_free")) else "",
            "or_slug": r.get("openrouter_slug") or "-",
        }
        for r in front
    ]
    print(f"# Pareto frontier (cheapest -> most expensive), {len(front)} models")
    _print_table(
        formatted,
        [("slug", "slug", 0), ("name", "name", 0), ("creator", "creator", 0),
         ("intel", "intel", 5), ("cost", "idx-run$", 10), ("free", "free", 4),
         ("or_slug", "openrouter", 0)],
    )
    return 0


def cmd_recommend(args) -> int:
    rows = load_rows(
        require_text=args.text, require_image=args.image,
        require_video=args.video, require_audio=args.audio,
        free_only=args.free, max_cost=args.max_cost or math.inf,
    )
    if args.intel_min is not None:
        rows = [r for r in rows if (_f(r["intelligence_index"]) or 0) >= args.intel_min]
    if args.context_min is not None:
        rows = [r for r in rows if (_f(r.get("context_window_tokens")) or 0) >= args.context_min]
    if args.reasoning is not None:
        rows = [r for r in rows if _is_true(r.get("reasoning_model")) == args.reasoning]
    if args.open_weights:
        rows = [r for r in rows if _is_true(r.get("is_open_weights"))]
    # Recommend by cheapest cost-to-run-index, breaking ties by higher intel.
    rows.sort(key=lambda r: (_cost_sort_key(r), -_intel_sort_key(r)))
    rows = rows[: args.limit]
    if not rows:
        print("# no models match constraints")
        return 1
    formatted = [
        {
            "slug": r["slug"],
            "name": r["name"],
            "creator": r.get("creator_name") or "-",
            "intel": _fmt_intel(r.get("intelligence_index")),
            "cost": _fmt_cost(r.get("intelligence_index_cost_usd")),
            "ctx": r.get("context_window_tokens") or "-",
            "free": "y" if _is_true(r.get("openrouter_has_free")) else "",
            "or_slug": r.get("openrouter_slug") or "-",
        }
        for r in rows
    ]
    _print_table(
        formatted,
        [("slug", "slug", 0), ("name", "name", 0), ("creator", "creator", 0),
         ("intel", "intel", 5), ("cost", "idx-run$", 10), ("ctx", "ctx", 8),
         ("free", "free", 4), ("or_slug", "openrouter", 0)],
    )
    return 0


def cmd_free(args) -> int:
    rows = load_rows(require_text=args.text, free_only=True)
    rows.sort(key=_intel_sort_key, reverse=True)
    formatted = [
        {
            "or_slug": r.get("openrouter_free_slug") or "-",
            "intel": _fmt_intel(r["intelligence_index"]),
            "cost": _fmt_cost(r["intelligence_index_cost_usd"]),
            "name": r["name"],
            "creator": r.get("creator_name") or "-",
        }
        for r in rows
    ]
    _print_table(
        formatted,
        [("or_slug", "openrouter slug", 0), ("intel", "intel", 5),
         ("cost", "idx-run$", 10), ("name", "name", 0), ("creator", "creator", 0)],
    )
    print(f"\n# {len(rows)} free models on OpenRouter")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _add_modality_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--text", action=argparse.BooleanOptionalAction, default=True,
                   help="Require text input (default: on)")
    p.add_argument("--image", action="store_true", help="Require image input")
    p.add_argument("--video", action="store_true", help="Require video input")
    p.add_argument("--audio", action="store_true", help="Require audio input")
    p.add_argument("--free", action="store_true",
                   help="Only models with a :free OpenRouter variant")


def main() -> int:
    ap = argparse.ArgumentParser(description="Query LLM model intelligence / cost / OR data.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("status", help="Show data freshness and counts.")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("refresh", help="Re-scrape AA and re-cross-reference OR.")
    sp.set_defaults(func=cmd_refresh)

    sp = sub.add_parser("find", help="Find models by name/slug/creator substring.")
    sp.add_argument("pattern")
    sp.set_defaults(func=cmd_find)

    sp = sub.add_parser("info", help="Full info for one model (slug or fuzzy name).")
    sp.add_argument("slug")
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("list", help="Top-N models, sorted by intelligence or cost.")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--by-cost", action="store_true",
                    help="Sort cheapest-first instead of smartest-first.")
    sp.add_argument("--max-cost", type=float, default=None)
    _add_modality_args(sp)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("frontier", help="Intelligence vs. cost Pareto frontier.")
    sp.add_argument("--min-cost", type=float, default=0.0)
    sp.add_argument("--max-cost", type=float, default=None)
    _add_modality_args(sp)
    sp.set_defaults(func=cmd_frontier)

    sp = sub.add_parser("recommend", help="Find best model under constraints.")
    sp.add_argument("--intel-min", type=float, default=None,
                    help="Minimum intelligence_index.")
    sp.add_argument("--max-cost", type=float, default=None,
                    help="Maximum cost to run intelligence index (USD).")
    sp.add_argument("--context-min", type=int, default=None,
                    help="Minimum context window in tokens.")
    sp.add_argument("--reasoning", type=lambda x: x.lower() == "true",
                    default=None, metavar="true|false",
                    help="Filter reasoning vs non-reasoning models.")
    sp.add_argument("--open-weights", action="store_true",
                    help="Restrict to open-weights models.")
    sp.add_argument("--limit", type=int, default=10)
    _add_modality_args(sp)
    sp.set_defaults(func=cmd_recommend)

    sp = sub.add_parser("free", help="List models available free on OpenRouter.")
    sp.add_argument("--text", action=argparse.BooleanOptionalAction, default=True)
    sp.set_defaults(func=cmd_free)

    args = ap.parse_args()
    if args.cmd != "refresh":
        ensure_data()
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
