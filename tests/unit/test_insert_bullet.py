# SPDX-License-Identifier: Apache-2.0
"""Regression tests for merge_candidates.insert_bullet idempotency (#104)."""
from __future__ import annotations

import merge_candidates as mc

SECTION = "## 출처 부족"


class TestInsertBullet:
    def test_exact_duplicate_is_skipped(self):
        base = f"# Open Questions\n\n{SECTION}\n- foo\n"
        assert mc.insert_bullet(base, SECTION, "- foo") == base

    def test_prefix_substring_bullet_is_still_added(self):
        # #104: "- note" must NOT be considered present just because
        # "- note extra" already is.
        base = f"# Open Questions\n\n{SECTION}\n- note extra\n"
        out = mc.insert_bullet(base, SECTION, "- note")
        assert "- note extra" in out
        # the new shorter bullet was actually inserted as its own line
        assert any(line.rstrip() == "- note" for line in out.splitlines())

    def test_new_section_created_when_missing(self):
        out = mc.insert_bullet("# Open Questions\n", SECTION, "- bar")
        assert SECTION in out and "- bar" in out
