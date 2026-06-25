import argparse
import csv
import json
import sys

import export as export_cmd
import frontier as frontier_cmd
import pytest
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
        "max_input_price": None,
        "max_output_price": None,
        "context_min": None,
        "max_index_tokens": None,
        "min_index_tokens": 0.0,
        "max_latency": None,
        "coding_min": None,
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


def test_quality_cost_behavior_uses_composed_filters(tmp_path, monkeypatch):
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

    args = _args(intel_min=50, sort="cost")
    rows = core.load_filtered_rows(args, preset="best")
    ranked = core.rank_rows(rows, core.sort_name(args, "best"))

    assert [row["slug"] for row in ranked] == ["cheap", "expensive"]


def test_removed_compound_presets_fail_loudly():
    for preset in [
        "cheap-good",
        "fast-good",
        "cheap-vision",
        "cheap-coding",
        "cheap-long-context",
    ]:
        try:
            core.sort_name(_args(), preset)
        except SystemExit as exc:
            assert "unknown preset" in str(exc)
        else:
            raise AssertionError(f"{preset} did not fail")


def test_vision_price_behavior_uses_composed_filters(tmp_path, monkeypatch):
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

    args = _args(intel_min=40, sort="input-price")
    rows = core.load_filtered_rows(args, preset="vision")
    ranked = core.rank_rows(rows, core.sort_name(args, "vision"))

    assert [row["slug"] for row in ranked] == ["cheap-image", "expensive-image"]


