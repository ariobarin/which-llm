from __future__ import annotations

import argparse
import math
from pathlib import Path

import pareto_chart
import which_llm_core as core


def _load_plot_deps():
    return pareto_chart._load_plot_deps()


def _label_rows(front: list[dict], limit: int | None = None) -> list[dict]:
    return pareto_chart.signal_rows(front, limit)


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


def _format_axis_value(value: float, is_usd: bool) -> str:
    return pareto_chart.format_axis_value(value, is_usd)


def _plot(rows: list[dict], front: list[dict], near: list[dict], *,
          x_field: str, y_field: str, x_dir: str, near_pct: float,
          chart_path: Path) -> None:
    pareto_chart.render_frontier_chart(
        rows, front, near,
        x_field=x_field,
        y_field=y_field,
        x_label=core.field_label(x_field),
        y_label=core.field_label(y_field),
        x_dir=x_dir,
        near_pct=near_pct,
        chart_path=chart_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=f"Generate an LLM {pareto_chart.CHART_TITLE} chart plus data.",
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
    core.validate_metric_pair(x_field, y_field)
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
        "intelligence_index_cost_per_task_usd",
        "agentic_index_cost_per_task_usd",
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
    core.print_cost_context()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
