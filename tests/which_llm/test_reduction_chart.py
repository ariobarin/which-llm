import reduction_chart


def test_signal_rows_use_fixed_evenly_spaced_slots():
    front = [{"_x": value, "slug": str(value)} for value in range(9)]

    assert [row["_x"] for row in reduction_chart.signal_rows(front)] == [0, 2, 4, 6, 8]


def test_metric_scope_separates_rates_from_workload_cost():
    assert reduction_chart.metric_scope("price_1m_input_tokens") == (
        "Token rate only. Workload volume is not modeled."
    )


def test_task_cost_values_keep_meaningful_decimals():
    assert reduction_chart.format_axis_value(2.74982, True) == "$2.75"
    assert reduction_chart.format_axis_value(1.0, True) == "$1"
    assert "Benchmark-specific" in reduction_chart.metric_scope(
        "agentic_index_cost_per_task_usd"
    )


def test_long_signal_names_are_bounded():
    label = reduction_chart.shorten("A Very Long Model Name With Many Variant Details")

    assert len(label) <= 34
    assert label.endswith("...")
