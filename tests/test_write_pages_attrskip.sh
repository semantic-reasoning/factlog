#!/usr/bin/env bash
# tests/test_write_pages_attrskip.sh — write_pages skips concept pages for
# attribute-relation objects, aligning with common.entity_set (#230)
#
# Pins:
#   - with attribute-relations.md declaring a relation, a literal OBJECT of
#     that relation gets NO pages/<obj>.md
#   - the SUBJECT of an attribute relation still gets a page
#   - the same string appearing as a non-attribute relation object DOES get a page
#   - the same string appearing as a subject DOES get a page
#   - no attribute-relations.md (absent file) -> behaviour unchanged (normal
#     object still gets a page), confirming no-op / backward compat
#
# Deterministic; no pyrewire.  Usage: bash tests/test_write_pages_attrskip.sh

set -euo pipefail

export XDG_CONFIG_HOME="$(mktemp -d)/factlog-test-cfg"

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$PLUGIN_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python3}"
MERGE="$PLUGIN_ROOT/tools/merge_candidates.py"

pass=0
fail=0
ok() { echo "PASS: $*"; pass=$((pass + 1)); }
bad() { echo "FAIL: $*" >&2; fail=$((fail + 1)); }

# ---------------------------------------------------------------------------
# Setup KB
# ---------------------------------------------------------------------------
KB="$(mktemp -d)/wiki"
"$PYTHON" -m factlog init --target "$KB" >/dev/null
printf 'source content\n' > "$KB/sources/a.md"

# Facts:
#   갑봇  --[정식_운영]--> 2030.1        (attribute relation -> literal object)
#   갑봇  --[통합_대상]--> 을서비스      (normal relation -> entity object)
#   을서비스 --[별칭]-->   갑봇           (을서비스 also as subject; 갑봇 as non-attr object)
cat > "$KB/runs/facts.json" <<'JSON'
[
  {"subject":"갑봇","relation":"정식_운영","object":"2030.1","source":"sources/a.md","status":"accepted","confidence":"0.9","note":""},
  {"subject":"갑봇","relation":"통합_대상","object":"을서비스","source":"sources/a.md","status":"accepted","confidence":"0.9","note":""},
  {"subject":"을서비스","relation":"별칭","object":"갑봇","source":"sources/a.md","status":"accepted","confidence":"0.9","note":""}
]
JSON

# ---------------------------------------------------------------------------
# Case 1: NO attribute-relations.md — backward compat: literal object DOES get
# a page (old behaviour unchanged when the file is absent).
# ---------------------------------------------------------------------------
rm -f "$KB/policy/attribute-relations.md"
"$PYTHON" "$MERGE" --wiki "$KB" >/dev/null 2>&1

SLUG_2030="$("$PYTHON" -c "import sys; sys.path.insert(0,'$PLUGIN_ROOT/tools'); import os; os.environ.setdefault('FACTLOG_ROOT','$KB'); import sys; sys.argv=['x']; from common import slugify; print(slugify('2030.1'))")"
if [ -f "$KB/pages/${SLUG_2030}.md" ]; then
    ok "no attribute-relations.md -> literal object still gets a page (backward compat)"
else
    bad "no attribute-relations.md -> literal object page missing (unexpected regression)"
fi

# ---------------------------------------------------------------------------
# Case 2: WITH attribute-relations.md declaring 정식_운영
# ---------------------------------------------------------------------------
printf -- '- `정식_운영`\n' > "$KB/policy/attribute-relations.md"
"$PYTHON" "$MERGE" --wiki "$KB" >/dev/null 2>&1

SLUG_GAPBOT="$("$PYTHON" -c "import sys; sys.path.insert(0,'$PLUGIN_ROOT/tools'); import os; os.environ.setdefault('FACTLOG_ROOT','$KB'); import sys; sys.argv=['x']; from common import slugify; print(slugify('갑봇'))")"
SLUG_EUL="$("$PYTHON" -c "import sys; sys.path.insert(0,'$PLUGIN_ROOT/tools'); import os; os.environ.setdefault('FACTLOG_ROOT','$KB'); import sys; sys.argv=['x']; from common import slugify; print(slugify('을서비스'))")"

# Literal object of attribute relation -> NO page
if [ ! -f "$KB/pages/${SLUG_2030}.md" ]; then
    ok "attribute relation object (literal) has no concept page"
else
    bad "attribute relation literal object got a page (should be skipped)"
fi

# Subject of attribute relation -> page exists
if [ -f "$KB/pages/${SLUG_GAPBOT}.md" ]; then
    ok "subject of attribute relation still gets a concept page"
else
    bad "subject of attribute relation missing its concept page"
fi

# Normal relation object -> page exists
if [ -f "$KB/pages/${SLUG_EUL}.md" ]; then
    ok "non-attribute relation object still gets a concept page"
else
    bad "non-attribute relation object missing its concept page"
fi

# 갑봇 also appears as a non-attribute relation OBJECT (을서비스 --별칭--> 갑봇)
# so it must still get a page (covered above via SLUG_GAPBOT, but confirm explicitly)
if [ -f "$KB/pages/${SLUG_GAPBOT}.md" ]; then
    ok "string appearing as non-attribute relation object gets a page"
else
    bad "string appearing as non-attribute relation object missing page"
fi

echo ""
echo "========================================"
echo "test_write_pages_attrskip: $pass passed, $fail failed"
echo "========================================"
[ "$fail" -eq 0 ]
