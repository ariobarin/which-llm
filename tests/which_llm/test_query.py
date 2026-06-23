import csv

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


def test_typed_returns_index_tokens_as_int():
    assert query._typed("indexTokensTotal", "123456789") == 123456789


def test_row_output_includes_index_token_count():
    row = {
        "slug": "model",
        "name": "Model",
        "creator_name": "Creator",
        "intelligence_index": "50",
        "intelligence_index_cost_usd": "100",
        "indexTokensTotal": "123456789",
    }
    assert query._row_for_output(row)["idx-tok"] == "123.5M"


def test_row_output_marks_estimated_index_cost():
    row = {
        "slug": "model",
        "name": "Model",
        "creator_name": "Creator",
        "intelligence_index": "50",
        "intelligence_index_cost_usd": "",
        "indexTokensTotal": "2500000",
        "price_1m_output_tokens": "4",
    }

    output = query._row_for_output(row)

    assert output["idx-run$"] == "~$10.00"
    assert output["cost-src"] == "est"


def test_json_row_exposes_effective_index_cost_fields():
    row = {
        "slug": "model",
        "name": "Model",
        "creator_name": "Creator",
        "intelligence_index": "50",
        "intelligence_index_cost_usd": "",
        "indexTokensTotal": "2500000",
        "price_1m_output_tokens": "4",
    }

    output = query._json_row(row)

    assert output["estimated_index_output_cost_usd"] == 10
    assert output["effective_index_cost_usd"] == 10
    assert output["effective_index_cost_source"] == "estimated_output"


def test_min_index_tokens_requires_token_count(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    fieldnames = ["slug", "name", "deprecated", "indexTokensTotal"]
    rows = [
        {
            "slug": "missing",
            "name": "Missing",
            "deprecated": "false",
            "indexTokensTotal": "",
        },
        {
            "slug": "low",
            "name": "Low",
            "deprecated": "false",
            "indexTokensTotal": "5",
        },
        {
            "slug": "high",
            "name": "High",
            "deprecated": "false",
            "indexTokensTotal": "20",
        },
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(query, "BASE_CSV", tmp_path / "missing.csv")

    filtered = query.load_rows(
        modalities=set(),
        include_deprecated=True,
        min_index_tokens=10,
    )

    assert [row["slug"] for row in filtered] == ["high"]


def test_max_cost_uses_estimated_index_cost(tmp_path, monkeypatch):
    csv_path = tmp_path / "models.csv"
    fieldnames = [
        "slug",
        "name",
        "deprecated",
        "intelligence_index_cost_usd",
        "indexTokensTotal",
        "price_1m_output_tokens",
    ]
    rows = [
        {
            "slug": "cheap-estimate",
            "name": "Cheap Estimate",
            "deprecated": "false",
            "intelligence_index_cost_usd": "",
            "indexTokensTotal": "2500000",
            "price_1m_output_tokens": "4",
        },
        {
            "slug": "expensive-estimate",
            "name": "Expensive Estimate",
            "deprecated": "false",
            "intelligence_index_cost_usd": "",
            "indexTokensTotal": "25000000",
            "price_1m_output_tokens": "4",
        },
        {
            "slug": "missing-cost",
            "name": "Missing Cost",
            "deprecated": "false",
            "intelligence_index_cost_usd": "",
            "indexTokensTotal": "2500000",
            "price_1m_output_tokens": "",
        },
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(query, "ENRICHED_CSV", csv_path)
    monkeypatch.setattr(query, "BASE_CSV", tmp_path / "missing.csv")

    filtered = query.load_rows(
        modalities=set(),
        include_deprecated=True,
        max_cost=20,
    )

    assert [row["slug"] for row in filtered] == ["cheap-estimate"]
