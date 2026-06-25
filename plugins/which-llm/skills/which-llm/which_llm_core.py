from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import query


HERE = Path(__file__).parent
EXPORT_DIR = HERE / "artifacts" / "exports"


PICK_PRESETS = {
    "best": {"sort": "intel"},
    "cheap-good": {"intel_min": 50, "sort": "cost"},
    "fast-good": {"intel_min": 30, "sort": "speed"},
    "vision": {"modalities": {"text", "image"}, "sort": "intel"},
    "long-context": {"context_min": 256000, "sort": "intel"},
    "open-weights": {"open_weights": True, "sort": "intel"},
    "free": {"free_only": True, "sort": "cost"},
    "coding": {"sort": "coding"},
}

FRONTIER_PRESETS = {
    "cost-intel": {
        "x_field": "intelligence_index_cost_usd",
        "y_field": "intelligence_index",
        "x_dir": "min",
    },
    "speed-intel": {
        "x_field": "e2e_response_seconds",
        "y_field": "intelligence_index",
        "x_dir": "min",
    },
    "tokens-intel": {
        "x_field": "indexTokensTotal",
        "y_field": "intelligence_index",
        "x_dir": "min",
    },
    "context-intel": {
        "x_field": "context_window_tokens",
        "y_field": "intelligence_index",
        "x_dir": "max",
    },
    "input-price-intel": {
        "x_field": "price_1m_input_tokens",
        "y_field": "intelligence_index",
        "x_dir": "min",
    },
    "output-price-intel": {
        "x_field": "price_1m_output_tokens",
        "y_field": "intelligence_index",
        "x_dir": "min",
    },
}

FIELD_LABELS = {
    "intelligence_index_cost_usd": "Index cost USD",
    "intelligence_index": "Intelligence index",
    "indexTokensTotal": "Index tokens",
    "context_window_tokens": "Context tokens",
    "price_1m_input_tokens": "Input USD per 1M",
    "price_1m_output_tokens": "Output USD per 1M",
    "e2e_response_seconds": "End to end seconds",
    "ttft_seconds": "TTFT seconds",
    "coding_index": "Coding index",
    "agentic_index": "Agentic index",
}

FIELD_GROUPS = {
    "core": [
        "slug",
        "name",
        "creator_name",
        "intelligence_index",
        "intelligence_index_cost_usd",
        "indexTokensTotal",
        "context_window_tokens",
        "price_1m_input_tokens",
        "price_1m_output_tokens",
        "e2e_response_seconds",
        "openrouter_slug",
    ],
    "pricing": [
        "slug",
        "name",
        "creator_name",
        "intelligence_index_cost_usd",
        "indexTokensTotal",
        "price_1m_input_tokens",
        "price_1m_output_tokens",
        "cache_hit_price",
        "openrouter_slug",
        "openrouter_free_slug",
    ],
    "benchmarks": [
        "slug",
        "name",
        "creator_name",
        "intelligence_index",
        "coding_index",
        "agentic_index",
        "math_index",
        "gpqa",
        "hle",
        "mmlu_pro",
        "livecodebench",
        "aime",
        "terminalbench_hard",
    ],
    "slugs": [
        "slug",
        "name",
        "creator_name",
        "openrouter_slug",
        "openrouter_free_slug",
        "openrouter_has_free",
    ],
}

SORT_KEYS = {
    "intel": lambda r: (-(query._f(r.get("intelligence_index")) or -math.inf),),
    "cost": lambda r: (query._f(r.get("intelligence_index_cost_usd")) or math.inf,),
    "ctx": lambda r: (-(query._f(r.get("context_window_tokens")) or 0),),
    "tokens": lambda r: (query._f(r.get("indexTokensTotal")) or math.inf,),
    "speed": lambda r: (query._f(r.get("e2e_response_seconds")) or math.inf,),
    "coding": lambda r: (-(query._f(r.get("coding_index")) or -math.inf),),
    "agentic": lambda r: (-(query._f(r.get("agentic_index")) or -math.inf),),
    "input-price": lambda r: (query._f(r.get("price_1m_input_tokens")) or math.inf,),
    "output-price": lambda r: (query._f(r.get("price_1m_output_tokens")) or math.inf,),
}


