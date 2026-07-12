import pytest

import enrich


def _row(timestamp, value="same", slug="model"):
    return {
        "snapshot_updated_at_utc": timestamp,
        "slug": slug,
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


def test_older_identical_snapshot_restores_tracked_row_order():
    current = [
        _row("2026-07-12T03:54:05Z", slug="second"),
        _row("2026-07-12T03:54:05Z", slug="first"),
    ]
    previous = [
        _row("2026-07-12T03:54:10Z", slug="first"),
        _row("2026-07-12T03:54:10Z", slug="second"),
    ]

    assert enrich.enforce_snapshot_monotonicity(current, previous) is True
    assert [row["slug"] for row in current] == ["first", "second"]


@pytest.mark.parametrize(
    "current",
    [
        [_row("2026-07-12T03:54:05Z", slug="")],
        [
            _row("2026-07-12T03:54:05Z", slug="duplicate"),
            _row("2026-07-12T03:54:05Z", slug="duplicate"),
        ],
    ],
)
def test_older_snapshot_rejects_blank_or_duplicate_slugs(current):
    previous = [_row("2026-07-12T03:54:10Z")]

    with pytest.raises(RuntimeError, match="unique slugs"):
        enrich.enforce_snapshot_monotonicity(current, previous)


def test_newer_snapshot_rejects_duplicate_slugs():
    current = [
        _row("2026-07-12T03:55:00Z", slug="duplicate"),
        _row("2026-07-12T03:55:00Z", slug="duplicate"),
    ]
    previous = [_row("2026-07-12T03:54:10Z")]

    with pytest.raises(RuntimeError, match="unique slugs"):
        enrich.enforce_snapshot_monotonicity(current, previous)


def test_first_snapshot_rejects_blank_slug():
    with pytest.raises(RuntimeError, match="unique slugs"):
        enrich.enforce_snapshot_monotonicity(
            [_row("2026-07-12T03:55:00Z", slug="")],
            [],
        )


@pytest.mark.parametrize("timestamp", ["not-a-time", "2026-07-12T03:55:00"])
def test_snapshot_rejects_invalid_or_naive_timestamp(timestamp):
    with pytest.raises(RuntimeError, match="snapshot source timestamp"):
        enrich.enforce_snapshot_monotonicity([_row(timestamp)], [])


def test_equivalent_timezone_offsets_compare_as_the_same_instant():
    current = [_row("2026-07-11T23:54:10-04:00")]
    previous = [_row("2026-07-12T03:54:10Z")]

    assert enrich.enforce_snapshot_monotonicity(current, previous) is False
