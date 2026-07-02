# SPDX-License-Identifier: Apache-2.0
"""Unit tests for alias-canonicalization in conflict detection (#227).

``check_conflicts.detect_conflicts`` must collapse surface variants of a
single-valued relation (e.g. ``게재연도`` and ``발행년도`` both aliased to
``published_year``) into one conflict key, so cross-variant contradictions are
caught.  KBs without an alias file (aliases={}) must reproduce pre-#227
behaviour byte-for-byte — including preserving NFD relation names verbatim.
"""
from __future__ import annotations

import unicodedata

import check_conflicts
import common


def _fact(subject: str, relation: str, obj: str, status: str = "confirmed") -> dict[str, str]:
    return {
        "subject": subject,
        "relation": relation,
        "object": obj,
        "source": "sources/x.md",
        "status": status,
        "confidence": "0.9",
        "note": "",
    }


# Aliases: two surface variants both map to one canonical name.
_ALIASES = {
    "게재연도": "published_year",
    "발행년도": "published_year",
}

# A typed amount spec keyed on the canonical name (mirrors typed_relations output).
_AMOUNT_SPEC = common.TypedRelSpec("amount", "revenue")
_TYPED_ON_CANONICAL = {"published_year": _AMOUNT_SPEC}

# Single-valued declared on the canonical name.
_SV_CANONICAL = {"published_year"}


class TestCrossVariantConflict:
    """Cross-variant contradictions collapse to one (subject, canonical) key."""

    def test_cross_variant_different_objects_detected(self):
        # 게재연도/2005 + 발행년도/2007, both → published_year, single-valued.
        # Must yield ONE conflict on (subject, "published_year") with 2 values.
        facts = [
            _fact("논문A", "게재연도", "2005"),
            _fact("논문A", "발행년도", "2007"),
        ]
        conflicts = check_conflicts.detect_conflicts(facts, _SV_CANONICAL, {}, _ALIASES)
        assert list(conflicts) == [("논문A", "published_year")]
        assert conflicts[("논문A", "published_year")] == ["2005", "2007"]

    def test_cross_variant_same_object_no_conflict(self):
        # Same value expressed via two surface variants → still one value, no conflict.
        facts = [
            _fact("논문A", "게재연도", "2005"),
            _fact("논문A", "발행년도", "2005"),
        ]
        conflicts = check_conflicts.detect_conflicts(facts, _SV_CANONICAL, {}, _ALIASES)
        assert conflicts == {}

    def test_single_variant_same_object_no_conflict(self):
        # Two rows with same variant and same value → no conflict.
        facts = [
            _fact("논문A", "게재연도", "2005"),
            _fact("논문A", "게재연도", "2005"),
        ]
        conflicts = check_conflicts.detect_conflicts(facts, _SV_CANONICAL, {}, _ALIASES)
        assert conflicts == {}

    def test_canonical_name_used_directly_collides_with_alias_variant(self):
        # If the KB stores published_year directly AND a surface variant with a
        # different value → conflict under the canonical name.
        facts = [
            _fact("논문A", "published_year", "2010"),
            _fact("논문A", "게재연도", "2005"),
        ]
        conflicts = check_conflicts.detect_conflicts(facts, _SV_CANONICAL, {}, _ALIASES)
        assert list(conflicts) == [("논문A", "published_year")]
        assert conflicts[("논문A", "published_year")] == ["2005", "2010"]

    def test_three_subjects_independent(self):
        # Conflicts per-subject: 논문A conflicts, 논문B does not.
        facts = [
            _fact("논문A", "게재연도", "2005"),
            _fact("논문A", "발행년도", "2007"),
            _fact("논문B", "게재연도", "2010"),
            _fact("논문B", "발행년도", "2010"),
        ]
        conflicts = check_conflicts.detect_conflicts(facts, _SV_CANONICAL, {}, _ALIASES)
        assert set(conflicts) == {("논문A", "published_year")}

    def test_sv_declared_on_canonical_detects_alias_variant(self):
        # Declaring single-valued on the canonical name catches variants.
        facts = [
            _fact("논문A", "게재연도", "2005"),
            _fact("논문A", "게재연도", "2008"),
        ]
        conflicts = check_conflicts.detect_conflicts(facts, {"published_year"}, {}, _ALIASES)
        assert list(conflicts) == [("논문A", "published_year")]

    def test_sv_declared_on_variant_also_works(self):
        # Declaring single-valued on a surface variant: _canonicalize maps it
        # to the canonical, so the sv set contains published_year, and cross-
        # variant conflicts are still caught.
        facts = [
            _fact("논문A", "게재연도", "2005"),
            _fact("논문A", "발행년도", "2007"),
        ]
        conflicts = check_conflicts.detect_conflicts(facts, {"게재연도"}, {}, _ALIASES)
        assert list(conflicts) == [("논문A", "published_year")]


class TestTypedEqualAcrossVariants:
    """Typed-equal values across alias variants must NOT produce a conflict."""

    def test_typed_equal_different_notation_across_variants(self):
        # 게재연도/amount(5400,"억") + 발행년도/amount(0.54,"조") → same scalar → no conflict.
        facts = [
            _fact("갑사", "게재연도", 'amount(5400,"억")'),
            _fact("갑사", "발행년도", 'amount(0.54,"조")'),
        ]
        conflicts = check_conflicts.detect_conflicts(
            facts, _SV_CANONICAL, _TYPED_ON_CANONICAL, _ALIASES
        )
        assert conflicts == {}

    def test_typed_equal_same_notation_across_variants(self):
        facts = [
            _fact("갑사", "게재연도", 'amount(5400,"억")'),
            _fact("갑사", "발행년도", 'amount(5400,"억")'),
        ]
        conflicts = check_conflicts.detect_conflicts(
            facts, _SV_CANONICAL, _TYPED_ON_CANONICAL, _ALIASES
        )
        assert conflicts == {}


