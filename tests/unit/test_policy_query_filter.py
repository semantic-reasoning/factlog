# SPDX-License-Identifier: Apache-2.0
"""Regression tests: a policy query's quoted constants must FILTER rows (#326).

``policy_result_line`` printed the whole extent of the policy predicate no
matter which entity the query pinned, so ``needs_review("Bob", R)?`` reported
three rows for a Bob the engine inferred NOTHING about — other subjects' reasons
rendered as Bob's. The report is the artifact SKILL.md tells the reader to show
verbatim before stating a conclusion, so a fabricated positive there is not a
cosmetic defect.

The filter must apply at EVERY argument position, not just the first: fixing
only ``args[0]`` would leave ``pred(E, "stale")?`` mis-attributing rows while
making the first-argument form accurate — which removes the only signal a reader
had that the second line is untrustworthy.

``ask_router.evaluate`` (the ``ask`` path) had the same defect at positions
other than the first. The parity class below pins the two paths together.

FACTLOG_ROOT is bound to a throwaway dir by ``tests/unit/conftest.py`` BEFORE
any tool module is imported, which matters here: ``ask_router`` re-exports
``FACTLOG_ROOT`` at import time from argv/env, so without that pin the parity
test would read the developer's real knowledge base.
"""
from __future__ import annotations

import json
import re
import unicodedata

import pytest

import ask_router
import run_logic_check as rlc
from common import canonical_value

PREDICATE = "needs_review"
INFERRED = {
    PREDICATE: {
        ("Alice", "low_conf"),
        ("Carol", "stale"),
        ("Dave", "no_source"),
    }
}


def _row_count(report_line: str) -> int:
    """Extract N from '<pred> results ...: N rows; ...'."""
    match = re.search(r"(\d+) rows", report_line)
    assert match, f"unparseable result line: {report_line!r}"
    return int(match.group(1))


def _report_rows(draft: str, inferred=None) -> int:
    return _row_count(rlc.policy_result_line(PREDICATE, draft, inferred or INFERRED))


def _router_rows(monkeypatch, draft: str, inferred=None) -> int:
    monkeypatch.setattr(ask_router, "policy_predicates", lambda program: {PREDICATE})
    monkeypatch.setattr(ask_router, "run_wirelog", lambda: inferred or INFERRED)
    return ask_router.evaluate(draft, [])["count"]


class TestPolicyResultLineFiltersFixedEntity:
    def test_named_entity_reports_only_its_own_rows(self):
        line = rlc.policy_result_line(PREDICATE, f'{PREDICATE}("Alice", R)?', INFERRED)
        assert _row_count(line) == 1
        assert "low_conf" in line
        assert "stale" not in line and "no_source" not in line

    def test_entity_with_no_inferred_rows_reports_zero(self):
        line = rlc.policy_result_line(PREDICATE, f'{PREDICATE}("Bob", R)?', INFERRED)
        assert _row_count(line) == 0
        assert "low_conf" not in line and "stale" not in line and "no_source" not in line

    def test_second_argument_constant_also_filters(self):
        # The defect is not first-argument-specific: a reason-pinned query must
        # not report the other reasons' rows either.
        line = rlc.policy_result_line(PREDICATE, f'{PREDICATE}(E, "stale")?', INFERRED)
        assert _row_count(line) == 1
        assert "Carol" in line
        assert "Alice" not in line and "Dave" not in line

    def test_second_argument_constant_with_no_match_reports_zero(self):
        line = rlc.policy_result_line(PREDICATE, f'{PREDICATE}(E, "missing_reason")?', INFERRED)
        assert _row_count(line) == 0

    def test_both_arguments_constant_matching_row(self):
        line = rlc.policy_result_line(PREDICATE, f'{PREDICATE}("Carol", "stale")?', INFERRED)
        assert _row_count(line) == 1

    def test_both_arguments_constant_crossed_pair_reports_zero(self):
        # Carol and low_conf each exist, but not together — a per-column filter
        # that ORed the positions would wrongly report a row here.
        line = rlc.policy_result_line(PREDICATE, f'{PREDICATE}("Carol", "low_conf")?', INFERRED)
        assert _row_count(line) == 0

    def test_all_variable_query_still_reports_full_extent(self):
        line = rlc.policy_result_line(PREDICATE, f"{PREDICATE}(E, R)?", INFERRED)
        assert _row_count(line) == 3
        assert "E=Alice, R=low_conf" in line

    # The 0-arity row case lives in TestReportRouterParity: asserting it on the
    # report alone let a router that dropped its short-row guard survive.