def ensure_snapshot(warn_stale: bool = True) -> None:
    query.ensure_data()
    if not warn_stale:
        return
    age = query._data_age_days()
    if age is not None and age > query.STALE_AFTER_DAYS:
        print(
            f"# WARN: snapshot is {age:.1f} days old; use query.py data refresh "
            "only when current freshness is required.",
            file=sys.stderr,
        )


def add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--pattern", help="Substring matched against name, slug, or creator.")
    p.add_argument("--creator", action="append", default=[],
                   help="Creator filter. Repeat for multiple creators.")
    p.add_argument("--free", action="store_true",
                   help="Only include models with an OpenRouter free variant.")
    p.add_argument("--min-intel", "--intel-min", dest="intel_min", type=float,
                   help="Minimum intelligence_index.")
    p.add_argument("--max-cost", type=float,
                   help="Maximum idx-run$ benchmark-run cost.")
    p.add_argument("--min-cost", type=float, default=0.0,
                   help="Minimum idx-run$ benchmark-run cost.")
    p.add_argument("--min-context", "--context-min", dest="context_min", type=int,
                   help="Minimum context window in tokens.")
    p.add_argument("--max-index-tokens", type=float,
                   help="Maximum total tokens to run AA's Intelligence Index.")
    p.add_argument("--min-index-tokens", type=float, default=0.0,
                   help="Minimum total tokens to run AA's Intelligence Index.")
    p.add_argument("--max-latency", type=float,
                   help="Maximum end to end response latency in seconds.")
    p.add_argument("--reasoning", action=argparse.BooleanOptionalAction,
                   default=None, help="Filter reasoning models.")
    p.add_argument("--open-weights", action=argparse.BooleanOptionalAction,
                   default=None, help="Filter open-weight models.")
    p.add_argument("--modality",
                   help="CSV of required modalities: text,image,video,audio.")
    p.add_argument("--text", action=argparse.BooleanOptionalAction, default=None,
                   help="Require or drop text input modality.")
    p.add_argument("--image", action="store_true", help="Require image input.")
    p.add_argument("--video", action="store_true", help="Require video input.")
    p.add_argument("--audio", action="store_true", help="Require audio input.")


def add_output_args(p: argparse.ArgumentParser, *, default_format: str = "markdown") -> None:
    p.add_argument("--format", choices=["markdown", "json"], default=default_format)


def add_fields_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--fields", choices=["core", "pricing", "benchmarks", "slugs", "full"],
                   default="core")


def _preset_cfg(preset: str | None) -> dict:
    if not preset:
        return {}
    return PICK_PRESETS.get(preset, {})


def modalities_from_args(args, preset_modalities: set[str] | None = None) -> set[str]:
    if getattr(args, "modality", None):
        return query._parse_modalities(args.modality)
    modalities = set(preset_modalities or {"text"})
    if getattr(args, "text", None) is True:
        modalities.add("text")
    if getattr(args, "text", None) is False:
        modalities.discard("text")
    if getattr(args, "image", False):
        modalities.add("image")
    if getattr(args, "video", False):
        modalities.add("video")
    if getattr(args, "audio", False):
        modalities.add("audio")
    return modalities


