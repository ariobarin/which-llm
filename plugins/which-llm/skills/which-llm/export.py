from __future__ import annotations

import argparse
from pathlib import Path

import which_llm_core as core


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export filtered LLM rows as CSV or JSON.",
    )
    parser.add_argument("preset", nargs="?", default="best",
                        choices=sorted(core.PICK_PRESETS),
                        help="Filter preset.")
    parser.add_argument("--sort", choices=sorted(core.SORT_KEYS),
                        help="Optional row ordering.")
    parser.add_argument("--top", type=int, default=0,
                        help="Maximum rows. Default 0 means unlimited.")
    parser.add_argument("--format", choices=["csv", "json"], default="csv")
    parser.add_argument("--out", help="Output file path.")
    parser.add_argument("--out-dir", help="Output directory for default file name.")
    core.add_fields_arg(parser)
    parser.add_argument("--columns",
                        help="Exact comma-separated output columns.")
    core.add_filter_args(parser)
    core.add_if_empty_arg(parser)
    args = parser.parse_args()

    rows = core.load_filtered_rows(args, preset=args.preset)
    sort = core.sort_name(args, args.preset)
    rows = core.rank_rows(rows, sort)
    rows = core.limit_rows(rows, args.top)
    if not rows:
        if args.if_empty == "nearest":
            if args.format == "json":
                core.emit_empty_with_nearest(
                    args,
                    preset=args.preset,
                    sort=sort,
                    top=args.top,
                    fmt="json",
                )
                core.print_cost_context()
                return 0
            print("path: (not written)")
            print(f"format: {args.format}")
            print("row_count: 0")
            print("relaxation_status: original filters matched 0 rows")
            core.print_snapshot_summary()
            print()
            core.emit_empty_with_nearest(
                args,
                preset=args.preset,
                sort=sort,
                top=args.top,
                fmt="markdown",
            )
            core.print_cost_context()
            return 0
        raise SystemExit("no models match")
    fields = (
        core.selected_columns(rows, args.columns)
        if args.columns
        else core.selected_fields(rows, args.fields)
    )
    suffix = "json" if args.format == "json" else "csv"
    path = Path(args.out) if args.out else core.default_artifact_path(
        "export",
        suffix,
        args.out_dir,
    )
    core.write_data_file(rows, path, args.format, fields)
    print(f"path: {path}")
    print(f"format: {args.format}")
    print(f"row_count: {len(rows)}")
    print(f"fields: {', '.join(fields)}")
    core.print_snapshot_summary()
    core.print_cost_context()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
