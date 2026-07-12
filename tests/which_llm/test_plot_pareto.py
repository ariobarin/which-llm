import csv
from datetime import datetime, timezone

import plot_pareto


def _write_models(path, rows):
    fieldnames = [
        "snapshot_updated_at_utc",
        "slug",
        "name",
        "creator_name",
        "deprecated",
        "input_modality_text",
        "input_modality_image",
        "input_modality_video",
        "input_modality_speech",
        "openrouter_has_free",
        "intelligence_index",
        "intelligence_index_cost_usd",
        "intelligence_index_cost_per_task_usd",
        "agentic_index_cost_per_task_usd",
        "agentic_index",
        "price_1m_output_tokens",
        "coding_index",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row.setdefault("snapshot_updated_at_utc", datetime.now(timezone.utc).isoformat())
            writer.writerow(row)


def test_load_rows_filters_creators_and_maps_metric_pair(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    _write_models(
        csv_path,
        [
            {
                "slug": "openai-front",
                "name": "OpenAI Front",
                "creator_name": "OpenAI",
                "deprecated": "false",
                "input_modality_text": "true",
                "input_modality_image": "false",
                "input_modality_video": "false",
                "input_modality_speech": "false",
                "openrouter_has_free": "false",
                "intelligence_index": "50",
                "intelligence_index_cost_usd": "100",
                "price_1m_output_tokens": "2",
                "coding_index": "45",
            },
            {
                "slug": "google-other",
                "name": "Google Other",
                "creator_name": "Google",
                "deprecated": "false",
                "input_modality_text": "true",
                "input_modality_image": "false",
                "input_modality_video": "false",
                "input_modality_speech": "false",
                "openrouter_has_free": "false",
                "intelligence_index": "50",
                "intelligence_index_cost_usd": "100",
                "price_1m_output_tokens": "1",
                "coding_index": "60",
            },
        ],
    )
    monkeypatch.setattr(plot_pareto, "CSV_PATH", csv_path)

    rows = plot_pareto.load_rows(
        min_cost=0,
        max_cost=10,
        require_text=True,
        require_image=False,
        require_video=False,
        require_audio=False,
        free_only=False,
        creators=["OpenAI", "Anthropic"],
        x_field="price_1m_output_tokens",
        y_field="coding_index",
    )

    assert [row["slug"] for row in rows] == ["openai-front"]
    assert rows[0]["_x"] == 2
    assert rows[0]["_y"] == 45
    assert rows[0]["_cost"] == 2
    assert rows[0]["_intel"] == 45


def test_pareto_front_uses_generic_plot_coordinates():
    rows = [
        {"slug": "cheap", "_x": 1, "_y": 10},
        {"slug": "dominated", "_x": 2, "_y": 9},
        {"slug": "better", "_x": 3, "_y": 12},
    ]

    assert [row["slug"] for row in plot_pareto.pareto_front(rows)] == ["cheap", "better"]


def test_plot_rejects_cross_benchmark_cost_pair():
    try:
        plot_pareto.validate_metric_pair(
            "agentic_index_cost_per_task_usd",
            "intelligence_index",
        )
    except SystemExit as exc:
        assert "cannot be paired" in str(exc)
    else:
        raise AssertionError("cross-benchmark pair was accepted")


def test_plot_pareto_price_axis_preserves_sub_dollar_labels():
    assert plot_pareto.format_axis_value(0, True) == "$0"
    assert plot_pareto.format_axis_value(0.25, True) == "$0.25"
    assert plot_pareto.format_axis_value(1, True) == "$1"
    assert plot_pareto.format_axis_value(2500, True) == "$2.5k"
    assert plot_pareto.format_axis_value(2500, False) == "2500"


def test_shorten_preserves_reasoning_effort():
    assert (
        plot_pareto.shorten("DeepSeek V4 Pro (Reasoning, High Effort)")
        == "DeepSeek V4 Pro (high)"
    )


def test_shorten_preserves_non_reasoning_variant():
    assert (
        plot_pareto.shorten("Qwen3.5 0.8B (Non-reasoning)")
        == "Qwen3.5 0.8B (non-reasoning)"
    )
    assert plot_pareto.shorten("Qwen3.5 0.8B (Reasoning)") == "Qwen3.5 0.8B"
    assert (
        plot_pareto.shorten("DeepSeek V4 Pro (Non-reasoning)")
        == "DeepSeek V4 Pro (non-reasoning)"
    )


def test_shorten_uses_slug_to_disambiguate_non_reasoning():
    assert (
        plot_pareto.shorten("DeepSeek V4 Pro", "deepseek-v4-pro-non-reasoning")
        == "DeepSeek V4 Pro (non-reasoning)"
    )
