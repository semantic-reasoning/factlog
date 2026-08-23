# SPDX-License-Identifier: Apache-2.0
"""Engine-independent coverage of the typed-projection insert loop (#126).

`_project_typed_relations(session, specs, accepted)` is the pure-Python core of
run_wirelog()'s typed-relation side-projection: it touches the session only via
intern()/insert(), never step()/close(). That lets these tests drive it with a
FakeSession that merely RECORDS inserts — no pyrewire, no engine, no monkeypatch,
no path globals. They pin the projection contract: which
(alias, intern(subject), scalar) tuples reach session.insert(), that a non-parsing
object is skipped + warned (the fact still loads untyped), that the scalar is a
bare int (never interned), and that the deterministic (relation, subject, object)
sort is load-bearing.

The pyrewire-gated e2e in test_typed_projection.py stays the authority on real
engine inference; this file owns the pure projection logic.
"""
from __future__ import annotations

import random
import unicodedata

import common


class FakeSession:
    """Records inserts; never touches engine internals.

    intern() hands back a stable, distinguishable id per value (same value ->
    same id, distinct values -> distinct ids) so a test can reverse-map an
    interned id back to its source string. step()/close() are intentionally
    omitted — _project_typed_relations never calls them.
    """

    def __init__(self):
        self.inserts: list[tuple[str, tuple]] = []
        self._ids: dict[object, int] = {}

    def intern(self, value):
        return self._ids.setdefault(value, len(self._ids))

    def insert(self, alias, payload):
        self.inserts.append((alias, payload))


# Two typed relations: a date (정식_운영 -> launch_date) and a number
# (버전 -> version_num). TypedRelSpec is (type, alias, units=None).
SPECS = {
    "정식_운영": common.TypedRelSpec("date", "launch_date"),
    "버전": common.TypedRelSpec("number", "version_num"),
}


def _row(subject: str, relation: str, object_: str) -> dict[str, str]:
    # Same dict shape _load_accepted_facts_from produces (subject/relation/object).
    return {"subject": subject, "relation": relation, "object": object_}


def _decode_inserts(session: FakeSession) -> set[tuple[str, str, int]]:
    """Reverse-map each recorded (alias, (interned_subject, scalar)) insert back to
    (alias, subject_string, scalar) so a test asserts the REAL projected identity,
    not whatever happened to be interned. Also proves payload[0] is a genuine
    intern() output and payload[1] is a bare int that was NOT interned."""
    id_to_value = {v: k for k, v in session._ids.items()}
    decoded: set[tuple[str, str, int]] = set()
    for alias, payload in session.inserts:
        subject_id, scalar = payload
        assert subject_id in id_to_value          # payload[0] is an interned id
        assert isinstance(scalar, int) and not isinstance(scalar, bool)
        assert scalar not in session._ids         # payload[1] was never interned
        decoded.add((alias, id_to_value[subject_id], scalar))
    return decoded


def test_insert_set_skips_nonparsing_row_and_warns(capsys):
    # A parseable date, a NON-parseable date (미정 -> None -> skip+warn), and a
    # parseable number. Only the two parseable rows should project.
    accepted = [
        _row("갑서비스", "정식_운영", "2030.1"),   # date 20300101
        _row("병서비스", "정식_운영", "미정"),      # does NOT parse -> skip + warn
        _row("appA", "버전", "2.5"),                # number 2500 (×1000)
    ]
    fake = FakeSession()

    common._project_typed_relations(fake, SPECS, accepted)

    decoded = _decode_inserts(fake)
    # EXACT set: only the two parseable rows project.
    assert decoded == {
        ("launch_date", "갑서비스", 20300101),
        ("version_num", "appA", 2500),
    }
    # Anti-masking: the skipped subject appears in NO insert.
    assert all(subject != "병서비스" for _alias, subject, _scalar in decoded)

    err = capsys.readouterr().err
    assert "does not parse" in err   # the skip warning fired
    assert "미정" in err              # names the offending value
    assert "병서비스" in err           # names the offending subject


def test_shuffled_accepted_inserts_in_sorted_key_order():
    # The projection sorts by (relation, subject, object); the input order does
    # not. Shuffle a list whose sorted order differs from its input order so that,
    # if sorted(...) were dropped, the insert order would flip.
    accepted = [
        _row("z앱", "버전", "2.5"),                 # number 2500
        _row("을서비스", "정식_운영", "2029.6"),    # date 20290601
        _row("갑서비스", "정식_운영", "2030.1"),    # date 20300101
    ]
    # Deterministic non-sorted input order (seed chosen so input != sorted).
    random.Random(7).shuffle(accepted)
    fake = FakeSession()

    common._project_typed_relations(fake, SPECS, accepted)

    id_to_value = {v: k for k, v in fake._ids.items()}
    ordered = [
        (alias, id_to_value[payload[0]], payload[1])
        for alias, payload in fake.inserts
    ]
    # LIST equality (ordered): inserts come out in sorted (relation, subject,
    # object) order regardless of input order. 버전 < 정식_운영 (ASCII < Hangul);
    # within 정식_운영, 갑서비스 < 을서비스 in Python string order.
    assert ordered == [
        ("version_num", "z앱", 2500),
        ("launch_date", "갑서비스", 20300101),
        ("launch_date", "을서비스", 20290601),
    ]


