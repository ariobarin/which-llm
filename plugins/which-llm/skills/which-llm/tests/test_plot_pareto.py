import plot_pareto


def test_shorten_preserves_reasoning_effort():
    assert (
        plot_pareto.shorten("DeepSeek V4 Pro (Reasoning, High Effort)")
        == "DeepSeek V4 Pro (high)"
    )


def test_shorten_preserves_non_reasoning_variant():
    assert (
        plot_pareto.shorten("DeepSeek V4 Pro (Non-reasoning)")
        == "DeepSeek V4 Pro (non-reasoning)"
    )


def test_shorten_uses_slug_to_disambiguate_non_reasoning():
    assert (
        plot_pareto.shorten("DeepSeek V4 Pro", "deepseek-v4-pro-non-reasoning")
        == "DeepSeek V4 Pro (non-reasoning)"
    )
