# SPDX-License-Identifier: Apache-2.0
"""``factlog status`` counts engine ATOMS, not engine-eligible rows (#372).

``compile_facts`` writes ``dedup_engine_atoms(engine_facts(facts))`` to
``facts/accepted.dl`` and its log reports that folded number. ``status`` counted
rows, so a KB holding one name in two canonically equivalent spellings read 3
here and 2 in the file — a contradiction a user hits by opening the file and
counting, with no judgement in between.

``common.engine_atom_key`` folds subject, relation, and object under NFC. Alias
names remain separate because this is canonical normalization, not semantic
renaming.
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from factlog.cli import _init_kb, _recompile_accepted, cmd_status  # noqa: E402

HEADER = "subject,relation,object,source,status,confidence,note\n"


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _nfd(value: str) -> str:
    return unicodedata.normalize("NFD", value)


def _kb(tmp_path, capsys, rows, sources=("a.md",)):
    kb = tmp_path / "kb"
    _init_kb(kb)
    for name in sources:
        (kb / "sources" / name).write_text("x\n", encoding="utf-8")
    (kb / "facts" / "candidates.csv").write_text(
        HEADER + "".join(f"{s},{r},{o},sources/{src},{st},0.9,\n" for s, r, o, src, st in rows),
        encoding="utf-8",
    )
    capsys.readouterr()
    return kb


def _status_lines(kb, capsys):
    assert cmd_status(argparse.Namespace(target=str(kb))) == 0
    return capsys.readouterr().out.splitlines()


def _line(lines, prefix):
    return next(line for line in lines if line.strip().startswith(prefix))


@pytest.fixture()
def folded_kb(tmp_path, capsys):
    """One fact in two spellings from two sources, plus an unrelated fact.

    Relation is the same object in both rows, so the two spellings fold.

    The ``needs_review`` row is load-bearing: it keeps the candidate count (4)
    apart from the engine-row count (3), so an implementation that folds
    against ``len(facts)`` instead of ``len(engine_rows)`` prints the wrong
    number in the suffix. With an all-``accepted`` fixture the two are equal
    and that mutation survives.
    """
    return _kb(
        tmp_path,
        capsys,
        [
            (_nfc("삼성"), "대표", _nfc("이재용"), "a.md", "accepted"),
            (_nfd("삼성"), "대표", _nfd("이재용"), "b.md", "accepted"),
            ("갑", "관계", "을", "a.md", "accepted"),
            ("병", "관계", "정", "a.md", "needs_review"),
        ],
        sources=("a.md", "b.md"),
    )


def test_canonically_equivalent_rows_are_one_engine_fact(folded_kb, capsys):
    facts = _line(_status_lines(folded_kb, capsys), "facts:")
    assert "2 engine fact(s)" in facts
    assert "3 engine fact(s)" not in facts
    # the row count stays visible on the same line, so nothing is hidden
    assert "4 candidate(s)" in facts


def test_the_count_says_it_folded(folded_kb, capsys):
    facts = _line(_status_lines(folded_kb, capsys), "facts:")
    assert "(folded from 3 row(s))" in facts


def test_status_count_matches_compiled_accepted_dl(folded_kb, capsys):
    """The claim #372 actually makes: the two numbers agree.

    Complements the literal assertions above rather than replacing them — a
    mutation that moves BOTH sides (changing engine_atom_key itself) keeps this
    green, and the literals catch that.
    """
    assert _recompile_accepted(folded_kb, "test") is True
    capsys.readouterr()
    compiled = sum(
        1
        for line in (folded_kb / "facts" / "accepted.dl").read_text(encoding="utf-8").splitlines()
        if line.startswith("relation(")
    )
    facts = _line(_status_lines(folded_kb, capsys), "facts:")
    assert f"{compiled} engine fact(s)" in facts


def test_folding_does_not_shrink_source_coverage(folded_kb, capsys):
    """dedup keeps only the first row of a group, so folding the shared
    engine_rows list would drop the source only the losing spelling cited."""
    sources = _line(_status_lines(folded_kb, capsys), "sources:")
    assert "2 file(s), 2 with facts" in sources


def test_a_kb_with_nothing_to_fold_is_unchanged(tmp_path, capsys):
    # needs_review row again: without it len(facts) == len(engine_rows) and a
    # suffix keyed on len(facts) would still print nothing here, hiding the bug.
    kb = _kb(
        tmp_path,
        capsys,
        [
            ("갑", "관계", "을", "a.md", "accepted"),
            ("병", "관계", "정", "a.md", "accepted"),
            ("무", "관계", "기", "a.md", "needs_review"),
        ],
    )
    facts = _line(_status_lines(kb, capsys), "facts:")
    assert "2 engine fact(s)" in facts
    assert "folded from" not in facts


def test_relation_spellings_fold_into_the_same_engine_fact(tmp_path, capsys):
    kb = _kb(
        tmp_path,
        capsys,
        [
            (_nfc("삼성"), _nfc("대표"), _nfc("이재용"), "a.md", "accepted"),
            (_nfd("삼성"), _nfd("대표"), _nfd("이재용"), "a.md", "accepted"),
        ],
    )
    facts = _line(_status_lines(kb, capsys), "facts:")
    assert "1 engine fact(s)" in facts
    assert "(folded from 2 row(s))" in facts
