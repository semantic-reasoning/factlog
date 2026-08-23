#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Detect contradictions among engine-input facts.

A relation declared *single-valued* (functional) in policy/single-valued.md may
hold at most one object per subject. If two distinct objects are asserted for the
same (subject, relation) among engine-input facts (status confirmed/accepted;
'superseded' rows are ignored), that is a contradiction — the kind of silent rot
a plain notes wiki accumulates. This surfaces it deterministically.

Resolution is human-in-the-loop and non-destructive: mark the outdated row's
status as 'superseded' in facts/candidates.csv (it stays for audit, drops out of
engine input, and the conflict clears). A value carrying non-ASCII digits is the
exception: it does not parse, so supersession can clear the gate while keeping the
unreadable value (see non_ascii_digit_note).

Exit code: 0 if no conflicts, 1 if any conflict is found.

Usage:
    python3 check_conflicts.py [--wiki <kb>]
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from pathlib import Path

_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


# Resolve the KB root and export it before importing common, which binds
# its module-level paths from FACTLOG_ROOT at import time.
import factlog_config  # noqa: E402

os.environ["FACTLOG_ROOT"] = factlog_config.resolve_root_from_argv("--wiki")

import literal_types  # noqa: E402
from common import (  # noqa: E402
    TypedRelSpec,
    ensure_dirs,
    load_facts,
    normalization_form,
    relation_aliases,
    single_valued_relations,
    typed_relations,
)
from factlog.conflicts import (  # noqa: E402
    ConflictScan,
    _canonicalize,
    _fold,
    _fold_classes,
    _group_key,
    _group_key_unfolded,
    _representative,
    collect_conflicts,
    detect_conflicts,
)


def _form_label(value: str) -> str:
    """Name the Unicode normalization form *value* is written in.

    ``common.normalization_form``, not a local copy: ``factlog vocab`` labels the
    same forms for the same reason (two names that render identically), and a
    report that disagrees with another about which form a string is in is worse
    than one that says nothing. See that docstring for what ``"mixed"`` covers.
    """
    return normalization_form(value)


def _spellings(raws: list[str]) -> str:
    """Render *raws* as an escaped, form-labelled list for the report.

    Escaped because the whole difficulty of this conflict class is that the
    strings are indistinguishable on screen, so the code points are the only way
    to tell them apart; labelled because the code points alone do not say which
    form to unify *to*. The answer is on the CONFLICT line above —
    ``_representative`` already picked the NFC spelling — and the label is what
    connects the two.
    """
    return ", ".join(f"{ascii(s)} ({_form_label(s)})" for s in raws)


def _atom_count(members: list[str], relations: dict[str, list[str]]) -> int:
    """How many ``accepted.dl`` atoms the canonically equivalent *members* become.

    ``common.engine_atom_key`` is ``(NFC(subject), relation, NFC(object))``. Every
    member of a fold class shares ``NFC(object)`` by definition, and they all sit
    under one ``_fold(subject)`` bucket, so ``NFC(subject)`` is shared too. The
    relation is the one component the compiler leaves verbatim while this module
    canonicalizes it — so the atom count is exactly the number of distinct raw
    relation spellings the members were written under.
    """
    return len({rel for member in members for rel in relations.get(member, ())})


