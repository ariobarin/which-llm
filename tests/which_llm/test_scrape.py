"""Contract tests for scrape.py's RSC parser.

Uses a synthetic fixture. No real AA HTML committed. The fixture mirrors
the exact encoding that scrape.py expects: __next_f.push chunks wrapping
JS-escaped RSC content with the anchored 'addToSelectedModels' /
'defaultData' markers.
"""
import gzip
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


def _make_rsc_stream(models: list[dict]) -> str:
    return (
        '37:["$","div",null,'
        '{"selectModelsByDefault":"$undefined",'
        '"addToSelectedModels":"$undefined",'
        '"defaultData":' + json.dumps(models) + "}]"
    )


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


def test_find_default_data_accepts_direct_rsc_stream():
    models = _fake_models(3)
    result = scrape.find_default_data(_make_rsc_stream(models), min_models=1)
    assert len(result) == 3
    assert result[2]["slug"] == "test-model-2"


def test_decode_text_handles_gzip():
    payload = gzip.compress("hello".encode("utf-8"))
    assert scrape._decode_text(payload, "gzip") == "hello"


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
        "indexTokensTotal": 123456789,
        "reasoning_model": True,
        "context_window_tokens": 200000,
        "parameters": 175,
        "activeParams": 175,
        "release_date": "2026-01-01",
        "price_1m_input_tokens": 5.0,
        "price_1m_output_tokens": 25.0,
        "gpqa": 0.91,
        "hle": 0.39,
        "intelligence_index_v4_1": 57.2,
        "canonicalIntelligenceIndexTokenCount": {
            "input": 1000,
            "output": 500,
            "answer": 200,
            "reasoning": 300,
        },
        "intelligenceIndexOutputTokensPerTask": {
            "answer": 20,
            "reasoning": 30,
            "output": 50,
        },
        "intelligenceIndexCostPerTask": {
            "cost": {
                "total": 1.5,
                "input": 0.6,
                "output": 0.9,
                "cacheRead": 0.1,
                "cacheWrite": 0.2,
                "reasoning": 0.3,
                "answer": 0.4,
            }
        },
        "timescaleData": {
            "median_output_speed": 42.5,
            "percentile_05_output_speed": 20,
            "percentile_95_output_speed": 80,
            "median_time_to_first_chunk": 0.7,
        },
        "performanceByPromptLength": [
            {
                "prompt_length_type": "medium_coding",
                "median_output_speed": 35,
                "median_time_to_first_chunk": 0.8,
                "median_time_to_first_answer_token": 1.2,
                "median_end_to_end_response_time": 9.5,
            }
        ],
        "briefcase": {
            "elo": 1200,
            "rubric": {"elo": 1100},
            "turns": {"avgPerTask": 12.5},
            "totalToolCalls": 90,
        },
        "openness": {"opennessIndex": 38.8, "modelAvailability": 6},
        "training_information": {"training_tokens_trillions": 15},
        "reasoning_properties": {
            "style": "in_chunk",
            "varied_reasoning": True,
        },
    }
    flat = scrape.flatten(m)
    assert flat["name"] == "Claude Test"
    assert flat["creator_name"] == "Anthropic"
    assert flat["intelligence_index"] == 55.123456
    assert flat["intelligence_index_cost_usd"] == 1234.5
    assert flat["indexTokensTotal"] == 123456789
    assert flat["reasoning_model"] is True
    assert flat["gpqa"] == 0.91
    assert flat["intelligence_index_v4_1"] == 57.2
    assert flat["index_input_tokens"] == 1000
    assert flat["index_cost_per_task_usd"] == 1.5
    assert flat["output_speed_median_tokens_per_second"] == 42.5
    assert flat["prompt_medium_coding_e2e_response_seconds"] == 9.5
    assert flat["briefcase_elo"] == 1200
    assert flat["briefcase_rubric_elo"] == 1100
    assert flat["openness_index"] == 38.8
    assert flat["training_tokens_trillions"] == 15
    assert flat["reasoning_style"] == "in_chunk"
    assert flat["reasoning_varied"] is True


def test_flatten_host_models_extracts_provider_endpoint_rows():
    models = [
        {
            "slug": "model",
            "name": "Model",
            "model_creators": {"slug": "lab"},
            "host_models": [
                {
                    "id": "hm-1",
                    "slug": "host_model",
                    "deleted": False,
                    "host_id": "host-1",
                    "host_api_id": "provider/model",
                    "host_model_string": "Provider_Model",
                    "price_1m_input_tokens": 1,
                    "price_1m_output_tokens": 2,
                    "cache_hit_price": 0.5,
                    "cache_write_price": 1.25,
                    "host_model_cache_hit_rate": {"cache_hit_rate": 0.75},
                    "json_mode": True,
                    "function_calling": False,
                    "gpqa_16x": {"median": 0.8},
                },
                {
                    "id": "hm-2",
                    "slug": "deleted",
                    "deleted": True,
                },
            ],
        }
    ]

    rows = scrape.flatten_host_models(models)

    assert len(rows) == 1
    assert rows[0]["model_slug"] == "model"
    assert rows[0]["host_model_slug"] == "host_model"
    assert rows[0]["host_api_id"] == "provider/model"
    assert rows[0]["price_1m_input_tokens"] == 1
    assert rows[0]["host_cache_hit_rate"] == 0.75
    assert rows[0]["json_mode"] is True
    assert rows[0]["function_calling"] is False
    assert rows[0]["gpqa_16x_median"] == 0.8


def test_flatten_extracts_latency_metrics():
    m = {
        "name": "Fast Model",
        "slug": "fast",
        "time_to_first_answer_token_metrics": {"total_time": 0.9},
        "end_to_end_response_time_metrics": {"total_time": 4.6, "answer_time": 3.4},
    }
    flat = scrape.flatten(m)
    assert flat["ttft_seconds"] == 0.9
    assert flat["e2e_response_seconds"] == 4.6


def test_flatten_treats_zero_latency_as_unmeasured():
    # AA emits an all-zero metrics dict for models it hasn't speed-tested;
    # total_time == 0 must become None so it doesn't sort as 'fastest'.
    m = {
        "name": "Untimed Model",
        "slug": "untimed",
        "time_to_first_answer_token_metrics": {"total_time": 0},
        "end_to_end_response_time_metrics": {"total_time": 0},
    }
    flat = scrape.flatten(m)
    assert flat["ttft_seconds"] is None
    assert flat["e2e_response_seconds"] is None


def test_flatten_missing_latency_is_none():
    flat = scrape.flatten({"name": "No Metrics", "slug": "none"})
    assert flat["ttft_seconds"] is None
    assert flat["e2e_response_seconds"] is None


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
