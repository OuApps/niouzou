"""Pure-function tests for services.ranked_query helpers (no DB)."""

from niouzou.services.ranked_query import interleave_by_source


def _row(source_id: str, rank: float, id_: str):
    # interleave only reads "source_id"; rank/id carried for cursor assertions.
    return {"source_id": source_id, "feed_rank": rank, "id": id_}


def test_interleave_empty():
    assert interleave_by_source([]) == []


def test_interleave_single_source_is_noop():
    rows = [_row("A", 0.9, "1"), _row("A", 0.8, "2"), _row("A", 0.7, "3")]
    # Every row shares the source — nothing can break the run; order preserved.
    assert [r["id"] for r in interleave_by_source(rows)] == ["1", "2", "3"]


def test_interleave_breaks_a_tunnel():
    # A publishes a burst (top 4 by rank); B and C are lower. The greedy pass
    # should pull B/C up between the A's instead of showing AAAA first.
    rows = [
        _row("A", 0.99, "a1"),
        _row("A", 0.98, "a2"),
        _row("A", 0.97, "a3"),
        _row("A", 0.96, "a4"),
        _row("B", 0.50, "b1"),
        _row("C", 0.40, "c1"),
    ]
    out = interleave_by_source(rows)
    sources = [r["source_id"] for r in out]
    # No two adjacent rows share a source until the queue is forced (only A's
    # remain at the tail).
    assert sources == ["A", "B", "A", "C", "A", "A"]
    # All rows preserved, none duplicated.
    assert sorted(r["id"] for r in out) == ["a1", "a2", "a3", "a4", "b1", "c1"]


def test_interleave_preserves_rank_minimum_for_cursor():
    # The caller derives the keyset cursor from the pre-reorder rank-min row;
    # interleave must not drop or invent rows, so that row is still present.
    rows = [_row("A", 0.9, "1"), _row("B", 0.8, "2"), _row("A", 0.1, "3")]
    out = interleave_by_source(rows)
    assert {r["id"] for r in out} == {"1", "2", "3"}
    assert min(r["feed_rank"] for r in out) == 0.1
