"""Partial upstream failures must not replace good model data with broken data."""

import csv
import json
import sys
import urllib.error
from datetime import datetime, timedelta, timezone

import data
import enrich
import pytest
import scrape


def _csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _ago(days):
    stamp = datetime.now(timezone.utc) - timedelta(days=days)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_home_subtables_refresh_independently(tmp_path, monkeypatch):
    old, new = _ago(1), _ago(0.5)
    previous = {
        "coding-agents": {"source_url": "old", "source_updated_at_utc": old,
                          "rows": [{"id": "old-agent"}]},
        "media/image": {"source_url": "old", "source_updated_at_utc": old,
                        "rows": [{"id": "old-image"}]},
        "media/text": {"source_url": "old", "source_updated_at_utc": old,
                       "rows": [{"id": "old-text"}]},
        "providers": {"source_url": "old", "source_updated_at_utc": old,
                      "rows": [{"id": "old-provider"}]},
    }
    path = tmp_path / "aa_data.json"
    path.write_text(json.dumps({"schema_version": 1, "datasets": previous}))
    monkeypatch.setattr(data, "DATA_PATH", path)
    monkeypatch.setattr(
        scrape, "discover_dataset",
        lambda url, key: ({"models": [{"slug": "new", key: 0.5}]}, new, url),
    )
    monkeypatch.setattr(
        scrape, "page_tables",
        lambda url: {"coding-agents": ([{"id": "new-agent"}], new),
                     "media/image": ([{"id": "new-image"}], new), "media/text": ([], new)},
    )
    result = scrape.collect_details([{"slug": "new"}], new)
    tables = result["datasets"]
    assert tables["catalog"]["rows"] == [{"slug": "new"}]
    assert tables["coding-agents"]["rows"] == [{"id": "new-agent"}]
    assert tables["media/image"]["rows"] == [{"id": "new-image"}]
    assert tables["media/text"]["rows"] == previous["media/text"]["rows"]
    assert tables["providers"]["rows"] == previous["providers"]["rows"]
    assert "refresh_error" in tables["media/text"]
    assert "refresh_error" in tables["providers"]
    assert tables["coding-agents"]["source_updated_at_utc"] == new
    assert "home" not in result["refresh_errors"]


def test_stale_cache_neither_blocks_shrink_nor_survives_retirement(tmp_path, monkeypatch):
    stale, new = _ago(10), _ago(0.5)
    previous = {
        "coding-agents": {"source_url": "old", "source_updated_at_utc": stale,
                          "rows": [{"id": f"agent-{i}"} for i in range(10)]},
        "speech/tts": {"source_url": "old", "source_updated_at_utc": stale, "rows": [{"id": "tts"}]},
    }
    path = tmp_path / "aa_data.json"
    path.write_text(json.dumps({"schema_version": 1, "datasets": previous}))
    monkeypatch.setattr(data, "DATA_PATH", path)
    monkeypatch.setattr(scrape, "discover_dataset",
                        lambda url, key: ({"models": [{"slug": "new", key: 0.5}]}, new, url))
    monkeypatch.setattr(scrape, "page_tables", lambda url: {
        "coding-agents": ([{"id": "agent-0"}], new),
        "speech/ttsHostModels": ([{"id": "tts"}], new),
    })
    tables = scrape.collect_details([{"slug": "new"}], new)["datasets"]
    assert tables["coding-agents"]["rows"] == [{"id": "agent-0"}]
    assert tables["speech/ttsHostModels"]["rows"] == [{"id": "tts"}]
    assert "speech/tts" not in tables


def test_page_tables_merges_split_manifests(monkeypatch):
    keys = {"/data/agents.txt": "a", "/data/image.txt": "b", "/data/speech.txt": "c",
            "/data/hosts.txt": "d", "/data/providers.txt": "e"}
    stream = "".join(json.dumps({"manifest": {"path": path, "key": key * 64}}) for path, key in keys.items())
    html = '<script>self.__next_f.push([1, ' + json.dumps(stream) + '])</script>'
    monkeypatch.setattr(scrape, "_get_text", lambda url: html)
    provider = {"host": {}, "model": {}, "pricing": {}}
    payloads = {
        "/data/agents.txt": ({"models": [], "codingAgents": [{"id": "a"}]}, "2026-10-21T01:00:00Z"),
        "/data/image.txt": ({"media": {"textToImage": [{"id": "i"}]}}, "2026-10-21T02:00:00Z"),
        "/data/speech.txt": ({"speech": {"sttModels": [{"id": "s"}]}}, "2026-10-21T03:00:00Z"),
        "/data/hosts.txt": ([{"host": {}, "slug": "not-a-provider-row"}], "2026-10-21T04:00:00Z"),
        "/data/providers.txt": ([provider], "2026-10-21T05:00:00Z"),
    }
    monkeypatch.setattr(scrape, "_decrypt_manifest", lambda path, key: payloads[path])
    assert scrape.page_tables("https://artificialanalysis.ai") == {
        "coding-agents": ([{"id": "a"}], "2026-10-21T01:00:00Z"),
        "media/textToImage": ([{"id": "i"}], "2026-10-21T02:00:00Z"),
        "speech/sttModels": ([{"id": "s"}], "2026-10-21T03:00:00Z"),
        "providers": ([provider], "2026-10-21T05:00:00Z"),
    }