def load_filtered_rows(args, *, preset: str | None = None,
                       include_deprecated: bool = False) -> list[dict]:
    ensure_snapshot()
    cfg = _preset_cfg(preset)
    modalities = modalities_from_args(args, cfg.get("modalities"))
    max_cost = getattr(args, "max_cost", None)
    rows = query.load_rows(
        modalities=modalities,
        free_only=getattr(args, "free", False) or cfg.get("free_only", False),
        include_deprecated=include_deprecated,
        min_cost=getattr(args, "min_cost", 0.0),
        max_cost=max_cost if max_cost is not None else math.inf,
        intel_min=getattr(args, "intel_min", None) if getattr(args, "intel_min", None) is not None
        else cfg.get("intel_min"),
        context_min=getattr(args, "context_min", None) if getattr(args, "context_min", None) is not None
        else cfg.get("context_min"),
        max_index_tokens=getattr(args, "max_index_tokens", None),
        min_index_tokens=getattr(args, "min_index_tokens", 0.0),
        max_latency=getattr(args, "max_latency", None),
        reasoning=getattr(args, "reasoning", None) if getattr(args, "reasoning", None) is not None
        else cfg.get("reasoning"),
        open_weights=getattr(args, "open_weights", None) if getattr(args, "open_weights", None) is not None
        else cfg.get("open_weights"),
    )
    creators = {
        creator.strip().lower()
        for creator in getattr(args, "creator", [])
        if creator and creator.strip()
    }
    if creators:
        rows = [
            row for row in rows
            if (row.get("creator_name") or "").strip().lower() in creators
        ]
    rows = query.apply_pattern(rows, getattr(args, "pattern", None))
    return rows


def sort_name(args, preset: str | None = None) -> str:
    cfg = _preset_cfg(preset)
    return getattr(args, "sort", None) or cfg.get("sort", "intel")


def rank_rows(rows: list[dict], sort: str) -> list[dict]:
    if sort not in SORT_KEYS:
        raise SystemExit(f"unknown sort {sort!r}; valid: {', '.join(SORT_KEYS)}")
    return sorted(rows, key=SORT_KEYS[sort])


def limit_rows(rows: list[dict], top: int | None) -> list[dict]:
    if top is not None and top > 0:
        return rows[:top]
    return rows


def resolve_one(model: str, *, prefer_openrouter: bool = False) -> dict:
    ensure_snapshot()
    rows = query.load_rows(modalities=set(), include_deprecated=True)
    row, candidates = query.resolve_model(
        rows,
        model,
        prefer_openrouter=prefer_openrouter,
    )
    if row:
        return row
    query._print_candidates(model, candidates)
    raise SystemExit(1)


def resolve_many(models: list[str]) -> list[dict]:
    ensure_snapshot()
    rows = query.load_rows(modalities=set(), include_deprecated=True)
    picked = []
    seen = set()
    for model in models:
        row, candidates = query.resolve_model(rows, model)
        if not row:
            query._print_candidates(model, candidates)
            raise SystemExit(1)
        key = row.get("slug")
        if key not in seen:
            picked.append(row)
            seen.add(key)
    return picked


def _display_value(row: dict, key: str):
    if key == "rank":
        return row.get("_rank", "")
    if key == "model":
        return row.get("name") or ""
    if key == "creator":
        return row.get("creator_name") or ""
    if key == "intelligence":
        return query._fmt_intel(row.get("intelligence_index"))
    if key == "idx_run_usd":
        return query._fmt_cost(row.get("intelligence_index_cost_usd"))
    if key == "idx_tokens":
        return query._fmt_tokens(row.get("indexTokensTotal"))
    if key == "input_usd_1m":
        return query._fmt_cost(row.get("price_1m_input_tokens"))
    if key == "output_usd_1m":
        return query._fmt_cost(row.get("price_1m_output_tokens"))
    if key == "context":
        return query._fmt_tokens(row.get("context_window_tokens"))
    if key == "e2e_s":
        return query._fmt_secs(row.get("e2e_response_seconds"))
    if key == "free":
        return "yes" if query._is_true(row.get("openrouter_has_free")) else ""
    if key == "modalities":
        return "+".join(
            name for name, col in query.MODALITY_TO_COLUMN.items()
            if query._is_true(row.get(col))
        ) or "-"
    if key == "reasoning":
        return "yes" if query._is_true(row.get("reasoning_model")) else ""
    if key == "open_weights":
        return "yes" if query._is_true(row.get("is_open_weights")) else ""
    return row.get(key) or ""