def _report_resolved_merges(scan: ConflictScan) -> None:
    """Disclose value groups whose Unicode fold *resolved* a contradiction.

    ``collect_conflicts`` keeps an object channel for a pair that ended up with a
    single group when folding is what collapsed it. Such a pair is absent from
    *conflicts* by construction, so nothing else in the report names it — and
    this is exactly the case where disclosure is the only signal there is: the
    checker exits 0 and ``finalize`` goes on to compile a KB the raw spellings
    would have blocked.

    **The two message classes below have different scopes, deliberately.** The
    equivalence message covers only the conflict-free pairs, because ``main``
    already prints ``value … spellings:`` under every CONFLICT it reports, and
    repeating it here would say each merge twice. The parse message covers
    **every** pair with a merge, conflict-free or not: a pair can merge two
    notations under the fold and still contradict on a third value, and nothing
    on the exit-1 path names the merged notation — the CONFLICT line lists the
    survivors, and the spelling lines under it come from ``_fold_classes``, which
    is silent about a merge that is not canonical equivalence. Restricting this
    loop to the conflict-free pairs made a row the previous release listed by
    name vanish from the output in any form.

    Scope is deliberately the **object** axis, the one where folding *resolves* a
    contradiction. Mixed spellings used to cost duplicate atoms downstream as
    well — ``common.dedup_engine_atoms`` keyed on the raw triple, so both
    spellings entered ``accepted.dl`` — and #342 closed that separately, on every
    axis it folds and not only under a resolved conflict. What is left for this
    advisory is the merge itself: the author wrote two strings and the gate
    treated them as one, which is worth saying whether or not anything
    downstream still doubles.

    **The equivalence message is gated on the atom count, not assumed.** "They
    collapse into a single ``accepted.dl`` atom" is a claim about the compiler,
    and this module's group is not the compiler's key: grouping canonicalizes
    declared aliases and NFC-folds the resulting relation, while
    ``engine_atom_key`` keeps it verbatim. Under ``CEO -> 대표``,
    ``삼성 CEO NFC(이재용)`` and
    ``삼성 대표 NFD(이재용)`` are one group here and two atoms there — measured,
    with the advisory printing "single atom" at exit 0 while ``accepted.dl``
    carried both. The reader was told the duplicate was already gone and left the
    sources unmerged, which is the checker-vs-engine disagreement this whole
    change exists to close. So ``_atom_count`` decides which sentence is printed,
    and where the rows really are two atoms the message keeps the older "separate
    atom" conclusion — true on that input before this change and still true —
    with the accurate reason, which is the relation axis and not the raw triple.

    **Two message classes, because folding merges values two ways.** Canonical
    equivalence is one; making a typed literal parse is the other, and calling
    the second "canonically equivalent" would be a false statement about the
    strings (``NFD('제3호')`` and ``'3위'`` are not equivalent — the fold merely let
    the first one parse as ordinal rank 3). It also carries a warning the first
    does not: the engine folds nowhere, so it cannot reproduce that merge — it
    loads the decomposed literal untyped, and every one of them when the relation
    name is decomposed as well (see ``collect_conflicts``). Keying the disclosure on
    ``_fold_classes`` left that path completely silent, which is how a KB that
    reported a CONFLICT on the previous release became "no contradictions".

    Printed on **stdout**, not stderr: this is an advisory rather than the
    failure report, and ``finalize`` forwards our stdout unconditionally (it
    writes ``conflicts.stdout`` before testing the return code), so it survives
    the exit-0 path where stderr would be dropped.
    """
    resolved = sorted(k for k in scan.object_variants if k not in scan.conflicts)
    lines: list[str] = []
    split_lines: list[str] = []
    for key in resolved:
        subject, relation = key
        relations = scan.object_relations.get(key, {})
        for obj, raws in sorted(scan.object_variants[key].items()):
            for members in _fold_classes(raws):
                line = (
                    f"    '{relation}' on '{subject}' value {obj!r} spellings: "
                    f"{_spellings(members)}"
                )
                bucket = lines if _atom_count(members, relations) <= 1 else split_lines
                bucket.append(line)
    if lines:
        print(
            f"check_conflicts: {len(lines)} spelling group(s) written in several Unicode "
            "normalization forms and merged into one value, so no contradiction is "
            "reported for them:"
        )
        for line in lines:
            print(line)
        print(
            "  These spellings are canonically equivalent, so they collapse into a single "
            "facts/accepted.dl atom, written in the composed spelling wherever the KB "
            "authored one. They still differ "
            "byte-wise in sources/ and facts/candidates.csv, where each one is its own row. "
            "Unify them at the source and re-collect."
        )
    if split_lines:
        print(
            f"check_conflicts: {len(split_lines)} spelling group(s) merged into one value "
            "here, but written under more than one relation spelling, so they do NOT "
            "collapse downstream:"
        )
        for line in split_lines:
            print(line)
        print(
            "  These spellings are canonically equivalent, so this check treats them as "
            "one value — it canonicalizes declared aliases and NFC-folds the resulting "
            "relation before grouping. The engine atom does not: it "
            "keys the relation verbatim, so each relation spelling still enters "
            "facts/accepted.dl as a separate atom and the duplicate survives this "
            "run's exit 0. Unify the relation spelling as well as the value at the "
            "source and re-collect."
        )
    # Every pair with a parse merge, not just the ones that ended up conflict-free.
    # A pair can merge two notations under the fold and still contradict on a
    # third value; ``resolved`` skips it, and then nothing anywhere names the
    # merged notation — main's CONFLICT block reports the surviving values and
    # the object-spelling lines under it come from ``_fold_classes``, which is
    # silent about a merge that is not canonical equivalence. So the reader was
    # shown two values where the previous release showed three, with the missing
    # one absent from the output in any form.
    parsed = []
    for key in sorted(scan.parse_merges):
        subject, relation = key
        for obj, notations in sorted(scan.parse_merges[key].items()):
            parsed.append(
                f"    '{relation}' on '{subject}' value {obj!r} notations: "
                f"{_spellings(notations)}"
            )
    if not parsed:
        return
    print(
        f"check_conflicts: {len(parsed)} value(s) merged only because a Unicode fold made "
        "a typed literal parse, so the notations below are counted as one value "
        "wherever this run reports a count:"
    )
    for line in parsed:
        print(line)
    print(
        "  These notations are NOT canonically equivalent: a decomposed literal does not "
        "parse as its declared type, and folding is what let it reach the scalar its "
        "counterpart already had. So they stay two separate atoms, and the engine's typed "
        "projection does not fold either — it hands the object as written to "
        "literal_types.normalize — so it loads the decomposed literal untyped (and, when "
        "the relation name is decomposed too, every one of them), and the notations never "
        "meet there. Unify the spelling in sources/ and re-collect, then re-run to see "
        "whether a contradiction remains."
    )


