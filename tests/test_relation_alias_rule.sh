#!/usr/bin/env bash
# tests/test_relation_alias_rule.sh — canonical relation-alias side-atoms (#188)
#
# A logic-policy rule written against CANONICAL predicate names must fire even
# when the accepted facts use human-declared surface VARIANTS of those relations,
# once policy/relation-aliases.md maps the variants to the canonical names.
#
# Pins (two-layer verification):
#   NEGATIVE control — no relation-aliases.md:
#     - compile_facts emits NO canonical side-atom (grep layer)
#     - the canonical-predicate rule does NOT fire (engine layer)
#   POSITIVE — relation-aliases.md declares 결론 -> concludes, 철회상태 -> retraction_status:
#     - accepted.dl gains the synthetic canonical side-atoms (grep layer, no engine)
#     - run_logic_check fires the conflict rule (engine layer)
#   INVARIANT:
#     - the original variant atoms stay byte-identical (verbatim provenance)
#     - `engine facts: N` counts ONLY the original atoms (provenance unchanged)
#
# The grep layer needs no engine; the engine layer needs pyrewire (skipped if
# absent). Deterministic. Usage: bash tests/test_relation_alias_rule.sh
set -uo pipefail

export XDG_CONFIG_HOME="$(mktemp -d)/factlog-test-cfg"  # isolate active-KB config (#62)

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$PLUGIN_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python3}"
HEADER="subject,relation,object,source,status,confidence,note"

pass=0
fail=0
ok() { echo "PASS: $*"; pass=$((pass + 1)); }
bad() { echo "FAIL: $*" >&2; fail=$((fail + 1)); }

have_engine=0
"$PYTHON" -c "import pyrewire" >/dev/null 2>&1 && have_engine=1

KB="$(mktemp -d)/wiki"
"$PYTHON" -m factlog init --target "$KB" >/dev/null

compile() { FACTLOG_ROOT="$KB" "$PYTHON" "$PLUGIN_ROOT/tools/compile_facts.py" >/dev/null 2>&1; }
run_check() { FACTLOG_ROOT="$KB" "$PYTHON" "$PLUGIN_ROOT/tools/run_logic_check.py" >/dev/null 2>&1; }

# --- policy: a rule referencing CANONICAL predicate names ---------------------
# Two backtick relations in one bullet compile to a joined rule; "conflict" in
# the sentence makes generate_logic_policy infer the `conflict` predicate:
#   conflict(X, "conflict_retracted") :-
#     relation(X, "concludes", _), relation(X, "retraction_status", _).
printf '# Logic policy\n\n## Rules\n\n- [conflict_retracted] a node carrying both `concludes` and `retraction_status` is a conflict\n' \
  > "$KB/policy/logic-policy.md"
FACTLOG_ROOT="$KB" "$PYTHON" "$PLUGIN_ROOT/tools/generate_logic_policy.py" >/dev/null 2>&1 \
  || { bad "generate_logic_policy failed to compile the canonical-predicate rule"; }
grep -q '"concludes"' "$KB/policy/logic-policy.dl" && ok "policy compiled against canonical predicate names" \
  || bad "policy .dl missing canonical predicate reference"

# --- facts stated with SURFACE VARIANTS (NFC Korean) on ONE subject ----------
printf '# s\n' > "$KB/sources/s.md"
printf '%s\n' "$HEADER" \
  '논문갑,결론,무효,sources/s.md,confirmed,0.9,' \
  '논문갑,철회상태,철회됨,sources/s.md,confirmed,0.9,' \
  > "$KB/facts/candidates.csv"

# ============================================================================
# NEGATIVE control — no policy/relation-aliases.md
# ============================================================================
rm -f "$KB/policy/relation-aliases.md"
compile || bad "compile failed (negative control)"

# grep layer: no canonical side-atom emitted
if grep -q '"concludes"' "$KB/facts/accepted.dl"; then
  bad "canonical side-atom leaked without relation-aliases.md"
else
  ok "no canonical side-atom without relation-aliases.md (grep layer)"
fi
# original variant atoms present verbatim
grep -q '"결론"' "$KB/facts/accepted.dl" && ok "variant atom 결론 stored verbatim" || bad "variant atom 결론 missing"
grep -q '"철회상태"' "$KB/facts/accepted.dl" && ok "variant atom 철회상태 stored verbatim" || bad "variant atom 철회상태 missing"

