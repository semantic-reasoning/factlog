#!/usr/bin/env bash
# tests/test_page_docspan.sh — page-only "spans N distinct documents" salience cue
#
# Pins (real KB, factlog init + merge):
#   - an entity whose facts come from TWO distinct source documents gets ONE
#     plain-text cue line prepended into its page's SOURCES block ("서로 다른 문서 2개")
#   - a single-source variant of the same entity gets NO cue line
#
# The cue is purely observational (possible homonym merge); identity is unchanged.
# Deterministic; no pyrewire.  Usage: bash tests/test_page_docspan.sh

set -euo pipefail

export XDG_CONFIG_HOME="$(mktemp -d)/factlog-test-cfg"  # isolate active-KB config from the dev machine

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$PLUGIN_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python3}"
MERGE="$PLUGIN_ROOT/tools/merge_candidates.py"

pass=0
fail=0
ok() { echo "PASS: $*"; pass=$((pass + 1)); }
bad() { echo "FAIL: $*" >&2; fail=$((fail + 1)); }

SLUG="$("$PYTHON" -c "import sys; sys.path.insert(0,'$PLUGIN_ROOT/tools'); from common import slugify; print(slugify('갑봇'))")"

# ---------------------------------------------------------------------------
# Case 1: two sources, one fact each, same subject -> cue present
# ---------------------------------------------------------------------------
KB="$(mktemp -d)/wiki"
"$PYTHON" -m factlog init --target "$KB" >/dev/null
printf 'doc a content\n' > "$KB/sources/a.md"
printf 'doc b content\n' > "$KB/sources/b.md"
cat > "$KB/runs/facts.json" <<'JSON'
[
  {"subject":"갑봇","relation":"통합_대상","object":"값가","source":"sources/a.md","status":"accepted","confidence":"0.9","note":""},
  {"subject":"갑봇","relation":"통합_대상","object":"값나","source":"sources/b.md","status":"accepted","confidence":"0.9","note":""}
]
JSON
"$PYTHON" "$MERGE" --wiki "$KB" >/dev/null 2>&1

PAGE="$KB/pages/${SLUG}.md"
if [ -f "$PAGE" ] && grep -qF "서로 다른 문서 2개" "$PAGE"; then
    ok "two distinct documents -> docspan cue present on subject page"
else
    bad "two distinct documents -> docspan cue missing"
fi
# The raw source list is still present (cue is additive, not a replacement).
grep -qF -e "- sources/a.md" "$PAGE" && grep -qF -e "- sources/b.md" "$PAGE" \
    && ok "both sources still listed alongside the cue" \
    || bad "source list altered by the cue"

# ---------------------------------------------------------------------------
# Case 2: single source, one fact -> NO cue
# ---------------------------------------------------------------------------
KB2="$(mktemp -d)/wiki"
"$PYTHON" -m factlog init --target "$KB2" >/dev/null
printf 'doc a content\n' > "$KB2/sources/a.md"
cat > "$KB2/runs/facts.json" <<'JSON'
[
  {"subject":"갑봇","relation":"통합_대상","object":"값가","source":"sources/a.md","status":"accepted","confidence":"0.9","note":""}
]
JSON
"$PYTHON" "$MERGE" --wiki "$KB2" >/dev/null 2>&1

PAGE2="$KB2/pages/${SLUG}.md"
if [ -f "$PAGE2" ] && ! grep -qF "서로 다른 문서" "$PAGE2"; then
    ok "single document -> no docspan cue"
else
    bad "single document -> unexpected docspan cue"
fi

echo ""
echo "========================================"
echo "test_page_docspan: $pass passed, $fail failed"
echo "========================================"
[ "$fail" -eq 0 ]