class TestTypedDifferentAcrossVariants:
    """Typed-different values across alias variants must produce a conflict
    with verbatim object representatives."""

    def test_typed_different_5000_vs_5400_across_variants(self):
        # 5000억 vs 5400억 are genuinely different scalars → conflict, 2 reps.
        facts = [
            _fact("갑사", "게재연도", 'amount(5000,"억")'),
            _fact("갑사", "발행년도", 'amount(5400,"억")'),
        ]
        conflicts = check_conflicts.detect_conflicts(
            facts, _SV_CANONICAL, _TYPED_ON_CANONICAL, _ALIASES
        )
        assert list(conflicts) == [("갑사", "published_year")]
        reps = conflicts[("갑사", "published_year")]
        assert len(reps) == 2
        assert reps == ['amount(5000,"억")', 'amount(5400,"억")']

    def test_typed_different_multi_row_two_distinct_scalars(self):
        # Three rows: 5000억 (once), 5400억 (once), 0.54조 (= 5400억, once).
        # Distinct scalars: 5000억 and 5400억 → 2 conflict reps.
        facts = [
            _fact("갑사", "게재연도", 'amount(5000,"억")'),
            _fact("갑사", "발행년도", 'amount(5400,"억")'),
            _fact("갑사", "게재연도", 'amount(0.54,"조")'),
        ]
        conflicts = check_conflicts.detect_conflicts(
            facts, _SV_CANONICAL, _TYPED_ON_CANONICAL, _ALIASES
        )
        reps = conflicts[("갑사", "published_year")]
        assert len(reps) == 2
        # sort-min representative per scalar group
        assert reps == ['amount(0.54,"조")', 'amount(5000,"억")']


class TestNoAliasOptIn:
    """aliases={} (or omitted) reproduces #208/#210 behaviour byte-for-byte."""

    def test_plain_single_valued_conflict_without_aliases(self):
        # A plain string conflict with no alias file in play.
        facts = [
            _fact("을서비스", "주_속성", "값가"),
            _fact("을서비스", "주_속성", "값나"),
        ]
        conflicts = check_conflicts.detect_conflicts(facts, {"주_속성"}, {}, {})
        assert conflicts == {("을서비스", "주_속성"): ["값가", "값나"]}

    def test_aliases_none_same_as_empty(self):
        # aliases=None is treated identically to aliases={}.
        facts = [
            _fact("을서비스", "주_속성", "값가"),
            _fact("을서비스", "주_속성", "값나"),
        ]
        c1 = check_conflicts.detect_conflicts(facts, {"주_속성"}, {}, None)
        c2 = check_conflicts.detect_conflicts(facts, {"주_속성"}, {}, {})
        assert c1 == c2

    def test_nfd_relation_key_preserved_when_no_aliases(self):
        # #210 regression guard: an NFD relation name must be reported exactly
        # as written (NFD) when it does not participate in any alias map.
        nfd_rel = unicodedata.normalize("NFD", "매출")
        assert nfd_rel != "매출"  # sanity: genuinely NFD
        facts = [
            _fact("갑사", nfd_rel, 'amount(5000,"억")'),
            _fact("갑사", nfd_rel, 'amount(5400,"억")'),
        ]
        _TYPED_NFD = {"매출": _AMOUNT_SPEC}  # NFC-keyed typed spec
        conflicts = check_conflicts.detect_conflicts(facts, {nfd_rel}, _TYPED_NFD, {})
        # Key must be NFD (verbatim), not silently NFC-coerced.
        assert list(conflicts) == [("갑사", nfd_rel)]
        assert conflicts[("갑사", nfd_rel)] == ['amount(5000,"억")', 'amount(5400,"억")']

    def test_cross_variant_not_detected_without_aliases(self):
        # Without an alias map the two surface variants are independent relations;
        # neither has two values → no conflict.
        facts = [
            _fact("논문A", "게재연도", "2005"),
            _fact("논문A", "발행년도", "2007"),
        ]
        # single_valued declared on canonical — but no aliases → variants unknown.
        conflicts = check_conflicts.detect_conflicts(facts, {"published_year"}, {}, {})
        assert conflicts == {}


class TestNfdVariantUnderAlias:
    """NFD-authored surface variant (macOS) must still map to the canonical."""

    def test_nfd_variant_collides_with_nfc_variant_under_canonical(self):
        # aliases keys are NFC; an NFD fact row for a variant must still
        # canonicalize via NFC lookup → collides with an NFC variant row.
        nfd_게재연도 = unicodedata.normalize("NFD", "게재연도")
        assert nfd_게재연도 != "게재연도"  # sanity
        facts = [
            _fact("논문A", nfd_게재연도, "2005"),   # NFD variant key
            _fact("논문A", "발행년도", "2007"),      # NFC variant key
        ]
        conflicts = check_conflicts.detect_conflicts(facts, _SV_CANONICAL, {}, _ALIASES)
        assert list(conflicts) == [("논문A", "published_year")]
        assert conflicts[("논문A", "published_year")] == ["2005", "2007"]
