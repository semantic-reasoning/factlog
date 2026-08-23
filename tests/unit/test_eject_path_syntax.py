# SPDX-License-Identifier: Apache-2.0
"""Platform-path pins for ``factlog eject`` source selection (#339)."""
from __future__ import annotations

import os
from argparse import Namespace

import pytest

from factlog import cli


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (r"sub\report.html", "sub/report.html"),
        (r"sources\sub\report.html", "sources/sub/report.html"),
        (r"runs\sources\sub\report.html.md", "runs/sources/sub/report.html.md"),
        (r"C:\kb\sources\sub\report.html", "C:/kb/sources/sub/report.html"),
        (r"\\server\share\report.html", "//server/share/report.html"),
        (r"sub\mixed/report.html", "sub/mixed/report.html"),
    ],
)
def test_windows_separator_is_spelled_like_a_stored_ref(raw, expected):
    assert cli._as_eject_ref_path(raw, "\\") == expected


@pytest.mark.parametrize(
    "raw",
    [r"sub\report.html", r"sources\sub\report.html", r"C:\kb\report.html"],
)
def test_posix_preserves_backslash_filename_characters(raw):
    assert cli._as_eject_ref_path(raw, "/") == raw


def _source_selection(tmp_path, monkeypatch, source):
    nested = tmp_path / "runs" / "sources" / "sub" / "report.html.md"
    flat = tmp_path / "runs" / "sources" / "report.html.md"
    nested.parent.mkdir(parents=True)
    flat.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text(
        "<!-- ingested-by-factlog | source: sub/report.html | converter: pandoc -->\n",
        encoding="utf-8",
    )
    flat.write_text(
        "<!-- ingested-by-factlog | source: report.html | converter: pandoc -->\n",
        encoding="utf-8",
    )
    original = tmp_path / "sources" / "sub" / "report.html"
    root_original = tmp_path / "sources" / "report.html"
    original.parent.mkdir(parents=True)
    original.write_text("nested\n", encoding="utf-8")
    root_original.write_text("root\n", encoding="utf-8")

    disk_refs = {
        "runs/sources/sub/report.html.md": nested,
        "runs/sources/report.html.md": flat,
        "sources/sub/report.html": original,
        "sources/report.html": root_original,
    }
    rows = [
        {"source": "runs/sources/sub/report.html.md"},
        {"source": "runs/sources/report.html.md"},
        {"source": "sources/sub/report.html"},
        {"source": "sources/report.html"},
    ]
    monkeypatch.setattr(os, "sep", "\\")
    result = cli._select_eject_sources(
        Namespace(orphans=False, sources=[source], purge=False, delete_original=False),
        rows,
        disk_refs,
        set(disk_refs),
        tmp_path,
        lambda value: value,
    )
    assert isinstance(result, cli._EjectSelection)
    return result, rows


def test_windows_sources_relative_path_selects_only_nested_conversion(tmp_path, monkeypatch):
    result, rows = _source_selection(tmp_path, monkeypatch, r"sub\report.html")

    assert result.conv_to_delete == ["runs/sources/sub/report.html.md"]
    assert [result.match_row(row) for row in rows] == [True, False, False, False]


@pytest.mark.parametrize(
    ("source", "conversions", "matched_rows"),
    [
        (
            r"sources\sub\report.html",
            ["runs/sources/sub/report.html.md"],
            [True, False, True, False],
        ),
        (
            r"runs\sources\sub\report.html.md",
            ["runs/sources/sub/report.html.md"],
            [True, False, False, False],
        ),
        (
            "report.html",
            ["runs/sources/report.html.md", "runs/sources/sub/report.html.md"],
            [True, True, True, True],
        ),
    ],
)
def test_windows_prefixes_and_bare_filename_contract(
    tmp_path, monkeypatch, source, conversions, matched_rows
):
    result, rows = _source_selection(tmp_path, monkeypatch, source)

    assert result.conv_to_delete == conversions
    assert [result.match_row(row) for row in rows] == matched_rows
