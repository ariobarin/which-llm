"""Shared visual system for which-llm Pareto charts."""
from __future__ import annotations

import re
from pathlib import Path


CANVAS = "#F4F1EA"
INK = "#171716"
MUTED = "#77736B"
GRID = "#D8D2C7"
OTHER = "#B8B3AA"
FRONTIER = "#0F766E"
NEAR = "#D97706"
ELBOW = "#E4624A"
CHART_TITLE = "Pareto frontier"

_EFFORT_RE = re.compile(
    r"\s*\((?:Adaptive\s+)?[Rr]easoning,\s*([A-Za-z]+)\s+Effort"
    r"(?:,\s*[^)]*Fallback)?\)"
)
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


def signal_rows(front: list[dict], limit: int | None = None) -> list[dict]:
    """Return every frontier row unless a caller explicitly requests a cap."""
    if not front or (limit is not None and limit <= 0):
        return []
    ordered = sorted(front, key=lambda row: row["_x"])
    if limit is None or limit >= len(ordered):
        return ordered
    count = min(limit, len(ordered))
    indexes = {
        round(index * (len(ordered) - 1) / max(1, count - 1))
        for index in range(count)
    }
    return [ordered[index] for index in sorted(indexes)]


def _scaled_points(rows: list[dict], point_transform=None) -> list[tuple[float, float]]:
    if not rows:
        return []
    if point_transform is None:
        xs = [float(row["_x"]) for row in rows]
        ys = [float(row["_y"]) for row in rows]
        if min(xs) > 0:
            import math
            xs = [math.log2(value) for value in xs]
    else:
        points = [point_transform((row["_x"], row["_y"])) for row in rows]
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
    x_span = max(xs) - min(xs) or 1.0
    y_span = max(ys) - min(ys) or 1.0
    return [
        ((x - min(xs)) / x_span, (y - min(ys)) / y_span)
        for x, y in zip(xs, ys)
    ]


def elbow_rows(
    front: list[dict], *, x_dir: str, limit: int = 2, point_transform=None,
) -> list[dict]:
    """Find the strongest local bends in normalized frontier geometry."""
    import math

    if limit <= 0 or len(front) < 3:
        return []
    ordered = sorted(front, key=lambda row: row["_x"], reverse=x_dir == "max")
    points = _scaled_points(ordered, point_transform)
    scored = []
    for index in range(1, len(points) - 1):
        before = (
            points[index][0] - points[index - 1][0],
            points[index][1] - points[index - 1][1],
        )
        after = (
            points[index + 1][0] - points[index][0],
            points[index + 1][1] - points[index][1],
        )
        before_length = math.hypot(*before)
        after_length = math.hypot(*after)
        if before_length == 0 or after_length == 0 or before[0] == 0 or after[0] == 0:
            continue
        cosine = (before[0] * after[0] + before[1] * after[1]) / (
            before_length * after_length
        )
        angle = math.acos(max(-1.0, min(1.0, cosine)))
        balance = min(before_length, after_length) / max(before_length, after_length)
        before_slope = before[1] / abs(before[0])
        after_slope = after[1] / abs(after[0])
        slope_drop = before_slope / max(after_slope, 1e-12)
        score = angle * balance ** 0.5 * max(0.0, math.log2(slope_drop))
        if angle >= math.radians(12) and slope_drop >= 1.5:
            scored.append((score, index, ordered[index]))

    selected = []
    for _score, index, row in sorted(scored, reverse=True):
        if any(abs(index - chosen_index) <= 1 for chosen_index, _row in selected):
            continue
        selected.append((index, row))
        if len(selected) == limit:
            break
    return [row for _index, row in sorted(selected)]


