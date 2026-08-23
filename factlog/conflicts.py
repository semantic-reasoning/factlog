# SPDX-License-Identifier: Apache-2.0
"""Import-safe, authoritative single-valued conflict grouping.

This module owns value equivalence and grouping only. It deliberately performs
no filesystem access, argument parsing, environment mutation, or report
rendering so installed-package consumers can share the checker's verdict.
"""

from __future__ import annotations

import unicodedata
from typing import NamedTuple

from factlog import literal_types
from factlog.common import (
    TypedRelSpec,
    composed_spelling,
    engine_facts,
    fold_relation_name,
    folded_relation_names,
)


def _canonicalize(relation: str, aliases: dict[str, str]) -> str:
    """Return the canonical relation name when *relation* participates in the
    alias map; otherwise return *relation* verbatim (NFD-preserving).

    Participation mirrors ``common.canonical_atoms``:

    * relation is an alias **key** (raw predicate) → ``aliases[NFC(relation)]``
    * relation **is** a canonical value (stored literally) → its NFC form
    * relation is not in the alias map → verbatim (no normalization)

    When *aliases* is empty the function short-circuits and returns *relation*
    unchanged, preserving byte-identical behaviour for KBs without a
    relation-aliases.md file.
    """
    if not aliases:
        return relation
    rn = unicodedata.normalize("NFC", relation)
    if rn in aliases:
        return aliases[rn]
    if rn in set(aliases.values()):
        return rn
    return relation


def _fold(value: str) -> str:
    """Return *value* under Unicode canonical composition (NFC).

    NFC only — **not** NFKC and **not** casefold. NFC merges strings that are
    *canonically equivalent*: the same abstract characters written with
    precomposed vs decomposed code points. macOS filesystems and IMEs routinely
    emit Hangul decomposed, so a KB assembled from mixed sources naturally
    collects both spellings of one string. It does **not** merge compatibility
    variants (fullwidth ``ＡＢＣ`` stays distinct from ``ABC``) nor case — those
    are genuinely different values and must keep firing a conflict.

    Precomposed-vs-decomposed is the case that matters here, but not the only one
    NFC folds: it also collapses the *canonical singletons* Unicode has
    deprecated in favour of an existing character — ``Ω`` U+2126 → U+03A9, ``K``
    U+212A → U+004B, ``Å`` U+212B → U+00C5. Merging them is correct (Unicode
    itself defines them as the same character), and it is why the report says
    "canonically equivalent" rather than "renders identically": equivalence is
    guaranteed by the standard, identical rendering is only a font's habit.

    ``common._canonical_value`` is deliberately *not* reused: it layers
    amount-quote normalization on top of the Unicode fold, which would perturb
    the typed-literal key space this module builds through ``literal_types``.

    One operation, three call sites, so: this is the *grouping* fold, applied to
    subjects and objects inside this module. ``common.fold_relation_name`` is the
    same NFC applied to a policy relation name for a *membership* test, and every
    consumer that tests membership must use it (see its docstring).
    ``common.composed_spelling`` picks which raw spelling of a folded group to
    display. Nothing else should re-derive any of the three.
    """
    return unicodedata.normalize("NFC", value)


def _representative(raws: set[str]) -> str:
    """Return the string reported on behalf of a folded group of *raws*.

    Deterministic, and always one of the strings as written (provenance). Where
    the group holds several normalization forms, the **composed (NFC)** spelling
    wins; ties break lexicographically.

    Plain ``min`` would be deterministic too, but it picks the wrong member in
    practice: Hangul conjoining jamo (U+1100…) sort below precomposed syllables
    (U+AC00…), so ``min`` on a mixed group *always* returns the decomposed form —
    the one that will not match if the reader types or pastes the name into a
    search from an NFC editor. Preferring NFC makes the reported string the one
    most likely to grep, and the full spelling list is printed alongside it for
    the rows it cannot reach.

    The grep argument only holds where the group *has* a composed member. On a
    uniformly decomposed KB every candidate is NFD and this returns NFD — still
    deterministic and still a spelling actually written (which is the guarantee
    that matters), but no more greppable than any other member. The labelled
    spelling list is what carries the reader there in that case.

    Shared with ``corroboration`` through ``common.composed_spelling``: both
    modules stand a representative in front of a folded group and must pick the
    same one, or the two reports name different rows for one value.
    """
    return composed_spelling(raws)



