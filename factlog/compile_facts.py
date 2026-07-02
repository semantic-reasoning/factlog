#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile confirmed factlog facts into a Datalog-like fact file."""

from __future__ import annotations

import unicodedata

from factlog.common import (
    FACTS_DIR,
    corroboration_counts,
    dedup_engine_atoms,
    dl_atom,
    engine_facts,
    ensure_dirs,
    load_facts,
    relation_aliases,
)


def main() -> None:
    ensure_dirs()
    facts = load_facts()
    # Collapse the same (subject, relation, object) accepted from several sources
    # to a single engine atom so accepted.dl / ask / run_logic_check use set
    # semantics. Source aggregation (sources: N, provenance) stays on the
    # candidates path and is unaffected. First-occurrence keeps accepted.dl
    # byte-identical when there are no duplicate triples.
    accepted = dedup_engine_atoms(engine_facts(facts))
    lines = [
        "// generated from facts/candidates.csv",
        "// only confirmed/accepted facts become engine input",
        "",
    ]
    for row in accepted:
        lines.append(dl_atom(row))

    # Canonical side-atoms (#188): a human-declared alias in
    # policy/relation-aliases.md maps a surface variant relation to a canonical
    # name so a policy rule written against the canonical predicate can fire over
    # facts stated with the variant. These are PARALLEL indexing atoms — the
    # original variant atom above is emitted verbatim and untouched, and the
    # candidates path (sources / provenance) is unaffected. Absent alias file →
    # relation_aliases() returns {} and this block is a complete no-op (accepted.dl
    # stays byte-identical). A malformed alias file raises FactlogError, which
    # propagates and fails the compile loudly (no silent side-atom drop).
    aliases = relation_aliases()
    if aliases:
        # (b) triples already emitted directly (a canonical name may be extracted
        # firsthand, or two variants may collapse to the same canonical triple):
        # a side-atom is only emitted when it is NOT already an original atom, so
        # accepted.dl never carries a duplicate triple.
        original_triples = {
            (row["subject"], row["relation"], row["object"]) for row in accepted
        }
        seen_side: set[tuple[str, str, str]] = set()  # (a) dedup side-atoms
        side_lines: list[str] = []
        for row in accepted:
            canonical = aliases.get(unicodedata.normalize("NFC", row["relation"]))
            if canonical is None:
                continue
            triple = (row["subject"], canonical, row["object"])
            if triple in original_triples or triple in seen_side:
                continue
            seen_side.add(triple)
            side_lines.append(
                dl_atom(
                    {
                        "subject": row["subject"],
                        "relation": canonical,
                        "object": row["object"],
                    }
                )
            )
        if side_lines:
            lines.append("")
            lines.append("// canonical side-atoms (policy/relation-aliases.md)")
            lines.extend(side_lines)

    out = FACTS_DIR / "accepted.dl"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Distinct-source count per collapsed triple, so the compile log surfaces the
    # multi-source provenance of a deduped atom (observability only — accepted.dl,
    # render's `sources: N`, and provenance are unchanged). Computed on the
    # candidates path (corroboration_counts), which is untouched by the dedup.
    source_counts = corroboration_counts(facts)
    print(f"engine facts: {len(accepted)} / {len(facts)}")
    for row in accepted:
        key = (row["subject"], row["relation"], row["object"])
        n_sources = source_counts.get(key, 1)
        print(
            "  - "
            f"{row['subject']} / {row['relation']} / {row['object']} "
            f"(confidence={row['confidence']}, source={row['source']}, sources={n_sources})"
        )
    print(f"written: {out}")


if __name__ == "__main__":
    from factlog.common import run_cli

    raise SystemExit(run_cli(main))
