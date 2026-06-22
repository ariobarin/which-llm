from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "skills" / "which-llm"
TARGET = ROOT / "plugins" / "which-llm" / "skills" / "which-llm"


def _runtime_files(root: Path) -> list[Path]:
    return sorted(
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
    )


def test_plugin_wrapper_mirrors_skill_package():
    source_files = _runtime_files(SOURCE)
    target_files = _runtime_files(TARGET)

    assert target_files == source_files
    for rel_path in source_files:
        assert (TARGET / rel_path).read_bytes() == (SOURCE / rel_path).read_bytes()
