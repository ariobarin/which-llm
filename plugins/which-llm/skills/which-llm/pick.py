from __future__ import annotations

import argparse

import which_llm_core as core


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pick ranked LLMs from constraints.",
    )
    parser.add_argument("preset", nargs="?", default="best",
                        choices=sorted(core.PICK_PRESETS),
                        help="Selection preset.")
    parser.add_argument("--top", type=int, default=8,
                        help="Maximum rows. Use 0 for unlimited.")
    parser.add_argument("--sort", choices=sorted(core.SORT_KEYS),
                        help="Ranking key.")
    core.add_filter_args(parser)
    core.add_if_empty_arg(parser, default="nearest")
    core.add_output_args(parser)
    args = parser.parse_args()

    rows = core.load_filtered_rows(args, preset=args.preset)
    sort = core.sort_name(args, args.preset)
    rows = core.rank_rows(rows, sort)
    rows = core.limit_rows(rows, args.top)
    if not rows:
        if args.if_empty == "nearest":
            core.emit_empty_with_nearest(
                args,
                preset=args.preset,
                sort=sort,
                top=args.top,
                fmt=args.format,
            )
            return 0
        raise SystemExit("no models match")
    core.emit_rows(
        core.shortlist_rows(
            rows,
            include_free_slug=args.preset == "free" or args.free,
        ),
        args.format,
    )
    core.print_snapshot_footer(args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
