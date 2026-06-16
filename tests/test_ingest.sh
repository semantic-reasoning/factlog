#!/usr/bin/env bash
# tests/test_ingest.sh — `factlog ingest` binary→text conversion (#4)
#
# Covers:
#   - a real .docx (minimal OOXML fixture) → sources/<name>.md with a
#     provenance header and the document text (when a converter is available),
#   - an unsupported format (.hwp) → non-zero exit + actionable hint,
#   - the overwrite guard (skip without --force, replace with --force).
#
# Runs factlog from the working tree via PYTHONPATH (no install / no pyrewire).
#
# Usage: bash tests/test_ingest.sh
#   Returns 0 if all checks pass, 1 if any fail.

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$PLUGIN_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python3}"
FACTLOG=("$PYTHON" -m factlog)

pass=0
fail=0
ok() { echo "PASS: $*"; pass=$((pass + 1)); }
bad() { echo "FAIL: $*" >&2; fail=$((fail + 1)); }

KB="$(mktemp -d)/wiki"
"${FACTLOG[@]}" init --target "$KB" >/dev/null
SRC_DIR="$(mktemp -d)"

# ---------------------------------------------------------------------------
# Build a minimal, valid .docx (OOXML) fixture with python's zipfile.
# ---------------------------------------------------------------------------
DOCX="$SRC_DIR/report.docx"
"$PYTHON" - "$DOCX" <<'PY'
import sys, zipfile
path = sys.argv[1]
ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
      '</Types>')
rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
       '<w:body><w:p><w:r><w:t>Acme uses Python for the ingest test.</w:t></w:r></w:p></w:body>'
       '</w:document>')
with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", ct)
    z.writestr("_rels/.rels", rels)
    z.writestr("word/document.xml", doc)
PY

# A converter for .docx must exist for the conversion assertions to be meaningful.
have_docx_converter=no
command -v pandoc >/dev/null 2>&1 && have_docx_converter=yes
command -v textutil >/dev/null 2>&1 && have_docx_converter=yes

# ---------------------------------------------------------------------------
# 1. ingest the .docx
# ---------------------------------------------------------------------------
if [ "$have_docx_converter" = yes ]; then
  if "${FACTLOG[@]}" ingest "$DOCX" --target "$KB" >/dev/null 2>&1; then
    ok "ingest .docx exits 0"
  else
    bad "ingest .docx should exit 0 (a docx converter is present)"
  fi
  OUT_MD="$KB/sources/report.md"
  OUT_TXT="$KB/sources/report.txt"
  if [ -f "$OUT_MD" ] || [ -f "$OUT_TXT" ]; then
    OUT="$([ -f "$OUT_MD" ] && echo "$OUT_MD" || echo "$OUT_TXT")"
    ok "converted source written to sources/ ($(basename "$OUT"))"
    grep -qF "ingested-by-factlog" "$OUT" && ok "provenance header present" || bad "missing provenance header"
    grep -qF "source: report.docx" "$OUT" && ok "provenance records original filename" || bad "provenance missing original filename"
    grep -qF "Acme uses Python" "$OUT" && ok "document text extracted" || bad "document text not extracted"
  else
    bad "no converted source file found in sources/"
  fi
else
  echo "SKIP: no docx converter (pandoc/textutil) available — skipping conversion assertions"
fi

# ---------------------------------------------------------------------------
# 2. unsupported format (.hwp) → non-zero + hint
# ---------------------------------------------------------------------------
touch "$SRC_DIR/notes.hwp"
err="$(mktemp)"
if "${FACTLOG[@]}" ingest "$SRC_DIR/notes.hwp" --target "$KB" >/dev/null 2>"$err"; then
  bad "ingest .hwp should exit non-zero"
else
  ok "ingest unsupported .hwp exits non-zero"
fi
grep -qiE "hwp|no common converter|no converter" "$err" && ok ".hwp prints an actionable hint" || bad ".hwp hint missing"

# ---------------------------------------------------------------------------
# 3. overwrite guard
# ---------------------------------------------------------------------------
if [ "$have_docx_converter" = yes ]; then
  if "${FACTLOG[@]}" ingest "$DOCX" --target "$KB" >/dev/null 2>&1; then
    bad "second ingest without --force should exit non-zero (file exists)"
  else
    ok "second ingest without --force is refused (exit non-zero)"
  fi
  if "${FACTLOG[@]}" ingest "$DOCX" --target "$KB" --force >/dev/null 2>&1; then
    ok "ingest --force overwrites existing converted file"
  else
    bad "ingest --force should succeed"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "test_ingest: $pass passed, $fail failed"
echo "========================================"
[ "$fail" -eq 0 ]
