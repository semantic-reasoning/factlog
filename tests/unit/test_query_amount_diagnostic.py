# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from factlog.common import query_amount_digit_near_matches


def rows(*objects: str) -> list[dict[str, str]]:
    return [
        {"subject": "A", "relation": "금액", "object": object_}
        for object_ in objects
    ]


def query(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'relation("A", "금액", "{escaped}")?'


def test_legacy_fullwidth_amount_quoting_near_match_is_found():
    written = "amount(１００,억)"
    accepted = 'amount(１００,"억")'
    assert query_amount_digit_near_matches(query(written), rows(accepted)) == (
        (written, accepted),
    )


def test_comma_and_spacing_differences_follow_legacy_canonicalization():
    written = "amount(１,０００, 억)"
    accepted = 'amount(１０００,"억")'
    assert query_amount_digit_near_matches(query(written), rows(accepted)) == (
        (written, accepted),
    )


def test_different_digits_number_unit_or_compound_type_do_not_match():
    accepted = rows('amount(１００,"억")')
    for value in (
        "amount(١٠٠,억)",
        "amount(２００,억)",
        "amount(１００,조)",
        "number(１００)",
        "제１분기",
        "１００억",
        "amount(100,억１)",
    ):
        assert query_amount_digit_near_matches(query(value), accepted) == ()


def test_ascii_query_and_exact_fullwidth_spelling_do_not_warn():
    accepted = rows('amount(１００,"억")', 'amount(100,"억")')
    assert query_amount_digit_near_matches(query('amount(１００,"억")'), accepted) == ()
    assert query_amount_digit_near_matches(query("amount(100,억)"), accepted) == ()


def test_unknown_identifier_with_non_ascii_digits_does_not_warn():
    assert query_amount_digit_near_matches(
        'relation("Model４", "금액", O)?', rows('amount(１００,"억")')
    ) == ()


def test_unrelated_subject_relation_arity_or_predicate_do_not_warn():
    accepted = rows('amount(１００,"억")')
    assert query_amount_digit_near_matches(
        'relation("B", "금액", "amount(１００,억)")?', accepted
    ) == ()
    assert query_amount_digit_near_matches(
        'relation("A", "예산", "amount(１００,억)")?', accepted
    ) == ()
    assert query_amount_digit_near_matches(
        'relation("A", "금액", "amount(１００,억)", X)?', accepted
    ) == ()
    assert query_amount_digit_near_matches(
        'path("A", "amount(１００,억)")?', accepted
    ) == ()


def test_amount_canonicalization_does_not_merge_relation_names():
    facts = [
        {
            "subject": "A",
            "relation": 'amount(1000,"억")',
            "object": 'amount(１００,"억")',
        }
    ]
    line = 'relation("A", "amount(1,000,\\"억\\")", "amount(１００,억)")?'
    assert query_amount_digit_near_matches(line, facts) == ()


def test_matches_are_deduplicated_and_sorted():
    facts = rows('amount(２００,"억")', 'amount(１００,"억")', 'amount(１００,"억")')
    line = 'relation("A", "금액", "amount(１００,억)")?'
    assert query_amount_digit_near_matches(line, facts) == (
        ("amount(１００,억)", 'amount(１００,"억")'),
    )
