#!/usr/bin/env bash
# tests/test_eject_cmd.sh — `factlog eject`, the inverse of ingest
#
# Pins (XDG-isolated; synthetic data; no pyrewire needed — eject recompiles
# accepted.dl deterministically via compile_facts):
#   - naming a binary original (deck.pptx) also matches its runs/sources/<stem>
#     conversion; eject deletes the conversion, strips the runs/*.json rows
#     (removing the now-empty file), and supersedes the citing candidate row
#   - the original under sources/ is KEPT by default (with a note); accepted.dl
#     drops the retired fact but keeps the others
#   - --dry-run changes nothing
#   - --purge deletes the candidate row instead of superseding it
#   - --delete-original also removes the user's original under sources/
#   - a bare stem matches; an unknown name errors (rc != 0); non-KB path errors
#
# Usage: bash tests/test_eject_cmd.sh

set -euo pipefail

export XDG_CONFIG_HOME="$(mktemp -d)/factlog-test-cfg"  # isolate active-KB config (#62)

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$PLUGIN_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON="${PYTHON:-python3}"

pass=0
fail=0
ok() { echo "PASS: $*"; pass=$((pass + 1)); }
bad() { echo "FAIL: $*" >&2; fail=$((fail + 1)); }

H="subject,relation,object,source,status,confidence,note"

# Scaffold a fresh KB with a binary original + its conversion + a text source,
# candidate rows citing each, and a runs/*.json extraction file for the deck.
seed() {  # $1 = KB path
  local kb="$1"
  "$PYTHON" -m factlog init --target "$kb" >/dev/null
  printf 'PK\003\004 fake pptx\000' > "$kb/sources/deck.pptx"
  printf '<!-- ingested -->\nslide text\n' > "$kb/runs/sources/deck.md"
  printf 'plain text\n' > "$kb/sources/notes.md"
  printf '%s\n%s\n%s\n%s\n' "$H" \
    'A,rel,B,runs/sources/deck.md,confirmed,0.9,' \
    'C,rel,D,sources/notes.md,confirmed,0.9,' \
    'E,rel,F,sources/notes.md,confirmed,0.9,' > "$kb/facts/candidates.csv"
  printf '[{"subject":"A","relation":"rel","object":"B","source":"runs/sources/deck.md","status":"candidate","confidence":0.9,"note":""}]\n' \
    > "$kb/runs/2026-01-01-deck.json"
}

# --- default: supersede; conversion + run file removed; original kept ----------
KB="$(mktemp -d)/wiki"; seed "$KB"
out="$("$PYTHON" -m factlog eject deck.pptx --target "$KB" 2>&1)"
printf '%s\n' "$out"; echo "---"
[ ! -f "$KB/runs/sources/deck.md" ] && ok "conversion deleted" || bad "conversion still present"
[ ! -f "$KB/runs/2026-01-01-deck.json" ] && ok "emptied runs/*.json removed" || bad "runs json still present"
[ -f "$KB/sources/deck.pptx" ] && ok "original kept by default" || bad "original was deleted without --delete-original"
grep -q "A,rel,B,runs/sources/deck.md,superseded," "$KB/facts/candidates.csv" && ok "citing row marked superseded" || bad "row not superseded"
grep -q '"A", "rel", "B"' "$KB/facts/accepted.dl" && bad "retired fact still in accepted.dl" || ok "retired fact dropped from accepted.dl"
grep -q '"C", "rel", "D"' "$KB/facts/accepted.dl" && ok "unrelated fact preserved in accepted.dl" || bad "unrelated fact lost"
printf '%s' "$out" | grep -qF "matched source ref" && printf '%s' "$out" | grep -qF "runs/sources/deck.md" && printf '%s' "$out" | grep -qF "sources/deck.pptx" \
  && ok "binary name matches both original and its conversion" || bad "stem-conversion match missing"

# --- --dry-run changes nothing -----------------------------------------------
KB="$(mktemp -d)/wiki"; seed "$KB"
before="$(cat "$KB/facts/candidates.csv")"
"$PYTHON" -m factlog eject deck.pptx --target "$KB" --dry-run >/dev/null 2>&1
[ -f "$KB/runs/sources/deck.md" ] && [ -f "$KB/runs/2026-01-01-deck.json" ] && [ "$(cat "$KB/facts/candidates.csv")" = "$before" ] \
  && ok "--dry-run leaves files and candidates.csv untouched" || bad "--dry-run mutated state"

# --- --purge deletes the candidate row ---------------------------------------
KB="$(mktemp -d)/wiki"; seed "$KB"
"$PYTHON" -m factlog eject deck.pptx --target "$KB" --purge >/dev/null 2>&1
grep -q "runs/sources/deck.md" "$KB/facts/candidates.csv" && bad "--purge left the row" || ok "--purge deletes the candidate row"

# --- --delete-original removes the user's original ----------------------------
KB="$(mktemp -d)/wiki"; seed "$KB"
"$PYTHON" -m factlog eject notes.md --target "$KB" --purge --delete-original >/dev/null 2>&1
[ ! -f "$KB/sources/notes.md" ] && ok "--delete-original removes the original" || bad "original not deleted"
grep -q "sources/notes.md" "$KB/facts/candidates.csv" && bad "notes rows not purged" || ok "text-source rows purged"

# --- bare stem matches; unknown name errors ----------------------------------
KB="$(mktemp -d)/wiki"; seed "$KB"
"$PYTHON" -m factlog eject deck --target "$KB" >/dev/null 2>&1 \
  && [ ! -f "$KB/runs/sources/deck.md" ] && ok "bare stem 'deck' matches the source" || bad "bare stem did not match"
set +e; "$PYTHON" -m factlog eject nope --target "$KB" >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -ne 0 ] && ok "unknown source name errors (rc != 0)" || bad "unknown name should error"

# --- non-KB path errors -------------------------------------------------------
set +e; "$PYTHON" -m factlog eject anything --target "$(mktemp -d)" >/dev/null 2>&1; rc=$?; set -e
[ "$rc" -ne 0 ] && ok "eject on a non-KB path errors" || bad "non-KB path should error"

echo ""
echo "========================================"
echo "test_eject_cmd: $pass passed, $fail failed"
echo "========================================"
[ "$fail" -eq 0 ]
