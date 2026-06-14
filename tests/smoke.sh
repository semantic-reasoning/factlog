#!/usr/bin/env bash
# tests/smoke.sh — clean-environment plugin smoke harness (AC5)
#
# Validates the 4 deterministic steps of the factlog pipeline in a fresh
# virtualenv with a freshly-initialised KB seeded from examples/sample-kb.
#
# Design notes:
#   - FACTLOG_ROOT is exported so tools/ scripts resolve the KB without
#     relying on cwd.  This matches the fix in u1 where ensure_wiki_root
#     no longer requires a tools/ directory alongside the KB.
#   - Only deterministic outputs are asserted here:
#       facts/accepted.dl       — from compile_facts.py
#       facts/logic_report.txt  — from run_logic_check.py
#     facts/query.dl and decisions/correction_trace.md are produced by the
#     LLM (Claude in-session) steps and are NOT checked here; the smoke
#     exercises only the engine scripts callable without a live Claude session.
#   - Local marketplace path is used for plugin references; no remote
#     operations.  See .claude-plugin/marketplace.json for the install path.
#
# Usage:
#   bash tests/smoke.sh
#
# Returns 0 if all checks pass, 1 on first failure.
#
# Acceptance checks (from unit u12):
#   bash -n tests/smoke.sh                        (syntax check)
#   CD /tmp; factlog init + run_logic_check.py    (FACTLOG_ROOT export check)
#   grep counts remote-push lines — must be zero  (no remote ops)

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SAMPLE_KB="$PLUGIN_ROOT/examples/sample-kb"

SMOKE_VENV="/tmp/factlog-smoke-venv"
SMOKE_KB="/tmp/factlog-smoke-kb"
PYTHON="$SMOKE_VENV/bin/python"

pass=0
fail=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ok() {
  echo "PASS: $*"
  pass=$((pass + 1))
}

fail_msg() {
  echo "FAIL: $*" >&2
  fail=$((fail + 1))
}

assert_nonempty() {
  local path="$1"
  local label="${2:-$1}"
  if [ -s "$path" ]; then
    ok "$label exists and is non-empty"
  else
    fail_msg "$label missing or empty (expected at $path)"
  fi
}

assert_exit0() {
  local label="$1"
  shift
  if "$@"; then
    ok "$label exit 0"
  else
    fail_msg "$label exited non-zero"
  fi
}

# ---------------------------------------------------------------------------
# Step 1: fresh virtualenv + pip install
# ---------------------------------------------------------------------------
echo "=== Step 1: create venv + install requirements ==="
rm -rf "$SMOKE_VENV"
python3 -m venv "$SMOKE_VENV"
"$SMOKE_VENV/bin/pip" install --quiet -r "$PLUGIN_ROOT/requirements.txt"
ok "pip install -r requirements.txt"

# Install factlog package itself so 'python -m factlog' works from anywhere.
"$SMOKE_VENV/bin/pip" install --quiet -e "$PLUGIN_ROOT"
ok "pip install -e factlog"

# ---------------------------------------------------------------------------
# Step 2: factlog doctor
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 2: factlog doctor ==="
assert_exit0 "factlog doctor" "$PYTHON" -m factlog doctor

# ---------------------------------------------------------------------------
# Step 3: init fresh KB, seed from sample-kb
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 3: init KB + seed from sample-kb ==="
rm -rf "$SMOKE_KB"
"$PYTHON" -m factlog init --target "$SMOKE_KB"
ok "factlog init --target $SMOKE_KB"

# Seed deterministic content from sample-kb (candidates, sources, pages,
# policy rules, decisions open-questions).  This gives compile_facts.py
# real input and validate.py all required artefacts.
cp "$SAMPLE_KB/facts/candidates.csv" "$SMOKE_KB/facts/"
cp -r "$SAMPLE_KB/sources/." "$SMOKE_KB/sources/"
cp -r "$SAMPLE_KB/pages/." "$SMOKE_KB/pages/"
cp "$SAMPLE_KB/policy/logic-policy.dl" "$SMOKE_KB/policy/"
cp "$SAMPLE_KB/policy/logic-policy.md" "$SMOKE_KB/policy/"
cp "$SAMPLE_KB/decisions/open-questions.md" "$SMOKE_KB/decisions/"
ok "seeded KB from sample-kb"

# ---------------------------------------------------------------------------
# Step 4: compile_facts.py  →  facts/accepted.dl
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 4: compile_facts.py ==="
export FACTLOG_ROOT="$SMOKE_KB"
assert_exit0 "compile_facts.py" \
  "$PYTHON" "$PLUGIN_ROOT/tools/compile_facts.py"
assert_nonempty "$SMOKE_KB/facts/accepted.dl" "facts/accepted.dl"

# ---------------------------------------------------------------------------
# Step 5: run_logic_check.py  →  facts/logic_report.txt
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 5: run_logic_check.py ==="
assert_exit0 "run_logic_check.py" \
  "$PYTHON" "$PLUGIN_ROOT/tools/run_logic_check.py"
assert_nonempty "$SMOKE_KB/facts/logic_report.txt" "facts/logic_report.txt"

# ---------------------------------------------------------------------------
# Step 6: validate.py
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 6: validate.py ==="
assert_exit0 "validate.py" \
  "$PYTHON" "$PLUGIN_ROOT/tools/validate.py" "$SMOKE_KB"

# ---------------------------------------------------------------------------
# Note on LLM-step outputs
# ---------------------------------------------------------------------------
# facts/query.dl and decisions/correction_trace.md are produced by the Claude
# in-session LLM steps (/factlog check and /factlog repair respectively).
# They are not produced by any deterministic script and therefore cannot be
# asserted in this harness without a live Claude session.  Full AC3 coverage
# requires a live /factlog invocation; AC5 covers the deterministic engine.

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Smoke results: $pass passed, $fail failed"
echo "========================================"
if [ "$fail" -gt 0 ]; then
  exit 1
fi
exit 0
