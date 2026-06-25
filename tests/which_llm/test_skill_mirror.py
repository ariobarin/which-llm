import ast
import re
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


def _declared_modules(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?ms)^py-modules\s*=\s*(\[[^\]]*\])", text)
    assert match, "pyproject.toml must declare tool.setuptools.py-modules"
    return set(ast.literal_eval(match.group(1)))


def test_pyproject_packages_all_runtime_modules():
    expected = {path.stem for path in SOURCE.glob("*.py")}

    assert _declared_modules(SOURCE / "pyproject.toml") == expected
