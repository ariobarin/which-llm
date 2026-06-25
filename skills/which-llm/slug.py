from __future__ import annotations

import argparse
import json

import which_llm_core as core


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve one LLM to provider endpoint names.",
    )
    parser.add_argument("model", help="Model slug, name, or OpenRouter slug.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    row = core.resolve_one(args.model, prefer_openrouter=True)
    record = core.endpoint_record(row)
    if args.format == "json":
        print(json.dumps(record, indent=2, default=str))
        return 0
    print(record["model"])
    print(f"slug: {record['slug']}")
    print(f"openrouter_slug: {record['openrouter_slug'] or '(no match found)'}")
    print(f"openrouter_free_slug: {record['openrouter_free_slug'] or '(not available)'}")
    if record["caveat"]:
        print(f"caveat: {record['caveat']}")
    core.print_snapshot_footer("text")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
