"""Compatibility CLI for Intelligence versus cost frontier charts."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import pareto_chart


_ART = Path(__file__).parent / "artifacts"
CSV_PATH = (
    _ART / "models_enriched.csv"
    if (_ART / "models_enriched.csv").exists()
    else _ART / "models.csv"
)
DEFAULT_X_FIELD = "intelligence_index_cost_per_task_usd"
DEFAULT_Y_FIELD = "intelligence_index"
FIELD_LABELS = {
    "intelligence_index_cost_usd": "Cost to Run Intelligence Index (USD, log base 2)",
    "intelligence_index_cost_per_task_usd": "Intelligence Cost per Task (USD, log scale)",
    "agentic_index_cost_per_task_usd": "Agentic Cost per Task (USD, log scale)",
    "intelligence_index": "Artificial Analysis Intelligence Index",
    "price_1m_input_tokens": "Input Price per 1M Tokens (USD, log scale)",
    "price_1m_output_tokens": "Output Price per 1M Tokens (USD, log scale)",
    "coding_index": "Artificial Analysis Coding Index",
    "agentic_index": "Artificial Analysis Agentic Index",
    "ttft_seconds": "Time to First Token (seconds, log scale)",
    "e2e_response_seconds": "End to End Response Time (seconds, log scale)",
}

shorten = pareto_chart.shorten


def format_axis_value(value: float, is_usd: bool) -> str:
    """Preserve the compatibility CLI's public tick formatting helper."""
    if not is_usd:
        return f"{value:g}"
    return pareto_chart.format_axis_value(value, True)


def _float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _is_true(value) -> bool:
    return (value or "").strip().lower() == "true"


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
    creator_set = {creator.strip().lower() for creator in creators or [] if creator.strip()}
    with CSV_PATH.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            y_value = _float(row.get(y_field))
            x_value = _float(row.get(x_field))
            if y_value is None or x_value is None or x_value <= 0:
                continue
            if x_value < min_cost or x_value > max_cost or _is_true(row.get("deprecated")):
                continue
            if creator_set and (row.get("creator_name") or "").lower() not in creator_set:
                continue
            requirements = (
                (require_text, "input_modality_text"),
                (require_image, "input_modality_image"),
                (require_video, "input_modality_video"),
                (require_audio, "input_modality_speech"),
                (free_only, "openrouter_has_free"),
            )
            if any(required and not _is_true(row.get(field)) for required, field in requirements):
                continue
            rows.append({**row, "_intel": y_value, "_cost": x_value,
                         "_x": x_value, "_y": y_value})
    return rows


def pareto_front(rows: list[dict]) -> list[dict]:
    """Return rows on the x-min and y-max Pareto frontier."""
    front: list[dict] = []
    best_y = -math.inf
    for row in sorted(rows, key=lambda item: (item["_x"], -item["_y"])):
        if row["_y"] > best_y:
            front.append(row)
            best_y = row["_y"]
    return front


def near_front(rows: list[dict], front: list[dict], gap_pct: float) -> list[dict]:
    """Return rows within a fixed share of the y range below the frontier."""
    if not rows:
        return []
    y_values = [row["_y"] for row in rows]
    y_range = max(y_values) - min(y_values)
    if y_range <= 0:
        return []
    gap_points = y_range * gap_pct / 100.0
    ordered_front = sorted(front, key=lambda row: row["_x"])
    front_slugs = {row["slug"] for row in front}
    near = []
    for row in rows:
        if row["slug"] in front_slugs:
            continue
        frontier_y = -math.inf
        for candidate in ordered_front:
            if candidate["_x"] > row["_x"]:
                break
            frontier_y = candidate["_y"]
        if frontier_y - row["_y"] <= gap_points:
            near.append(row)
    return near


def field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").title())


def validate_metric_pair(x_field: str, y_field: str) -> None:
    pairs = {
        "intelligence_index_cost_per_task_usd": "intelligence_index",
        "agentic_index_cost_per_task_usd": "agentic_index",
    }
    expected = pairs.get(x_field)
    if expected and y_field != expected:
        raise SystemExit(
            f"{x_field} cannot be paired with {y_field}; use --y-field {expected}"
        )


def _load_plot_deps():
    return pareto_chart._load_plot_deps()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-cost", type=float, default=750.0)
    parser.add_argument("--min-cost", type=float, default=0.0)
    parser.add_argument("--near", type=float, default=15.0)
    parser.add_argument("--text", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--image", action="store_true")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--audio", action="store_true")
    parser.add_argument("--free-only", action="store_true")
    parser.add_argument("--creator", action="append", default=[])
    parser.add_argument("--x-field", default=DEFAULT_X_FIELD)
    parser.add_argument("--y-field", default=DEFAULT_Y_FIELD)
    parser.add_argument("--out", default="artifacts/pareto.png")
    return parser


def main() -> int:
    _load_plot_deps()
    args = _parser().parse_args()
    validate_metric_pair(args.x_field, args.y_field)
    rows = load_rows(
        args.min_cost, args.max_cost, args.text, args.image, args.video,
        args.audio, args.free_only, args.creator, args.x_field, args.y_field,
    )
    if not rows:
        raise SystemExit("No models matched the requested filters and metric fields.")
    front = pareto_front(rows)
    near = near_front(rows, front, args.near)
    frontier_slugs = {row["slug"] for row in front}
    near_slugs = {row["slug"] for row in near}
    others = [
        row for row in rows
        if row["slug"] not in frontier_slugs and row["slug"] not in near_slugs
    ]

    y_values = [row["_y"] for row in rows]
    window_points = (max(y_values) - min(y_values)) * args.near / 100.0
    creator_desc = ", ".join(args.creator) if args.creator else "all creators"
    print(f"Creator filter: {creator_desc}")
    print(f"Metric fields: x={args.x_field}, y={args.y_field}")
    print(f"Pareto frontier: {len(front)} models")
    print(f"Near-frontier: {len(near)} models ({window_points:.2f} y-axis points)")
    print(f"Other: {len(others)} models")
    print("\n--- Pareto frontier (lowest x -> highest x) ---")
    for row in sorted(front, key=lambda item: item["_x"]):
        print(f"  {row['_x']:8.2f}  {row['_y']:6.2f}  {row['name']}")

    output = Path(args.out)
    pareto_chart.render_frontier_chart(
        rows, front, near,
        x_field=args.x_field,
        y_field=args.y_field,
        x_label=field_label(args.x_field),
        y_label=field_label(args.y_field),
        x_dir="min",
        near_pct=args.near,
        chart_path=output,
    )
    print(f"# cost context: {pareto_chart.metric_scope(args.x_field)}", file=sys.stderr)
    print(f"\nSaved {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