def _fold_classes(raws: list[str]) -> list[list[str]]:
    """Partition *raws* into canonical-equivalence classes, keeping merged ones.

    Returns one sorted list per class that holds more than one spelling, sorted
    between classes; an empty result means no Unicode merge happened here. This
    is *the* answer to both "did folding merge anything" and "which strings did
    it merge" — the gate and the payload have to be one computation, because a
    value group is keyed on the typed scalar (#116) and can hold strings that are
    not canonically equivalent at all. ``amount(5400,"억")`` and
    ``amount(0.54,"조")`` share a group by parsing to 5.4e11, ``제3호`` and ``3위``
    by ordinal rank (#218). Reporting the whole group calls those "canonically
    equivalent" and asks the reader to unify notations #116 exists to keep apart.

    Two failure modes this avoids, both worse than the bug:

    * **Do not drop the non-equivalent members from the group itself.** They are
      the same value and must keep collapsing, or #116's false CONFLICT returns.
      The narrowing is for the *report*, never for the grouping.
    * **Do not keep only the members where ``_fold(r) != r``.** That drops the
      composed twin — precisely the spelling the reader must unify *to*, and the
      one ``_representative`` already put on the CONFLICT line.

    One class per line matters too: a single group can hold several independent
    classes (NFC/NFD of ``amount(5400,"억")`` *and* NFC/NFD of
    ``amount(0.54,"조")`` all key to 5.4e11), and "canonically equivalent" is
    true within a class but false across them.
    """
    classes: dict[str, list[str]] = {}
    for raw in raws:
        classes.setdefault(_fold(raw), []).append(raw)
    return [sorted(members) for _, members in sorted(classes.items()) if len(members) > 1]


def _parse_merge(raws: set[str], unfolded_keys: dict[str, tuple]) -> list[str]:
    """Return the notations folding merged that nothing else explains, or ``[]``.

    ``_fold_classes`` reports the merges Unicode equivalence explains. This
    reports the ones it does not: a typed literal that ``literal_types.normalize``
    parses **only after** the fold joins a group it could never have reached
    unfolded — ``NFD('제3호')`` degrades to ``("raw", …)`` as written and keys as
    ordinal rank 3 once folded, meeting ``'3위'``. Calling those two "canonically
    equivalent" would be false, so they need their own sentence, and without one
    the fold silently resolves a contradiction the previous release reported.

    The test is *not* "the group spans several equivalence classes" — a #116
    scalar merge does that with no decomposed code point in sight
    (``amount(5400,"억")`` and ``amount(0.54,"조")`` both key to 5.4e11 with or
    without the fold), and announcing it as a Unicode merge is the exact false
    diagnostic ``_fold_classes`` exists to avoid. Nor is it "folding changed the
    partition", which fires on ``{NFC('제3호'), NFD('제3호'), '3위'}``: there the
    fold joined ``NFD('제3호')`` to a class ``_fold_classes`` already names, and
    the rank equivalence to ``'3위'`` was #218's doing, not the fold's.

    So both explanations get to speak first. Two raws are joined when they share
    an **unfolded** group key (they were one value before the fold — #116/#218
    equivalence) or when they are **canonically equivalent** (the plain Unicode
    merge, already listed by ``_fold_classes``). Whatever components survive that
    were joined by nothing but the fold-enabled parse, and only those are
    reported — one representative each (NFC spelling preferred, see
    ``_representative``), since the members inside a component are covered above.
    """
    parent = {raw: raw for raw in raws}

    def find(raw: str) -> str:
        while parent[raw] != raw:
            parent[raw] = parent[parent[raw]]
            raw = parent[raw]
        return raw

    seen: dict[tuple, str] = {}
    for raw in sorted(raws):
        for label in (("key", unfolded_keys[raw]), ("fold", _fold(raw))):
            other = seen.setdefault(label, raw)
            roots = sorted((find(raw), find(other)))
            parent[roots[1]] = roots[0]
    components: dict[str, set[str]] = {}
    for raw in raws:
        components.setdefault(find(raw), set()).add(raw)
    if len(components) <= 1:
        return []
    return sorted(_representative(members) for members in components.values())


def _relation_map(by_object: dict[str, set[str]]) -> dict[str, list[str]]:
    """Freeze ``{raw object: raw relation spellings}`` into sorted lists.

    Same determinism argument as ``_variant_map``: the sets are built by
    iterating rows, and this is a public field of ``ConflictScan``.
    """
    return {obj: sorted(relations) for obj, relations in sorted(by_object.items())}



