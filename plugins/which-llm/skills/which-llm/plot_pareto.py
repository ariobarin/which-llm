"""Plot the Intelligence vs. Cost Pareto frontier from scraped AA data.

  uv run python plot_pareto.py
  uv run python plot_pareto.py --max-cost 750 --near 3 --out artifacts/pareto.png

Conventions match the AA chart: y = Intelligence Index (linear),
x = cost to run the Intelligence Index in USD (log base 2). Models with
no published cost or intelligence are silently dropped.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter
from adjustText import adjust_text

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


def _float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _is_true(v) -> bool:
    return (v or "").strip().lower() == "true"


def load_rows(
    min_cost: float,
    max_cost: float,
    require_text: bool,
    require_image: bool,
    require_video: bool,
    require_audio: bool,
    free_only: bool,
) -> list[dict]:
    rows = []
    with CSV_PATH.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            intel = _float(r["intelligence_index"])
            cost = _float(r["intelligence_index_cost_usd"])
            if intel is None or cost is None or cost <= 0:
                continue
            if cost < min_cost or cost > max_cost:
                continue
            if _is_true(r.get("deprecated")):
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
            rows.append({**r, "_intel": intel, "_cost": cost})
    return rows


def pareto_front(rows: list[dict]) -> list[dict]:
    """Return rows on the cost-min / intelligence-max Pareto frontier.

    Sort by cost ascending (tiebreak: intelligence descending), then walk left
    to right keeping only points that strictly raise the running max intel.
    """
    sorted_rows = sorted(rows, key=lambda r: (r["_cost"], -r["_intel"]))
    front: list[dict] = []
    best_intel = -math.inf
    for r in sorted_rows:
        if r["_intel"] > best_intel:
            front.append(r)
            best_intel = r["_intel"]
    return front


def near_front(rows: list[dict], front: list[dict], gap_pct: float) -> list[dict]:
    """Rows within `gap_pct`% of the y-axis intelligence range below the frontier.

    The window is a fixed number of index points (gap_pct%% * y-range), so the
    bottom-left and top-right of the chart get the same vertical tolerance. The
    frontier is a non-decreasing step function over cost; at cost c the frontier
    value is the intelligence of the largest-cost frontier point with cost <= c.
    """
    if not rows:
        return []
    intel_values = [r["_intel"] for r in rows]
    y_range = max(intel_values) - min(intel_values)
    if y_range <= 0:
        return []
    gap_points = y_range * gap_pct / 100.0

    front_sorted = sorted(front, key=lambda r: r["_cost"])
    front_set = {r["slug"] for r in front}
    near: list[dict] = []
    for r in rows:
        if r["slug"] in front_set:
            continue
        # Frontier intel at this cost = last frontier point with cost <= r._cost.
        f_intel = -math.inf
        for fr in front_sorted:
            if fr["_cost"] <= r["_cost"]:
                f_intel = fr["_intel"]
            else:
                break
        if f_intel - r["_intel"] <= gap_points:
            near.append(r)
    return near


def color_for(creator: str) -> str:
    return CREATOR_COLORS.get(creator or "", DEFAULT_COLOR)


_EFFORT_RE = re.compile(
    r"\s*\((?:Adaptive\s+|Non-)?[Rr]easoning,\s*([A-Za-z]+)\s+Effort\)"
)
_BARE_REASON_RE = re.compile(r"\s*\((?:Adaptive\s+)?[Rr]easoning\)|\s*\(Non-[Rr]easoning\)")


def shorten(name: str) -> str:
    """Mirror AA's chart-label shortening: keep effort level, drop the rest."""
    s = _EFFORT_RE.sub(lambda m: f" ({m.group(1).lower()})", name)
    s = _BARE_REASON_RE.sub("", s)
    return s


def main() -> int:
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
    ap.add_argument("--out", default="artifacts/pareto.png", help="Output PNG path.")
    args = ap.parse_args()

    rows = load_rows(args.min_cost, args.max_cost,
                     args.text, args.image, args.video, args.audio, args.free_only)
    front = pareto_front(rows)
    near = near_front(rows, front, args.near)
    front_set = {r["slug"] for r in front}
    near_set = {r["slug"] for r in near}
    others = [r for r in rows if r["slug"] not in front_set and r["slug"] not in near_set]

    intel_values = [r["_intel"] for r in rows]
    y_range = max(intel_values) - min(intel_values) if intel_values else 0
    window_pts = y_range * args.near / 100.0
    modality_bits = [
        f"text={'on' if args.text else 'off'}",
        f"image={'on' if args.image else 'off'}",
        f"video={'on' if args.video else 'off'}",
        f"audio={'on' if args.audio else 'off'}",
    ]
    print(f"Modality filters: {', '.join(modality_bits)}")
    print(f"{len(rows)} models in ${args.min_cost:.0f} <= cost <= ${args.max_cost:.0f}")
    print(f"  y-range: {min(intel_values):.1f} -> {max(intel_values):.1f}  "
          f"(near window = {args.near:g}% = {window_pts:.2f} index pts)")
    print(f"  Pareto frontier: {len(front)} models")
    print(f"  Near-frontier: {len(near)} models")
    print(f"  Other (off-frontier): {len(others)} models")

    print("\n--- Pareto frontier (cheapest -> most expensive) ---")
    for r in sorted(front, key=lambda r: r["_cost"]):
        print(f"  ${r['_cost']:8.2f}  {r['_intel']:6.2f}  {r['name']}  [{r['creator_name']}]")

    print("\n--- Near-frontier ---")
    for r in sorted(near, key=lambda r: r["_cost"]):
        print(f"  ${r['_cost']:8.2f}  {r['_intel']:6.2f}  {r['name']}  [{r['creator_name']}]")

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
            r["_cost"], r["_intel"], free_mark + shorten(r["name"]),
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
    def fmt_usd(x, _pos):
        if x >= 1000:
            return f"${x/1000:.1f}k".replace(".0k", "k")
        return f"${x:.0f}"
    ax.xaxis.set_major_formatter(FuncFormatter(fmt_usd))

    ax.set_xlabel("Cost to Run Intelligence Index (USD, log base 2)", fontsize=11)
    ax.set_ylabel("Artificial Analysis Intelligence Index", fontsize=11)
    cost_range = (
        f"<= ${args.max_cost:.0f}"
        if args.min_cost <= 0
        else f"${args.min_cost:.0f}-${args.max_cost:.0f}"
    )
    ax.set_title(
        f"Intelligence vs. Cost Pareto Frontier  "
        f"(cost {cost_range}, near = within {args.near:g}% of y-range "
        f"= {window_pts:.1f} idx pts)",
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
