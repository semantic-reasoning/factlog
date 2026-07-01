# SPDX-License-Identifier: Apache-2.0
"""Regression tests for dedup_engine_atoms triple collapse (#191).

The same (subject, relation, object) accepted from several sources must become
a single engine atom so accepted.dl / ask / run_logic_check use set semantics
(one row, true count) instead of an inflated, duplicated count. The collapse is
first-occurrence stable (not sort-min) so accepted.dl stays byte-identical when
the KB has no duplicate triple. Source aggregation lives on the separate
candidates path and is untouched.
"""
from __future__ import annotations

import common


def _row(subject, relation, object_, **extra):
    row = {"subject": subject, "relation": relation, "object": object_}
    row.update(extra)
    return row


class TestDedupEngineAtoms:
    def test_multi_source_same_triple_collapses_to_one(self):
        rows = [
            _row("PMID:16354850", "게재저널", "Chest", source="sources/a.md"),
            _row("PMID:16354850", "게재저널", "Chest", source="sources/b.md"),
        ]
        out = common.dedup_engine_atoms(rows)
        assert len(out) == 1
        assert (out[0]["subject"], out[0]["relation"], out[0]["object"]) == (
            "PMID:16354850",
            "게재저널",
            "Chest",
        )

    def test_first_occurrence_is_kept(self):
        rows = [
            _row("A", "r", "B", source="first"),
            _row("A", "r", "B", source="second"),
        ]
        out = common.dedup_engine_atoms(rows)
        assert len(out) == 1
        # stable, not sort-min: the first-seen row survives verbatim
        assert out[0]["source"] == "first"

    def test_three_or_more_sources_collapse_to_one(self):
        rows = [
            _row("A", "r", "B", source="s1"),
            _row("A", "r", "B", source="s2"),
            _row("A", "r", "B", source="s3"),
            _row("A", "r", "B", source="s4"),
        ]
        out = common.dedup_engine_atoms(rows)
        assert len(out) == 1
        assert out[0]["source"] == "s1"  # first-occurrence survives

    def test_scattered_duplicates_keep_first_and_preserve_order(self):
        # a=same triple appearing 3x, interleaved with distinct b and c:
        # [a, b, a, c, a] -> [a, b, c] with a's FIRST occurrence retained.
        rows = [
            _row("A", "r", "B", source="a1"),
            _row("X", "r", "Y", source="b1"),
            _row("A", "r", "B", source="a2"),
            _row("P", "r", "Q", source="c1"),
            _row("A", "r", "B", source="a3"),
        ]
        out = common.dedup_engine_atoms(rows)
        keys = [(r["subject"], r["relation"], r["object"]) for r in out]
        assert keys == [("A", "r", "B"), ("X", "r", "Y"), ("P", "r", "Q")]
        # the first-seen row for the scattered triple is the one kept
        assert out[0]["source"] == "a1"

    def test_distinct_triples_preserve_order(self):
        rows = [
            _row("A", "r", "B"),
            _row("A", "r", "C"),
            _row("A", "s", "B"),
        ]
        out = common.dedup_engine_atoms(rows)
        keys = [(r["subject"], r["relation"], r["object"]) for r in out]
        assert keys == [("A", "r", "B"), ("A", "r", "C"), ("A", "s", "B")]

    def test_no_duplicates_is_a_noop(self):
        rows = [_row("A", "r", "B"), _row("C", "s", "D")]
        out = common.dedup_engine_atoms(rows)
        assert out == rows

    def test_object_differs_by_case_or_value_not_collapsed(self):
        rows = [_row("A", "r", "B"), _row("A", "r", "b")]
        out = common.dedup_engine_atoms(rows)
        assert len(out) == 2

    def test_empty_input(self):
        assert common.dedup_engine_atoms([]) == []