def _report_relation_atom_divergence(scan: ConflictScan) -> None:
    """Disclose conflict-free relation spellings that compile as separate atoms.

    Conflict grouping compares canonically equivalent relation spellings
    together, but the engine atom identity still preserves the relation bytes.
    At exit 0 there is no CONFLICT line to carry the spelling list, so disclose
    the remaining compiler divergence before finalize writes separate atoms.

    Pairs already covered by a CONFLICT line are skipped — that line carries the
    suffix and the spelling list on stderr, and repeating it here would double-
    report one fact in two streams.
    """
    conflicting = {(_fold(s), _fold(r)) for s, r in scan.conflicts}
    lines = []
    for key in sorted(scan.relation_variants):
        subject, relation = key
        if (_fold(subject), relation) in conflicting:
            continue
        lines.append(f"    on '{subject}' spellings: {_spellings(scan.relation_variants[key])}")
    if not lines:
        return
    # One line per (subject, relation) pair, so the header names that unit and no
    # other. Naming either axis alone miscounts in one direction or the other:
    # "N subject(s)" reads as N people when one subject has two split relations,
    # and "N relation(s) … for one subject" reads as one person when N subjects
    # each have one. There is no single axis to name — the pair is the count.
    print(
        f"check_conflicts: {len(lines)} (subject, relation) pair(s) whose single-valued relation "
        "is written in several Unicode normalization forms:"
    )
    for line in lines:
        print(line)
    print(
        "  Conflict analysis compared these spellings together as one relation. The current "
        "compiler still preserves relation spelling in atom identity, so if finalize proceeds "
        "they enter accepted.dl as separate relation/3 atoms. Unify the spelling in sources/ "
        "and re-collect, then re-run."
    )


