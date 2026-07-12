"""Reduction visual system for which-llm charts."""
from __future__ import annotations

import re
from pathlib import Path


CANVAS = "#F4F1EA"
PANEL = "#EAE6DD"
INK = "#171A1F"
MUTED = "#6B7280"
GRID = "#D8D2C7"
OTHER = "#B8B3AA"
FRONTIER = "#0F766E"
NEAR = "#D97706"
SIGNALS = ["#0F766E", "#4F46E5", "#C2410C", "#BE185D", "#0369A1"]

_EFFORT_RE = re.compile(r"\s*\((?:Adaptive\s+)?[Rr]easoning,\s*([A-Za-z]+)\s+Effort\)")
_BARE_REASON_RE = re.compile(r"\s*\((?:Adaptive\s+)?[Rr]easoning\)")
_NON_REASON_RE = re.compile(r"\s*\(Non-[Rr]easoning\)")


def shorten(name: str, slug: str = "", limit: int = 34) -> str:
    """Keep variant identity while fitting the fixed signal rail."""
    text = _EFFORT_RE.sub(lambda match: f" ({match.group(1).lower()})", name)
    text = _NON_REASON_RE.sub(" (non-reasoning)", text)
    text = _BARE_REASON_RE.sub("", text)
    if "non-reasoning" in slug and "(non-reasoning)" not in text.lower():
        text = f"{text} (non-reasoning)"
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def format_axis_value(value: float, is_usd: bool) -> str:
    if not is_usd:
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:g}B"
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:g}M"
        if abs(value) >= 1_000:
            return f"{value / 1_000:g}K"
        return f"{value:g}"
    if abs(value) >= 1000:
        return f"${value / 1000:.1f}k".replace(".0k", "k")
    if value == 0:
        return "$0"
    if 0 < abs(value) < 0.01:
        return f"${value:.3f}"
    if 0 < abs(value) < 1:
        return f"${value:.2f}"
    return f"${value:.0f}"


def signal_rows(front: list[dict], limit: int = 5) -> list[dict]:
    if limit <= 0 or not front:
        return []
    ordered = sorted(front, key=lambda row: row["_x"])
    count = min(limit, len(ordered))
    indexes = {
        round(index * (len(ordered) - 1) / max(1, count - 1))
        for index in range(count)
    }
    return [ordered[index] for index in sorted(indexes)]


def metric_scope(x_field: str) -> str:
    if x_field in {"price_1m_input_tokens", "price_1m_output_tokens"}:
        return "Token rate only. Workload volume is not modeled."
    if x_field in {
        "intelligence_index_cost_per_task_usd",
        "agentic_index_cost_per_task_usd",
    }:
        return "Benchmark-specific task cost. Not an application spend estimate."
    if x_field == "intelligence_index_cost_usd":
        return "Full benchmark-run cost. Not a per-call price."
    return "A tradeoff view, not a model recommendation."


def _load_plot_deps():
    try:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except ImportError as exc:
        raise SystemExit(
            "Chart generation needs matplotlib. Install the plot extra and rerun."
        ) from exc
    return plt, FuncFormatter