def test_openrouter_invalid_api_response_preserves_cache(tmp_path, monkeypatch):
    cached = tmp_path / "openrouter.json"
    original = json.dumps({"data": [{"id": "cached/model"}]})
    cached.write_text(original)
    monkeypatch.setattr(enrich, "OR_JSON", cached)
    monkeypatch.setattr(enrich, "_get_json", lambda url: {"data": [{"broken": True}]})
    with pytest.raises(RuntimeError, match="empty or invalid"):
        enrich.fetch_openrouter(refresh=True)
    assert cached.read_text() == original


def test_openrouter_network_failure_retains_published_mappings(tmp_path, monkeypatch):
    current = tmp_path / "models.csv"
    published = tmp_path / "models_enriched.csv"
    unmatched = tmp_path / "unmatched.txt"
    _csv(current, [
        {"snapshot_updated_at_utc": "2026-10-10T00:00:00Z",
         "slug": "old", "name": "Old", "deprecated": "False"},
        {"snapshot_updated_at_utc": "2026-10-10T00:00:00Z",
         "slug": "new", "name": "New", "deprecated": "False"},
    ])
    _csv(published, [
        {"snapshot_updated_at_utc": "2026-10-08T00:00:00Z",
         "slug": "old", "name": "Old", "deprecated": "False",
         "openrouter_slug": "test/old", "openrouter_free_slug": "",
         "openrouter_has_free": "false"},
    ])
    monkeypatch.setattr(enrich, "AA_CSV", current)
    monkeypatch.setattr(enrich, "OUT_CSV", published)
    monkeypatch.setattr(enrich, "UNMATCHED_TXT", unmatched)
    monkeypatch.setattr(sys, "argv", ["enrich.py", "--refresh"])

    def down(*args):
        raise urllib.error.HTTPError("https://openrouter.ai", 503, "offline", {}, None)
    monkeypatch.setattr(enrich, "fetch_openrouter", down)

    assert enrich.main() == 0
    rows = list(csv.DictReader(published.open(encoding="utf-8")))
    assert len(rows) == 2
    assert rows[0]["openrouter_slug"] == "test/old"
    assert rows[0]["openrouter_data_status"] == "cached"
    assert rows[1]["openrouter_slug"] == ""
    assert rows[1]["openrouter_data_status"] == "unavailable"
    assert "cached slugs may be stale" in unmatched.read_text()
    assert rows[0]["snapshot_updated_at_utc"] == "2026-10-10T00:00:00Z"


def test_openrouter_network_failure_without_fallback_still_fails(tmp_path, monkeypatch):
    current = tmp_path / "models.csv"
    _csv(current, [{"snapshot_updated_at_utc": "2026-10-10T00:00:00Z",
                    "slug": "new", "name": "New", "deprecated": "False"}])
    monkeypatch.setattr(enrich, "AA_CSV", current)
    monkeypatch.setattr(enrich, "OUT_CSV", tmp_path / "missing.csv")
    monkeypatch.setattr(sys, "argv", ["enrich.py", "--refresh"])
    monkeypatch.setattr(enrich, "fetch_openrouter",
                        lambda *args: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(RuntimeError, match="no published slug mappings"):
        enrich.main()


def test_malformed_rsc_chunk_does_not_hide_valid_chunk():
    malformed = r'<script>self.__next_f.push([1, "\x"])</script>'
    valid = '<script>self.__next_f.push([1, "valid"])</script>'
    assert scrape.extract_rsc_stream(malformed + valid) == "valid"


def test_malformed_manifest_does_not_hide_valid_manifest():
    broken = '"manifest":{broken}'
    valid = '"manifest":{"path":"/models","key":"' + "a" * 64 + '"}'
    assert list(scrape.manifests(broken + valid)) == [("/models", "a" * 64)]


def test_invalid_aa_html_does_not_overwrite_cache(tmp_path, monkeypatch):
    cached = tmp_path / "models.html"
    cached.write_text("previous valid page")
    monkeypatch.setattr(scrape, "HTML_PATH", cached)
    monkeypatch.setattr(scrape, "_get_text", lambda url: "<html>temporarily broken</html>")
    with pytest.raises(RuntimeError, match="preserving cached HTML"):
        scrape.fetch_html(refresh=True)
    assert cached.read_text() == "previous valid page"