def _variant_map(groups: dict[tuple, set[str]]) -> dict[str, list[str]]:
    """Return ``{reported object: sorted raw objects}`` for *groups*, key-sorted.

    Sorted rather than insertion-ordered. ``main`` reads this through the sorted
    ``conflicts`` list and each key's sorted object list, so the report never
    depended on it — but *groups* is built by iterating sets, so insertion order
    tracks row order, and this is a public return value of a module whose entire
    contract is determinism. Leaving row order in it is a trap for the next
    caller, not a defect in this one.

    Group representatives are distinct by construction (each raw object falls in
    exactly one group, so the groups' raw sets are disjoint), hence sorting on
    the key alone is a total order.
    """
    return dict(
        sorted(
            ((_representative(raws), sorted(raws)) for raws in groups.values()),
            key=lambda item: item[0],
        )
    )


def _group_key(obj: str, spec: TypedRelSpec | None) -> tuple:
    """Return the equivalence key an *object* string is grouped under.

    For a relation declared typed (#116), the object's canonical scalar
    (``literal_types.normalize``) is the key, so equivalent notations of the same
    value (e.g. ``amount(5400,"억")`` and ``amount(0.54,"조")`` -> 5.4e11) collapse
    to one value instead of firing a false CONFLICT. ``amount`` needs its unit
    table, so ``spec.units`` is passed through.

    Falls back to the raw object string when the relation is untyped OR the value
    does not parse (normalize -> None): backward-compatible, lossless degrade. The
    two key spaces are tagged (``"scalar"`` vs ``"raw"``) so a scalar never
    collides with an unrelated raw string. Total: never raises (normalize is
    total).

    **ordinal unit loss (#218 / #224 A):** ``normalize("ordinal", …)`` keeps only
    the integer *rank* — the ordinal-class unit (호/위/번/차/등/째) is dropped at
    parse time (``literal_types.parse_ordinal``), so it never enters the key. A
    cross-unit pair therefore collapses onto one scalar: ``제3호`` and ``3위`` both
    key as ``("scalar", 3)``. This is **by design** and consistent with the engine,
    which likewise compares ordinals on rank alone (``_TYPED_COL["ordinal"]`` is a
    bare int64, no unit column). ordinal is a *rank-only* contract: same rank =
    same value. If two notations denote genuinely different domains (a rank vs a
    house number), that distinction belongs in the model — declare them as
    **separate relations**, not one single-valued ordinal relation. (Contrast
    ``amount``, where 억↔조 equivalence is the intended collapse.)

    **int64 divergence note (#224 C):** ``normalize`` can return a scalar wider
    than int64 (mainly ``number`` via ``parse_number_scaled``, and unbounded
    ``ordinal`` ranks — both lack a range guard; ``amount`` already degrades to raw
    when ``parse_amount`` overflows, #205). The engine, by contrast, **skips insertion** of an out-of-int64-range
    scalar (see ``insert_typed_facts`` in ``common.py`` ~ the ``-(2**63) <= scalar
    < 2**63`` guard). So this checker may group under a scalar the engine would
    drop. That affects **grouping only** (never insertion) and is harmless: the
    checker is strictly more willing to merge equivalents, never less. No behaviour
    change here — note only.

    **Unicode folding (#325):** *obj* is NFC-folded **once, on entry**, and the
    folded string feeds *both* the typed ``normalize`` call and the raw fallback.
    Folding before ``normalize`` is required, not cosmetic. An NFD-authored typed
    literal fails to parse — ``normalize("amount", NFD('amount(5400,"억")'), units)``
    and ``normalize("ordinal", NFD("제3호"), None)`` both return ``None`` — so it
    degrades to ``("raw", …)`` while its NFC twin keys as ``("scalar", …)``. The
    two tags never meet, and folding only the fallback would not reach them.
    Typed relations are in fact the *more* exposed axis, since amount and ordinal
    units are Hangul (억/조/호/위/번/차). The ``scalar``/``raw`` tag split itself is
    correct and unchanged.

    Consequence, stated plainly: an **all-NFD typed KB can change output**. Two
    NFD rows that previously degraded to distinct raw strings now parse and may
    collapse onto one scalar. That is not a regression — it is #116's cross-
    notation equivalence (억↔조) starting to work on that KB for the first time.
    The invariant held here is the one the issue asks for: an **NFC-only** KB is
    byte-identical.

    That the change is merge-only is **not** free, and it is worth naming the way
    it was nearly lost. Folding here also folds the string handed to
    ``parse_amount``, which resolves a Hangul unit (억/조/원) against a table
    ``policy/typed-relations.md`` supplies. While that table kept the policy
    file's own spelling, an NFD units clause plus a folded object was a *miss*:
    the amount degraded to ``("raw", …)``, and ``5400억`` and ``0.54조`` — one
    value, 5.4e11, which parsed and merged **unfolded** — split into a CONFLICT
    this checker did not previously report, on the very macOS-decomposed KB
    #325 exists for. Folding can add a conflict as easily as it removes one when
    only one end of a lookup folds.

    So the merge-only direction rests on a stated dependency: every table this
    key parses against is composed on both ends (``common._parse_amount_units``
    stores NFC keys, ``parse_amount`` composes the lookup key). Given that, no
    parser matches a decomposed string its composed form fails — the ordinal and
    amount markers are all spelled composed in their regexes — so folding can
    only join groups, never split one. A future typed parser that resolves a
    non-ASCII token against a table has to fold that table too, or it reopens
    exactly this hole."""
    return _typed_key(_fold(obj), spec)


