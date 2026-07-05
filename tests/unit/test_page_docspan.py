# SPDX-License-Identifier: Apache-2.0
"""Regression tests for the page-only "spans N distinct documents" salience cue.

``write_pages`` prepends ONE plain-text line into the ``{{SOURCES}}`` block when
an entity's facts come from >=2 distinct source *documents* (anchor stripped,
NFC-normalized), so a human can spot a possible homonym merge. Single-doc /
empty-source entities must be byte-identical to the pre-change output.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import merge_candidates

# The exact cue substring the feature must (and only-multi-doc must) emit.
_CUE_MARKER = "서로 다른 문서"


def _row(subject: str, obj: str, source: str, status: str = "accepted") -> dict[str, str]:
    return {
        "subject": subject,
        "relation": "통합_대상",
        "object": obj,
        "source": source,
        "status": status,
        "confidence": "0.9",
        "note": "",
    }


def _init_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "wiki"
    (kb / "pages").mkdir(parents=True)
    return kb


def _page_text(kb: Path, entity: str) -> str:
    page = kb / "pages" / merge_candidates.page_filename(entity)
    return page.read_text(encoding="utf-8")


def _sources_block(page_text: str) -> str:
    """Extract the rendered SOURCES section from a generated default-template page."""
    # Default template renders "## 출처" then the SOURCES block; slice between the
    # SOURCES heading and the next "## " heading. This keeps the assertion robust
    # to the surrounding template without pinning the whole page byte layout.
    lines = page_text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## 출처"))
    rest = lines[start + 1 :]
    end = next((i for i, ln in enumerate(rest) if ln.startswith("## ")), len(rest))
    return "\n".join(rest[:end]).strip("\n")


class TestDocspanCue:
    def test_multi_doc_cue_present(self, tmp_path: Path):
        """Facts from two distinct docs -> cue line naming '2개' + both sources listed."""
        kb = _init_kb(tmp_path)
        rows = [
            _row("갑봇", "값가", "sources/a.md"),
            _row("갑봇", "값나", "sources/b.md"),
        ]
        merge_candidates.write_pages(kb, rows)
        block = _sources_block(_page_text(kb, "갑봇"))
        assert "서로 다른 문서 2개" in block
        assert "- sources/a.md" in block
        assert "- sources/b.md" in block

    def test_anchor_only_difference_no_cue(self, tmp_path: Path):
        """Same file, different #anchor -> one distinct doc -> no cue; block ==
        the plain no-cue baseline."""
        kb = _init_kb(tmp_path)
        rows = [
            _row("갑봇", "값가", "sources/a.md#s1"),
            _row("갑봇", "값나", "sources/a.md#s2"),
        ]
        merge_candidates.write_pages(kb, rows)
        block = _sources_block(_page_text(kb, "갑봇"))
        assert _CUE_MARKER not in block
        # Byte-identical to the plain sorted source list (no cue prepended).
        expected = "\n".join(sorted({"- sources/a.md#s1", "- sources/a.md#s2"}))
        assert block == expected

    def test_single_doc_byte_identical(self, tmp_path: Path):
        """One document -> no cue; SOURCES section equals the plain source list."""
        kb = _init_kb(tmp_path)
        rows = [
            _row("갑봇", "값가", "sources/a.md"),
            _row("갑봇", "값나", "sources/a.md"),
        ]
        merge_candidates.write_pages(kb, rows)
        block = _sources_block(_page_text(kb, "갑봇"))
        assert _CUE_MARKER not in block
        assert block == "- sources/a.md"

    def test_superseded_second_doc_excluded(self, tmp_path: Path):
        """A superseded row from a 2nd doc must not raise the distinct-doc count
        (relies on the upstream superseded filter) -> single-doc -> no cue."""
        kb = _init_kb(tmp_path)
        rows = [
            _row("갑봇", "값가", "sources/a.md"),
            _row("갑봇", "값나", "sources/b.md", status="superseded"),
        ]
        merge_candidates.write_pages(kb, rows)
        block = _sources_block(_page_text(kb, "갑봇"))
        assert _CUE_MARKER not in block
        assert block == "- sources/a.md"

    def test_nfd_nfc_same_file_one_doc(self, tmp_path: Path):
        """Two rows whose source paths differ only by Unicode normalization of the
        same filename count as one document -> no cue."""
        kb = _init_kb(tmp_path)
        name_nfc = "sources/각문서.md"
        name_nfd = unicodedata.normalize("NFD", name_nfc)
        assert name_nfc != name_nfd  # guard: the two encodings really differ as text
        rows = [
            _row("갑봇", "값가", name_nfc),
            _row("갑봇", "값나", name_nfd),
        ]
        merge_candidates.write_pages(kb, rows)
        block = _sources_block(_page_text(kb, "갑봇"))
        assert _CUE_MARKER not in block