class TestReportRouterParity:
    """The report and the ``ask`` router must answer a policy query identically.

    Parity is NOT correctness: two paths can agree and both be wrong, which is
    exactly the state before this fix at non-first argument positions. So every
    case asserts the ABSOLUTE row count as well as the agreement, and the router
    side calls ``ask_router.evaluate`` directly rather than re-implementing the
    filter in the test (a re-implementation would prove nothing about either
    production path).
    """

    @pytest.mark.parametrize(
        ("draft", "expected"),
        [
            (f'{PREDICATE}("Alice", R)?', 1),
            (f'{PREDICATE}("Bob", R)?', 0),
            (f'{PREDICATE}(E, "stale")?', 1),
            (f'{PREDICATE}(E, "missing_reason")?', 0),
            (f'{PREDICATE}("Carol", "stale")?', 1),
            (f'{PREDICATE}("Carol", "low_conf")?', 0),
            (f"{PREDICATE}(E, R)?", 3),
        ],
    )
    def test_report_and_router_agree_on_the_verified_row_count(self, monkeypatch, draft, expected):
        report_rows = _report_rows(draft)
        router_rows = _router_rows(monkeypatch, draft)
        assert report_rows == expected
        assert router_rows == expected
        assert report_rows == router_rows

    def test_zero_arity_row_is_dropped_by_both_paths(self, monkeypatch):
        # The cases above are all 2-column rows, so neither path's short-row
        # guard is exercised by them: a router that dropped the guard kept
        # passing. A 0-arity row cannot satisfy a pinned constant, on EITHER path.
        inferred = {PREDICATE: {(), ("Alice", "low_conf")}}
        pinned = f'{PREDICATE}("Alice", R)?'
        assert _report_rows(pinned, inferred) == 1
        assert _router_rows(monkeypatch, pinned, inferred) == 1
        # Non-vacuous: the empty row IS in the extent both paths start from, so
        # the 1 above is a filter result, not an absent row.
        variables = f"{PREDICATE}(E, R)?"
        assert _report_rows(variables, inferred) == 2
        assert _router_rows(monkeypatch, variables, inferred) == 2

    def test_a_reason_code_in_the_other_normal_form_meets_the_row_on_both_paths(
        self, monkeypatch
    ):
        # #383. resolve_query_spellings has no _QUERY_VALUE_POSITIONS entry for a
        # policy predicate, so it treats position 1 as a KB value and moves the
        # constant onto whatever spelling the KB wrote — while the engine carries
        # the reason code exactly as logic-policy.extra.dl typed it. Comparing
        # raw there reported 0 rows under an extent line that had just said 1.
        nfd_reason = unicodedata.normalize("NFD", "보류")
        nfc_reason = unicodedata.normalize("NFC", "보류")
        assert nfd_reason != nfc_reason
        inferred = {PREDICATE: {("삼성", nfc_reason)}}
        for typed in (nfc_reason, nfd_reason):
            query = f'{PREDICATE}("삼성", "{typed}")?'
            assert _report_rows(query, inferred) == 1, typed
            assert _router_rows(monkeypatch, query, inferred) == 1, typed
        # Folding did not disable the filter: a genuinely different reason code
        # still reports nothing. Without this the "drop the position-1 filter"
        # mutation survives, which is the #326 fabricated positive.
        other = f'{PREDICATE}("삼성", "승인")?'
        assert _report_rows(other, inferred) == 0
        assert _router_rows(monkeypatch, other, inferred) == 0

    def test_position_1_folds_the_way_canonical_value_does_not_merely_nfc(
        self, monkeypatch
    ):
        # canonical_value is NFC *plus* literal_types.canonical_amount. A copy
        # that reached for unicodedata.normalize on its own passes every other
        # case here, because they are ASCII or Hangul; this one separates them.
        inferred = {PREDICATE: {("Alice", 'amount(1000,"억")')}}
        query = (
            f"{PREDICATE}(\"Alice\", "
            + json.dumps('amount(1,000,"억")', ensure_ascii=False)
            + ")?"
        )
        assert _report_rows(query, inferred) == 1
        assert _router_rows(monkeypatch, query, inferred) == 1

    def test_position_0_is_not_folded_on_either_path(self, monkeypatch):
        # The other half of #383's fix, and the half that is easy to "complete"
        # by mistake. Position 0 is the entity axis; resolve_query_spellings
        # already aligns it wherever the KB writes that value one way, so folding
        # here changes an answer ONLY where that map REFUSED the key — where
        # accepted.dl holds one value in two spellings. Measured on a KB reached
        # by a plain compile_facts run (merge_candidates canonicalises amounts on
        # the object only, so two amount-shaped subjects survive), a folded
        # position 0 returned the asked-for atom's row AND the other atom's,
        # indistinguishable because a constant position suppresses its binding.
        # classify_query's policy gate also compares args[0] raw, so folding here
        # alone answers positively for an entity the same report warns about.
        mine, theirs = 'amount(1,000,"억")', 'amount(1000,"억")'
        assert canonical_value(mine) == canonical_value(theirs)
        inferred = {PREDICATE: {(mine, "고평가"), (theirs, "저평가")}}
        query = f"{PREDICATE}({json.dumps(mine, ensure_ascii=False)}, R)?"
        assert _report_rows(query, inferred) == 1
        assert _router_rows(monkeypatch, query, inferred) == 1
        # Non-vacuous: the other atom's row is in the extent both paths start
        # from, so the 1 above is the raw comparison holding, not an absent row.
        variables = f"{PREDICATE}(E, R)?"
        assert _report_rows(variables, inferred) == 2
        assert _router_rows(monkeypatch, variables, inferred) == 2

    def test_nfd_stored_entity_does_not_meet_an_nfc_query_on_either_path(self, monkeypatch):
        # Position 0 compares RAW on both paths, so an NFD-stored entity is
        # invisible to an NFC-typed constant and the query reports 0 rows —
        # which reads as a verified negative. That reading is a real cost, and
        # it is NOT waiting to be paid off by folding here: the sibling
        # test_position_0_is_not_folded_on_either_path measures what folding
        # position 0 buys, which is another atom's rows returned under the
        # subject the user named, indistinguishable because a constant position
        # suppresses its binding.
        #
        # What remains reachable is the entity axis: an accepted.dl holding one
        # value in two spellings makes kb_query_spellings refuse that key, and
        # then this 0 sits under an extent line that counted the row. Closing it
        # means folding entity_set / engine_atom_key so the two atoms become one
        # — #213/#210, not this function.
        nfd = unicodedata.normalize("NFD", "박수영")
        nfc = unicodedata.normalize("NFC", "박수영")
        assert nfd != nfc
        inferred = {PREDICATE: {(nfd, "stale")}}
        nfc_query = f'{PREDICATE}("{nfc}", R)?'
        assert _report_rows(nfc_query, inferred) == 0
        assert _router_rows(monkeypatch, nfc_query, inferred) == 0
        # Non-vacuous: the row is reachable — an NFD-typed constant finds it on
        # both paths, so the 0 above is the position-0 raw comparison holding,
        # not an empty extent.
        nfd_query = f'{PREDICATE}("{nfd}", R)?'
        assert _report_rows(nfd_query, inferred) == 1
        assert _router_rows(monkeypatch, nfd_query, inferred) == 1