def _typed_key(value: str, spec: TypedRelSpec | None) -> tuple:
    """Tag *value* as a typed scalar when *spec* parses it, else as a raw string."""
    if spec is not None:
        scalar = literal_types.normalize(spec.type, value, spec.units)
        if scalar is not None:
            return ("scalar", scalar)
    return ("raw", value)


def _group_key_unfolded(obj: str, spec: TypedRelSpec | None) -> tuple:
    """Return the key *obj* would group under if this module did not fold (#325).

    Used only by the disclosure, to answer one question ``_fold_classes`` cannot:
    **did folding change how these rows partition?** Canonical equivalence is the
    right axis for the untyped fallback and the wrong one for a typed relation,
    because folding also decides whether ``literal_types.normalize`` parses at
    all. ``NFD('제3호')`` does not parse and keys ``("raw", …)``; folded it parses
    to ordinal rank 3 and meets ``'3위'`` under ``("scalar", 3)``. Those two
    strings are *not* canonically equivalent, so the fold is what merged them and
    nothing on the equivalence axis can say so — which is how a pair that main
    reported as a CONFLICT became a silent exit 0.

    Two rows sharing this key were already one value before the fold, so
    ``_parse_merge`` uses it to subtract the merges #116/#218 equivalence
    accounts for on its own.
    """
    return _typed_key(obj, spec)


class ConflictScan(NamedTuple):
    """Everything one pass over the facts learned about a single-valued KB.

    A NamedTuple rather than a plain tuple because the channels are no longer two
    symmetric ones: folding merges strings on several axes and each merge has a
    different consequence, so the caller has to be able to name the one it is
    reporting. ``detect_conflicts`` still reads ``.conflicts`` and nothing else.

    * *conflicts* — ``{(reported subject, canonical relation): sorted objects}``,
      the pairs holding more than one distinct value. The report's exit-1 payload.
    * *subject_variants* — for each conflicting key, the sorted raw subject
      spellings the fold merged under it. Conflicting pairs only.
    * *object_variants* — ``{reported object: sorted raw objects}`` per key. Its
      key set is a **superset** of *conflicts*: a pair whose objects folding
      collapsed to a single value is not a conflict, yet is retained so the
      caller can disclose that the fold is what resolved it.
    * *parse_merges* — the subset of *object_variants* where folding merged
      values that neither #116/#218 equivalence nor canonical equivalence
      explains, by making a typed literal parse (see ``_parse_merge``). Same
      shape, but the value list is one representative per merged component,
      because "these are the same string written two ways" is false here and the
      reader needs the other sentence — including the part where the engine
      cannot reproduce the merge at all.
    * *relation_variants* — ``{(reported subject, NFC relation): sorted raw
      relation spellings}`` wherever one folded relation was written more than
      one way for a subject. Membership folds but grouping does not, so those
      rows sit in **separate** pairs: a contradiction between them is invisible
      to this module, and at exit 0 nothing else in the run mentions the rows at
      all. Keyed on all pairs, not only conflicting ones, for that reason.
    * *object_relations* — ``{reported object: sorted raw relation spellings}``
      per key: the relation names the rows behind each raw object were actually
      written under. Same key set as *object_variants*. Grouping canonicalizes
      the relation and ``common.engine_atom_key`` does not, so a group here can
      be more than one atom there; this is what lets the disclosure say which.

    Every public mapping is inserted in sorted key order, including both levels
    of nested mappings. Iterating a scan therefore never exposes input row order.
    """

    conflicts: dict[tuple[str, str], list[str]]
    subject_variants: dict[tuple[str, str], list[str]]
    object_variants: dict[tuple[str, str], dict[str, list[str]]]
    parse_merges: dict[tuple[str, str], dict[str, list[str]]]
    relation_variants: dict[tuple[str, str], list[str]]
    object_relations: dict[tuple[str, str], dict[str, list[str]]]