def shortlist_rows(rows: list[dict], *, include_rank: bool = True) -> list[dict]:
    fields = [
        ("rank", "rank"),
        ("model", "model"),
        ("slug", "slug"),
        ("creator", "creator"),
        ("intelligence", "intel"),
        ("idx_run_usd", "idx-run$"),
        ("idx_tokens", "idx-tok"),
        ("input_usd_1m", "in$/1m"),
        ("output_usd_1m", "out$/1m"),
        ("context", "ctx"),
        ("e2e_s", "e2e_s"),
        ("openrouter_slug", "openrouter"),
    ]
    out = []
    for idx, row in enumerate(rows, start=1):
        item = dict(row)
        item["_rank"] = idx if include_rank else ""
        out.append({label: _display_value(item, key) for key, label in fields})
    return out


def comparison_rows(rows: list[dict]) -> list[dict]:
    fields = [
        ("model", "model"),
        ("slug", "slug"),
        ("creator", "creator"),
        ("intelligence", "intel"),
        ("idx_run_usd", "idx-run$"),
        ("idx_tokens", "idx-tok"),
        ("input_usd_1m", "in$/1m"),
        ("output_usd_1m", "out$/1m"),
        ("context", "ctx"),
        ("e2e_s", "e2e_s"),
        ("modalities", "modalities"),
        ("reasoning", "reasoning"),
        ("openrouter_slug", "openrouter"),
    ]
    return [
        {label: _display_value(row, key) for key, label in fields}
        for row in rows
    ]


def endpoint_record(row: dict) -> dict:
    free = row.get("openrouter_free_slug") or None
    return {
        "model": row.get("name") or "",
        "slug": row.get("slug") or "",
        "openrouter_slug": row.get("openrouter_slug") or None,
        "openrouter_free_slug": free,
        "caveat": (
            "free endpoints are prototype options and can differ from paid listings"
            if free
            else None
        ),
    }


def print_markdown_table(rows: list[dict]) -> None:
    if not rows:
        print("_No rows._")
        return
    cols = list(rows[0].keys())
    print("| " + " | ".join(cols) + " |")
    print("| " + " | ".join("---" for _ in cols) + " |")
    for row in rows:
        values = [
            str(row.get(col, "")).replace("|", "\\|")
            for col in cols
        ]
        print("| " + " | ".join(values) + " |")


def emit_rows(rows: list[dict], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(rows, indent=2, default=str))
        return
    print_markdown_table(rows)


def profile_text(row: dict) -> str:
    bench_keys = [
        ("gpqa", "GPQA Diamond"),
        ("hle", "HLE"),
        ("mmlu_pro", "MMLU-Pro"),
        ("mmmu_pro", "MMMU-Pro"),
        ("livecodebench", "LiveCodeBench"),
        ("math_500", "MATH-500"),
        ("aime", "AIME"),
        ("aime25", "AIME-25"),
        ("scicode", "SciCode"),
        ("humaneval", "HumanEval"),
        ("tau2", "tau2"),
        ("terminalbench_hard", "TerminalBench-hard"),
        ("ifbench", "IFBench"),
        ("coding_index", "Coding Index"),
        ("math_index", "Math Index"),
        ("agentic_index", "Agentic Index"),
    ]
    modalities = _display_value(row, "modalities")
    lines = [
        f"# {row.get('name') or row.get('slug')}",
        "",
        f"- slug: {row.get('slug') or '-'}",
        f"- creator: {row.get('creator_name') or '-'} ({row.get('creator_slug') or '-'})",
        f"- family: {row.get('model_family_slug') or '-'}",
        f"- release: {row.get('release_date') or '-'}",
        f"- knowledge cutoff: {row.get('knowledge_cutoff_date') or '-'}",
        f"- deprecated: {row.get('deprecated')}",
        f"- context: {_display_value(row, 'context')}",
        f"- modalities: {modalities}",
        f"- reasoning: {_display_value(row, 'reasoning') or 'no'}",
        f"- open weights: {_display_value(row, 'open_weights') or 'no'}",
        "",
        "## Quality",
        "",
        f"- intelligence index: {_display_value(row, 'intelligence')}",
        f"- idx-run$: {_display_value(row, 'idx_run_usd')} (benchmark-run proxy, not per-call price)",
        f"- idx-tok: {_display_value(row, 'idx_tokens')}",
        f"- index per 1M output: {query._fmt_cost(row.get('intelligence_index_per_m_output_tokens'))}",
        "",
        "## Price And Speed",
        "",
        f"- input price: {query._fmt_cost(row.get('price_1m_input_tokens'))} per 1M tokens",
        f"- output price: {query._fmt_cost(row.get('price_1m_output_tokens'))} per 1M tokens",
        f"- cached price: {query._fmt_cost(row.get('cache_hit_price'))} per 1M tokens",
        f"- ttft: {query._fmt_secs(row.get('ttft_seconds'))}s",
        f"- end to end: {query._fmt_secs(row.get('e2e_response_seconds'))}s",
        "",
        "## OpenRouter",
        "",
        f"- production: {row.get('openrouter_slug') or '(no match found)'}",
        f"- free: {row.get('openrouter_free_slug') or '(not available)'}",
    ]
    if query._is_true(row.get("openrouter_has_free")):
        lines.append("- free caveat: prototype only, rate limits and serving details can differ")
    lines.extend(["", "## Benchmarks", ""])
    for key, label in bench_keys:
        value = query._f(row.get(key))
        if value is None:
            continue
        rendered = f"{value * 100:.1f}%" if value < 1 and "index" not in key else f"{value:.1f}"
        lines.append(f"- {label}: {rendered}")
    return "\n".join(lines)


