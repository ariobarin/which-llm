from __future__ import annotations

import argparse
import math
from pathlib import Path

import plot_pareto
import which_llm_core as core


CREATOR_COLORS = plot_pareto.CREATOR_COLORS
DEFAULT_COLOR = plot_pareto.DEFAULT_COLOR


def _load_plot_deps():
    try:
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except ImportError as exc:
        raise SystemExit(
            "frontier.py needs matplotlib. Install the plot extra and rerun."
        ) from exc
    try:
        from adjustText import adjust_text
    except ImportError:
        adjust_text = None
    return plt, FuncFormatter, adjust_text


def _color(row: dict) -> str:
    return CREATOR_COLORS.get(row.get("creator_name") or "", DEFAULT_COLOR)


def _status_rows(rows: list[dict], front: list[dict], near: list[dict]) -> list[dict]:
    front_set = {row.get("slug") for row in front}
    near_set = {row.get("slug") for row in near}
    out = []
    for row in sorted(rows, key=lambda item: item["_x"]):
        status = "frontier" if row.get("slug") in front_set else "near" if row.get("slug") in near_set else "other"
        out.append({**row, "frontier_status": status})
    return out


def _unique_fields(fields: list[str]) -> list[str]:
    out = []
    for field in fields:
        if field not in out:
            out.append(field)
    return out


