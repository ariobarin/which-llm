import json

import scrape


def _rsc(payload: str) -> str:
    return f'<script>self.__next_f.push([1, {json.dumps(payload)}])</script>'


def test_extract_rsc_stream_finds_chunks():
    assert scrape.extract_rsc_stream(_rsc('1:{"ok":true}')) == '1:{"ok":true}'


def test_find_model_array_uses_schema_not_first_array():
    stream = (
        '1:{"models":[{"slug":"catalog-only"}]}'
        '2:{"models":['
        '{"slug":"a","headlineValue":12,"costPerTask":{},"evalCost":{}},'
        '{"slug":"b","headlineValue":13,"costPerTask":{},"evalCost":{}}]}'
    )
    rows = scrape.find_model_array(
        stream,
        min_models=2,
        required_keys={"slug", "headlineValue", "costPerTask", "evalCost"},
    )
    assert [row["slug"] for row in rows] == ["a", "b"]


def test_find_catalog_manifest_selects_full_model_dataset(monkeypatch):
    stream = '"manifest":{"path":"/data/models.txt","key":"' + "a" * 64 + '"}'
    models = [
        {"slug": f"m-{i}", "name": f"M {i}", "intelligenceIndex": i, "creator": {}}
        for i in range(3)
    ]
    monkeypatch.setattr(
        scrape,
        "_decrypt_manifest",
        lambda path, key: ({"models": models}, "2026-07-12T00:00:00Z"),
    )
    found, updated = scrape.find_catalog_manifest(stream, min_models=3)
    assert found == models
    assert updated == "2026-07-12T00:00:00Z"


def test_find_catalog_manifest_rejects_undated_data(monkeypatch):
    stream = '"manifest":{"path":"/data/models.txt","key":"' + "a" * 64 + '"}'
    models = [
        {"slug": f"m-{i}", "name": f"M {i}", "intelligenceIndex": i, "creator": {}}
        for i in range(3)
    ]
    monkeypatch.setattr(
        scrape,
        "_decrypt_manifest",
        lambda path, key: ({"models": models}, None),
    )
    try:
        scrape.find_catalog_manifest(stream, min_models=3)
    except RuntimeError as exc:
        assert "missing Last-Modified source timestamp" in str(exc)
    else:
        raise AssertionError("undated manifest was accepted")


def test_flatten_current_schema_and_matching_agentic_cost():
    model = {
        "name": "GPT Test",
        "shortName": "GPT Test",
        "slug": "gpt-test",
        "creator": {"name": "OpenAI", "slug": "openai"},
        "intelligenceIndex": 58.9,
        "agenticIndex": 54,
        "intelligenceIndexCost": {"total": 2824.18},
        "intelligenceIndexCostPerTask": {"cost": {"total": 1.04}},
        "canonicalIntelligenceIndexTokenCount": {"input": 100, "output": 20},
        "isReasoning": True,
        "inputModalityImage": True,
        "timeToFirstAnswerToken": {"total": 1.2},
        "endToEndResponseTime": {"total": 4.5},
    }
    agentic = {
        "headlineValue": 54.1,
        "costPerTask": {"total": 2.55},
        "evalCost": {"total": 925.34},
        "outputTokensPerTask": {"output": 24526},
        "timePerTaskSeconds": 354.5,
    }
    row = scrape.flatten(model, agentic, "2026-07-12T00:00:00Z")
    assert row["intelligence_index_cost_per_task_usd"] == 1.04
    assert row["agentic_index_cost_per_task_usd"] == 2.55
    assert row["agentic_index"] == 54.1
    assert row["indexTokensTotal"] == 120
    assert row["snapshot_updated_at_utc"] == "2026-07-12T00:00:00Z"
    assert row["input_modality_image"] is True


def test_flatten_treats_zero_latency_as_unmeasured():
    row = scrape.flatten({
        "slug": "untimed",
        "timeToFirstAnswerToken": {"total": 0},
        "endToEndResponseTime": {"total": 0},
    })
    assert row["ttft_seconds"] is None
    assert row["e2e_response_seconds"] is None
