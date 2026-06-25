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
    core.add_filter_args(parser)
    args = parser.parse_args()

    rows = core.load_filtered_rows(args, preset=args.preset)
    rows = core.rank_rows(rows, core.sort_name(args, args.preset))
    rows = core.limit_rows(rows, args.top)
    fields = core.selected_fields(rows, args.fields)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
