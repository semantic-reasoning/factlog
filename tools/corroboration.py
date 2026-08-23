#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Report multi-source corroboration for engine-input facts.

For each accepted fact, how many DISTINCT sources back it (a trust signal a plain
notes wiki cannot give); and, for single-valued relations, the competing values
with their per-source support — the source-level view of a contradiction.

Informational: always exits 0.

Usage:
    python3 corroboration.py [--wiki <kb>]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


# Resolve the KB root and export it before importing common, which binds
# its module-level paths from FACTLOG_ROOT at import time.
import factlog_config  # noqa: E402

os.environ["FACTLOG_ROOT"] = factlog_config.resolve_root_from_argv("--wiki")

from common import (  # noqa: E402
    FactlogError,
    composed_spelling,
    engine_atom_key,
    engine_facts,
    ensure_dirs,
    load_facts,
    relation_aliases,
    single_valued_relations,
    typed_relations,
)
from factlog.conflicts import collect_conflict_support  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report multi-source corroboration of facts.")
    # --wiki is resolved by the import-time prepass (it must set FACTLOG_ROOT
    # before common is imported); this declaration is only for --help/validation.
    parser.add_argument("--wiki", default=os.environ.get("FACTLOG_ROOT", "."), help="KB root")
    parser.parse_args(argv)

    ensure_dirs()
    facts = load_facts()
    # `common.engine_atom_key` — the same fold `common.corroboration_counts` now
    # uses, since #342 made engine atoms fold too and the raw triple stopped
    # being the right key anywhere. The loop stays here rather than calling that
    # helper only because it collects the per-axis spellings in the same pass.
    #
    # The competing-values clause below folds the subject and object axes; the
    # head line and this list used the raw triple, so one report answered "how
    # many facts, how many corroborated" on one equivalence and "which values
    # compete" on another. Two spellings of one fact backed by two different
    # sources were counted as two facts with one source each — the corroboration
    # signal this tool exists to give, under-reported in exactly the mixed KB
    # #325 is about. Sources are counted per folded fact, so a source backing
    # both spellings counts once (summing the raw counts would double it). The
    # The general fact list follows raw engine relation identity until #386;
    # the competing-values clause uses the conflict core's folded relation axis.
    backing: dict[tuple[str, str, str], set[str]] = {}
    triple_spellings: dict[tuple[str, str, str], tuple[set[str], set[str]]] = {}
    for row in engine_facts(facts):
        key = engine_atom_key(row)
        backing.setdefault(key, set()).add(row["source"])
        subjects, objects = triple_spellings.setdefault(key, (set(), set()))
        subjects.add(row["subject"])
        objects.add(row["object"])
    counts = {key: len(srcs) for key, srcs in backing.items()}
    if not counts:
        print("corroboration: no engine-input facts")
        return 0

    multi = sum(1 for n in counts.values() if n > 1)
    print(f"corroboration: {len(counts)} fact(s); {multi} backed by >1 source")
    for key, n in sorted(counts.items()):
        # Report spellings that were actually written, the same provenance rule
        # the competing-values clause follows.
        subjects, objects = triple_spellings[key]
        print(
            f"  {n} source(s): {composed_spelling(subjects)}, {key[1]}, "
            f"{composed_spelling(objects)}"
        )

    # Source-level view of single-valued competition: same (subject, relation)
    # given different objects (each with its own source support).
    failed: list[str] = []
    try:
        single_valued = single_valued_relations()
    except (FactlogError, OSError, ValueError):
        single_valued = set()
        failed.append("single-valued.md")
    if not failed and not single_valued:
        return 0

    # Policy inputs are independent: collect every failure in a deterministic
    # order and never fall back to a raw grouping that could claim a false
    # competition. The general corroboration report above remains useful.
    try:
        typed = typed_relations(emit_warnings=False)
    except (FactlogError, OSError, ValueError):
        typed = {}
        failed.append("typed-relations.md")
    try:
        aliases = relation_aliases()
    except (FactlogError, OSError, ValueError):
        aliases = {}
        failed.append("relation-aliases.md")
    if failed:
        print(
            "\ncorroboration: competing-values analysis unavailable ("
            + ", ".join(failed) + "); fix policy"
        )
        return 0

    support = collect_conflict_support(facts, single_valued, typed, aliases)
    if support:
        print(f"\ncorroboration: {len(support)} single-valued relation(s) with competing values")
        for pair, objects in support.items():
            detail = "; ".join(
                f"{obj} ({len(sources)} src)" for obj, sources in objects.items()
            )
            print(f"  {pair[0]} / {pair[1]}: {detail}")
    return 0


if __name__ == "__main__":
    from common import run_cli

    sys.exit(run_cli(main))
