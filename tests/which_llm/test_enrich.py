import pytest

import enrich


def _row(timestamp, value="same"):
    return {
        "snapshot_updated_at_utc": timestamp,
        "slug": "model",
        "value": value,
        "openrouter_slug": "provider/model",
    }


def test_older_identical_snapshot_keeps_newer_tracked_timestamp():
    current = [_row("2026-07-12T03:54:05Z")]
    previous = [_row("2026-07-12T03:54:10Z")]

    assert enrich.enforce_snapshot_monotonicity(current, previous) is True
    assert current[0]["snapshot_updated_at_utc"] == "2026-07-12T03:54:10Z"


def test_older_changed_snapshot_is_rejected():
    current = [_row("2026-07-12T03:54:05Z", value="changed")]
    previous = [_row("2026-07-12T03:54:10Z")]

    with pytest.raises(RuntimeError, match="refusing changed snapshot"):
        enrich.enforce_snapshot_monotonicity(current, previous)


def test_newer_snapshot_timestamp_is_preserved():
    current = [_row("2026-07-12T03:55:00Z")]
    previous = [_row("2026-07-12T03:54:10Z")]

    assert enrich.enforce_snapshot_monotonicity(current, previous) is False
    assert current[0]["snapshot_updated_at_utc"] == "2026-07-12T03:55:00Z"