def near_signal_rows(
    near: list[dict], front: list[dict], limit: int = 6, point_transform=None,
) -> list[dict]:
    """Return the near-frontier rows closest to the normalized frontier path."""
    if limit <= 0 or not near or not front:
        return []
    combined = sorted(front, key=lambda row: row["_x"]) + near
    points = _scaled_points(combined, point_transform)
    front_points = points[:len(front)]
    near_points = points[len(front):]

    def segment_distance(point, start, end) -> float:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return ((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2) ** 0.5
        position = max(0.0, min(1.0, (
            (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
        ) / length_squared))
        closest = (start[0] + position * dx, start[1] + position * dy)
        return ((point[0] - closest[0]) ** 2 + (point[1] - closest[1]) ** 2) ** 0.5

    segments = list(zip(front_points, front_points[1:]))
    if not segments:
        segments = [(front_points[0], front_points[0])]
    ranked = sorted(
        zip(near, near_points),
        key=lambda item: min(
            segment_distance(item[1], start, end) for start, end in segments
        ),
    )
    return [row for row, _point in ranked[:limit]]


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
    return "This Pareto view is not a model recommendation."


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
    preferred = [
        (10, 8), (10, -10), (-10, 8), (-10, -10),
        (24, 18), (24, -18), (-24, 18), (-24, -18),
    ]
    expanded = []
    vertical_steps = [0]
    for distance in range(16, 161, 16):
        vertical_steps.extend([distance, -distance])
    for horizontal_distance in (38, 58, 82, 110, 142, 178):
        for vertical_distance in vertical_steps:
            expanded.extend([
                (horizontal_distance, vertical_distance),
                (-horizontal_distance, vertical_distance),
            ])
    candidates = [
        (x * horizontal, y * vertical) for x, y in preferred + expanded
    ]
    return list(dict.fromkeys(candidates))


def _placement_order(ax, rows: list[dict]) -> list[dict]:
    points = [ax.transData.transform((row["_x"], row["_y"])) for row in rows]
    if len(points) < 2:
        return rows
    density = []
    for index, point in enumerate(points):
        nearest = min(
            ((point[0] - other[0]) ** 2 + (point[1] - other[1]) ** 2) ** 0.5
            for other_index, other in enumerate(points) if other_index != index
        )
        density.append((nearest, index))
    return [rows[index] for _nearest, index in sorted(density)]


def _point_obstacles(
    fig,
    ax,
    rows: list[dict],
    *,
    elbow_slugs: set[str] | None = None,
) -> list:
    """Reserve visible clearance around important model markers."""
    from matplotlib.transforms import Bbox

    elbow_slugs = elbow_slugs or set()
    obstacles = []
    for row in rows:
        center_x, center_y = ax.transData.transform((row["_x"], row["_y"]))
        half_points = 8.5 if row.get("slug") in elbow_slugs else 6.5
        half_pixels = half_points * fig.dpi / 72
        obstacles.append(Bbox.from_extents(
            center_x - half_pixels,
            center_y - half_pixels,
            center_x + half_pixels,
            center_y + half_pixels,
        ))
    return obstacles


def _annotate_points(
    fig,
    ax,
    selected: list[dict],
    *,
    tier: str,
    elbow_slugs: set[str],
    placed: list,
) -> int:
    from matplotlib.text import Text

    placed_count = 0
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for row in _placement_order(ax, selected):
        label = shorten(
            row.get("name") or row.get("slug") or "",
            row.get("slug") or "",
            limit=30 if tier == "frontier" else 24,
        )
        is_elbow = row.get("slug") in elbow_slugs
        if is_elbow:
            label = f"{label}  elbow"
        for offset in _callout_candidates(ax, row):
            below = offset[1] < 0
            annotation = ax.annotate(
                label,
                xy=(row["_x"], row["_y"]),
                xycoords="data",
                xytext=offset,
                textcoords="offset points",
                ha="right" if offset[0] < 0 else "left",
                va="top" if below else "bottom" if offset[1] > 0 else "center",
                fontsize=7.4 if tier == "frontier" else 6.7,
                fontweight="normal",
                color=ELBOW if is_elbow else INK if tier == "frontier" else MUTED,
                bbox={"boxstyle": "square,pad=0.12", "fc": CANVAS, "ec": "none", "alpha": 0.9},
                arrowprops={
                    "arrowstyle": "-",
                    "color": ELBOW if is_elbow else GRID,
                    "lw": 0.7 if is_elbow else 0.5,
                },
                zorder=6,
            )
            annotation.update_positions(renderer)
            bounds = Text.get_window_extent(annotation, renderer)
            padded = bounds.expanded(1.05, 1.22)
            inside = (
                ax.bbox.contains(padded.x0, padded.y0)
                and ax.bbox.contains(padded.x1, padded.y1)
            )
            if inside and not any(padded.overlaps(existing) for existing in placed):
                placed.append(padded)
                placed_count += 1
                break
            annotation.remove()
        else:
            if tier == "frontier":
                raise RuntimeError(f"could not place chart label for {row.get('slug')}")
    return placed_count


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
    """Render a Pareto frontier with direct, collision-aware labels."""
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

    fig = plt.figure(figsize=(13.6, 8.0), facecolor=CANVAS)
    ax = fig.add_axes((0.08, 0.10, 0.89, 0.68))
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

    def point_transform(point):
        return ax.transAxes.inverted().transform(ax.transData.transform(point))

    elbows = elbow_rows(front, x_dir=x_dir, point_transform=point_transform)
    elbow_slugs = {row.get("slug") for row in elbows}
    near_selected = near_signal_rows(
        near, front, point_transform=point_transform,
    )
    if elbows:
        ax.scatter(
            [row["_x"] for row in elbows], [row["_y"] for row in elbows],
            s=146, facecolors="none", edgecolors=ELBOW,
            linewidths=1.7, zorder=5,
        )

    placed = _point_obstacles(
        fig, ax, front + near, elbow_slugs=elbow_slugs,
    )
    _annotate_points(
        fig, ax, selected,
        tier="frontier", elbow_slugs=elbow_slugs, placed=placed,
    )
    labeled_near = _annotate_points(
        fig, ax, near_selected,
        tier="near", elbow_slugs=elbow_slugs, placed=placed,
    )

    fig.text(0.08, 0.95, "WHICH LLM", color=FRONTIER, fontsize=9,
             fontweight="bold", ha="left")
    fig.text(0.08, 0.895, CHART_TITLE, color=INK, fontsize=21,
             fontfamily="DejaVu Serif", fontweight="normal", ha="left")
    fig.text(0.08, 0.845,
             f"{y_label} vs. {x_label}  |  {len(rows)} models  |  "
             f"{len(front)} frontier labeled  |  {labeled_near} closest near labeled",
             color=MUTED, fontsize=9, ha="left")
    fig.text(0.08, 0.81,
             f"{metric_scope(x_field)} Coral rings mark local efficiency elbows.",
             color=MUTED, fontsize=7.5,
             ha="left")

    chart_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(chart_path, dpi=170, facecolor=CANVAS)
    plt.close(fig)