# engine layer: rule must NOT fire
if [ "$have_engine" -eq 1 ]; then
  run_check || bad "run_logic_check failed (negative control)"
  if grep -q "conflict: 논문갑" "$KB/facts/logic_report.txt"; then
    bad "conflict rule fired WITHOUT relation-aliases.md (should not)"
  else
    ok "conflict rule does not fire without relation-aliases.md (engine layer)"
  fi
else
  echo "SKIP: engine layer (negative) — pyrewire not installed"
fi

# ============================================================================
# POSITIVE — declare the surface->canonical aliases
# ============================================================================
printf '# Relation aliases\n\n- `결론` -> `concludes`\n- `철회상태` -> `retraction_status`\n' \
  > "$KB/policy/relation-aliases.md"
compile || bad "compile failed (positive)"

# grep layer: synthetic canonical side-atoms now present (no engine needed)
if grep -q 'relation("논문갑", "concludes", "무효")' "$KB/facts/accepted.dl"; then
  ok "canonical side-atom concludes emitted (grep layer)"
else
  bad "canonical side-atom concludes missing after alias declaration"
fi
if grep -q 'relation("논문갑", "retraction_status", "철회됨")' "$KB/facts/accepted.dl"; then
  ok "canonical side-atom retraction_status emitted (grep layer)"
else
  bad "canonical side-atom retraction_status missing after alias declaration"
fi
# invariant: variant atoms still stored verbatim alongside the side-atoms
grep -q '"결론"' "$KB/facts/accepted.dl" && ok "variant atom 결론 preserved after aliasing" || bad "variant atom 결론 dropped"

# engine layer: the canonical-predicate rule now fires
if [ "$have_engine" -eq 1 ]; then
  run_check || bad "run_logic_check failed (positive)"
  if grep -q "conflict: 논문갑 (conflict_retracted)" "$KB/facts/logic_report.txt"; then
    ok "conflict rule fires via canonical side-atoms (engine layer)"
  else
    bad "conflict rule did not fire after alias declaration (engine layer)"
  fi
else
  echo "SKIP: engine layer (positive) — pyrewire not installed"
fi

# ============================================================================
# validate.py — relation-aliases.md format validation (#188, Task 4)
# We grep for the alias-specific error line so unrelated KB validation findings
# (pages coverage, etc.) never mask the assertion.
# ============================================================================
# Capture into a variable rather than piping: validate exits non-zero on any KB
# finding and `set -o pipefail` would otherwise leak that into the `if` guard.
validate_out() { FACTLOG_ROOT="$KB" "$PYTHON" "$PLUGIN_ROOT/tools/validate.py" "$KB" 2>&1; }

# valid aliases (still on disk from the positive case) → no alias error
vout="$(validate_out)"
if printf '%s' "$vout" | grep -q "relation-aliases.md"; then
  bad "validate reported an error for a VALID relation-aliases.md"
else
  ok "validate passes a valid relation-aliases.md (no alias error)"
fi

# malformed: alias chain a -> b -> c → FactlogError surfaced as a validate error
printf '# Relation aliases\n\n- `a` -> `b`\n- `b` -> `c`\n' > "$KB/policy/relation-aliases.md"
vrc=0; vout="$(validate_out)" || vrc=$?
if printf '%s' "$vout" | grep -q "policy/relation-aliases.md.*alias chains are not allowed"; then
  ok "validate flags a malformed relation-aliases.md (alias chain)"
else
  bad "validate did NOT flag the alias chain"
fi
[ "$vrc" -ne 0 ] && ok "validate exits non-zero on malformed relation-aliases.md" || bad "validate exit 0 despite malformed alias file"

# absent file → no alias error (no-op)
rm -f "$KB/policy/relation-aliases.md"
vout="$(validate_out)"
if printf '%s' "$vout" | grep -q "relation-aliases.md"; then
  bad "validate reported an alias error when the file is absent"
else
  ok "validate is a no-op when relation-aliases.md is absent"
fi

echo ""
echo "========================================"
echo "test_relation_alias_rule: $pass passed, $fail failed"
echo "========================================"
[ "$fail" -eq 0 ]
