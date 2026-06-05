"""Tests for plot_pareto.py filtering and frontier logic. Synthetic CSV via a
monkeypatched CSV_PATH; no plotting is exercised."""
import csv

import plot_pareto as pp


def _write(path, rows):
    cols = sorted({k for r in rows for k in r})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path


def _fixture(tmp_path, monkeypatch):
    rows = [
        {"slug": "a", "name": "A", "intelligence_index": "30",
         "creator_name": "Alibaba", "creator_slug": "alibaba",
         "intelligence_index_cost_usd": "100", "e2e_response_seconds": "5",
         "input_modality_text": "true", "reasoning_model": "false"},
        {"slug": "b", "name": "B", "intelligence_index": "40",
         "creator_name": "DeepSeek", "creator_slug": "deepseek",
         "intelligence_index_cost_usd": "200", "e2e_response_seconds": "10",
         "input_modality_text": "true", "reasoning_model": "true"},
        {"slug": "c", "name": "C", "intelligence_index": "20",
         "creator_name": "OpenAI", "creator_slug": "openai",
         "intelligence_index_cost_usd": "50", "e2e_response_seconds": "",
         "input_modality_text": "true", "reasoning_model": "false"},
    ]
    monkeypatch.setattr(pp, "CSV_PATH", _write(tmp_path / "m.csv", rows))


def _load(axis="cost", **kw):
    base = dict(require_text=True, require_image=False, require_video=False,
                require_audio=False, free_only=False)
    base.update(kw)
    return pp.load_rows(axis, 0.0, float("inf"), **base)


def test_speed_axis_reads_latency_and_drops_missing(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    rows = _load(axis="speed")
    # 'c' has no latency, so it's dropped on the speed axis.
    assert {r["slug"]: r["_x"] for r in rows} == {"a": 5.0, "b": 10.0}


def test_cost_axis_keeps_all_with_cost(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    assert {r["slug"] for r in _load(axis="cost")} == {"a", "b", "c"}


def test_creator_filter(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    assert {r["slug"] for r in _load(creators=["deepseek"])} == {"b"}


def test_reasoning_filter(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    assert {r["slug"] for r in _load(reasoning=False)} == {"a", "c"}


def test_pareto_front_min_x_max_intel():
    rows = [
        {"slug": "x", "_x": 1.0, "_intel": 10.0},
        {"slug": "y", "_x": 2.0, "_intel": 8.0},   # dominated by x
        {"slug": "z", "_x": 3.0, "_intel": 20.0},
    ]
    assert [r["slug"] for r in pp.pareto_front(rows)] == ["x", "z"]