def render_frontier_chart(
    rows: list[dict],
    front: list[dict],
    near: list[dict],
    *,
    x_field: str,
    y_field: str,
    x_label: str,
    y_label: str,
    x_dir: str,
    near_pct: float,
    chart_path: Path,
) -> None:
    """Render a branded frontier with selected labels in a fixed side rail."""
    plt, FuncFormatter = _load_plot_deps()
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
    })
    front_slugs = {row.get("slug") for row in front}
    near_slugs = {row.get("slug") for row in near}
    other = [
        row for row in rows
        if row.get("slug") not in front_slugs and row.get("slug") not in near_slugs
    ]

    fig = plt.figure(figsize=(13.2, 7.4), facecolor=CANVAS)
    grid = fig.add_gridspec(
        1, 2, width_ratios=(4.7, 1.55),
        left=0.07, right=0.97, bottom=0.13, top=0.79, wspace=0.08,
    )
    ax = fig.add_subplot(grid[0, 0])
    rail = fig.add_subplot(grid[0, 1])
    ax.set_facecolor(CANVAS)
    rail.set_facecolor(PANEL)

    if other:
        ax.scatter(
            [row["_x"] for row in other], [row["_y"] for row in other],
            s=16, color=OTHER, alpha=0.52, linewidths=0, zorder=1,
        )
    if near:
        ax.scatter(
            [row["_x"] for row in near], [row["_y"] for row in near],
            s=40, facecolors="none", edgecolors=NEAR, alpha=0.72,
            linewidths=1.1, zorder=2,
        )
    if front:
        ax.scatter(
            [row["_x"] for row in front], [row["_y"] for row in front],
            s=58, color=FRONTIER, edgecolors=CANVAS, linewidths=1.0, zorder=4,
        )
        ordered = sorted(front, key=lambda row: row["_x"])
        ax.plot(
            [row["_x"] for row in ordered], [row["_y"] for row in ordered],
            color=FRONTIER, linewidth=1.8, alpha=0.72, zorder=3,
        )

    selected = signal_rows(front)
    for color, row in zip(SIGNALS, selected):
        ax.scatter(
            [row["_x"]], [row["_y"]], s=104, color=color,
            edgecolors=CANVAS, linewidths=1.8, zorder=5,
        )

    x_min = min(row["_x"] for row in rows)
    x_max = max(row["_x"] for row in rows)
    y_min = min(row["_y"] for row in rows)
    y_max = max(row["_y"] for row in rows)
    if x_min > 0:
        ax.set_xscale("log", base=2)
        ax.set_xlim(x_min / 1.35, x_max * 1.35)
    elif ("cost" in x_field or "price" in x_field) and x_max > 0:
        positives = [row["_x"] for row in rows if row["_x"] > 0]
        threshold = min(positives) / 2 if positives else 0.01
        ax.set_xscale("symlog", base=2, linthresh=threshold)
        ax.set_xlim(0, x_max * 1.3)
    else:
        padding = (x_max - x_min) * 0.05 or 1
        ax.set_xlim(x_min - padding, x_max + padding)
    y_padding = (y_max - y_min) * 0.08 or 1
    ax.set_ylim(y_min - y_padding, y_max + y_padding)
    x_is_usd = "cost" in x_field or "price" in x_field
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda value, _position: format_axis_value(value, x_is_usd))
    )
    x_goal = "maximize" if x_dir == "max" else "minimize"
    ax.set_xlabel(f"{x_label} / objective: {x_goal}")
    ax.set_ylabel(f"{y_label} / higher is up")
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
    ax.grid(axis="x", color=GRID, linewidth=0.5, alpha=0.35)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("bottom", "left"):
        ax.spines[side].set_color(GRID)

    rail.set_xticks([])
    rail.set_yticks([])
    for spine in rail.spines.values():
        spine.set_visible(False)
    rail.text(0.08, 0.94, "FRONTIER SIGNALS", color=INK, fontsize=9,
              fontweight="bold", transform=rail.transAxes)
    rail.text(0.08, 0.895, f"{len(front)} frontier / {len(near)} near",
              color=MUTED, fontsize=8, transform=rail.transAxes)
    y_positions = [0.76, 0.62, 0.48, 0.34, 0.20]
    for color, row, y_pos in zip(SIGNALS, selected, y_positions):
        rail.scatter([0.10], [y_pos], s=74, color=color, edgecolors=CANVAS,
                     linewidths=1.2, transform=rail.transAxes, clip_on=False)
        rail.text(
            0.18, y_pos + 0.025,
            shorten(row.get("name") or row.get("slug") or "", row.get("slug") or ""),
            color=INK, fontsize=8.5, fontweight="bold", va="center",
            transform=rail.transAxes,
        )
        rail.text(
            0.18, y_pos - 0.035,
            f"{format_axis_value(row['_x'], x_is_usd)}  /  {row['_y']:.1f}",
            color=MUTED, fontsize=8, va="center", transform=rail.transAxes,
        )
    rail.text(0.08, 0.075, metric_scope(x_field), color=MUTED, fontsize=7.5,
              va="bottom", wrap=True, transform=rail.transAxes)

    fig.text(0.07, 0.945, "WHICH LLM", color=FRONTIER, fontsize=10,
             fontweight="bold", ha="left")
    fig.text(0.07, 0.895, f"{y_label} / {x_label}", color=INK, fontsize=19,
             fontweight="bold", ha="left")
    fig.text(0.07, 0.848,
             f"Reduction frontier  |  {len(rows)} models  |  near = {near_pct:g}%",
             color=MUTED, fontsize=9, ha="left")
    fig.text(0.07, 0.045,
             "Artificial Analysis + OpenRouter  |  evidence for comparison, not a decision",
             color=MUTED, fontsize=7.5, ha="left")

    chart_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(chart_path, dpi=170, facecolor=CANVAS)
    plt.close(fig)