def _plot(rows: list[dict], front: list[dict], near: list[dict], *,
          x_field: str, y_field: str, x_dir: str, near_pct: float,
          chart_path: Path) -> None:
    plt, FuncFormatter, adjust_text = _load_plot_deps()
    front_set = {row.get("slug") for row in front}
    near_set = {row.get("slug") for row in near}
    other = [
        row for row in rows
        if row.get("slug") not in front_set and row.get("slug") not in near_set
    ]

    fig, ax = plt.subplots(figsize=(16, 10))
    if other:
        ax.scatter(
            [row["_x"] for row in other],
            [row["_y"] for row in other],
            s=14,
            color="#D1D5DB",
            alpha=0.55,
            label="Other",
            zorder=1,
        )
    for row in near:
        ax.scatter(
            row["_x"],
            row["_y"],
            s=55,
            facecolors="none",
            edgecolors=_color(row),
            linewidths=1.4,
            zorder=3,
        )
    for row in front:
        ax.scatter(
            row["_x"],
            row["_y"],
            s=85,
            color=_color(row),
            edgecolors="white",
            linewidths=0.9,
            zorder=4,
        )

    ordered_front = sorted(front, key=lambda row: row["_x"])
    ax.plot(
        [row["_x"] for row in ordered_front],
        [row["_y"] for row in ordered_front],
        color="#16A34A",
        linewidth=2,
        alpha=0.75,
        label=f"Pareto frontier ({len(front)} models)",
        zorder=2,
    )

    texts = []
    for row in front + near:
        label = plot_pareto.shorten(row.get("name") or row.get("slug") or "", row.get("slug") or "")
        text = ax.text(
            row["_x"],
            row["_y"],
            label,
            fontsize=9 if row.get("slug") in front_set else 7,
            fontweight="bold" if row.get("slug") in front_set else "normal",
            color=_color(row),
            ha="left",
            va="bottom",
            zorder=5,
        )
        texts.append(text)
    if adjust_text and texts:
        adjust_text(
            texts,
            ax=ax,
            expand_text=(1.2, 1.5),
            expand_points=(1.5, 1.8),
            force_text=(0.7, 1.0),
            force_points=(0.4, 0.7),
            lim=250,
        )

    ax.set_xscale("log", base=2)
    x_min = min(row["_x"] for row in rows)
    x_max = max(row["_x"] for row in rows)
    y_min = min(row["_y"] for row in rows)
    y_max = max(row["_y"] for row in rows)
    ax.set_xlim(x_min / 1.4, x_max * 1.4)
    ax.set_ylim(y_min - 2, y_max + 4)
    x_is_usd = "cost" in x_field or "price" in x_field

    def fmt_x(value, _pos):
        if not x_is_usd:
            if value >= 1_000_000:
                return f"{value / 1_000_000:g}M"
            if value >= 1_000:
                return f"{value / 1_000:g}K"
            return f"{value:g}"
        if value >= 1000:
            return f"${value / 1000:.1f}k".replace(".0k", "k")
        return f"${value:.0f}"

    ax.xaxis.set_major_formatter(FuncFormatter(fmt_x))
    x_goal = "maximize" if x_dir == "max" else "minimize"
    ax.set_xlabel(f"{core.field_label(x_field)} ({x_goal})", fontsize=11)
    ax.set_ylabel(core.field_label(y_field), fontsize=11)
    ax.set_title(
        f"{core.field_label(y_field)} vs. {core.field_label(x_field)} "
        f"(near = {near_pct:g}% of y range)",
        fontsize=13,
    )
    ax.grid(True, which="major", alpha=0.25)
    ax.legend(loc="lower right", fontsize=9)
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(chart_path, dpi=150)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an LLM tradeoff frontier chart plus data.",
    )
    parser.add_argument("preset", nargs="?", default="cost-intel",
                        choices=sorted(core.FRONTIER_PRESETS),
                        help="Metric frame preset.")
    parser.add_argument("--x-field", help="CSV metric on x-axis.")
    parser.add_argument("--y-field", help="CSV metric on y-axis.")
    parser.add_argument("--x-dir", choices=["min", "max"],
                        help="Whether lower or higher x values are better.")
    parser.add_argument("--min-x", type=float, default=0.0,
                        help="Minimum x value to include.")
    parser.add_argument("--max-x", type=float, default=math.inf,
                        help="Maximum x value to include.")
    parser.add_argument("--near", type=float, default=15.0,
                        help="Near-frontier threshold as percent of y range.")
    parser.add_argument("--out", help="Output PNG path.")
    parser.add_argument("--data-out", help="Output CSV path for plotted rows.")
    parser.add_argument("--out-dir", help="Output directory for default files.")
    core.add_filter_args(parser)
    args = parser.parse_args()

    preset = core.FRONTIER_PRESETS[args.preset]
    x_field = args.x_field or preset["x_field"]
    y_field = args.y_field or preset["y_field"]
    x_dir = args.x_dir or preset["x_dir"]
    rows = core.load_filtered_rows(args)
    rows = core.metric_rows(rows, x_field, y_field, args.min_x, args.max_x)
    if not rows:
        raise SystemExit("no models match frontier filters and metric fields")

    front = core.pareto_front(rows, x_dir)
    near = core.near_front(rows, front, args.near, x_dir)
    status_rows = _status_rows(rows, front, near)
    chart_path = Path(args.out) if args.out else core.default_artifact_path(
        f"frontier-{args.preset}",
        "png",
        args.out_dir,
    )
    data_path = Path(args.data_out) if args.data_out else chart_path.with_suffix(".csv")
    fields = _unique_fields([
        "frontier_status",
        "slug",
        "name",
        "creator_name",
        x_field,
        y_field,
        "intelligence_index",
        "intelligence_index_cost_usd",
        "indexTokensTotal",
        "context_window_tokens",
        "price_1m_input_tokens",
        "price_1m_output_tokens",
        "e2e_response_seconds",
        "openrouter_slug",
    ])
    _load_plot_deps()
    core.write_data_file(status_rows, data_path, "csv", fields)
    _plot(
        rows,
        front,
        near,
        x_field=x_field,
        y_field=y_field,
        x_dir=x_dir,
        near_pct=args.near,
        chart_path=chart_path,
    )

    print(f"chart_path: {chart_path}")
    print(f"data_path: {data_path}")
    print(f"models: {len(rows)}")
    print(f"frontier_rows: {len(front)}")
    print(f"near_frontier_rows: {len(near)}")
    print(f"x_metric: {x_field} ({'maximize' if x_dir == 'max' else 'minimize'})")
    print(f"y_metric: {y_field} (maximize)")
    core.print_snapshot_summary()
    print()
    print("Frontier:")
    display = [
        {
            "model": row.get("name") or "",
            "x": f"{row['_x']:g}",
            "y": f"{row['_y']:g}",
            "creator": row.get("creator_name") or "",
            "openrouter": row.get("openrouter_slug") or "-",
        }
        for row in sorted(front, key=lambda item: item["_x"])
    ]
    core.print_markdown_table(display)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
