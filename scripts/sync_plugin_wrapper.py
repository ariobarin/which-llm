from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "which-llm"
TARGET = ROOT / "plugins" / "which-llm" / "skills" / "which-llm"


def main() -> int:
    if not SOURCE.is_dir():
        raise SystemExit(f"missing source skill: {SOURCE}")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(
        SOURCE,
        TARGET,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            ".pytest_cache",
            "*.egg-info",
            "*.pyc",
        ),
    )
    print(f"synced {TARGET.relative_to(ROOT)} from {SOURCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