ConflictSupport = dict[tuple[str, str], dict[str, tuple[str, ...]]]


class _ConflictGroups(NamedTuple):
    """Private result of one authoritative pass over engine-input rows."""

    by_key: dict[tuple[str, str], dict[tuple, set[str]]]
    unfolded: dict[tuple[str, str], dict[str, tuple]]
    raw_subjects: dict[tuple[str, str], set[str]]
    object_relations: dict[tuple[str, str], dict[str, set[str]]]
    raw_relations: dict[tuple[str, str], set[str]]
    relation_subjects: dict[tuple[str, str], set[str]]
    sources: dict[tuple[str, str], dict[tuple, set[str]]]


def _group_conflict_rows(
    facts: list[dict[str, str]],
    single_valued: set[str],
    typed: dict[str, TypedRelSpec] | None = None,
    aliases: dict[str, str] | None = None,
) -> _ConflictGroups:
    """Build every conflict and source channel in one engine-row iteration."""
    typed = typed or {}
    aliases = aliases or {}
    sv = folded_relation_names(_canonicalize(r, aliases) for r in single_valued)
    by_key: dict[tuple[str, str], dict[tuple, set[str]]] = {}
    unfolded: dict[tuple[str, str], dict[str, tuple]] = {}
    raw_subjects: dict[tuple[str, str], set[str]] = {}
    object_relations: dict[tuple[str, str], dict[str, set[str]]] = {}
    raw_relations: dict[tuple[str, str], set[str]] = {}
    relation_subjects: dict[tuple[str, str], set[str]] = {}
    sources: dict[tuple[str, str], dict[tuple, set[str]]] = {}
    for row in engine_facts(facts):
        relation = row["relation"]
        canon = _canonicalize(relation, aliases)
        if fold_relation_name(canon) not in sv:
            continue
        obj = row["object"]
        spec = typed.get(canon) or typed.get(_fold(relation))
        key = _group_key(obj, spec)
        pair = (_fold(row["subject"]), canon)
        by_key.setdefault(pair, {}).setdefault(key, set()).add(obj)
        unfolded.setdefault(pair, {})[obj] = _group_key_unfolded(obj, spec)
        raw_subjects.setdefault(pair, set()).add(row["subject"])
        object_relations.setdefault(pair, {}).setdefault(obj, set()).add(relation)
        split = (pair[0], _fold(canon))
        raw_relations.setdefault(split, set()).add(canon)
        relation_subjects.setdefault(split, set()).add(row["subject"])
        sources.setdefault(pair, {}).setdefault(key, set()).add(row.get("source", ""))
    return _ConflictGroups(
        by_key,
        unfolded,
        raw_subjects,
        object_relations,
        raw_relations,
        relation_subjects,
        sources,
    )


