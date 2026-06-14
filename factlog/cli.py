"""factlog command-line helper.

The skill itself is installed as a Claude Code **plugin** (see README), so this
CLI does not install the skill. It provides environment and knowledge-base
helpers for the deterministic engine:

- `doctor`  — verify Python and pyrewire meet factlog's requirements.
- `init`    — scaffold an empty knowledge base layout (stub; see plan).
"""

from __future__ import annotations

import argparse
import sys

from factlog import __version__

MIN_PYTHON = (3, 10)
MIN_PYREWIRE = (1, 0, 1)


def _version_tuple(value: str) -> tuple[int, ...]:
    import re

    return tuple(int(part) for part in re.findall(r"\d+", value)[:3])


def cmd_doctor(_args: argparse.Namespace) -> int:
    ok = True

    if sys.version_info[:2] >= MIN_PYTHON:
        print(f"OK  Python {sys.version_info.major}.{sys.version_info.minor}")
    else:
        ok = False
        print(f"FAIL Python {sys.version_info.major}.{sys.version_info.minor} < 3.10", file=sys.stderr)

    try:
        import pyrewire  # type: ignore

        current = _version_tuple(str(getattr(pyrewire, "__version__", "0")))
        if current >= MIN_PYREWIRE:
            print(f"OK  pyrewire {getattr(pyrewire, '__version__', '?')}")
        else:
            ok = False
            print(
                f"FAIL pyrewire {getattr(pyrewire, '__version__', '?')} < 1.0.1 "
                "(pip install -r requirements.txt)",
                file=sys.stderr,
            )
    except ImportError:
        ok = False
        print("FAIL pyrewire not installed (pip install -r requirements.txt)", file=sys.stderr)

    return 0 if ok else 1


_TEMPLATES: dict[str, str] = {
    "policy/prompts/text_to_fact.md": """\
# Text-to-Fact Extraction Prompt

You are a fact extraction assistant. Given the source text below, extract
atomic, verifiable facts in the form (subject, relation, object).

## Source text

{source_text}

## Output format

Return one fact per line as CSV with columns:
subject,relation,object,source,status,confidence,note
""",
    "policy/prompts/text_to_datalog.md": """\
# Text-to-Datalog Query Prompt

Given the following schema context and natural-language question, produce a
valid Datalog query that answers the question.

## Schema context

{{SCHEMA_CONTEXT}}

## Question

{{QUESTION}}

## Output

Return only the Datalog query, no explanation.
""",
    "policy/prompts/self_correct.md": """\
# Self-Correction Prompt

The Datalog query below produced errors. Fix the query so it is valid.

## Schema context

{{SCHEMA_CONTEXT}}

## Logic report

{{LOGIC_REPORT}}

## Draft query

{{DRAFT_QUERY}}

## Output

Return only the corrected Datalog query, no explanation.
""",
    "policy/prompts/natural_language_to_policy.md": """\
# Natural Language to Policy Prompt

Convert the following natural-language policy description into Datalog rules.

## Policy text

{{POLICY_TEXT}}

## Output

Return only valid Datalog rules, one per line, no explanation.
""",
    "policy/questions.md": """\
# Research questions

- [q1] What are the key facts to extract from this knowledge base?
""",
    "policy/logic-policy.md": """\
# Logic policy

This file describes the Datalog rules used to reason over the knowledge base.

## Rules

Add your policy rules here. Each rule should be documented with a brief
explanation of its purpose.
""",
}


def cmd_init(args: argparse.Namespace) -> int:
    from pathlib import Path

    target = Path(args.target).expanduser().resolve()
    dirs = ["sources", "pages", "facts", "decisions", "policy", "policy/prompts", "runs"]
    created_dirs: list[str] = []
    for dirname in dirs:
        d = target / dirname
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created_dirs.append(dirname + "/")

    created_files: list[str] = []
    for rel_path, content in _TEMPLATES.items():
        dest = target / rel_path
        if not dest.exists():
            dest.write_text(content, encoding="utf-8")
            created_files.append(rel_path)

    if created_dirs or created_files:
        print(f"factlog init: created {target}")
        for name in created_dirs:
            print(f"  {name}")
        for name in created_files:
            print(f"  {name}")
    else:
        print(f"factlog init: {target} already exists, nothing to do")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factlog", description="factlog environment and KB helpers")
    parser.add_argument("--version", action="version", version=f"factlog {__version__}")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", help="verify Python and pyrewire requirements")
    doctor.set_defaults(func=cmd_doctor)

    init = sub.add_parser("init", help="scaffold an empty knowledge base layout")
    init.add_argument("--target", default="~/wiki", help="knowledge base root to create")
    init.set_defaults(func=cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
