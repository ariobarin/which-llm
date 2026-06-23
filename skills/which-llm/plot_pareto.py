"""Plot the Intelligence vs. Cost Pareto frontier from scraped AA data.

  python plot_pareto.py
  python plot_pareto.py --max-cost 750 --near 3 --out artifacts/pareto.png

Conventions match the AA chart: y = Intelligence Index (linear),
x = effective cost to run the Intelligence Index in USD (log base 2).
Published AA cost is preferred. When it is missing, the plot falls back to
indexTokensTotal * price_1m_output_tokens / 1,000,000.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

_ART = Path(__file__).parent / "artifacts"
# Prefer the enriched CSV (with OpenRouter columns) when present.
CSV_PATH = _ART / "models_enriched.csv" if (_ART / "models_enriched.csv").exists() else _ART / "models.csv"

# Approximate creator colors mirroring the AA legend.
CREATOR_COLORS = {
    "OpenAI": "#000000",
    "Anthropic": "#8B4513",
    "Google": "#2E8B57",
    "DeepSeek": "#1F6FEB",
    "xAI": "#9370DB",
    "Mistral": "#FF8C00",
    "Alibaba": "#FF8C00",
    "Amazon": "#FF8C00",
    "Kimi": "#1A1A1A",
    "Moonshot": "#1A1A1A",
    "Moonshot AI": "#1A1A1A",
    "MiniMax": "#E91E63",
    "NVIDIA": "#76B900",
    "Xiaomi": "#FF8C00",
    "Meta": "#1877F2",
    "Microsoft": "#00A4EF",
    "Cohere": "#39CCCC",
    "01 AI": "#FF6F00",
    "Reka": "#7C3AED",
    "Databricks": "#FF3621",
    "Snowflake": "#29B5E8",
    "AI21 Labs": "#3B82F6",
    "Inflection": "#06B6D4",
    "Liquid AI": "#10B981",
    "Perplexity": "#20808D",
}
DEFAULT_COLOR = "#6B7280"
DEFAULT_X_FIELD = "effective_index_cost_usd"
DEFAULT_Y_FIELD = "intelligence_index"
FIELD_LABELS = {
    "effective_index_cost_usd": "Effective Cost to Run Intelligence Index (USD, log base 2)",
    "estimated_index_output_cost_usd": "Estimated Cost from Index Tokens and Output Price (USD, log base 2)",
    "intelligence_index_cost_usd": "Cost to Run Intelligence Index (USD, log base 2)",
    "intelligence_index": "Artificial Analysis Intelligence Index",
    "price_1m_input_tokens": "Input Price per 1M Tokens (USD, log scale)",
    "price_1m_output_tokens": "Output Price per 1M Tokens (USD, log scale)",
    "price_1m_blended_7_2_1": "Blended Price per 1M Tokens (USD, 7:2:1, log scale)",
    "coding_index": "Artificial Analysis Coding Index",
    "agentic_index": "Artificial Analysis Agentic Index",
    "ttft_seconds": "Time to First Token (seconds, log scale)",
    "e2e_response_seconds": "End to End Response Time (seconds, log scale)",
}


def _float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _is_true(v) -> bool:
    return (v or "").strip().lower() == "true"


def estimated_index_output_cost_usd(r: dict) -> float | None:
    tokens = _float(r.get("indexTokensTotal"))
    output_price = _float(r.get("price_1m_output_tokens"))
    if tokens is None or output_price is None or tokens <= 0 or output_price <= 0:
        return None
    return tokens * output_price / 1_000_000


def effective_index_cost_usd(r: dict) -> tuple[float | None, str | None]:
    published = _float(r.get("intelligence_index_cost_usd"))
    if published is not None and published > 0:
        return published, "published"
    estimated = estimated_index_output_cost_usd(r)
    if estimated is not None:
        return estimated, "estimated_output"
    return None, None


def metric_value(r: dict, field: str) -> tuple[float | None, str | None]:
    if field == "effective_index_cost_usd":
        return effective_index_cost_usd(r)
    if field == "estimated_index_output_cost_usd":
        return estimated_index_output_cost_usd(r), "estimated_output"
    return _float(r.get(field)), None


def load_rows(
    min_cost: float,
    max_cost: float,
    require_text: bool,
    require_image: bool,
    require_video: bool,
    require_audio: bool,
    free_only: bool,
    creators: list[str] | None = None,
    x_field: str = DEFAULT_X_FIELD,
    y_field: str = DEFAULT_Y_FIELD,
) -> list[dict]:
    rows = []
    creator_set = {c.strip().lower() for c in creators or [] if c.strip()}
    with CSV_PATH.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            y_value = _float(r.get(y_field))
            x_value, x_source = metric_value(r, x_field)
            if y_value is None or x_value is None or x_value <= 0:
                continue
            if x_value < min_cost or x_value > max_cost:
                continue
            if _is_true(r.get("deprecated")):
                continue
            if creator_set and (r.get("creator_name") or "").lower() not in creator_set:
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
            rows.append({**r, "_intel": y_value, "_cost": x_value,
                         "_cost_source": x_source or "field",
                         "_x": x_value, "_y": y_value})
    return rows


def pareto_front(rows: list[dict]) -> list[dict]:
    """Return rows on the x-min / y-max Pareto frontier.

    Sort by x ascending (tiebreak: y descending), then walk left to right
    keeping only points that strictly raise the running max y.
    """
    sorted_rows = sorted(rows, key=lambda r: (r["_x"], -r["_y"]))
    front: list[dict] = []
    best_y = -math.inf
    for r in sorted_rows:
        if r["_y"] > best_y:
            front.append(r)
            best_y = r["_y"]
    return front


def near_front(rows: list[dict], front: list[dict], gap_pct: float) -> list[dict]:
    """Rows within `gap_pct`% of the y-axis range below the frontier.

    The window is a fixed number of index points (gap_pct%% * y-range), so the
    bottom-left and top-right of the chart get the same vertical tolerance. The
    frontier is a non-decreasing step function over cost; at cost c the frontier
    value is the intelligence of the largest-cost frontier point with cost <= c.
    """
    if not rows:
        return []
    y_values = [r["_y"] for r in rows]
    y_range = max(y_values) - min(y_values)
    if y_range <= 0:
        return []
    gap_points = y_range * gap_pct / 100.0

    front_sorted = sorted(front, key=lambda r: r["_x"])
    front_set = {r["slug"] for r in front}
    near: list[dict] = []
    for r in rows:
        if r["slug"] in front_set:
            continue
        # Frontier y at this x = last frontier point with x <= r._x.
        f_y = -math.inf
        for fr in front_sorted:
            if fr["_x"] <= r["_x"]:
                f_y = fr["_y"]
            else:
                break
        if f_y - r["_y"] <= gap_points:
            near.append(r)
    return near


def color_for(creator: str) -> str:
    return CREATOR_COLORS.get(creator or "", DEFAULT_COLOR)


_EFFORT_RE = re.compile(r"\s*\((?:Adaptive\s+)?[Rr]easoning,\s*([A-Za-z]+)\s+Effort\)")
_BARE_REASON_RE = re.compile(r"\s*\((?:Adaptive\s+)?[Rr]easoning\)")
_NON_REASON_RE = re.compile(r"\s*\(Non-[Rr]easoning\)")


def shorten(name: str, slug: str = "") -> str:
    """Short chart labels while preserving reasoning variant disambiguation."""
    s = _EFFORT_RE.sub(lambda m: f" ({m.group(1).lower()})", name)
    s = _NON_REASON_RE.sub(" (non-reasoning)", s)
    s = _BARE_REASON_RE.sub("", s)
    if "non-reasoning" in slug and "(non-reasoning)" not in s.lower():
        s = f"{s} (non-reasoning)"
    return s


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").title())


def _load_plot_deps():
    try:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FixedLocator, FuncFormatter
        from adjustText import adjust_text
    except ImportError as exc:
        raise SystemExit(
            "plot_pareto.py needs optional plotting packages: "
            "matplotlib and adjustText. Install them, then rerun the same command."
        ) from exc
    return plt, FixedLocator, FuncFormatter, adjust_text


def main() -> int:
    plt, FixedLocator, FuncFormatter, adjust_text = _load_plot_deps()
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-cost", type=float, default=750.0,
                    help="Drop models with cost above this (USD).")
    ap.add_argument("--min-cost", type=float, default=0.0,
                    help="Drop models with cost below this (USD).")
    ap.add_argument("--near", type=float, default=15.0,
                    help="Near-frontier threshold as %% of the y-axis intelligence "
                         "range. E.g. 15 means a uniform window of 15%% of the "
                         "y-range below the frontier at every cost level.")
    ap.add_argument("--text", action=argparse.BooleanOptionalAction, default=True,
                    help="Require text input modality (default: True). Use --no-text to drop the filter.")
    ap.add_argument("--image", action="store_true", help="Require image input modality.")
    ap.add_argument("--video", action="store_true", help="Require video input modality.")
    ap.add_argument("--audio", action="store_true",
                    help="Require audio/speech input modality.")
    ap.add_argument("--free-only", action="store_true",
                    help="Only include models with a :free OpenRouter variant "
                         "(requires running enrich.py first).")
    ap.add_argument("--creator", action="append", default=[],
                    help="Only include this creator. Repeat for multiple creators.")
    ap.add_argument("--x-field", default=DEFAULT_X_FIELD,
                    help="CSV field to minimize on the x-axis.")
    ap.add_argument("--y-field", default=DEFAULT_Y_FIELD,
                    help="CSV field to maximize on the y-axis.")
    ap.add_argument("--out", default="artifacts/pareto.png", help="Output PNG path.")
    args = ap.parse_args()

    rows = load_rows(args.min_cost, args.max_cost,
                     args.text, args.image, args.video, args.audio, args.free_only,
                     args.creator, args.x_field, args.y_field)
    if not rows:
        raise SystemExit("No models matched the requested filters and metric fields.")
    front = pareto_front(rows)
    near = near_front(rows, front, args.near)
    front_set = {r["slug"] for r in front}
    near_set = {r["slug"] for r in near}
    others = [r for r in rows if r["slug"] not in front_set and r["slug"] not in near_set]

    y_values = [r["_y"] for r in rows]
    y_range = max(y_values) - min(y_values) if y_values else 0
    window_pts = y_range * args.near / 100.0
    modality_bits = [
        f"text={'on' if args.text else 'off'}",
        f"image={'on' if args.image else 'off'}",
        f"video={'on' if args.video else 'off'}",
        f"audio={'on' if args.audio else 'off'}",
    ]
    creator_desc = ", ".join(args.creator) if args.creator else "all creators"
    print(f"Modality filters: {', '.join(modality_bits)}")
    print(f"Creator filter: {creator_desc}")
    print(f"Metric fields: x={args.x_field}, y={args.y_field}")
    print(f"{len(rows)} models in {args.min_cost:.2f} <= x <= {args.max_cost:.2f}")
    print(f"  y-range: {min(y_values):.1f} -> {max(y_values):.1f}  "
          f"(near window = {args.near:g}% = {window_pts:.2f} y-axis pts)")
    print(f"  Pareto frontier: {len(front)} models")
    print(f"  Near-frontier: {len(near)} models")
    print(f"  Other (off-frontier): {len(others)} models")

    print("\n--- Pareto frontier (lowest x -> highest x) ---")
    for r in sorted(front, key=lambda r: r["_x"]):
        print(f"  {r['_x']:8.2f}  {r['_y']:6.2f}  {r['name']}  [{r['creator_name']}]")

    print("\n--- Near-frontier ---")
    for r in sorted(near, key=lambda r: r["_x"]):
        print(f"  {r['_x']:8.2f}  {r['_y']:6.2f}  {r['name']}  [{r['creator_name']}]")

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(20, 14))

    # Off-frontier in light gray.
    if others:
        ax.scatter(
            [r["_cost"] for r in others],
            [r["_intel"] for r in others],
            s=14, color="#D1D5DB", alpha=0.55, zorder=1, label="Off-frontier",
        )

    # Near-frontier: hollow circles colored by creator.
    for r in near:
        ax.scatter(r["_cost"], r["_intel"], s=70,
                   facecolors="none", edgecolors=color_for(r["creator_name"]),
                   linewidths=1.6, zorder=3)

    # Frontier dots: filled.
    for r in front:
        ax.scatter(r["_cost"], r["_intel"], s=95,
                   color=color_for(r["creator_name"]), edgecolors="white",
                   linewidths=0.9, zorder=4)

    # Frontier step line.
    front_sorted = sorted(front, key=lambda r: r["_cost"])
    fx = [r["_cost"] for r in front_sorted]
    fy = [r["_intel"] for r in front_sorted]
    ax.step(fx, fy, where="post", color="#16A34A", linewidth=2, alpha=0.7,
            zorder=2, label=f"Pareto frontier ({len(front)} models)")

    # Axes set BEFORE labels so adjust_text can use real display coords.
    # log2 X, linear Y. Tick at base-2 powers from min to max.
    ax.set_xscale("log", base=2)
    min_cost = min(r["_cost"] for r in rows)
    max_cost = max(r["_cost"] for r in rows)
    lo_exp = math.floor(math.log2(min_cost))
    hi_exp = math.ceil(math.log2(max_cost))
    ticks = [2 ** e for e in range(lo_exp, hi_exp + 1)]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    # Y padding for label headroom; X padding so right-edge labels fit.
    y_min = min(r["_intel"] for r in rows)
    y_max = max(r["_intel"] for r in rows)
    ax.set_ylim(y_min - 2, y_max + 5)
    ax.set_xlim(min_cost / 1.5, max_cost * 1.6)

    # Labels (only for frontier + near).
    texts = []
    for r in front + near:
        bold = r["slug"] in front_set
        free_mark = "* " if _is_true(r.get("openrouter_has_free")) else ""
        txt = ax.text(
            r["_cost"], r["_intel"], free_mark + shorten(r["name"], r["slug"]),
            fontsize=9 if bold else 7,
            fontweight="bold" if bold else "normal",
            color=color_for(r["creator_name"]),
            ha="left", va="bottom", zorder=5,
        )
        texts.append(txt)
    print("\nLaying out labels (adjustText, may take a few seconds)...")
    adjust_text(
        texts, ax=ax,
        expand_text=(1.3, 1.8), expand_points=(1.8, 2.4),
        force_text=(0.9, 1.4), force_points=(0.6, 1.0),
        lim=400,  # more iterations for the dense top-right cluster
        arrowprops=dict(arrowstyle="-", color="#9CA3AF", lw=0.5, alpha=0.7),
    )
    x_is_usd = "cost" in args.x_field or "price" in args.x_field

    def fmt_x(x, _pos):
        if not x_is_usd:
            return f"{x:g}"
        if x >= 1000:
            return f"${x/1000:.1f}k".replace(".0k", "k")
        return f"${x:.0f}"
    ax.xaxis.set_major_formatter(FuncFormatter(fmt_x))

    x_label = field_label(args.x_field)
    y_label = field_label(args.y_field)
    ax.set_xlabel(x_label, fontsize=11)
    ax.set_ylabel(y_label, fontsize=11)
    x_range = (
        f"<= {args.max_cost:.0f}"
        if args.min_cost <= 0
        else f"{args.min_cost:.0f}-{args.max_cost:.0f}"
    )
    ax.set_title(
        f"{y_label} vs. {x_label} Pareto Frontier  "
        f"(x {x_range}, near = within {args.near:g}% of y-range "
        f"= {window_pts:.1f} pts)",
        fontsize=13,
    )
    ax.grid(True, which="major", alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)

    # Note the free-marker convention if any free models are present.
    if any(_is_true(r.get("openrouter_has_free")) for r in front + near):
        ax.text(0.01, 0.98, "* = available free on OpenRouter",
                transform=ax.transAxes, fontsize=9, va="top",
                color="#16A34A", fontweight="bold")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