def collect_conflicts(
    facts: list[dict[str, str]],
    single_valued: set[str],
    typed: dict[str, TypedRelSpec] | None = None,
    aliases: dict[str, str] | None = None,
) -> ConflictScan:
    """Return a :class:`ConflictScan` — the conflicts plus every spelling channel.

    ``scan.conflicts`` is exactly what ``detect_conflicts`` returns (see there).
    The remaining fields are the disclosure channels; each is documented on the
    NamedTuple. They exist so ``main`` can report what folding did without
    duplicating the grouping logic, while ``detect_conflicts`` keeps its
    established return shape (a large body of pinned tests asserts that dict
    directly).

    A variant list holds one entry when nothing was merged. More than one means
    the KB writes that string in several Unicode normalization forms, so the
    reported representative does not grep to every row behind it — which is
    exactly what the caller has to disclose.

    **Subject axis folding (#325):** rows group under the NFC fold of the
    subject, so a contradiction written with the subject NFC on one row and NFD
    on another is detected instead of splitting into two singleton groups. That
    split was an *unsound* false negative: the finalize gate passed KBs that do
    contain a contradiction, and nobody ever saw it. Conversely the untyped
    object axis folds too, so two objects that render identically stop being
    reported as a contradiction the reader cannot act on.

    The *reported* key preserves provenance: a raw subject actually seen for that
    (folded subject, canonical relation) pair, chosen by ``_representative`` (NFC
    spelling preferred, ties lexicographic — not a plain ``min``, see there). The
    map is keyed per **pair**, never per folded subject globally — a global map
    would rewrite the reported subject spelling of unrelated relations and break
    byte-identity on inputs where folding merges nothing.

    **Relation axis (#325):** it is two mechanisms, and only *grouping* is
    deferred. Membership — whether a relation is declared single-valued at all —
    is folded above, because it gates entry to the loop and
    ``common._relation_names_from`` does not normalize the names it reads from
    policy/single-valued.md. Left raw it was a byte comparison between two
    hand-written files, so a KB written uniformly in NFD never reached the check
    and exited 0 with a contradiction in it. That is a *wider* false negative
    than the mixed-subject one above — it needs no mixed spelling at all, just
    one consistently decomposed KB, which is the scenario ``_fold`` itself cites.
    Grouping stays verbatim: two spellings of one relation remain two groups, and
    the reported relation is byte-for-byte as written. Folding that as well is
    mechanically possible and the #210 pins survive it, so "the pins forbid it"
    would be a false reason; the real reason is that it changes which rows
    collide, and how far #210's "no silent NFC coercion for non-participating
    relations" was meant to reach is a maintainer's call. Raised as a follow-up.

    **Engine agreement, and exactly how far it reaches (#342).**
    ``common.dedup_engine_atoms`` keys on ``common.engine_atom_key``, which
    applies the same NFC as ``_fold`` to the subject and the object. It is not
    the same *fold* on the subject, and the difference is the whole of what
    survives: ``engine_atom_key`` folds each value **inside its own triple**,
    while ``_group_key`` folds the subject **across rows**, into a
    ``(folded subject, relation)`` bucket that then collects every value written
    for it. Two rows agreeing on the folded subject and differing on the object
    are one group here and two atoms there, by construction.

    So the two axes did not both close:

    * **subject axis — checker still stricter, present tense.** Measured:
      ``NFC(김철수) 소속 A사`` and ``NFD(김철수) 소속 B사`` give **2** engine atoms
      with 2 subject spellings, while this module reports **1** conflict on
      ``('김철수', '소속')``. The gate still closes on a KB the engine would have
      accepted — nothing slips through, so the direction is the safe one, but the
      divergence is live and #342 did not touch it. Behaviour here is identical
      to before #342.
    * **object axis — checker more permissive, and this one closed.** Two objects
      the raw grouping called a contradiction now agree, so the gate *opens*
      where it used to close, ``finalize`` compiles — and both spellings then
      reached ``accepted.dl`` as separate atoms, the inflated duplicate count
      ``dedup_engine_atoms`` exists to prevent, arrived at through the normal
      path. That is what #342 closed: one atom, so the engine now reproduces the
      merge the checker made.

    The permissive direction is semantically right: ``common._canonical_value``
    (#213) already fixed NFC as value equality. What is not acceptable is doing
    it silently, so the object channel below survives for a pair folding
    resolved, and ``_report_resolved_merges`` discloses it at exit 0 — the merge
    is still a merge the author did not ask for, even now that the engine
    reproduces it.

    **The relation axis is NOT untouched — do not read #342 as leaving it
    clean.** Grouping here is verbatim and ``engine_atom_key`` leaves the
    relation raw, so *those two* split two spellings of one relation the same
    way. That agreement is only between this module and ``relation/3``, and only
    while no alias is declared: ``_canonicalize`` collapses the relation axis
    here whenever ``policy/relation-aliases.md`` names it, so
    ``삼성 CEO NFC(이재용)`` and ``삼성 대표 NFD(이재용)`` under ``CEO -> 대표``
    are ONE group here and **two** atoms in ``accepted.dl`` — measured. That is
    why ``_report_resolved_merges`` counts atoms with ``_atom_count`` instead of
    asserting the collapse: the merge this module made is not always a merge the
    compiler reproduces. Two places downstream already fold the relation, and
    they did before #342:

    * ``common.canonical_atoms`` NFC-folds the relation before the alias lookup,
      so an aliased pair emits **two** ``relation/3`` atoms and **one**
      ``canonical/3`` atom into the same ``accepted.dl`` — measured.
    * ``common._canonical_value`` (#213) folds the relation argument of a query,
      so one spelling typed by the user matches both atoms.

    Whoever judges #210/#345 needs that: the axis is already folded at the query
    layer and in the canonical block, and the choice is not "start folding" but
    "make the rest agree with what those two already do". Folding it in
    ``engine_atom_key`` remains deferred, and deliberately so — it changes which
    rows collide — but the premise "both sides raw, nothing diverges" is false.

    **The typed projection still does not fold (#325 follow-up).** ``_group_key``
    folds *before* ``literal_types.normalize``; the engine's counterpart,
    ``common._project_typed_relations``, hands ``normalize`` the object of the
    atom as written (and looks its spec up under the raw relation name). So an
    NFD-authored typed literal can still parse here and nowhere else, and this
    module can declare two values equal on grounds the engine cannot reproduce.

    #342 narrows this without closing it. Two *canonically equivalent* spellings
    are now one atom, written in the composed spelling wherever the KB authored
    one, so they no longer land on opposite sides of the typed table — the case
    that used to insert the composed literal typed and degrade the decomposed one
    with a warning. What survives is everything the atom fold does not reach: a
    uniformly decomposed KB keeps its decomposed spelling (there is no composed
    member to prefer), so ``normalize`` still fails on it, and with the relation
    name decomposed the spec lookup still misses every row and none load typed at
    all. A *parse* merge is untouched by construction — ``NFD('제3호')`` and
    ``'3위'`` are not canonically equivalent, so they are two atoms here and two
    atoms in the engine, and only this module ever calls them one value.

    Aligning the typed projection too is the root fix and a follow-up of its
    own: it changes which rows enter the typed side-relations, hence what
    ``factlog ask`` answers, and it needs the deferred #210 relation-axis call
    decided first. What belongs *here* is that the checker never merges on that
    basis in silence — see ``_parse_merge`` and ``_report_resolved_merges``.
    """
    groups_result = _group_conflict_rows(facts, single_valued, typed, aliases)
    by_key = groups_result.by_key
    unfolded = groups_result.unfolded
    raw_subjects = groups_result.raw_subjects
    object_relations = groups_result.object_relations
    raw_relations = groups_result.raw_relations
    relation_subjects = groups_result.relation_subjects
    conflicts: dict[tuple[str, str], list[str]] = {}
    subject_variants: dict[tuple[str, str], list[str]] = {}
    object_variants: dict[tuple[str, str], dict[str, list[str]]] = {}
    reported_relations: dict[tuple[str, str], dict[str, list[str]]] = {}
    parse_merges: dict[tuple[str, str], dict[str, list[str]]] = {}
    for pair, groups in by_key.items():
        subjects = raw_subjects[pair]
        if len(groups) <= 1:
            # No contradiction to report — but if folding is what collapsed the
            # objects, it *resolved* one the raw spellings would have fired, and
            # dropping the pair here would make that the only silent outcome in
            # the module. Keep the object channel so ``main`` can disclose it.
            # Gated on the fold, not on len(raws): a #116 scalar merge is not a
            # Unicode merge and must not be announced as one. Both merge
            # mechanisms open this gate — canonical equivalence (_fold_classes)
            # and a typed parse the fold enabled (_parse_merge) — because either
            # one lets finalize compile a KB the raw spellings would have blocked,
            # and this advisory is the only signal on that path.
            merged = {
                _representative(raws): names
                for raws in groups.values()
                if (names := _parse_merge(raws, unfolded[pair]))
            }
            merged = dict(sorted(merged.items()))
            if merged or any(_fold_classes(sorted(raws)) for raws in groups.values()):
                reported = (_representative(subjects), pair[1])
                object_variants[reported] = _variant_map(groups)
                reported_relations[reported] = _relation_map(object_relations[pair])
                if merged:
                    parse_merges[reported] = merged
            continue
        # Representative restoration on both axes: report strings as written.
        # Distinct folded subjects cannot share a representative (the choice is a
        # function of the fold), so reported keys stay unique.
        reported = (_representative(subjects), pair[1])
        objects = _variant_map(groups)
        conflicts[reported] = sorted(objects)
        subject_variants[reported] = sorted(subjects)
        object_variants[reported] = objects
        reported_relations[reported] = _relation_map(object_relations[pair])
        # A pair that still contradicts can ALSO hold a fold-enabled parse merge:
        # three values collapse to two, one of them merged only because folding
        # let a typed literal parse. The CONFLICT line then names the survivors
        # and the merged notation appears nowhere in the output — a row the
        # previous release listed by name simply vanishes, and the reader
        # supersedes what is on screen without knowing a third row is behind it.
        # Canonical-equivalence merges are disclosed on this path already (main's
        # per-object `_fold_classes` loop), so leaving this one to the exit-0
        # branch made the parse merge the single merge class with a hole.
        merged = {
            _representative(raws): names
            for raws in groups.values()
            if (names := _parse_merge(raws, unfolded[pair]))
        }
        merged = dict(sorted(merged.items()))
        if merged:
            parse_merges[reported] = merged
    relation_variants = {
        (_representative(relation_subjects[split]), split[1]): sorted(names)
        for split, names in raw_relations.items()
        if len(names) > 1
    }
    return ConflictScan(
        dict(sorted(conflicts.items())),
        dict(sorted(subject_variants.items())),
        dict(sorted(object_variants.items())),
        dict(sorted(parse_merges.items())),
        dict(sorted(relation_variants.items())),
        dict(sorted(reported_relations.items())),
    )


