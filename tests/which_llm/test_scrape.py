import json
import urllib.error

import data
import pytest

import scrape


def _rsc(payload: str) -> str:
    return f'<script>self.__next_f.push([1, {json.dumps(payload)}])</script>'


def test_extract_rsc_stream_finds_chunks():
    assert scrape.extract_rsc_stream(_rsc('1:{"ok":true}')) == '1:{"ok":true}'


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


def test_shared_dataset_uses_complete_manifest_not_preview(monkeypatch):
    manifest = {"key": "a" * 64, "path": "/data/all.txt", "extra": True}
    preview = {"initialModels": [{"slug": "preview", "canonicalEvalTokenCounts": {}}], "manifest": manifest}
    monkeypatch.setattr(scrape, "_get_text", lambda url: _rsc(json.dumps(preview)))
    complete = {"models": [{"slug": "a", "canonicalEvalTokenCounts": {"hle": {"answer": 12}}},
                            {"slug": "b", "canonicalEvalTokenCounts": {}}]}
    monkeypatch.setattr(scrape, "_decrypt_manifest", lambda *args: (complete, "2026-09-06T00:00:00Z"))
    result, _ = scrape.shared_dataset("https://artificialanalysis.ai/evaluations/example", "canonicalEvalTokenCounts")
    assert result == complete


def test_shared_dataset_rejects_changed_home_schema(monkeypatch):
    page = _rsc(json.dumps({"manifest": {"path": "/data/home.txt", "key": "a" * 64}}))
    monkeypatch.setattr(scrape, "_get_text", lambda url: page)
    monkeypatch.setattr(scrape, "_decrypt_manifest", lambda *args:
                        ({"media": None, "speech": [], "codingAgents": []}, "2026-09-06T00:00:00Z"))
    with pytest.raises(RuntimeError, match="No dated shared dataset"):
        scrape.shared_dataset("https://artificialanalysis.ai")


def test_discovery_survives_retired_page(monkeypatch):
    monkeypatch.setattr(scrape, "_get_text", lambda url:
                        '<a href="/evaluations/a-retired">Old</a><a href="/evaluations/b-current">Current</a>')
    calls = []

    def fetch(url, key):
        calls.append(url)
        if url.endswith("a-retired"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return {"models": [{"slug": "model", key: {}}]}, "2026-09-06T00:00:00Z"

    monkeypatch.setattr(scrape, "shared_dataset", fetch)
    _, _, url = scrape.discover_dataset("https://artificialanalysis.ai/evaluations", "canonicalEvalTokenCounts")
    assert url.endswith("b-current")
    assert len(calls) == 2


def test_optional_failure_preserves_date_and_core_catalog(tmp_path, monkeypatch):
    old = {"source_url": "old", "source_updated_at_utc": "2020-01-01T00:00:00Z", "rows": [{"slug": "old"}]}
    path = tmp_path / "aa_data.json"
    path.write_text(json.dumps({"schema_version": 1, "datasets": {"evaluations": old}}))
    monkeypatch.setattr(data, "DATA_PATH", path)

    def unavailable(*args):
        raise RuntimeError("source disappeared")

    monkeypatch.setattr(scrape, "discover_dataset", unavailable)
    monkeypatch.setattr(scrape, "shared_dataset", unavailable)
    bundle = scrape.collect_details([{"slug": "new"}], "2026-09-06T00:00:00Z")
    assert bundle["datasets"]["catalog"]["rows"] == [{"slug": "new"}]
    assert bundle["datasets"]["evaluations"]["source_updated_at_utc"] == old["source_updated_at_utc"]
    assert "refresh_error" in bundle["datasets"]["evaluations"]


def test_current_benchmarks_keep_zero_and_nested_details():
    row = scrape.flatten({"slug": "test", "gdpPdfAllPass": 0, "terminalbenchV21": 0.75,
                          "briefcaseBreakdown": {"overall": {"elo": 1400}},
                          "timescaleData": {"medianOutputSpeed": 80},
                          "effort": {"slug": "high"}})
    assert row["gdp_pdf_all_pass"] == 0
    assert row["terminalbench_v2_1"] == 0.75
    assert row["briefcase_elo"] == 1400
    assert row["output_tokens_per_second"] == 80
    assert row["reasoning_effort"] == "high"


@pytest.mark.parametrize("status, attempts", [(429, 2), (503, 2), (404, 1)])
def test_retry_only_transient_http_errors(monkeypatch, status, attempts):
    calls = []
    sentinel = object()

    def open_url(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, status, "error", {}, None)
        return sentinel

    monkeypatch.setattr(scrape.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(scrape.time, "sleep", lambda seconds: None)
    if status == 404:
        with pytest.raises(urllib.error.HTTPError):
            scrape._open("https://artificialanalysis.ai/example")
    else:
        assert scrape._open("https://artificialanalysis.ai/example") is sentinel
    assert len(calls) == attempts
