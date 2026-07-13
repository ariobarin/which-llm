import math

import pareto_chart


def test_chart_name_is_pareto_frontier():
    assert pareto_chart.CHART_TITLE == "Pareto frontier"


def test_signal_rows_include_every_frontier_model_by_default():
    front = [{"_x": value, "slug": str(value)} for value in range(9)]

    assert [row["_x"] for row in pareto_chart.signal_rows(front)] == list(range(9))


def test_signal_rows_can_still_apply_an_explicit_cap():
    front = [{"_x": value, "slug": str(value)} for value in range(9)]

    assert [row["_x"] for row in pareto_chart.signal_rows(front, 5)] == [0, 2, 4, 6, 8]


def test_elbow_rows_find_strong_separated_bends():
    front = [
        {"_x": 1, "_y": 1, "slug": "a"},
        {"_x": 2, "_y": 5, "slug": "b"},
        {"_x": 4, "_y": 6, "slug": "c"},
        {"_x": 8, "_y": 6.5, "slug": "d"},
    ]

    assert [row["slug"] for row in pareto_chart.elbow_rows(
        front, x_dir="min", limit=1,
    )] == ["b"]


def test_elbow_rows_ignore_bends_with_accelerating_returns():
    front = [
        {"_x": 1, "_y": 1, "slug": "a"},
        {"_x": 2, "_y": 2, "slug": "b"},
        {"_x": 4, "_y": 10, "slug": "c"},
        {"_x": 8, "_y": 11, "slug": "d"},
    ]

    assert [row["slug"] for row in pareto_chart.elbow_rows(
        front, x_dir="min", limit=1,
    )] == ["c"]


def test_zero_cost_elbows_follow_the_rendered_symlog_axis():
    front = [
        {"_x": 0, "_y": 35, "slug": "mimo"},
        {"_x": 0.14, "_y": 40.3, "slug": "flash"},
        {"_x": 0.3, "_y": 44.4, "slug": "minimax"},
        {"_x": 1, "_y": 51.2, "slug": "luna"},
        {"_x": 2, "_y": 53.8, "slug": "grok"},
        {"_x": 2.5, "_y": 55, "slug": "terra"},
        {"_x": 5, "_y": 58.9, "slug": "sol"},
        {"_x": 10, "_y": 59.9, "slug": "fable"},
    ]

    def symlog(point):
        x, y = point
        threshold = 0.07
        transformed_x = (
            2 * x if x <= threshold
            else threshold * (2 + math.log2(x / threshold))
        )
        return transformed_x, y

    elbows = pareto_chart.elbow_rows(
        front, x_dir="min", point_transform=symlog,
    )

    assert [row["slug"] for row in elbows] == ["sol"]


def test_near_signal_rows_prioritize_the_frontier_path():
    front = [
        {"_x": 1, "_y": 1, "slug": "a"},
        {"_x": 10, "_y": 10, "slug": "b"},
    ]
    near = [
        {"_x": 5, "_y": 5.1, "slug": "close"},
        {"_x": 5, "_y": 1, "slug": "far"},
    ]

    assert pareto_chart.near_signal_rows(near, front, limit=1)[0]["slug"] == "close"


def test_metric_scope_separates_rates_from_workload_cost():
    assert pareto_chart.metric_scope("price_1m_input_tokens") == (
        "Token rate only. Workload volume is not modeled."
    )


def test_task_cost_values_keep_meaningful_decimals():
    assert pareto_chart.format_axis_value(2.74982, True) == "$2.75"
    assert pareto_chart.format_axis_value(1.0, True) == "$1"
    assert "Benchmark-specific" in pareto_chart.metric_scope(
        "agentic_index_cost_per_task_usd"
    )


def test_long_signal_names_are_bounded():
    label = pareto_chart.shorten("A Very Long Model Name With Many Variant Details")

    assert len(label) <= 34
    assert label.endswith("...")


def test_fallback_variant_keeps_effort_without_the_long_fallback_name():
    label = pareto_chart.shorten(
        "Claude Fable 5 (Adaptive Reasoning, Max Effort, Opus 4.8 Fallback)"
    )

    assert label == "Claude Fable 5 (max)"
