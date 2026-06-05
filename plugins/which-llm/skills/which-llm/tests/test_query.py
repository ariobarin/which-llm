"""Unit tests for query.py filtering. Uses a tiny synthetic CSV via a
monkeypatched _csv_path so no real artifacts are touched."""
import csv

import query


def _write_csv(path, rows):
    cols = sorted({k for r in rows for k in r})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path


def _fixture(tmp_path, monkeypatch):
    rows = [
        {"slug": "qwen-x", "name": "Qwen X", "creator_name": "Alibaba",
         "creator_slug": "alibaba", "input_modality_text": "true",
         "e2e_response_seconds": "5.0"},
        {"slug": "ds-x", "name": "DeepSeek X", "creator_name": "DeepSeek",
         "creator_slug": "deepseek", "input_modality_text": "true",
         "e2e_response_seconds": "4.0"},
        {"slug": "gpt-x", "name": "GPT X", "creator_name": "OpenAI",
         "creator_slug": "openai", "input_modality_text": "true",
         "e2e_response_seconds": ""},
    ]
    csv_path = _write_csv(tmp_path / "models_enriched.csv", rows)
    monkeypatch.setattr(query, "_csv_path", lambda: csv_path)


def test_split_csv():
    assert query._split_csv("alibaba, deepseek ,") == ["alibaba", "deepseek"]
    assert query._split_csv(None) == []
    assert query._split_csv("") == []


def test_creator_filter_matches_name_and_slug(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    got = {r["slug"] for r in query.load_rows(creators=["alibaba", "deepseek"])}
    assert got == {"qwen-x", "ds-x"}


def test_creator_filter_is_case_insensitive(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    got = {r["slug"] for r in query.load_rows(creators=["OpenAI"])}
    assert got == {"gpt-x"}


def test_creator_filter_empty_returns_all(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    assert len(query.load_rows(creators=[])) == 3
    assert len(query.load_rows(creators=None)) == 3


def test_max_latency_drops_unmeasured(tmp_path, monkeypatch):
    _fixture(tmp_path, monkeypatch)
    # gpt-x has no measured latency, so it must be excluded even at a high cap.
    got = {r["slug"] for r in query.load_rows(max_latency=100)}
    assert got == {"qwen-x", "ds-x"}
