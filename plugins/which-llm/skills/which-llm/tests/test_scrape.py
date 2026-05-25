"""Contract tests for scrape.py's RSC parser.

Uses a synthetic fixture — no real AA HTML committed. The fixture mirrors
the exact encoding that scrape.py expects: __next_f.push chunks wrapping
JS-escaped RSC content with the anchored 'addToSelectedModels' /
'defaultData' markers.
"""
import json

import scrape


def _make_fixture(models: list[dict]) -> str:
    """Build a minimal HTML page whose RSC payload contains `models`."""
    rsc_content = (
        '37:["$","div",null,'
        '{"selectModelsByDefault":"$undefined",'
        '"addToSelectedModels":"$undefined",'
        '"defaultData":' + json.dumps(models) + "}]"
    )
    js_escaped = json.dumps(rsc_content)
    return f'<html><script>self.__next_f.push([1, {js_escaped}])</script></html>'


def _fake_models(n: int) -> list[dict]:
    return [
        {
            "name": f"Test Model {i}",
            "slug": f"test-model-{i}",
            "intelligence_index": 40 + i,
            "model_creator_id": f"creator-{i}",
        }
        for i in range(n)
    ]


def test_extract_rsc_stream_finds_chunks():
    html = _make_fixture(_fake_models(3))
    stream = scrape.extract_rsc_stream(html)
    assert "defaultData" in stream
    assert "addToSelectedModels" in stream


def test_find_default_data_parses_array():
    models = _fake_models(5)
    html = _make_fixture(models)
    stream = scrape.extract_rsc_stream(html)
    result = scrape.find_default_data(stream, min_models=1)
    assert len(result) == 5
    assert result[0]["slug"] == "test-model-0"
    assert result[4]["intelligence_index"] == 44


def test_find_default_data_validates_min_count():
    html = _make_fixture(_fake_models(2))
    stream = scrape.extract_rsc_stream(html)
    try:
        scrape.find_default_data(stream, min_models=100)
        assert False, "should have raised"
    except RuntimeError as e:
        assert "Parsed only 2" in str(e)


def test_find_default_data_validates_required_keys():
    bad_models = [{"foo": "bar"} for _ in range(5)]
    html = _make_fixture(bad_models)
    stream = scrape.extract_rsc_stream(html)
    try:
        scrape.find_default_data(stream, min_models=1)
        assert False, "should have raised"
    except RuntimeError as e:
        assert "missing expected keys" in str(e)


def test_flatten_extracts_core_fields():
    m = {
        "name": "Claude Test",
        "short_name": "CT",
        "slug": "claude-test",
        "model_family_slug": "claude",
        "model_creators": {"name": "Anthropic", "slug": "anthropic"},
        "intelligence_index": 55.123456,
        "intelligence_index_cost": {"total_cost": 1234.5, "input_cost": 800,
                                     "output_cost": 400, "reasoning_cost": 34.5},
        "intelligence_index_is_estimated": False,
        "estimated_intelligence_index": None,
        "intelligence_index_per_m_output_tokens": 0.5,
        "reasoning_model": True,
        "context_window_tokens": 200000,
        "parameters": 175,
        "activeParams": 175,
        "release_date": "2026-01-01",
        "price_1m_input_tokens": 5.0,
        "price_1m_output_tokens": 25.0,
        "gpqa": 0.91,
        "hle": 0.39,
    }
    flat = scrape.flatten(m)
    assert flat["name"] == "Claude Test"
    assert flat["creator_name"] == "Anthropic"
    assert flat["intelligence_index"] == 55.123456
    assert flat["intelligence_index_cost_usd"] == 1234.5
    assert flat["reasoning_model"] is True
    assert flat["gpqa"] == 0.91


def test_flatten_coerces_rsc_sentinels():
    m = {
        "name": "Sparse Model",
        "slug": "sparse",
        "intelligence_index_cost": "$undefined",
        "model_creators": {"name": "$undefined"},
    }
    flat = scrape.flatten(m)
    assert flat["intelligence_index_cost_usd"] is None
    assert flat["creator_name"] is None
