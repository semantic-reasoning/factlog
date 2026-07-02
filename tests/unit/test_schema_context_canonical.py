# SPDX-License-Identifier: Apache-2.0
"""Unit tests for schema_context canonical relation exposure (#188).

_canonical_relation_lines() is the load-bearing new logic spliced into
schema_context: it lists human-declared canonical relation names and their
surface variants (policy/relation-aliases.md) so a query author prefers the
canonical name. Absent alias file → empty list → schema_context byte-identical.
"""
from __future__ import annotations

import common  # noqa: F401  (conftest puts the repo root on sys.path via this wrapper)
from factlog import common as fc  # patch the real module the functions close over


def _write_alias_file(tmp_path, text: str):
    policy = tmp_path / "policy"
    policy.mkdir(parents=True, exist_ok=True)
    (policy / "relation-aliases.md").write_text(text, encoding="utf-8")
    return policy


class TestCanonicalRelationLines:
    def test_no_alias_file_returns_empty(self, tmp_path, monkeypatch):
        # No policy/relation-aliases.md → section omitted entirely → the
        # schema_context splice adds nothing, keeping output byte-identical.
        (tmp_path / "policy").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(fc, "POLICY_DIR", tmp_path / "policy")
        assert fc._canonical_relation_lines() == []

    def test_alias_file_lists_canonicals_and_variants(self, tmp_path, monkeypatch):
        policy = _write_alias_file(
            tmp_path,
            "# Relation aliases\n"
            "- `게재연도` -> `published_year`\n"
            "- `publication_year` -> `published_year`\n"
            "- `결론` -> `concludes`\n",
        )
        monkeypatch.setattr(fc, "POLICY_DIR", policy)
        lines = fc._canonical_relation_lines()
        assert lines[0] == "Canonical relation names (prefer these):"
        # canonicals sorted; variants sorted within each canonical
        assert "- concludes <- 결론" in lines
        assert "- published_year <- publication_year, 게재연도" in lines
        # trailing blank line so the section is separated in the joined output
        assert lines[-1] == ""

    def test_multiple_canonicals_sorted(self, tmp_path, monkeypatch):
        policy = _write_alias_file(
            tmp_path,
            "- `z1` -> `zeta`\n- `a1` -> `alpha`\n",
        )
        monkeypatch.setattr(fc, "POLICY_DIR", policy)
        lines = fc._canonical_relation_lines()
        assert lines.index("- alpha <- a1") < lines.index("- zeta <- z1")


class TestSideAtomExclusion:
    """Synthetic canonical side-atoms (#188) live in accepted.dl for the engine
    but must NOT surface as verbatim confirmed facts. _load_accepted_facts_from
    with include_side_atoms=False drops everything after the shared marker; the
    default keeps them so the engine still consumes them."""

    ACCEPTED = (
        "// generated from facts/candidates.csv\n"
        "// only confirmed/accepted facts become engine input\n"
        "\n"
        'relation("논문갑", "결론", "무효").\n'
        "\n"
        f"{fc.CANONICAL_SIDE_ATOM_MARKER}\n"
        'relation("논문갑", "concludes", "무효").\n'
    )

    def _write(self, tmp_path):
        path = tmp_path / "accepted.dl"
        path.write_text(self.ACCEPTED, encoding="utf-8")
        return path

    def test_default_includes_side_atoms_for_engine(self, tmp_path):
        rows = fc._load_accepted_facts_from(self._write(tmp_path))
        rels = {r["relation"] for r in rows}
        assert "결론" in rels and "concludes" in rels  # engine sees both

    def test_exclude_drops_side_atoms(self, tmp_path):
        rows = fc._load_accepted_facts_from(
            self._write(tmp_path), include_side_atoms=False
        )
        rels = {r["relation"] for r in rows}
        assert rels == {"결론"}  # only the verbatim human fact
        assert "concludes" not in rels

    def test_exclude_no_marker_is_noop(self, tmp_path):
        # accepted.dl with no side-atom block → exclusion changes nothing.
        path = tmp_path / "accepted.dl"
        path.write_text('relation("a", "b", "c").\n', encoding="utf-8")
        assert fc._load_accepted_facts_from(path, include_side_atoms=False) == (
            fc._load_accepted_facts_from(path, include_side_atoms=True)
        )
