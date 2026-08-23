# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unicodedata

import pytest

from factlog import conflicts, literal_types
from factlog.common import TypedRelSpec


def fact(relation: str, object_: str, source: str = "sources/a.md") -> dict[str, str]:
    return {
        "subject": "A",
        "relation": relation,
        "object": object_,
        "source": source,
        "status": "confirmed",
        "confidence": "0.9",
        "note": "",
    }


@pytest.mark.parametrize(
    "type_tag,raw,units",
    [
        ("date", "２０２０.１", None),
        ("number", "١٢٣", None),
        ("number", "𝟏𝟎𝟎", None),
        ("ordinal", "제३호", None),
        ("amount", "１００억", None),
        ("amount", 'amount(１２３,"억")', None),
    ],
)
def test_numeric_token_shadow_proves_supported_type_failures(type_tag, raw, units):
    assert literal_types.digit_width_causes_parse_failure(type_tag, raw, units)


@pytest.mark.parametrize(
    "type_tag,raw,units",
    [
        ("date", "제１분기", None),
        ("amount", 'amount(100,"억１")', {"억1": 100000000}),
        ("amount", 'amount(１００,"unknown")', {"억": 100000000}),
        ("number", "１２３oops", None),
    ],
)
def test_non_numeric_token_failures_are_not_attributed_to_width(type_tag, raw, units):
    assert not literal_types.digit_width_causes_parse_failure(type_tag, raw, units)


def test_sidecar_uses_actual_alias_rows_and_is_deterministic():
    aliases = {"게재연도": "published_year"}
    typed = {"published_year": TypedRelSpec("number", "pub_year")}
    rows = [fact("게재연도", "２０２０", "sources/b.md"), fact("published_year", "2021")]
    scans = [
        conflicts.collect_conflicts(order, {"published_year"}, typed, aliases)
        for order in (rows, list(reversed(rows)), rows + [rows[0]])
    ]
    results = [
        conflicts.collect_conflict_digit_width_offenders(scan, typed, aliases)
        for scan in scans
    ]
    assert results[0] == results[1] == results[2] == {
        ("A", "published_year"): (
            conflicts.DigitWidthOffender(
                "２０２０", "number", "\\uff12\\uff10\\uff12\\uff10"
            ),
        )
    }


def test_sidecar_resolves_nfd_surface_alias_to_canonical_spec():
    surface = "게재연도"
    nfd_surface = unicodedata.normalize("NFD", surface)
    aliases = {surface: "published_year"}
    typed = {"published_year": TypedRelSpec("number", "pub_year")}
    scan = conflicts.collect_conflicts(
        [fact(nfd_surface, "２０２０"), fact("published_year", "2021")],
        {"published_year"},
        typed,
        aliases,
    )
    assert conflicts.collect_conflict_digit_width_offenders(scan, typed, aliases)


def test_sidecar_does_not_borrow_spec_from_nonparticipating_relation():
    typed = {"published_year": TypedRelSpec("number", "pub_year")}
    scan = conflicts.collect_conflicts(
        [fact("게재연도", "２０２０"), fact("게재연도", "2021")],
        {"게재연도"},
        typed,
        {},
    )
    assert scan.conflicts
    assert conflicts.collect_conflict_digit_width_offenders(scan, typed, {}) == {}


def test_sidecar_checks_hidden_raw_variants_but_not_resolved_merges():
    nfd_unit = unicodedata.normalize("NFD", "억")
    typed = {"매출": TypedRelSpec("amount", "revenue")}
    rows = [fact("매출", "１００억"), fact("매출", "１００" + nfd_unit), fact("매출", "200억")]
    scan = conflicts.collect_conflicts(rows, {"매출"}, typed, {})
    offenders = conflicts.collect_conflict_digit_width_offenders(scan, typed, {})
    assert {item.value for item in offenders[("A", "매출")]} == {
        "１００억",
        "１００" + nfd_unit,
    }

    resolved = conflicts.collect_conflicts(
        [fact("매출", "100억"), fact("매출", 'amount(100,"억")')],
        {"매출"},
        typed,
        {},
    )
    assert not resolved.conflicts
    assert conflicts.collect_conflict_digit_width_offenders(resolved, typed, {}) == {}


def test_conflict_scan_public_shape_remains_six_fields():
    assert len(conflicts.ConflictScan._fields) == 6


def test_offender_marks_numeric_token_but_not_valid_digit_bearing_unit():
    typed = {
        "매출": TypedRelSpec("amount", "revenue", {"억１": 100000000})
    }
    raw = 'amount(１００,"억１")'
    scan = conflicts.collect_conflicts(
        [fact("매출", raw), fact("매출", 'amount(200,"억１")')],
        {"매출"},
        typed,
        {},
    )
    offender = conflicts.collect_conflict_digit_width_offenders(scan, typed, {})[
        ("A", "매출")
    ][0]
    assert offender.marked_value == 'amount(\\uff11\\uff10\\uff10,"억１")'
    assert "억\\uff11" not in offender.marked_value
    assert literal_types.normalize(
        "amount", literal_types.numeric_token_ascii_shadow("amount", raw), typed["매출"].units
    ) is not None


def test_marker_preserves_nfd_unit_and_distinguishes_raw_variants():
    nfd_unit = unicodedata.normalize("NFD", "억") + "１"
    typed = {"매출": TypedRelSpec("amount", "revenue", {"억１": 100000000})}
    nfd_raw = f'amount(１００,"{nfd_unit}")'
    nfc_raw = 'amount(１００,"억１")'
    scan = conflicts.collect_conflicts(
        [fact("매출", nfd_raw), fact("매출", nfc_raw), fact("매출", 'amount(200,"억１")')],
        {"매출"},
        typed,
        {},
    )
    marked = {
        offender.marked_value
        for offender in conflicts.collect_conflict_digit_width_offenders(
            scan, typed, {}
        )[("A", "매출")]
    }
    assert marked == {
        f'amount(\\uff11\\uff10\\uff10,"{nfd_unit}")',
        'amount(\\uff11\\uff10\\uff10,"억１")',
    }


def test_marker_preserves_nfd_ordinal_affixes_and_outer_whitespace():
    raw = "  " + unicodedata.normalize("NFD", "제") + "１" + unicodedata.normalize("NFD", "호") + "  "
    marked = literal_types.mark_numeric_token_non_ascii_digits("ordinal", raw)
    assert marked == raw.replace("１", "\\uff11")
    assert unicodedata.normalize("NFC", marked) != marked