def collect_conflict_support(
    facts: list[dict[str, str]],
    single_valued: set[str],
    typed: dict[str, TypedRelSpec] | None = None,
    aliases: dict[str, str] | None = None,
) -> ConflictSupport:
    """Return distinct source provenance for each authoritative conflict value.

    The nested shape is ``{reported pair: {reported object: sorted sources}}``.
    Only contested pairs are included. Pair and object spellings use the same
    input-preserving representative rule as :func:`collect_conflicts`; source
    strings are preserved exactly, de-duplicated, and sorted. Both dictionary
    levels have sorted insertion order, so row permutations return equal and
    identically ordered results.

    This function and :func:`collect_conflicts` each call the same private
    builder exactly once. Each individual call therefore performs one
    authoritative ``engine_facts`` grouping pass; calling both APIs performs two
    independent passes, as expected.
    """
    grouped = _group_conflict_rows(facts, single_valued, typed, aliases)
    entries: list[tuple[tuple[str, str], dict[str, tuple[str, ...]]]] = []
    for pair, value_groups in grouped.by_key.items():
        if len(value_groups) <= 1:
            continue
        reported = (_representative(grouped.raw_subjects[pair]), pair[1])
        support = {
            _representative(raw_objects): tuple(sorted(grouped.sources[pair][key]))
            for key, raw_objects in value_groups.items()
        }
        entries.append((reported, dict(sorted(support.items()))))
    return dict(sorted(entries, key=lambda item: item[0]))


