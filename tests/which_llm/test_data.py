import csv
import io
import json
from datetime import datetime, timezone

import data
import pytest
import query
import which_llm_core as core


def snapshot(stamp=None):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    stamp = stamp or datetime.now(timezone.utc).isoformat()
    writer.writerow(["slug", "name", "intelligence_index", "openrouter_slug", "snapshot_updated_at_utc"])
    for i in range(400):
        writer.writerow([f"model-{i}", f"Model {i}", 50, "provider/model", stamp or datetime.now(timezone.utc).isoformat()])
    return output.getvalue()


def test_invalid_remote_does_not_replace_cache(tmp_path, monkeypatch):
    path = tmp_path / "models_enriched.csv"
    path.write_text("original cache")
    monkeypatch.setattr(data.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"<html>error</html>"))
    with pytest.raises(RuntimeError, match="incomplete"):
        data.refresh_file(path, data.validate_csv)
    assert path.read_text() == "original cache"
    assert list(tmp_path.iterdir()) == [path]


def test_stale_install_fetches_current_snapshot_without_scraper(tmp_path, monkeypatch):
    path = tmp_path / "models_enriched.csv"
    path.write_text(snapshot("2020-01-01T00:00:00Z"))
    stamp = datetime.now(timezone.utc).isoformat()
    current = snapshot(stamp)
    calls = []

    def download(request, timeout):
        calls.append(request.full_url)
        return io.BytesIO(current.encode())

    monkeypatch.setattr(query, "ENRICHED_CSV", path)
    monkeypatch.setattr(data.urllib.request, "urlopen", download)
    monkeypatch.setattr(query, "_run_python", lambda *args: pytest.fail("runtime launched the scraper"))
    query.ensure_data()
    assert path.read_text() == current
    query.ensure_data()
    assert len(calls) == 1


@pytest.mark.parametrize("stamp", ["2020-01-01T00:00:00Z", "", "2099-01-01T00:00:00Z"])
def test_remote_rejects_stale_undated_or_future_data(stamp):
    content = snapshot("placeholder").replace("placeholder", stamp)
    with pytest.raises(ValueError, match="stale or undated"):
        data.validate_csv(content)


def test_download_falls_back_from_stale_daily_branch(tmp_path, monkeypatch):
    current = snapshot(datetime.now(timezone.utc).isoformat())
    contents = iter([snapshot("2020-01-01T00:00:00Z"), current])
    monkeypatch.setattr(data.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(next(contents).encode()))
    path = tmp_path / "models_enriched.csv"
    data.refresh_file(path, data.validate_csv)
    assert path.read_text() == current


def test_dataset_cli_preserves_config_identity_and_zero_cost(tmp_path, monkeypatch, capsys):
    stamp = datetime.now(timezone.utc).isoformat()
    table = {"source_url": "source", "source_updated_at_utc": stamp, "rows": [
        {"displayLabel": "Agent A + Model", "indexScore": 0.7, "mean": {"costUsd": 0}},
        {"displayLabel": "Agent B + Model", "indexScore": 0.8, "mean": {"costUsd": 2}},
        {"displayLabel": "Untimed", "indexScore": 0.9, "mean": {"costUsd": None}},
    ]}
    path = tmp_path / "aa_data.json"
    path.write_text(json.dumps({"schema_version": 1, "datasets": {"catalog": table, "coding-agents": table}}))
    monkeypatch.setattr(data, "DATA_PATH", path)
    monkeypatch.setattr(data.sys, "argv", ["data.py", "coding-agents", "--sort", "mean.costUsd", "--ascending",
                                           "--fields", "displayLabel,indexScore,mean.costUsd"])
    assert data.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert [row["displayLabel"] for row in result["rows"]] == ["Agent A + Model", "Agent B + Model"]
    assert result["rows"][0]["mean.costUsd"] == 0
    assert result["source_updated_at_utc"] == stamp


def test_retired_index_cannot_produce_arbitrary_ranking():
    with pytest.raises(SystemExit, match="legacy coding index"):
        core.rank_rows([{"slug": "model", "coding_index": ""}], "coding")
