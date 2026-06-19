# SPDX-License-Identifier: Apache-2.0
"""Unit tests for source-path helpers: glob matching and ref keying."""
from __future__ import annotations

import common
import pytest


class TestSourceRelKey:
    def test_strips_sources_prefix_and_suffix(self):
        assert common.source_rel_key("sources/a/report.pdf") == "a/report"

    def test_conversion_pairs_with_original(self):
        # The binary original and its runs/sources conversion key identically.
        assert common.source_rel_key("runs/sources/a/report.md") == "a/report"
        assert common.source_rel_key("sources/a/report.pdf") == "a/report"

    def test_top_level_unchanged(self):
        assert common.source_rel_key("sources/report.pdf") == "report"

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
