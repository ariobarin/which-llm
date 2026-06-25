import argparse
import csv
import json

import which_llm_core as core


def _write_rows(path, rows):
    fields = [
        "slug",
        "name",
        "creator_name",
        "deprecated",
        "input_modality_text",
        "input_modality_image",
        "input_modality_video",
        "input_modality_speech",
        "openrouter_has_free",
        "openrouter_slug",
        "openrouter_free_slug",
        "intelligence_index",
        "intelligence_index_cost_usd",
        "indexTokensTotal",
        "context_window_tokens",
        "price_1m_input_tokens",
        "price_1m_output_tokens",
        "e2e_response_seconds",
        "reasoning_model",
        "is_open_weights",
        "coding_index",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _args(**overrides):
    defaults = {
        "pattern": None,
        "creator": [],
        "free": False,
        "intel_min": None,
        "max_cost": None,
        "min_cost": 0.0,
        "context_min": None,
        "max_index_tokens": None,
        "min_index_tokens": 0.0,
        "max_latency": None,
        "reasoning": None,
        "open_weights": None,
        "modality": None,
        "text": None,
        "image": False,
        "video": False,
        "audio": False,
        "sort": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_pick_preset_filters_and_ranks(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "cheap",
                "name": "Cheap",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "51",
                "intelligence_index_cost_usd": "10",
            },
            {
                "slug": "weak",
                "name": "Weak",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "20",
                "intelligence_index_cost_usd": "1",
            },
            {
                "slug": "expensive",
                "name": "Expensive",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "60",
                "intelligence_index_cost_usd": "100",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")

    rows = core.load_filtered_rows(_args(), preset="cheap-good")
    ranked = core.rank_rows(rows, core.sort_name(_args(), "cheap-good"))

    assert [row["slug"] for row in ranked] == ["cheap", "expensive"]


def test_cheap_vision_preset_filters_image_and_ranks_price(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "cheap-image",
                "name": "Cheap Image",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "input_modality_image": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "42",
                "price_1m_input_tokens": "0.2",
            },
            {
                "slug": "expensive-image",
                "name": "Expensive Image",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "input_modality_image": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "45",
                "price_1m_input_tokens": "2",
            },
            {
                "slug": "text-only",
                "name": "Text Only",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "input_modality_image": "false",
                "openrouter_has_free": "false",
                "intelligence_index": "50",
                "price_1m_input_tokens": "0.1",
            },
            {
                "slug": "weak-image",
                "name": "Weak Image",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "input_modality_image": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "20",
                "price_1m_input_tokens": "0.01",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")

    rows = core.load_filtered_rows(_args(), preset="cheap-vision")
    ranked = core.rank_rows(rows, core.sort_name(_args(), "cheap-vision"))

    assert [row["slug"] for row in ranked] == ["cheap-image", "expensive-image"]


def test_context_frontier_maximizes_x():
    rows = core.metric_rows(
        [
            {"slug": "long", "context_window_tokens": "200", "intelligence_index": "45"},
            {"slug": "long-weak", "context_window_tokens": "200", "intelligence_index": "20"},
            {"slug": "smart", "context_window_tokens": "100", "intelligence_index": "50"},
            {"slug": "dominated", "context_window_tokens": "80", "intelligence_index": "40"},
        ],
        "context_window_tokens",
        "intelligence_index",
        0,
        float("inf"),
    )

    front = core.pareto_front(rows, "max")

    assert [row["slug"] for row in front] == ["smart", "long"]


def test_endpoint_record_marks_free_slug_as_caveated():
    record = core.endpoint_record(
        {
            "name": "Model",
            "slug": "model",
            "openrouter_slug": "provider/model",
            "openrouter_free_slug": "provider/model:free",
        }
    )

    assert record["openrouter_slug"] == "provider/model"
    assert record["openrouter_free_slug"] == "provider/model:free"
    assert "prototype" in record["caveat"]


def test_write_json_export_uses_selected_fields(tmp_path):
    path = tmp_path / "export.json"
    rows = [{"slug": "model", "name": "Model", "intelligence_index": "50.2"}]

    core.write_data_file(rows, path, "json", ["slug", "intelligence_index"])

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == [{"slug": "model", "intelligence_index": 50.2}]


def test_selected_fields_combines_export_groups():
    fields = core.selected_fields([], "pricing,context")

    assert fields.count("slug") == 1
    assert "price_1m_input_tokens" in fields
    assert "price_1m_output_tokens" in fields
    assert "context_window_tokens" in fields
    assert "input_modality_image" in fields
