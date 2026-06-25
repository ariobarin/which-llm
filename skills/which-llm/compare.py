from __future__ import annotations

import argparse

import which_llm_core as core


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare named LLMs in one table.",
    )
    parser.add_argument("models", nargs="+",
                        help="Model slugs, names, or OpenRouter slugs.")
    core.add_output_args(parser)
    args = parser.parse_args()

    rows = core.resolve_many(args.models)
    core.emit_rows(core.comparison_rows(rows), args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
