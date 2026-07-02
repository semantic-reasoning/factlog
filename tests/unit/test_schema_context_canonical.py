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
