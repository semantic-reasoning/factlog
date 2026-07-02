# SPDX-License-Identifier: Apache-2.0
"""Unit tests for source-path helpers: glob matching and ref keying."""
from __future__ import annotations

import common
import pytest


class TestSourceRelKey:
    def test_original_keeps_full_name(self):
        # An original keeps its extension (#213: extension is part of the key).
        assert common.source_rel_key("sources/a/report.pdf") == "a/report.pdf"

    def test_conversion_pairs_with_original(self):
        # The binary original and its runs/sources conversion key identically:
        # ingest names the conversion <original-full-name>.<out-suffix>.
        assert common.source_rel_key("runs/sources/a/report.pdf.md") == "a/report.pdf"
        assert common.source_rel_key("sources/a/report.pdf") == "a/report.pdf"

    def test_same_stem_different_ext_do_not_collide(self):
        # The #213 bug: report.hwpx and report.pptx must key distinctly so each
        # pairs with only its own conversion.
        assert common.source_rel_key("sources/report.hwpx") == "report.hwpx"
        assert common.source_rel_key("sources/report.pptx") == "report.pptx"
        assert common.source_rel_key("sources/report.hwpx") != common.source_rel_key(
            "sources/report.pptx"
        )
        assert common.source_rel_key("runs/sources/report.hwpx.md") == "report.hwpx"
        assert common.source_rel_key("runs/sources/report.pptx.md") == "report.pptx"

    def test_top_level_full_name(self):
        assert common.source_rel_key("sources/report.pdf") == "report.pdf"

    def test_subdirs_do_not_collide(self):
        assert common.source_rel_key("sources/a/report.pdf") != common.source_rel_key(
            "sources/b/report.pdf"
        )


class TestGlobToRegex:
    def _match(self, pattern, ref):
        import re

        return re.match(common._glob_to_regex(pattern), ref) is not None

    def test_star_stays_within_segment(self):
        assert self._match("drafts/*.md", "drafts/x.md")
        assert not self._match("drafts/*.md", "drafts/sub/x.md")

    def test_doublestar_crosses_segments(self):
        assert self._match("drafts/**", "drafts/sub/x.md")
        assert self._match("drafts/**", "drafts/x.md")

    def test_trailing_slash_is_subtree(self):
        assert self._match("drafts/", "drafts/sub/x.md")

    def test_question_mark_single_char(self):
        assert self._match("a?.md", "ab.md")
        assert not self._match("a?.md", "a/.md")


class TestIsSyncIgnored:
    def test_empty_patterns_never_ignores(self):
        assert not common.is_sync_ignored("sources/x.md", [])

    def test_matches_within_source_root(self):
        assert common.is_sync_ignored("sources/drafts/x.md", ["drafts/*.md"])

    def test_matches_full_ref(self):
        assert common.is_sync_ignored("sources/wip.md", ["sources/wip.md"])

    def test_non_match(self):
        assert not common.is_sync_ignored("sources/keep.md", ["drafts/*.md"])

    @pytest.mark.parametrize("ref", ["sources/x.md", "runs/sources/x.md"])
    def test_both_source_roots(self, ref):
        assert common.is_sync_ignored(ref, ["x.md"])