def test_coding_price_behavior_uses_composed_filters(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "cheap-code",
                "name": "Cheap Code",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "coding_index": "50",
                "price_1m_input_tokens": "0.2",
            },
            {
                "slug": "expensive-code",
                "name": "Expensive Code",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "coding_index": "60",
                "price_1m_input_tokens": "5",
            },
            {
                "slug": "weak-code",
                "name": "Weak Code",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "coding_index": "20",
                "price_1m_input_tokens": "0.1",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")

    args = _args(coding_min=45, sort="input-price")
    rows = core.load_filtered_rows(args, preset="coding")
    ranked = core.rank_rows(rows, core.sort_name(args, "coding"))

    assert [row["slug"] for row in ranked] == ["cheap-code", "expensive-code"]


def test_api_price_filters_are_separate_from_run_cost(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "cheap-api",
                "name": "Cheap API",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index_cost_usd": "1000",
                "price_1m_input_tokens": "0.2",
                "price_1m_output_tokens": "0.8",
            },
            {
                "slug": "cheap-run",
                "name": "Cheap Run",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index_cost_usd": "1",
                "price_1m_input_tokens": "5",
                "price_1m_output_tokens": "20",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")

    rows = core.load_filtered_rows(
        _args(max_input_price=1, max_output_price=1),
        preset="best",
    )

    assert [row["slug"] for row in rows] == ["cheap-api"]


def test_zero_api_price_filters_and_sorts_as_real_value(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "zero-api",
                "name": "Zero API",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "price_1m_input_tokens": "0",
                "price_1m_output_tokens": "0",
            },
            {
                "slug": "paid-api",
                "name": "Paid API",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "price_1m_input_tokens": "0.2",
                "price_1m_output_tokens": "1",
            },
            {
                "slug": "unknown-api",
                "name": "Unknown API",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")

    args = _args(max_input_price=0, max_output_price=0)
    rows = core.load_filtered_rows(args, preset="best")
    ranked = core.rank_rows(rows, "input-price")

    assert [row["slug"] for row in ranked] == ["zero-api"]


def test_run_cost_bound_excludes_unknown_run_cost(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "cheap-run",
                "name": "Cheap Run",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index_cost_usd": "0.5",
            },
            {
                "slug": "unknown-run",
                "name": "Unknown Run",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")

    rows = core.load_filtered_rows(_args(max_cost=1), preset="best")

    assert [row["slug"] for row in rows] == ["cheap-run"]


def test_resolve_choice_uses_token_matching_for_family_names():
    rows = [
        {
            "slug": "gemini-3-5-flash",
            "name": "Gemini 3.5 Flash",
            "openrouter_slug": "google/gemini-3.5-flash",
            "intelligence_index": "50",
            "price_1m_input_tokens": "1.5",
        },
        {
            "slug": "gpt-5-4-nano",
            "name": "GPT-5.4 nano (xhigh)",
            "openrouter_slug": "openai/gpt-5.4-nano",
            "intelligence_index": "38",
            "price_1m_input_tokens": "0.2",
        },
    ]

    row, candidates, status = core.resolve_choice(rows, "gemini flash")

    assert row["slug"] == "gemini-3-5-flash"
    assert candidates == []
    assert status == "single"


def test_nearest_relaxations_label_relaxed_constraints(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "free-vision",
                "name": "Free Vision",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "input_modality_image": "true",
                "openrouter_has_free": "true",
                "intelligence_index": "20",
            },
            {
                "slug": "paid-smart",
                "name": "Paid Smart",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "input_modality_image": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "80",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")

    args = _args(free=True, intel_min=70, image=True)
    relaxations = core.nearest_relaxations(args, preset="vision", sort="intel", top=5)

    labels = {item["relaxation"] for item in relaxations}
    assert "drop --free" in labels
    assert "drop --min-intel" in labels


def test_nearest_relaxations_can_drop_min_coding(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "code-model",
                "name": "Code Model",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "coding_index": "50",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")

    relaxations = core.nearest_relaxations(
        _args(coding_min=999),
        preset="coding",
        sort="coding",
        top=5,
    )

    assert [item["relaxation"] for item in relaxations] == ["drop --min-coding"]


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


def test_price_frontier_keeps_zero_price_rows():
    rows = core.metric_rows(
        [
            {"slug": "zero", "price_1m_input_tokens": "0", "intelligence_index": "30"},
            {"slug": "paid", "price_1m_input_tokens": "1", "intelligence_index": "40"},
        ],
        "price_1m_input_tokens",
        "intelligence_index",
        0,
        float("inf"),
    )

    front = core.pareto_front(rows, "min")

    assert [row["slug"] for row in front] == ["zero", "paid"]


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


def test_shortlist_can_include_free_openrouter_slug():
    rows = [
        {
            "slug": "model",
            "name": "Model",
            "creator_name": "Lab",
            "openrouter_slug": "provider/model",
            "openrouter_free_slug": "provider/model:free",
        }
    ]

    rendered = core.shortlist_rows(rows, include_free_slug=True)

    assert rendered[0]["free_openrouter"] == "provider/model:free"


def test_write_json_export_uses_selected_fields(tmp_path):
    path = tmp_path / "export.json"
    rows = [
        {
            "slug": "model",
            "name": "Model",
            "intelligence_index": "50.2",
            "coding_index": "62.5",
            "gpqa": "0.734",
            "terminalbench_hard": "41",
        }
    ]

    core.write_data_file(
        rows,
        path,
        "json",
        ["slug", "intelligence_index", "coding_index", "gpqa", "terminalbench_hard"],
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == [
        {
            "slug": "model",
            "intelligence_index": 50.2,
            "coding_index": 62.5,
            "gpqa": 0.734,
            "terminalbench_hard": 41.0,
        }
    ]


def test_export_default_empty_behavior_does_not_write_file(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    out_path = tmp_path / "empty.csv"
    _write_rows(
        csv_path,
        [
            {
                "slug": "weak",
                "name": "Weak",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "20",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(
        sys,
        "argv",
        ["export.py", "best", "--min-intel", "70", "--out", str(out_path)],
    )

    with pytest.raises(SystemExit) as exc:
        export_cmd.main()

    assert "no models match" in str(exc.value)
    assert not out_path.exists()


def test_selected_fields_combines_export_groups():
    fields = core.selected_fields([], "pricing,context")

    assert fields.count("slug") == 1
    assert "price_1m_input_tokens" in fields
    assert "price_1m_output_tokens" in fields
    assert "context_window_tokens" in fields
    assert "input_modality_image" in fields


def test_coding_export_group_is_focused():
    fields = core.selected_fields([], "coding")

    assert fields == [
        "slug",
        "name",
        "creator_name",
        "price_1m_input_tokens",
        "price_1m_output_tokens",
        "context_window_tokens",
        "openrouter_slug",
        "openrouter_free_slug",
        "coding_index",
        "livecodebench",
        "terminalbench_hard",
    ]


def test_selected_columns_accepts_exact_export_columns():
    rows = [{"slug": "model", "name": "Model", "coding_index": "50"}]

    fields = core.selected_columns(rows, "name,coding_index")

    assert fields == ["name", "coding_index"]


def test_frontier_csv_headers_are_unique(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    data_path = tmp_path / "frontier.csv"
    chart_path = tmp_path / "frontier.png"
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
                "intelligence_index": "40",
                "intelligence_index_cost_usd": "1",
            },
            {
                "slug": "smart",
                "name": "Smart",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "50",
                "intelligence_index_cost_usd": "2",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(frontier_cmd, "_load_plot_deps", lambda: object())
    monkeypatch.setattr(frontier_cmd, "_plot", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "frontier.py",
            "cost-intel",
            "--out",
            str(chart_path),
            "--data-out",
            str(data_path),
        ],
    )

    assert frontier_cmd.main() == 0
    header = data_path.read_text(encoding="utf-8").splitlines()[0].split(",")

    assert len(header) == len(set(header))


def test_frontier_dependency_failure_does_not_write_artifacts(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    data_path = tmp_path / "frontier.csv"
    chart_path = tmp_path / "frontier.png"
    _write_rows(
        csv_path,
        [
            {
                "slug": "model",
                "name": "Model",
                "creator_name": "Lab",
                "deprecated": "false",
                "input_modality_text": "true",
                "openrouter_has_free": "false",
                "intelligence_index": "40",
                "intelligence_index_cost_usd": "1",
            },
        ],
    )
    monkeypatch.setattr(core.query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(core.query, "BASE_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(
        frontier_cmd,
        "_load_plot_deps",
        lambda: (_ for _ in ()).throw(SystemExit("missing plot deps")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "frontier.py",
            "cost-intel",
            "--out",
            str(chart_path),
            "--data-out",
            str(data_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        frontier_cmd.main()

    assert "missing plot deps" in str(exc.value)
    assert not data_path.exists()
    assert not chart_path.exists()


def test_frontier_price_axis_preserves_sub_dollar_labels():
    assert frontier_cmd._format_axis_value(0, True) == "$0"
    assert frontier_cmd._format_axis_value(0.25, True) == "$0.25"
    assert frontier_cmd._format_axis_value(1, True) == "$1"
    assert frontier_cmd._format_axis_value(2500, True) == "$2.5k"
    assert frontier_cmd._format_axis_value(2500, False) == "2.5K"