def json_record(row: dict, fields: list[str] | None = None) -> dict:
    keys = fields or list(row.keys())
    return {key: query._typed(key, row.get(key)) for key in keys if key in row}


def selected_fields(rows: list[dict], group: str) -> list[str]:
    if group == "full":
        seen = []
        for row in rows:
            for key in row.keys():
                if key not in seen and not key.startswith("_"):
                    seen.append(key)
        return seen
    return FIELD_GROUPS[group]


def write_data_file(rows: list[dict], path: Path, fmt: str, fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        payload = [json_record(row, fields) for row in rows]
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        return path
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def default_artifact_path(kind: str, suffix: str, out_dir: str | None) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = Path(out_dir) if out_dir else EXPORT_DIR
    return base / f"which-llm-{kind}-{stamp}.{suffix}"


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").title())


def _metric_value(row: dict, field: str) -> float | None:
    value = query._f(row.get(field))
    if value is None or value <= 0:
        return None
    return value


def metric_rows(rows: list[dict], x_field: str, y_field: str,
                min_x: float, max_x: float) -> list[dict]:
    out = []
    for row in rows:
        x_value = _metric_value(row, x_field)
        y_value = query._f(row.get(y_field))
        if x_value is None or y_value is None:
            continue
        if x_value < min_x or x_value > max_x:
            continue
        out.append({**row, "_x": x_value, "_y": y_value})
    return out


def pareto_front(rows: list[dict], x_dir: str) -> list[dict]:
    if x_dir == "max":
        sorted_rows = sorted(rows, key=lambda row: (-row["_x"], -row["_y"]))
    else:
        sorted_rows = sorted(rows, key=lambda row: (row["_x"], -row["_y"]))
    front = []
    best_y = -math.inf
    for row in sorted_rows:
        if row["_y"] > best_y:
            front.append(row)
            best_y = row["_y"]
    return sorted(front, key=lambda row: row["_x"])


def near_front(rows: list[dict], front: list[dict], gap_pct: float,
               x_dir: str) -> list[dict]:
    if not rows:
        return []
    y_values = [row["_y"] for row in rows]
    y_range = max(y_values) - min(y_values)
    if y_range <= 0:
        return []
    gap_points = y_range * gap_pct / 100.0
    front_set = {row.get("slug") for row in front}
    near = []
    ordered_front = sorted(front, key=lambda row: row["_x"], reverse=(x_dir == "max"))
    for row in rows:
        if row.get("slug") in front_set:
            continue
        frontier_y = -math.inf
        for item in ordered_front:
            if x_dir == "min" and item["_x"] <= row["_x"]:
                frontier_y = item["_y"]
            elif x_dir == "max" and item["_x"] >= row["_x"]:
                frontier_y = item["_y"]
            else:
                break
        if frontier_y - row["_y"] <= gap_points:
            near.append(row)
    return sorted(near, key=lambda row: row["_x"])