def detect_conflicts(
    facts: list[dict[str, str]],
    single_valued: set[str],
    typed: dict[str, TypedRelSpec] | None = None,
    aliases: dict[str, str] | None = None,
) -> dict[tuple[str, str], list[str]]:
    """Map (subject, canonical_relation) -> sorted distinct *display* objects,
    for single-valued relations that hold more than one *distinct value* (a
    contradiction).

    Distinctness is judged on the canonical grouping key (typed scalar when
    available, else the raw string — see ``_group_key``), so equivalent typed
    notations do not false-positive. The reported values, however, preserve the
    original object strings (provenance): each distinct key contributes one
    deterministic representative (an object seen for it, chosen by
    ``_representative``). Deterministic; never raises.

    Two grouping subtleties documented on ``_group_key``: ordinal collapses
    cross-unit notations onto the shared rank (rank-only contract, #218/#224 A),
    and a scalar wider than int64 groups here even though the engine skips its
    insertion (harmless grouping-only divergence, #224 C).

    **Alias canonicalization (#227):** when *aliases* is provided (non-empty),
    each row's relation is canonicalized via ``_canonicalize`` before the
    single-valued membership test and before grouping.  This causes surface
    variants that map to the same canonical name (e.g. ``게재연도`` and ``발행년도``
    both aliased to ``published_year``) to collide under one key, so a cross-
    variant contradiction is detected as a single conflict on the canonical
    name.  Relations that do **not** participate in the alias map are passed
    through verbatim (no normalization), preserving byte-identical behaviour for
    those predicates.

    When *aliases* is ``None`` or ``{}`` the function is byte-identical to the
    pre-#227 behaviour: the raw relation string is used throughout, and an NFD-
    authored relation name is reported exactly as written (no silent NFC coercion
    for non-participating relations).

    **Typed-spec lookup (#210):** the ``typed`` dict is keyed by NFC-normalized
    names (``typed_relations`` normalizes at ``common._parse_typed_relations``).
    The lookup first tries the canonical relation name (already NFC when it came
    from the alias map), then falls back to the NFC form of the raw relation
    string.  This ensures that an NFD-authored relation that also participates in
    the alias map still reaches its typed spec, so equivalent notations (억↔조)
    collapse correctly.

    **Unicode folding (#325):** the subject and untyped-object axes are folded to
    NFC, and the reported strings are restored to raw spellings seen. Callers that
    also need to know *which* raw spellings were merged should use
    ``collect_conflicts``, which documents the grouping in full and returns those
    maps alongside this dict."""
    return collect_conflicts(facts, single_valued, typed, aliases).conflicts