# --- #387: projection shares the conflict core's NFC + alias boundary --------


def _nfd(value: str) -> str:
    return unicodedata.normalize("NFD", value)


_ORDINAL = {"순위": common.TypedRelSpec("ordinal", "rank")}


def test_nfc_relation_and_nfd_object_project_without_warning(capsys):
    accepted = [_row("갑", "순위", _nfd("제3호")), _row("갑", "순위", "3위")]
    fake = FakeSession()
    common._project_typed_relations(fake, _ORDINAL, accepted)
    assert fake.inserts == [("rank", (0, 3)), ("rank", (0, 3))]
    assert capsys.readouterr().err == ""


def test_uniformly_nfd_relation_and_objects_project(capsys):
    accepted = [
        _row("갑", _nfd("순위"), _nfd("제3호")),
        _row("갑", _nfd("순위"), "3위"),
    ]
    fake = FakeSession()
    common._project_typed_relations(fake, _ORDINAL, accepted)
    assert fake.inserts == [("rank", (0, 3)), ("rank", (0, 3))]
    assert capsys.readouterr().err == ""


def test_dedup_preserves_authored_relation_but_both_atoms_project(capsys):
    accepted = common.dedup_engine_atoms(
        [
            _row("갑", _nfd("순위"), "3위"),
            _row("을", "순위", "4위"),
        ]
    )
    assert [row["relation"] for row in accepted] == [_nfd("순위"), "순위"]

    fake = FakeSession()
    common._project_typed_relations(fake, _ORDINAL, accepted)
    assert _decode_inserts(fake) == {("rank", "갑", 3), ("rank", "을", 4)}
    assert capsys.readouterr().err == ""


def test_alias_surface_uses_canonical_spec_and_canonical_wins(capsys):
    surface = "게재순위"
    canonical = "순위"
    aliases = {surface: canonical}
    canonical_spec = common.TypedRelSpec("ordinal", "canonical_rank")
    surface_spec = common.TypedRelSpec("ordinal", "surface_rank")
    specs = {canonical: canonical_spec, surface: surface_spec}
    fake = FakeSession()

    common._project_typed_relations(
        fake,
        specs,
        [_row("갑", _nfd(surface), _nfd("제3호"))],
        aliases=aliases,
    )

    assert _decode_inserts(fake) == {("canonical_rank", "갑", 3)}
    assert capsys.readouterr().err == ""


def test_surface_spec_is_fallback_when_canonical_spec_is_absent():
    surface = "게재순위"
    fake = FakeSession()
    common._project_typed_relations(
        fake,
        {surface: common.TypedRelSpec("ordinal", "surface_rank")},
        [_row("갑", _nfd(surface), "3위")],
        aliases={surface: "순위"},
    )
    assert _decode_inserts(fake) == {("surface_rank", "갑", 3)}


def test_alias_custom_units_and_nfd_object_use_canonical_spec(capsys):
    spec = common.TypedRelSpec(
        "amount", "budget_minor", {"달러": 100, "센트": 1}
    )
    fake = FakeSession()
    common._project_typed_relations(
        fake,
        {"예산": spec},
        [_row("갑", _nfd("책정액"), _nfd("2달러"))],
        aliases={"책정액": "예산"},
    )
    assert _decode_inserts(fake) == {("budget_minor", "갑", 200)}
    assert capsys.readouterr().err == ""


def test_invalid_value_warns_with_authored_relation_and_object(capsys):
    relation = _nfd("순위")
    object_ = _nfd("미정")
    fake = FakeSession()
    common._project_typed_relations(
        fake, _ORDINAL, [_row("갑", relation, object_)]
    )
    assert fake.inserts == []
    err = capsys.readouterr().err
    assert repr(relation) in err
    assert repr(object_) in err
    assert err.count("does not parse") == 1


def test_non_ascii_digits_still_reject_with_authored_marker(capsys):
    object_ = "제３호"
    fake = FakeSession()
    common._project_typed_relations(fake, _ORDINAL, [_row("갑", "순위", object_)])
    assert fake.inserts == []
    err = capsys.readouterr().err
    assert repr(object_) in err
    assert "\\uff13" in err
    assert err.count("does not parse") == 1


def test_case_and_nfkc_relation_lookalikes_do_not_find_a_spec(capsys):
    specs = {"Rank": common.TypedRelSpec("ordinal", "rank")}
    fake = FakeSession()
    common._project_typed_relations(
        fake,
        specs,
        [_row("갑", "rank", "3위"), _row("을", "Ｒａｎｋ", "4위")],
    )
    assert fake.inserts == []
    assert capsys.readouterr().err == ""
