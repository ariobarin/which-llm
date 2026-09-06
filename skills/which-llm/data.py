"""Inspect the shared AA datasets and fetch published snapshots without dependencies."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ART = Path(__file__).parent / "artifacts"
DATA_PATH = ART / "aa_data.json"
STALE_AFTER_DAYS = 2
PUBLISHED_ROOTS = [
    "https://raw.githubusercontent.com/ariobarin/which-llm/automation/daily-data-refresh/skills/which-llm/artifacts/",
    "https://raw.githubusercontent.com/ariobarin/which-llm/main/skills/which-llm/artifacts/",
]


def age_days(stamp: str | None) -> float:
    if not stamp:
        return math.inf
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return math.inf
        age = (datetime.now(timezone.utc) - parsed).total_seconds() / 86400
        return age if age >= -1 / 24 else math.inf
    except (ValueError, TypeError):
        return math.inf


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_csv(content: str) -> None:
    rows = list(csv.DictReader(io.StringIO(content)))
    if len(rows) < 400 or not {"slug", "name", "intelligence_index", "openrouter_slug"} <= rows[0].keys():
        raise ValueError("incomplete model snapshot")
    slugs = [row["slug"] for row in rows]
    if not all(slugs) or len(set(slugs)) != len(rows):
        raise ValueError("missing or duplicate model slugs")
    stamps = {row.get("snapshot_updated_at_utc") for row in rows}
    if len(stamps) != 1 or age_days(next(iter(stamps))) > STALE_AFTER_DAYS:
        raise ValueError("published model snapshot is stale or undated")
    if not any(row.get("intelligence_index") for row in rows):
        raise ValueError("published model snapshot has no intelligence scores")


def read_bundle(path: Path) -> dict:
    return parse_bundle(path.read_text(encoding="utf-8"))


def parse_bundle(content: str) -> dict:
    value = json.loads(content)
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("datasets"), dict):
        raise ValueError("unsupported AA dataset snapshot")
    for name, dataset in value["datasets"].items():
        if not isinstance(dataset, dict) or not isinstance(dataset.get("rows"), list):
            raise ValueError(f"invalid {name} dataset")
        if not all(isinstance(row, dict) for row in dataset["rows"]):
            raise ValueError(f"invalid {name} rows")
    return value


def refresh_file(path: Path, validate) -> None:
    errors = []
    for root in PUBLISHED_ROOTS:
        try:
            request = urllib.request.Request(root + path.name, headers={"User-Agent": "which-llm/0.5"})
            with urllib.request.urlopen(request, timeout=20) as response:
                content = response.read().decode("utf-8")
            validate(content)
            atomic_write(path, content)
            return
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    raise RuntimeError("Could not fetch a current published snapshot: " + "; ".join(errors))


def dataset_is_fresh(bundle: dict, name: str) -> bool:
    dataset = bundle["datasets"].get(name, {})
    return bool(dataset.get("rows")) and age_days(dataset.get("source_updated_at_utc")) <= STALE_AFTER_DAYS


def load_bundle(name: str = "catalog") -> dict:
    try:
        bundle = read_bundle(DATA_PATH)
    except (OSError, ValueError):
        bundle = {"datasets": {}}
    if dataset_is_fresh(bundle, name):
        return bundle

    def validate(content):
        candidate = parse_bundle(content)
        if not dataset_is_fresh(candidate, name):
            raise ValueError(f"{name} is missing, stale, or undated")

    try:
        print(f"# Fetching current AA data for {name}...", file=sys.stderr)
        refresh_file(DATA_PATH, validate)
    except RuntimeError as exc:
        raise SystemExit(f"{exc}. Cached data was preserved. Maintainers can run: python query.py data refresh") from exc
    return read_bundle(DATA_PATH)


def nested(row: dict, path: str):
    for key in path.split("."):
        if not isinstance(row, dict):
            return None
        row = row.get(key)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?", help="Omit to list datasets, row counts, and source dates.")
    parser.add_argument("--model", help="Substring in model name, slug, or coding-agent label.")
    parser.add_argument("--fields", help="Comma-separated fields; nested paths such as mean.costUsd work.")
    parser.add_argument("--sort", help="Numeric field or nested path. Missing values are excluded.")
    parser.add_argument("--ascending", action="store_true", help="Lower is better. Default sort is descending.")
    parser.add_argument("--top", type=int, default=10, help="Maximum rows; 0 means all.")
    args = parser.parse_args()
    if args.top < 0:
        parser.error("--top must be nonnegative")
    # A typo must not cause a download when a current local catalog can list valid names.
    bundle = load_bundle()
    if not args.dataset:
        for name, error in bundle.get("refresh_errors", {}).items():
            print(f"# {name} refresh failed: {error}", file=sys.stderr)
        print(json.dumps({name: {**{k: v for k, v in table.items() if k != "rows"},
                                 "row_count": len(table["rows"]),
                                 "fresh": dataset_is_fresh(bundle, name)}
                          for name, table in bundle["datasets"].items()}, indent=2))
        return 0
    if args.dataset not in bundle["datasets"]:
        parser.error("unknown dataset; choose " + ", ".join(bundle["datasets"]))
    bundle = load_bundle(args.dataset)
    dataset = bundle["datasets"][args.dataset]
    rows = dataset["rows"]
    if args.model:
        rows = [row for row in rows if args.model.lower() in " ".join(
            str(row.get(key) or "") for key in ("name", "slug", "displayLabel", "hostModelSlug")
        ).lower()]
    if args.sort:
        rows = [row for row in rows if isinstance(nested(row, args.sort), (float, int))
                and not isinstance(nested(row, args.sort), bool) and math.isfinite(nested(row, args.sort))]
        rows = sorted(rows, key=lambda row: nested(row, args.sort), reverse=not args.ascending)
    if not rows:
        parser.error("no rows match the model and numeric metric")
    if args.top:
        rows = rows[:args.top]
    if args.fields:
        fields = [field.strip() for field in args.fields.split(",")]
        for field in fields:
            if not any(nested(row, field) is not None for row in dataset["rows"]):
                parser.error(f"unknown or entirely unmeasured field: {field}")
        rows = [{field: nested(row, field) for field in fields} for row in rows]
    print(json.dumps({**{k: v for k, v in dataset.items() if k != "rows"}, "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
