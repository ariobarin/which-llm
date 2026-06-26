from __future__ import annotations

import argparse

import which_llm_core as core


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve natural model names to current model slugs.",
    )
    parser.add_argument("models", nargs="+",
                        help="Model names, shorthand, slugs, or OpenRouter slugs.")
    parser.add_argument("--mode", choices=["auto", "strict", "all"], default="auto",
                        help="auto selects the strongest match while listing alternates.")
    core.add_output_args(parser)
    args = parser.parse_args()

    rows = core.resolve_display_rows(args.models, mode=args.mode)
    core.emit_rows(rows, args.format)
    core.print_snapshot_footer(args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
