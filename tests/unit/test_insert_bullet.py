# SPDX-License-Identifier: Apache-2.0
"""Regression tests for merge_candidates.insert_bullet idempotency (#104)."""
from __future__ import annotations

import pytest

import merge_candidates as mc
from factlog.markdown import scan_markdown_structure

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

    def test_fenced_heading_and_duplicate_bullet_are_ignored(self):
        base = (
            "# Open Questions\n\n"
            "```markdown\n"
            f"{SECTION}\n"
            "- foo\n"
            "```\n"
        )
        out = mc.insert_bullet(base, SECTION, "- foo")
        structure = scan_markdown_structure(out)
        outside = [structure.lines[index] for index in structure.outside_indexes]
        assert outside.count(SECTION) == 1
        assert outside.count("- foo") == 1
        assert out.count(SECTION) == 2
        assert out.count("- foo") == 2
        assert mc.insert_bullet(out, SECTION, "- foo") == out

    def test_fenced_heading_is_not_the_real_section_boundary(self):
        base = (
            f"# Open Questions\n\n{SECTION}\nprose\n"
            "```markdown\n## fenced decoy\n```\n"
            "tail\n## real next section\n"
        )
        out = mc.insert_bullet(base, SECTION, "- added")
        assert out.index("## fenced decoy") < out.index("tail")
        assert out.index("tail") < out.index("- added")
        assert out.index("- added") < out.index("## real next section")

    @pytest.mark.parametrize(
        ("opening", "closing"),
        [
            ("```python", "```"),
            (" ````python", " `````"),
            ("  ~~~~ markdown", "  ~~~~\t"),
            ("   ~~~", "   ~~~~~"),
        ],
    )
    @pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
    def test_commonmark_fence_forms_hide_structural_lines(
        self, opening, closing, ending
    ):
        text = ending.join((opening, SECTION, "- foo", closing)) + ending
        structure = scan_markdown_structure(text)
        outside = [structure.lines[index] for index in structure.outside_indexes]
        assert SECTION not in outside
        assert "- foo" not in outside
        assert structure.unclosed_fence_start is None

    @pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
    def test_unicode_separators_do_not_manufacture_structural_lines(self, separator):
        text = f"prose{separator}{SECTION}{separator}- foo"
        structure = scan_markdown_structure(text)
        assert structure.lines == (text,)
        assert mc.insert_bullet(text, SECTION, "- foo") == (
            f"{text}\n\n{SECTION}\n- foo\n"
        )

    def test_four_space_fence_like_text_is_not_a_fence(self):
        text = f"    ```markdown\n{SECTION}\n    ```\n"
        structure = scan_markdown_structure(text)
        assert structure.outside_indexes == (0, 1, 2)
        out = mc.insert_bullet(text, SECTION, "- foo")
        assert out.count(SECTION) == 1

    def test_backtick_in_backtick_info_string_is_not_an_opener(self):
        text = f"```python`bad\n{SECTION}\n- old\n"
        structure = scan_markdown_structure(text)
        assert structure.outside_indexes == (0, 1, 2)
        assert mc.insert_bullet(text, SECTION, "- old") == text

    @pytest.mark.parametrize(
        ("opening", "invalid_closer", "valid_closer"),
        [
            ("````", "```", "````"),
            ("```", "~~~", "```"),
            ("~~~", "```", "~~~"),
            ("```", "``` trailing text", "```"),
            ("~~~", "~~~ trailing text", "~~~"),
        ],
    )
    def test_invalid_closer_keeps_decoy_structure_inside_fence(
        self, opening, invalid_closer, valid_closer
    ):
        text = "\n".join(
            (
                opening,
                invalid_closer,
                SECTION,
                "- fenced bullet",
                valid_closer,
                "outside prose",
            )
        )
        structure = scan_markdown_structure(text)
        assert structure.outside_indexes == (5,)
        assert structure.lines[structure.outside_indexes[0]] == "outside prose"

    def test_unclosed_fence_uses_safe_boundary_for_existing_section(self):
        base = f"# Open\r\n\r\n{SECTION}\r\nprose\r\n```markdown\r\ncode  \r\n"
        suffix = "```markdown\r\ncode  \r\n"
        expected = f"# Open\n\n{SECTION}\nprose\n\n- foo\n" + suffix
        out = mc.insert_bullet(base, SECTION, "- foo")
        assert out == expected
        assert out[out.index("```markdown") :] == suffix
        assert out.count("```") == 1
        assert mc.insert_bullet(out, SECTION, "- foo") == out

    def test_unclosed_fence_uses_safe_boundary_for_missing_section(self):
        base = "# Open\r\n```markdown\r\ncode  \r\n"
        suffix = "```markdown\r\ncode  \r\n"
        expected = f"# Open\r\n\n{SECTION}\n- foo\n\n" + suffix
        out = mc.insert_bullet(base, SECTION, "- foo")
        assert out == expected
        assert out[out.index("```markdown") :] == suffix
        assert out.count("```") == 1
        assert mc.insert_bullet(out, SECTION, "- foo") == out

    @pytest.mark.parametrize("ending", ["\r\n", "\r"])
    def test_found_section_preserves_historical_lf_normalization(self, ending):
        base = ending.join(("# Open", "", SECTION, "old", "## Next")) + ending
        assert mc.insert_bullet(base, SECTION, "- foo") == (
            f"# Open\n\n{SECTION}\nold\n\n- foo\n## Next\n"
        )

    @pytest.mark.parametrize(
        ("base", "expected"),
        [
            ("# Open", f"# Open\n\n{SECTION}\n- foo\n"),
            ("# Open\n", f"# Open\n\n{SECTION}\n- foo\n"),
            ("# Open\r\n \t", f"# Open\r\n \t\n\n{SECTION}\n- foo\n"),
            ("# Open\r", f"# Open\r\n\n{SECTION}\n- foo\n"),
        ],
    )
    def test_missing_section_preserves_historical_append_bytes(self, base, expected):
        assert mc.insert_bullet(base, SECTION, "- foo") == expected
