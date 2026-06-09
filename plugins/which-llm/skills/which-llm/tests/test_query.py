import query


def _row(slug, name, intel, openrouter_slug=None, free_slug=None):
    return {
        "slug": slug,
        "name": name,
        "intelligence_index": str(intel),
        "openrouter_slug": openrouter_slug or "",
        "openrouter_free_slug": free_slug or "",
    }


def test_resolve_model_exact_slug():
    rows = [_row("claude-opus-4-7", "Claude Opus 4.7", 57.3)]
    match, candidates = query.resolve_model(rows, "claude-opus-4-7")
    assert match["slug"] == "claude-opus-4-7"
    assert candidates == []


def test_resolve_model_normalized_name():
    rows = [_row("claude-opus-4-7", "Claude Opus 4.7", 57.3)]
    match, candidates = query.resolve_model(rows, "Claude Opus 4.7")
    assert match["slug"] == "claude-opus-4-7"
    assert candidates == []


def test_resolve_model_returns_ambiguous_candidates():
    rows = [
        _row("claude-opus-4-7", "Claude Opus 4.7", 57.3),
        _row("claude-haiku", "Claude Haiku", 30.0),
    ]
    match, candidates = query.resolve_model(rows, "claude")
    assert match is None
    assert [r["slug"] for r in candidates] == ["claude-opus-4-7", "claude-haiku"]


def test_resolve_model_can_prefer_strongest_openrouter_endpoint():
    rows = [
        _row("model-low", "Model Low", 40.0, "provider/model"),
        _row("model-high", "Model High", 55.0, "provider/model"),
    ]
    match, candidates = query.resolve_model(
        rows,
        "provider/model",
        prefer_openrouter=True,
    )
    assert match["slug"] == "model-high"
    assert candidates == []
