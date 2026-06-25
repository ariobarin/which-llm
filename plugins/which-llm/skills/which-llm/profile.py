from __future__ import annotations

import argparse
import json

import which_llm_core as core


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect one LLM profile.",
    )
    parser.add_argument("model", help="Model slug, name, or OpenRouter slug.")
    core.add_output_args(parser)
    args = parser.parse_args()

    row = core.resolve_one(args.model)
    if args.format == "json":
        print(json.dumps(core.json_record(row), indent=2, default=str))
        return 0
    print(core.profile_text(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
