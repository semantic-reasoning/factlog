# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import itertools
import unicodedata

import factlog.conflicts as conflicts
from factlog.common import TypedRelSpec


def row(subject, relation, object_, source, status="confirmed"):
    return {
        "subject": subject,
        "relation": relation,
        "object": object_,
        "source": source,
        "status": status,
        "confidence": "0.9",
        "note": "",
    }


def test_conflict_scan_shape_and_existing_projection_are_unchanged():
    assert conflicts.ConflictScan._fields == (
        "conflicts",
        "subject_variants",
        "object_variants",
        "parse_merges",
        "relation_variants",
        "object_relations",
    )
    pair = ("S", "r")
    scan = conflicts.collect_conflicts(
        [row("S", "r", "A", "a"), row("S", "r", "B", "b", "accepted")],
        {"r"},
    )
    assert scan == conflicts.ConflictScan(
        {pair: ["A", "B"]},
        {pair: ["S"]},
        {pair: {"A": ["A"], "B": ["B"]}},
        {},
        {},
        {pair: {"A": ["r"], "B": ["r"]}},
    )


def test_existing_conflict_projection_does_not_require_source_field():
    facts = [
        {"subject": "S", "relation": "r", "object": "A", "status": "confirmed"},
        {"subject": "S", "relation": "r", "object": "B", "status": "confirmed"},
    ]
    assert conflicts.collect_conflicts(facts, {"r"}).conflicts == {
        ("S", "r"): ["A", "B"]
    }


def test_typed_support_matches_conflict_keys_and_unions_exact_sources():
    nfd_ordinal = unicodedata.normalize("NFD", "제3호")
    facts = [
        row("갑사", "순위", nfd_ordinal, "sources/a.md#one"),
        row("갑사", "순위", "3위", "sources/b.md"),
        row("갑사", "순위", "4위", "sources/c.md"),
        row("갑사", "순위", "4위", "ignored", "candidate"),
        row("갑사", "순위", "5위", "ignored", "superseded"),
        row("갑사", "순위", "6위", "ignored", "needs_review"),
    ]
    typed = {"순위": TypedRelSpec("ordinal", "rank_value")}
    scan = conflicts.collect_conflicts(facts, {"순위"}, typed)
    support = conflicts.collect_conflict_support(facts, {"순위"}, typed)
    assert set(support) == set(scan.conflicts)
    pair = ("갑사", "순위")
    assert set(support[pair]) == set(scan.conflicts[pair])
    assert support[pair] == {
        "3위": ("sources/a.md#one", "sources/b.md"),
        "4위": ("sources/c.md",),
    }


def test_equivalent_typed_values_alone_are_not_contested_and_deduplicate_source():
    nfd_ordinal = unicodedata.normalize("NFD", "제3호")
    facts = [
        row("갑사", "순위", nfd_ordinal, "sources/a.md"),
        row("갑사", "순위", "3위", "sources/a.md", "accepted"),
    ]
    typed = {"순위": TypedRelSpec("ordinal", "rank_value")}
    assert conflicts.collect_conflict_support(facts, {"순위"}, typed) == {}
    facts.append(row("갑사", "순위", "4위", "sources/b.md"))
    assert conflicts.collect_conflict_support(facts, {"순위"}, typed)[("갑사", "순위")]["3위"] == (
        "sources/a.md",
    )


def test_aliases_group_under_canonical_relation_and_preserve_sources():
    facts = [
        row("S", "surface", "A", "z/source.md#L2"),
        row("S", "canonical", "B", "a/source.md"),
    ]
    support = conflicts.collect_conflict_support(
        facts, {"canonical"}, aliases={"surface": "canonical"}
    )
    assert support == {
        ("S", "canonical"): {
            "A": ("z/source.md#L2",),
            "B": ("a/source.md",),
        }
    }


def test_support_is_order_stable_and_uses_written_subject_representative():
    nfd_subject = unicodedata.normalize("NFD", "김철수")
    facts = [
        row(nfd_subject, "소속", "B", "z"),
        row("김철수", "소속", "A", "a", "accepted"),
        row("김철수", "소속", "B", "b"),
    ]
    expected = conflicts.collect_conflict_support(facts, {"소속"})
    assert next(iter(expected)) == ("김철수", "소속")
    assert list(expected[("김철수", "소속")]) == ["A", "B"]
    assert all(
        conflicts.collect_conflict_support(list(permutation), {"소속"}) == expected
        for permutation in itertools.permutations(facts)
    )


def test_each_public_projection_calls_the_shared_builder_once(monkeypatch):
    calls = 0
    original = conflicts._group_conflict_rows

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(conflicts, "_group_conflict_rows", counted)
    facts = [row("S", "r", "A", "a"), row("S", "r", "B", "b")]
    conflicts.collect_conflicts(facts, {"r"})
    assert calls == 1
    conflicts.collect_conflict_support(facts, {"r"})
    assert calls == 2
