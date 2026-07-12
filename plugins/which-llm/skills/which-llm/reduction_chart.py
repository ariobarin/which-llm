"""Shared visual system for which-llm trade-off charts."""
from __future__ import annotations

import re
from pathlib import Path


CANVAS = "#F4F1EA"
INK = "#171A1F"
MUTED = "#6B7280"
GRID = "#D8D2C7"
OTHER = "#B8B3AA"
FRONTIER = "#0F766E"
NEAR = "#D97706"

_EFFORT_RE = re.compile(r"\s*\((?:Adaptive\s+)?[Rr]easoning,\s*([A-Za-z]+)\s+Effort\)")
_BARE_REASON_RE = re.compile(r"\s*\((?:Adaptive\s+)?[Rr]easoning\)")
_NON_REASON_RE = re.compile(r"\s*\(Non-[Rr]easoning\)")


def shorten(name: str, slug: str = "", limit: int = 34) -> str:
    """Keep variant identity while fitting compact point callouts."""
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
    if abs(value) < 10:
        return f"${value:.2f}".rstrip("0").rstrip(".")
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


def _callout_candidates(ax, row: dict) -> list[tuple[int, int]]:
    point_px = ax.transData.transform((row["_x"], row["_y"]))
    point_axes = ax.transAxes.inverted().transform(point_px)
    horizontal = -1 if point_axes[0] > 0.68 else 1
    vertical = -1 if point_axes[1] > 0.70 else 1
    return [
        (7 * horizontal, 9 * vertical),
        (7 * horizontal, -13 * vertical),
        (-7 * horizontal, 9 * vertical),
        (14 * horizontal, 22 * vertical),
        (14 * horizontal, -22 * vertical),
        (-14 * horizontal, 22 * vertical),
        (-14 * horizontal, -22 * vertical),
        (28 * horizontal, 0),
        (-28 * horizontal, 0),
    ]


def _annotate_points(fig, ax, selected: list[dict], *, x_is_usd: bool) -> None:
    placed = []
    for row in selected:
        label = shorten(
            row.get("name") or row.get("slug") or "",
            row.get("slug") or "",
            limit=26,
        )
        value = f"{format_axis_value(row['_x'], x_is_usd)} | {row['_y']:.1f}"
        for offset in _callout_candidates(ax, row):
            below = offset[1] < 0
            annotation = ax.annotate(
                f"{label}\n{value}",
                xy=(row["_x"], row["_y"]),
                xycoords="data",
                xytext=offset,
                textcoords="offset points",
                ha="right" if offset[0] < 0 else "left",
                va="top" if below else "bottom" if offset[1] > 0 else "center",
                fontsize=7.5,
                fontweight="bold",
                color=INK,
                linespacing=1.35,
                bbox={"boxstyle": "round,pad=0.35", "fc": CANVAS, "ec": GRID, "lw": 0.7},
                arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.6},
                zorder=6,
            )
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            bounds = annotation.get_bbox_patch().get_window_extent(renderer)
            padded = bounds.expanded(1.04, 1.14)
            inside = (
                ax.bbox.contains(padded.x0, padded.y0)
                and ax.bbox.contains(padded.x1, padded.y1)
            )
            if inside and not any(padded.overlaps(existing) for existing in placed):
                placed.append(padded)
                break
            annotation.remove()
        else:
            raise RuntimeError(f"could not place chart label for {row.get('slug')}")


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
    """Render a trade-off frontier with selected points annotated in the plot."""
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

    fig = plt.figure(figsize=(12.4, 7.2), facecolor=CANVAS)
    ax = fig.add_axes((0.08, 0.11, 0.88, 0.67))
    ax.set_facecolor(CANVAS)

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
    for row in selected:
        ax.scatter(
            [row["_x"]], [row["_y"]], s=104, color=FRONTIER,
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
        ax.set_xlim(-threshold * 0.3, x_max * 1.3)
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
    ax.set_xlabel(f"{x_label} ({'higher' if x_goal == 'maximize' else 'lower'} is better)")
    ax.set_ylabel(f"{y_label} (higher is better)")
    ax.grid(axis="y", color=GRID, linewidth=0.8, alpha=0.8)
    ax.grid(axis="x", color=GRID, linewidth=0.5, alpha=0.35)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("bottom", "left"):
        ax.spines[side].set_color(GRID)

    _annotate_points(fig, ax, selected, x_is_usd=x_is_usd)

    fig.text(0.08, 0.95, "WHICH LLM", color=FRONTIER, fontsize=9,
             fontweight="bold", ha="left")
    fig.text(0.08, 0.895, "Trade-off frontier", color=INK, fontsize=19,
             fontweight="bold", ha="left")
    fig.text(0.08, 0.845,
             f"{y_label} vs. {x_label}  |  {len(rows)} models  |  "
             f"{len(front)} frontier  |  {len(near)} near",
             color=MUTED, fontsize=9, ha="left")
    fig.text(0.08, 0.81, metric_scope(x_field), color=MUTED, fontsize=7.5,
             ha="left")

    chart_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(chart_path, dpi=170, facecolor=CANVAS)
    plt.close(fig)
