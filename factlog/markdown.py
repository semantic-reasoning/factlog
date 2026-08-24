# SPDX-License-Identifier: Apache-2.0
"""Small, import-safe Markdown structure helpers used by factlog tools."""

from __future__ import annotations

import re
from typing import NamedTuple


_LINE_ENDING_RE = re.compile(r"\r\n|\r|\n")
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")


class MarkdownStructure(NamedTuple):
    """Markdown lines, raw offsets, outside indexes, and an unclosed fence."""

    lines: tuple[str, ...]
    line_start_offsets: tuple[int, ...]
    outside_indexes: tuple[int, ...]
    unclosed_fence_start: int | None


def _markdown_lines(text: str) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Split CommonMark line endings without treating Unicode separators as LF.

    The trailing empty field produced by a final line ending is dropped to match
    the historical ``str.splitlines()`` shape used by the writer and validator.
    """
    if not text:
        return (), ()
    lines: list[str] = []
    starts: list[int] = []
    start = 0
    for ending in _LINE_ENDING_RE.finditer(text):
        starts.append(start)
        lines.append(text[start : ending.start()])
        start = ending.end()
    starts.append(start)
    lines.append(text[start:])
    if lines[-1] == "" and start == len(text):
        lines.pop()
        starts.pop()
    return tuple(lines), tuple(starts)


def scan_markdown_structure(text: str) -> MarkdownStructure:
    """Locate lines outside CommonMark-style backtick and tilde fences.

    Only LF, CRLF, and lone CR delimit lines. Fence markers may be indented by
    at most three spaces. A backtick opener's info string may not itself contain
    a backtick; closers must use the same marker and be at least as long.
    """
    lines, line_start_offsets = _markdown_lines(text)
    outside: list[int] = []
    fence: tuple[str, int, int] | None = None

    for index, line in enumerate(lines):
        if fence is not None:
            closing = _FENCE_CLOSE_RE.fullmatch(line)
            if (
                closing
                and closing.group(1)[0] == fence[0]
                and len(closing.group(1)) >= fence[1]
            ):
                fence = None
            continue

        opening = _FENCE_OPEN_RE.match(line)
        if opening:
            marker, info = opening.groups()
            if marker[0] == "~" or "`" not in info:
                fence = (marker[0], len(marker), index)
                continue
        outside.append(index)

    return MarkdownStructure(
        lines,
        line_start_offsets,
        tuple(outside),
        fence[2] if fence is not None else None,
    )