def non_ascii_digit_note(objects: list[str], spec: TypedRelSpec | None) -> list[str] | None:
    """Extra guidance lines for a **typed** relation's conflict group when one of
    its values carries non-ASCII digits; ``None`` otherwise.

    The generic advice printed by ``main`` ("mark the outdated row superseded")
    assumes one of the values is out of date. Under a typed relation a value
    carrying non-ASCII digits does not parse as the declared type at all
    (``_group_key`` degrades it to ``("raw", obj)``), so superseding the OTHER row
    clears this gate while leaving the KB holding the value the engine cannot
    read.

    **The ``spec is None`` gate is load-bearing, not defensive.** Under an untyped
    single-valued relation ``_group_key`` returns a raw key because there is no
    spec, *not* because of digit width — ``GPT-４`` and ``GPT-5`` key identically,
    ``GPT-４`` is a perfectly usable ``relation/3`` fact, and superseding the
    outdated row is exactly the right fix. Every clause of this note would be
    false there, and it would steer the user away from the one action that works.

    **Carrying non-ASCII digits is not the same as failing to parse**, so the
    normalizer decides, not the digit predicate alone. The unit group is outside
    the digit policy on purpose and ``_parse_amount_units`` does not *validate* a
    unit NAME, so a declared unit may carry them: ``amount(100,"억１")`` under a
    declared ``억１`` unit normalizes to a scalar and ``_group_key`` keys it
    ``("scalar", …)``. Both leading clauses of the note would be false there.
    Asking ``normalize`` converges this note and ``_group_key`` on one predicate.

    ``_parse_amount_units`` does now **NFC-fold** a unit name (#325), which is a
    normalization and not a validation, so the example above is unaffected. That
    fold runs at policy load, *before* any value meets the ``[0-9]`` numeric
    group — it is upstream of the digit gate, not downstream of it — so its
    harmlessness cannot rest on ordering. It rests on the fold itself: NFC does
    not change a single non-ASCII digit, anywhere in Unicode. Of the 750
    non-ASCII ``Nd`` code points, 80 carry a decomposition mapping and **none of
    those mappings is canonical** — every one is compatibility-tagged, which is
    precisely what NFKC would apply and NFC will not. So no ``Nd`` code point is
    touched by NFC or NFD, ``has_non_ascii_digits`` is invariant under canonical
    equivalence as a general fact rather than as a claim about fullwidth, and the
    fold can neither make a value the digit policy rejects start parsing nor the
    reverse. The same sweep also finds **0 canonical decompositions whose base
    character is an ``Nd`` digit**, which extends the invariant from single code
    points to arbitrary strings: no ``digit + combining mark`` sequence composes
    into something else either. (All measured on unicodedata 16.0.0.)

    Two things the wording deliberately does NOT claim:

    * that supersession cannot resolve the conflict — superseding the offending
      row itself resolves it correctly, so the note says supersession *can* leave
      the bad value behind, never that it is useless;
    * that re-collection *replaces* supersession — for genuinely different values
      (``100억`` vs ``２００억``) correcting the source yields ``100억`` vs
      ``200억``, still a conflict that supersession must settle.

    Pure; never raises."""
    if spec is None:
        return None
    offenders = [
        o
        for o in objects
        if literal_types.has_non_ascii_digits(o)
        and literal_types.normalize(spec.type, o, spec.units) is None
    ]
    if not offenders:
        return None
    shown = ", ".join(f"'{literal_types.mark_non_ascii_digits(o)}'" for o in offenders)
    return [
        f"    note: {shown} carries non-ASCII digits, so it does not parse as this",
        f"          relation's declared type ({spec.type}) and is compared here as a raw",
        "          string. Superseding a row clears this gate but can leave that",
        "          unreadable value in the KB. Correct the source to ASCII digits and",
        "          re-collect; if the values still differ afterwards, supersede the",
        "          outdated one (docs/reference/typed-relations.md).",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect single-valued-relation contradictions.")
    parser.add_argument("--wiki", default=os.environ.get("FACTLOG_ROOT", "."), help="KB root")
    parser.parse_args(argv)

    ensure_dirs()
    single_valued = single_valued_relations()
    if not single_valued:
        print("check_conflicts: no single-valued relations declared (policy/single-valued.md); nothing to check")
        return 0

    typed = typed_relations()
    scan = collect_conflicts(load_facts(), single_valued, typed, relation_aliases())
    conflicts, subject_variants, object_variants = (
        scan.conflicts,
        scan.subject_variants,
        scan.object_variants,
    )
    if not conflicts:
        print(f"check_conflicts: 0 conflicts across {len(single_valued)} single-valued relation(s)")
        _report_resolved_merges(scan)
        _report_relation_atom_divergence(scan)
        return 0

    print(f"check_conflicts: {len(conflicts)} conflict(s) found", file=sys.stderr)
    _report_resolved_merges(scan)
    _report_relation_atom_divergence(scan)
    aliases = relation_aliases()
    # Whether folding merged spellings anywhere. This is an *extra* disclosure,
    # never a replacement for the supersede guidance: a contradiction that a mixed
    # spelling merely joined is still a contradiction, and unifying the spelling
    # does not resolve it.
    any_mixed = False
    # Grouping folds the relation under NFC and restores one authored spelling,
    # so disclose the other spellings for the same provenance reason as the
    # subject axis: the representative does not grep to every source row.
    # ``relation_variants`` counts spellings over every pair examined, not only
    # conflicting ones. Re-keyed on the fold so the reported subject and relation
    # representatives find their provenance channel. The count comes from rows,
    # not from
    # policy/single-valued.md: sv holds folded names, so several policy spellings
    # collapse to one element there.
    relation_spellings = {(_fold(s), r): names for (s, r), names in scan.relation_variants.items()}
    for key, objects in sorted(conflicts.items()):
        subject, relation = key
        suffix = " (canonical; incl. surface variants)" if aliases and relation in set(aliases.values()) else ""
        subjects = subject_variants[key]
        if len(subjects) > 1:
            suffix += f" (subject written in {len(subjects)} mixed Unicode normalization forms)"
        relations = relation_spellings.get((_fold(subject), _fold(relation)), [relation])
        if len(relations) > 1:
            suffix += f" (relation written in {len(relations)} mixed Unicode normalization forms)"
        print(
            f"  CONFLICT: single-valued '{relation}'{suffix} on '{subject}' has "
            f"{len(objects)} values: {', '.join(objects)}",
            file=sys.stderr,
        )
        # Print the spellings themselves, escaped: the whole difficulty of this
        # class of conflict is that the strings render identically, so naming a
        # count without the code points leaves the reader unable to act.
        if len(subjects) > 1:
            any_mixed = True
            print(f"    subject spellings: {_spellings(subjects)}", file=sys.stderr)
        if len(relations) > 1:
            any_mixed = True
            print(f"    relation spellings: {_spellings(relations)}", file=sys.stderr)
        for obj in objects:
            # Evidence of a *Unicode* merge is that folding collapses spellings,
            # not that the group holds several strings: a typed relation groups on
            # the parsed scalar, so #116 cross-notation equivalents (amount(5400,
            # "억") and amount(0.54,"조") -> 5.4e11) share a group while being
            # plain NFC and rendering nothing alike. _fold_classes answers "did it
            # merge" and "what did it merge" at once, so the gate and the strings
            # printed under it cannot disagree — one line per class, since
            # "canonically equivalent" holds within a class and not across them.
            for members in _fold_classes(object_variants[key][obj]):
                any_mixed = True
                print(
                    f"    value {obj!r} spellings: {_spellings(members)}",
                    file=sys.stderr,
                )
        # The conflict key is the canonical relation, which is already NFC when it
        # came from the alias map; fall back to the NFC form for an NFD-authored
        # name. NOT identical to detect_conflicts' lookup: there the second probe
        # uses the NFC of the ROW's relation, which can differ from the canonical
        # one when an NFD surface form participates in an alias (#210).
        spec = typed.get(relation) or typed.get(unicodedata.normalize("NFC", relation))
        for line in non_ascii_digit_note(objects, spec) or ():
            print(line, file=sys.stderr)
    print(
        "  Resolve by marking the outdated row(s) status='superseded' in "
        "facts/candidates.csv, then re-run.",
        file=sys.stderr,
    )
    if any_mixed:
        print(
            "  Some string(s) above are written in more than one Unicode normalization form: "
            "they are canonically equivalent but differ byte-wise, so the reported spelling "
            "does not grep to every row behind it (the spellings are listed with their form "
            "under each conflict). Do NOT repair this by editing facts/candidates.csv: "
            "merge_candidates rebuilds those rows from runs/*.json and matches everything it "
            "carries back — statuses and superseded rows alike — on the raw "
            "(subject, relation, object, source-without-anchor) key, so a hand-edited spelling "
            "is discarded on the next merge and stops matching the key that preserves its 'superseded' "
            "mark. Unify the spelling in sources/ and re-collect. "
            "That is a separate repair from superseding, and neither substitutes for the other.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    from common import run_cli

    sys.exit(run_cli(main))
