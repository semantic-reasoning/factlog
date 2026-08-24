# SPDX-License-Identifier: Apache-2.0
"""A freshly ``factlog init``ed KB must pass ``tools/validate.py`` (#327).

The policy half of that promise lives in ``test_validate_empty_policy.py``. This
module covers the scaffold half: ``init`` never wrote ``facts/candidates.csv`` or
``decisions/open-questions.md``, and ``validate`` requires both — including four
review-section headings that only ever appeared once a ``needs_review`` fact of
that exact class happened to show up. So a new user's first ``validate`` was
rc=1 with nothing they had done wrong.

The fix is in ``init``, not in ``validate``: the fact-ledger header is the schema
contract, and the four review sections are a standing contract a reviewer reads
("here is what was looked at"), not a by-product of the facts. Narrowing
``validate`` to "only require a section that already has bullets" would instead
let a KB silently lose the 충돌 section and only notice on the day a conflict
appears — the exact class of rot validate exists to catch. So the section check
stays total, and the drift pins below hold it there.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import validate
from common import FACT_HEADER
from factlog.markdown import scan_markdown_structure

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from factlog.cli import _TEMPLATES, _init_kb  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# (heading the scaffold writes, diagnostic label). Kept in canonical order so a
# parametrised failure names the section a reader can find.
SCAFFOLDED_SECTIONS = [
    ("## 중복 개념 후보", "중복"),
    ("## 모호한 관계명", "모호"),
    ("## 출처 부족", "출처"),
    ("## 기존 내용과 충돌할 수 있는 항목", "충돌"),
]


@pytest.fixture()
def fresh_kb(tmp_path, capsys):
    """A KB in exactly the state ``factlog init`` leaves it.

    ``_init_kb`` is ``cmd_init``'s scaffold body without the
    ``factlog_config.write_root`` call, so this never touches the developer's
    active-KB config.
    """
    kb = tmp_path / "kb"
    _init_kb(kb)
    capsys.readouterr()
    return kb


class TestFreshInitPassesValidate:
    def test_validate_reports_no_errors(self, fresh_kb):
        assert validate.validate(fresh_kb) == []

    def test_validate_script_exits_zero(self, fresh_kb):
        # The user-visible contract from the issue: rc=0 straight after init.
        env = dict(os.environ, FACTLOG_ROOT=str(fresh_kb))
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "validate.py"), str(fresh_kb)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr

    def test_init_scaffolds_the_review_sections(self, fresh_kb):
        text = (fresh_kb / "decisions" / "open-questions.md").read_text(encoding="utf-8")
        for section in ["중복", "모호", "출처", "충돌"]:
            assert section in text

    def test_scaffolded_headings_match_the_sync_headings(self, fresh_kb):
        # merge_candidates.decision_section() emits these exact headings; if the
        # scaffold drifts from them, `sync` appends duplicate sections instead of
        # filling the ones init created.
        import merge_candidates

        lines = (fresh_kb / "decisions" / "open-questions.md").read_text(
            encoding="utf-8"
        ).splitlines()
        for note in ["중복", "모호한 관계", "출처", "충돌"]:
            heading = merge_candidates.decision_section({"note": note})
            assert heading in lines, f"{heading!r} not scaffolded"
        assert tuple(heading for heading, _keyword in SCAFFOLDED_SECTIONS) == validate.REVIEW_HEADINGS

    def test_init_scaffolds_the_candidates_header(self, fresh_kb):
        csv_path = fresh_kb / "facts" / "candidates.csv"
        assert csv_path.read_text(encoding="utf-8") == ",".join(FACT_HEADER) + "\n"

    def test_candidates_template_tracks_fact_header(self):
        # Single source of truth: validate compares the header against
        # FACT_HEADER, so the template must be derived from it, not retyped.
        assert _TEMPLATES["facts/candidates.csv"] == ",".join(FACT_HEADER) + "\n"


class TestScaffoldIsNotADoormat:
    """The other direction: a fresh KB passing must not mean validate went blind."""

    @pytest.mark.parametrize("heading,keyword", SCAFFOLDED_SECTIONS)
    def test_removed_review_section_is_still_an_error(self, fresh_kb, heading, keyword):
        # Only the heading line goes; the rest of the scaffold stays. Validation
        # requires each canonical heading as an exact line, so prose mentioning a
        # section cannot answer the check on a deleted heading's behalf.
        decisions = fresh_kb / "decisions" / "open-questions.md"
        lines = decisions.read_text(encoding="utf-8").splitlines()
        assert heading in lines, f"{heading!r} not scaffolded"
        decisions.write_text(
            "\n".join(line for line in lines if line != heading) + "\n", encoding="utf-8"
        )
        errors = validate.validate(fresh_kb)
        assert any(repr(heading) in e for e in errors), (keyword, errors)

    def test_deleted_open_questions_is_still_an_error(self, fresh_kb):
        (fresh_kb / "decisions" / "open-questions.md").unlink()
        assert "missing decisions/open-questions.md" in validate.validate(fresh_kb)

    def test_deleted_candidates_csv_is_still_an_error(self, fresh_kb):
        (fresh_kb / "facts" / "candidates.csv").unlink()
        assert "missing facts/candidates.csv" in validate.validate(fresh_kb)

    def test_corrupted_candidates_header_is_still_an_error(self, fresh_kb):
        (fresh_kb / "facts" / "candidates.csv").write_text("a,b,c\n", encoding="utf-8")
        assert any(
            "candidates.csv header must be" in e for e in validate.validate(fresh_kb)
        ), validate.validate(fresh_kb)

    def test_needs_review_without_bullets_is_still_an_error(self, fresh_kb):
        (fresh_kb / "sources" / "x.md").write_text("# x\n\n## s\n\nbody\n", encoding="utf-8")
        (fresh_kb / "pages" / "a.md").write_text("# A\n\nsources/x.md\n", encoding="utf-8")
        (fresh_kb / "facts" / "candidates.csv").write_text(
            ",".join(FACT_HEADER) + "\n" "A,uses,B,sources/x.md,needs_review,0.9,ambiguous\n",
            encoding="utf-8",
        )
        errors = validate.validate(fresh_kb)
        assert any("no review bullets" in e for e in errors), errors


class TestSyncFillsTheScaffoldedSections:
    def test_sync_adds_no_heading_of_its_own(self, fresh_kb):
        # The scaffold/sync seam: with the headings already present,
        # merge_candidates must insert into them rather than append a second copy.
        #
        # The load-bearing assertion is that the set of `## ` headings is
        # BYTE-IDENTICAL before and after sync. Asserting only "the bullet landed
        # under a 중복 heading" does not pin this: insert_bullet falls back to
        # appending the section when it cannot find one, so a sync-created
        # heading looks exactly like an init-created one from the bullet's point
        # of view — that weaker form passed both with the scaffold deleted and
        # with a scaffold heading drifted.
        import merge_candidates

        decisions = fresh_kb / "decisions" / "open-questions.md"
        before = [
            line
            for line in decisions.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        ]
        assert before, "init scaffolded no review headings at all"

        merge_candidates.write_decisions(
            fresh_kb,
            [
                {
                    "subject": "A",
                    "relation": "same_as",
                    "object": "B",
                    "source": "sources/x.md",
                    "status": "needs_review",
                    "confidence": "0.5",
                    "note": "duplicate?",
                }
            ],
        )
        after = [
            line
            for line in decisions.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ")
        ]
        assert after == before, (
            "sync changed the heading list — it appended its own section instead "
            f"of filling a scaffolded one: {before!r} -> {after!r}"
        )

    def test_bullet_lands_inside_the_duplicate_section(self, fresh_kb):
        # Placement, given the headings match: the bullet goes under 중복, not at
        # the end of the file. This one does NOT pin the seam — see the test
        # above for that.
        import merge_candidates

        merge_candidates.write_decisions(
            fresh_kb,
            [
                {
                    "subject": "A",
                    "relation": "same_as",
                    "object": "B",
                    "source": "sources/x.md",
                    "status": "needs_review",
                    "confidence": "0.5",
                    "note": "duplicate?",
                }
            ],
        )
        lines = (fresh_kb / "decisions" / "open-questions.md").read_text(
            encoding="utf-8"
        ).splitlines()
        assert lines.count("## 중복 개념 후보") == 1
        heading = lines.index("## 중복 개념 후보")
        following = lines[heading:]
        bullet = next(i for i, line in enumerate(following) if line.startswith("- needs_review:"))
        next_heading = next(
            (i for i, line in enumerate(following[1:], start=1) if line.startswith("## ")),
            len(following),
        )
        assert bullet < next_heading, "bullet did not land inside the 중복 section"


class TestFencedLedgerWriterValidatorParity:
    def test_needs_review_fenced_bullet_fails_then_writer_repairs_once(self, fresh_kb):
        import merge_candidates

        row = {
            "subject": "A",
            "relation": "related_to",
            "object": "B",
            "source": "sources/x.md",
            "status": "needs_review",
            "confidence": "0.5",
            "note": "ambiguous",
        }
        facts = fresh_kb / "facts" / "candidates.csv"
        facts.write_text(
            ",".join(FACT_HEADER) + "\n" + ",".join(row[key] for key in FACT_HEADER) + "\n",
            encoding="utf-8",
        )
        ledger = fresh_kb / "decisions" / "open-questions.md"
        expected_bullet = (
            "- needs_review: A / related_to / B "
            "(sources/x.md, confidence=0.5) - ambiguous"
        )
        ledger.write_text(
            _TEMPLATES["decisions/open-questions.md"]
            + f"\n```markdown\n{expected_bullet}\n```\n",
            encoding="utf-8",
        )
        error = "needs_review facts exist but decisions/open-questions.md has no review bullets"
        assert error in validate.validate(fresh_kb)

        assert merge_candidates.write_decisions(fresh_kb, [row]) == [expected_bullet]
        assert error not in validate.validate(fresh_kb)
        first = ledger.read_bytes()
        assert merge_candidates.write_decisions(fresh_kb, [row]) == []
        assert ledger.read_bytes() == first
        structure = scan_markdown_structure(ledger.read_text(encoding="utf-8"))
        outside = [structure.lines[index] for index in structure.outside_indexes]
        assert outside.count(expected_bullet) == 1

    def test_stale_fenced_record_fails_then_writer_repairs_once(self, fresh_kb):
        import merge_candidates

        page = fresh_kb / "pages" / "a.md"
        page.write_text("source: sources/gone.md\n", encoding="utf-8")
        ledger = fresh_kb / "decisions" / "open-questions.md"
        expected_bullet = (
            "- stale_source: pages/a.md references removed source sources/gone.md"
        )
        ledger.write_text(
            _TEMPLATES["decisions/open-questions.md"]
            + f"\n~~~markdown\n{expected_bullet}\n~~~\n",
            encoding="utf-8",
        )

        def stale_errors():
            return [
                error
                for error in validate.validate(fresh_kb)
                if "pages/a.md" in error and "sources/gone.md" in error
            ]

        assert stale_errors()
        assert merge_candidates.record_stale_page_refs(fresh_kb) == [expected_bullet]
        assert stale_errors() == []
        first = ledger.read_bytes()
        assert merge_candidates.record_stale_page_refs(fresh_kb) == []
        assert ledger.read_bytes() == first
        structure = scan_markdown_structure(ledger.read_text(encoding="utf-8"))
        outside = [structure.lines[index] for index in structure.outside_indexes]
        assert outside.count(expected_bullet) == 1


class TestLegacyReviewLedgerRecovery:
    def _run_cli(self, root: Path, env: dict[str, str] | None = None):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "validate.py"), str(root)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def test_header_only_reports_four_errors_and_one_stable_hint(self, fresh_kb):
        ledger = fresh_kb / "decisions" / "open-questions.md"
        ledger.write_text("# Open Questions\n", encoding="utf-8")
        before = ledger.read_bytes()
        first_errors = validate.validate(fresh_kb)
        second_errors = validate.validate(fresh_kb)
        first_cli = self._run_cli(fresh_kb)
        second_cli = self._run_cli(fresh_kb)

        assert first_errors == second_errors
        assert len([e for e in first_errors if "exact review heading" in e]) == 4
        assert first_cli.returncode == second_cli.returncode == 1
        assert first_cli.stdout == second_cli.stdout
        assert first_cli.stdout.count("hint:") == 1
        assert "factlog init does not modify an existing" in first_cli.stdout
        assert ledger.read_bytes() == before

    def test_partial_names_only_missing_headings_in_canonical_order(self, fresh_kb):
        ledger = fresh_kb / "decisions" / "open-questions.md"
        present = validate.REVIEW_HEADINGS[:2]
        ledger.write_text("# Open Questions\n\n" + "\n\n".join(present) + "\n", encoding="utf-8")
        errors = [e for e in validate.validate(fresh_kb) if "exact review heading" in e]
        assert len(errors) == 2
        assert repr(validate.REVIEW_HEADINGS[2]) in errors[0]
        assert repr(validate.REVIEW_HEADINGS[3]) in errors[1]
        assert all(repr(heading) not in "\n".join(errors) for heading in present)

    def test_renamed_heading_and_custom_content_are_read_only(self, fresh_kb):
        ledger = fresh_kb / "decisions" / "open-questions.md"
        text = _TEMPLATES["decisions/open-questions.md"].replace(
            "## 출처 부족", "## 근거 없는 항목"
        ) + "\n사용자 메모\n"
        ledger.write_text(text, encoding="utf-8")
        before = ledger.read_bytes()
        completed = self._run_cli(fresh_kb)
        assert completed.returncode == 1
        assert repr("## 출처 부족") in completed.stdout
        assert "rename it back instead of adding a duplicate" in completed.stdout
        assert ledger.read_bytes() == before

    def test_crlf_headings_pass_but_whitespace_variants_fail(self, fresh_kb):
        ledger = fresh_kb / "decisions" / "open-questions.md"
        ledger.write_bytes(
            _TEMPLATES["decisions/open-questions.md"].replace("\n", "\r\n").encode()
        )
        assert validate.validate(fresh_kb) == []

        text = _TEMPLATES["decisions/open-questions.md"].replace(
            "## 모호한 관계명", " ## 모호한 관계명 "
        )
        ledger.write_text(text, encoding="utf-8")
        errors = validate.validate(fresh_kb)
        assert any(repr("## 모호한 관계명") in error for error in errors)

    @pytest.mark.parametrize(
        "decoy",
        [
            "본문의 출처 부족 문구",
            "- ## 출처 부족",
            "```markdown\n## 출처 부족\n```",
            "````markdown\n```\n## 출처 부족\n````",
            "~~~~markdown\n~~~\n## 출처 부족\n~~~~",
            "```markdown\n```still code\n## 출처 부족\n```",
            "```markdown\n```~\n## 출처 부족\n```",
        ],
    )
    def test_prose_bullet_and_fence_do_not_count_as_anchor(self, fresh_kb, decoy):
        ledger = fresh_kb / "decisions" / "open-questions.md"
        text = _TEMPLATES["decisions/open-questions.md"].replace("## 출처 부족", "")
        ledger.write_text(text + "\n" + decoy + "\n", encoding="utf-8")
        assert any(
            repr("## 출처 부족") in error for error in validate.validate(fresh_kb)
        )

    def test_existing_partial_file_is_untouched_by_init(self, fresh_kb, capsys):
        ledger = fresh_kb / "decisions" / "open-questions.md"
        ledger.write_text("# Open Questions\n", encoding="utf-8")
        before = ledger.read_bytes()
        assert _init_kb(fresh_kb) is False
        assert "already exists, nothing to do" in capsys.readouterr().out
        assert ledger.read_bytes() == before

    def test_missing_file_hint_uses_nonactivating_init_recovery(self, fresh_kb, tmp_path):
        ledger = fresh_kb / "decisions" / "open-questions.md"
        ledger.unlink()
        completed = self._run_cli(fresh_kb)
        assert completed.returncode == 1
        assert "missing decisions/open-questions.md" in completed.stdout
        assert "exact review heading" not in completed.stdout
        assert completed.stdout.count("hint:") == 1
        assert "factlog init --target <KB_PATH> --no-activate" in completed.stdout
        assert "replace <KB_PATH>" in completed.stdout

        xdg = tmp_path / "xdg"
        config = xdg / "factlog" / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"root": "/already-active"}\n', encoding="utf-8")
        config_before = config.read_bytes()
        env = dict(os.environ, XDG_CONFIG_HOME=str(xdg), PYTHONPATH=str(REPO_ROOT))
        recovered = subprocess.run(
            [
                sys.executable,
                "-m",
                "factlog",
                "init",
                "--target",
                str(fresh_kb),
                "--no-activate",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        assert recovered.returncode == 0, recovered.stdout + recovered.stderr
        assert ledger.read_text(encoding="utf-8") == _TEMPLATES[
            "decisions/open-questions.md"
        ]
        assert config.read_bytes() == config_before

    @pytest.mark.parametrize(
        "obstruction_kind", ["directory", "directory_symlink", "broken_symlink"]
    )
    def test_non_file_ledger_gets_obstruction_hint(
        self, fresh_kb, obstruction_kind
    ):
        ledger = fresh_kb / "decisions" / "open-questions.md"
        ledger.unlink()
        if obstruction_kind == "directory":
            ledger.mkdir()
        elif obstruction_kind == "directory_symlink":
            target = fresh_kb / "ledger-directory"
            target.mkdir()
            ledger.symlink_to(target, target_is_directory=True)
        else:
            ledger.symlink_to(fresh_kb / "missing-ledger-target")

        completed = self._run_cli(fresh_kb)
        assert completed.returncode == 1
        assert "must be a regular file" in completed.stdout
        assert completed.stdout.count("hint:") == 1
        assert "Move or repair that path first" in completed.stdout
        assert "factlog init --target" not in completed.stdout
        assert "factlog init cannot replace it" in completed.stdout

    def test_merge_delegate_keeps_failure_summary_and_rc(self, fresh_kb, capsys):
        import merge_candidates

        (fresh_kb / "decisions" / "open-questions.md").write_text(
            "# Open Questions\n", encoding="utf-8"
        )
        assert merge_candidates.validate_outputs(fresh_kb) == 1
        out = capsys.readouterr().out
        assert "Fact sync validation failed:" in out
        assert out.count("hint:") == 1
