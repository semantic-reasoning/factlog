# SPDX-License-Identifier: Apache-2.0
"""Regression tests for run_logic_check query evaluation (#99).

A comma inside a quoted object literal must not be split into extra args.
With the old naive ``split(",")`` parser these queries produced 0 rows even
though the fact exists; after delegating to common's string-aware parser they
resolve correctly.
"""
from __future__ import annotations

import json
import unicodedata

import run_logic_check as rlc


def _fact(subject, relation, object_):
    return {"subject": subject, "relation": relation, "object": object_}


class TestRelationResultsCommaLiteral:
    def test_object_with_comma_matches(self):
        facts = [_fact("A", "born_in", "Paris, France")]
        rows = rlc.relation_results('relation("A", "born_in", "Paris, France")?', facts)
        assert rows == [("A", "born_in", "Paris, France")]

    def test_object_with_comma_does_not_match_different_value(self):
        facts = [_fact("A", "born_in", "Paris, France")]
        rows = rlc.relation_results('relation("A", "born_in", "Lyon, France")?', facts)
        assert rows == []

    def test_variable_object_binds_comma_value(self):
        facts = [_fact("A", "born_in", "Paris, France")]
        rows = rlc.relation_results('relation("A", "born_in", O)?', facts)
        assert rows == [("A", "born_in", "Paris, France")]

    def test_plain_three_arg_still_works(self):
        facts = [_fact("A", "knows", "B")]
        rows = rlc.relation_results('relation("A", "knows", "B")?', facts)
        assert rows == [("A", "knows", "B")]

    def test_relation_name_matches_across_nfc_forms(self):
        relation = "소속"
        nfd_relation = unicodedata.normalize("NFD", relation)
        facts = [_fact("A", relation, "B")]
        rows = rlc.relation_results(
            f'relation("A", "{nfd_relation}", "B")?', facts
        )
        assert rows == [("A", relation, "B")]


class TestPredicateExactDispatch:
    """evaluate_queries must dispatch on the exact predicate, not a prefix.

    The branches used to select an evaluator with ``line.startswith("relation")``
    and friends. When a query predicate is only a *prefix* of the line's actual
    predicate (``relationship`` vs ``relation``, ``pathway`` vs ``path``), the
    startswith test drew the query into the wrong branch and printed a bogus
    VERIFIED-looking answer for a predicate validate_query already rejects as
    ``query unknown predicate``. Matching the predicate token exactly keeps those
    lines out of every evaluation branch, leaving the Errors section to speak.
    """

    def _run(self, monkeypatch, line, facts=None, inferred=None):
        monkeypatch.setattr(rlc, "query_lines", lambda: [line])
        return rlc.evaluate_queries(facts or [], inferred or {}, set())

    def test_relationship_does_not_enter_relation_branch(self, monkeypatch):
        facts = [_fact("A", "knows", "B")]
        assert self._run(monkeypatch, 'relationship("A", "knows", "B")?', facts) == []

    def test_pathway_does_not_enter_path_branch(self, monkeypatch):
        assert self._run(monkeypatch, 'pathway("A", "B")?', inferred={"path": {("A", "B")}}) == []

    def test_counter_does_not_enter_count_branch(self, monkeypatch):
        facts = [_fact("A", "knows", "B")]
        assert self._run(monkeypatch, 'counter("A", "knows")?', facts) == []

    def test_review_required_prefix_does_not_enter_review_branch(self, monkeypatch):
        assert self._run(monkeypatch, 'review_required_extra("q")?') == []

    def test_invalid_review_required_does_not_render_an_answer(self, monkeypatch):
        for line in [
            "review_required(Q)?",
            'review_required("a", "b")?',
            'review_required("")?',
        ]:
            assert self._run(monkeypatch, line) == []

    def test_exact_predicates_still_evaluate(self, monkeypatch):
        facts = [_fact("A", "knows", "B")]
        inferred = {"path": {("A", "B")}}
        assert self._run(monkeypatch, 'relation("A", "knows", "B")?', facts) == [
            "relation results: 1 rows; A, knows, B"
        ]
        assert self._run(monkeypatch, 'path("A", "B")?', facts, inferred) == ["path A -> B: A -> B"]
        assert self._run(monkeypatch, 'count("A", "knows")?', facts) == [
            'count results (query: count("A", "knows")?): 1 (distinct objects)'
        ]
        assert self._run(monkeypatch, 'review_required("q")?') == ["review_required: q"]

    def test_relation_and_count_reports_fold_relation_names(self, monkeypatch):
        relation = "소속"
        nfd_relation = unicodedata.normalize("NFD", relation)
        facts = [_fact("A", relation, "B")]
        assert self._run(
            monkeypatch, f'relation("A", "{nfd_relation}", O)?', facts
        ) == ["relation results: 1 rows; O=B"]
        assert self._run(
            monkeypatch, f'count("A", "{nfd_relation}")?', facts
        ) == [
            f'count results (query: count("A", "{nfd_relation}")?): '
            "1 (distinct objects)"
        ]

    def test_non_nfc_relation_equivalences_stay_distinct(self, monkeypatch):
        pairs = [
            ('amount(1,000,"억")', 'amount(1000,"억")'),
            ("rel", "REL"),
            ("rel", "ｒｅｌ"),
        ]
        for stored, queried in pairs:
            facts = [_fact("A", stored, "B")]
            relation_query = f'relation("A", {json.dumps(queried)}, O)?'
            count_query = f'count("A", {json.dumps(queried)})?'
            assert rlc.relation_results(relation_query, facts) == []
            assert self._run(monkeypatch, relation_query, facts) == [
                "relation results: 0 rows"
            ]
            assert self._run(monkeypatch, count_query, facts) == [
                f"count results (query: {count_query}): 0 (distinct objects)"
            ]
