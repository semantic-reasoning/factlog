#!/usr/bin/env bash
# tests/test_compile_dedup.sh — accepted.dl triple dedup across sources (#191)
#
# The same (subject, relation, object) accepted from several sources must become
# a SINGLE engine atom in facts/accepted.dl so ask/evaluate and run_logic_check
# report set semantics (one row / true count), not an inflated duplicated count.
# Source aggregation (sources: N, provenance) lives on the separate candidates
# path and must stay lossless.
#
# Pins:
#   (a) compile: a multi-source triple appears exactly once in accepted.dl
#   (b) ask evaluate: count=1, one row (no duplicate row)
#   (c) render: the single row still shows (sources: 2) — provenance lossless
#   (d) run_logic_check: `engine facts` count reflects the deduped set (no dup)
#   (e) byte-stability: a KB with no duplicate triple compiles unchanged
#
# Synthetic data only (relation path needs no pyrewire).
# Usage: bash tests/test_compile_dedup.sh

set -euo pipefail

export XDG_CONFIG_HOME="$(mktemp -d)/factlog-test-cfg"  # isolate active-KB config (#62) from the dev machine

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$PLUGIN_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python3}"
ROUTER="$PLUGIN_ROOT/tools/ask_router.py"
HEADER="subject,relation,object,source,status,confidence,note"

pass=0
fail=0
ok() { echo "PASS: $*"; pass=$((pass + 1)); }
bad() { echo "FAIL: $*" >&2; fail=$((fail + 1)); }

KB="$(mktemp -d)/wiki"
"$PYTHON" -m factlog init --target "$KB" >/dev/null
# Two distinct sources on disk backing the SAME triple, both accepted.
printf 'a\n' > "$KB/sources/a.md"; printf 'b\n' > "$KB/sources/b.md"
printf '%s\n%s\n%s\n' "$HEADER" \
  'PMID:16354850,게재저널,Chest,sources/a.md,confirmed,0.90,' \
  'PMID:16354850,게재저널,Chest,sources/b.md,confirmed,0.95,' \
  > "$KB/facts/candidates.csv"

# --- compile ---------------------------------------------------------------
FACTLOG_ROOT="$KB" "$PYTHON" -m factlog.compile_facts >/dev/null

# (a) exactly one relation() line for the triple in accepted.dl
n_lines="$(grep -cF 'relation("PMID:16354850", "게재저널", "Chest")' "$KB/facts/accepted.dl" || true)"
if [ "$n_lines" = "1" ]; then ok "multi-source triple appears once in accepted.dl"; else bad "expected 1 accepted.dl line, got $n_lines"; fi

router() { "$PYTHON" "$ROUTER" "$@" --target "$KB"; }
field() { "$PYTHON" -c "import json,sys; print(json.load(sys.stdin).get(sys.argv[1]))" "$1"; }

# (b) ask evaluate: count=1 and exactly one row
ev="$(router evaluate 'relation("PMID:16354850", "게재저널", O)?')"
cnt="$(printf '%s' "$ev" | field count)"
nrows="$(printf '%s' "$ev" | "$PYTHON" -c "import json,sys; print(len(json.load(sys.stdin).get('rows', [])))")"
[ "$cnt" = "1" ] && ok "evaluate count=1 (no inflation)" || bad "evaluate count=$cnt (expected 1)"
[ "$nrows" = "1" ] && ok "evaluate returns exactly one row" || bad "evaluate returned $nrows rows (expected 1)"

# (c) render keeps both sources on the single row — provenance lossless
rn="$(router render 'relation("PMID:16354850", "게재저널", O)?')"
printf '%s' "$rn" | grep -qF "sources: 2" && ok "render keeps (sources: 2) — provenance lossless" || bad "render lost the second source: $rn"
# still just one rendered fact row
frows="$(printf '%s' "$rn" | grep -cF '게재저널, Chest' || true)"
[ "$frows" = "1" ] && ok "render shows the fact once (deduped)" || bad "render showed the fact $frows times"

# (d) run_logic_check: engine-facts count reflects the deduped set. Needs a
# compiled policy (and pyrewire); guard so environments without it skip.
if "$PYTHON" -c "import pyrewire" >/dev/null 2>&1; then
  printf '# policy\n## Rules\n- [j] 어떤 항목이 `게재저널` 관계를 가지면 검토(review)가 필요하다.\n' > "$KB/policy/logic-policy.md"
  ( cd "$PLUGIN_ROOT" && FACTLOG_ROOT="$KB" "$PYTHON" tools/generate_logic_policy.py >/dev/null 2>&1 )
  lc="$(FACTLOG_ROOT="$KB" "$PYTHON" "$PLUGIN_ROOT/tools/run_logic_check.py" 2>/dev/null || true)"
  ef="$(printf '%s' "$lc" | grep -oE 'engine facts: [0-9]+' | grep -oE '[0-9]+' | head -1)"
  [ "$ef" = "1" ] && ok "run_logic_check engine facts=1 (no duplicate)" || bad "run_logic_check engine facts=$ef (expected 1)"
else
  echo "SKIP: pyrewire unavailable — skipping run_logic_check assertion"
fi

# --- (e) byte-stability: no duplicate triple -> accepted.dl unchanged -------
KB2="$(mktemp -d)/wiki"
"$PYTHON" -m factlog init --target "$KB2" >/dev/null
printf 'a\n' > "$KB2/sources/a.md"
printf '%s\n%s\n%s\n' "$HEADER" \
  'A,uses,X,sources/a.md,confirmed,0.90,' \
  'B,uses,Y,sources/a.md,confirmed,0.90,' \
  > "$KB2/facts/candidates.csv"
FACTLOG_ROOT="$KB2" "$PYTHON" -m factlog.compile_facts >/dev/null
before="$(cat "$KB2/facts/accepted.dl")"
FACTLOG_ROOT="$KB2" "$PYTHON" -m factlog.compile_facts >/dev/null
after="$(cat "$KB2/facts/accepted.dl")"
[ "$before" = "$after" ] && ok "no-duplicate KB: accepted.dl compiles byte-stable" || bad "accepted.dl changed on a no-duplicate KB"
# and each distinct triple present exactly once
[ "$(grep -cE '^relation\(' "$KB2/facts/accepted.dl")" = "2" ] && ok "distinct triples preserved (2 rows)" || bad "distinct triple count wrong"

echo ""
echo "========================================"
echo "test_compile_dedup: $pass passed, $fail failed"
echo "========================================"
[ "$fail" -eq 0 ]
