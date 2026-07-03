#!/usr/bin/env bash
# .claude/commands/_audit-validate.sh
#
# Validates file/dir path references in `.claude/commands/audit-*/SKILL.md`,
# `.claude/commands/fix-issue/SKILL.md`, and `.claude/commands/_audit-*.md`
# against the live repo tree.
#
# Why: "stale path" findings keep recurring after module moves/renames.
# This gate catches drift on the commit that introduces it, instead of
# letting a report cite a Location: that no longer exists.
#
# What it checks:
#   - Every backticked path token ending in a known source/doc extension
#     (.py .md .yaml .yml .json .asm .cfg .s .sh .bat .txt) is resolved
#     against the repo root. Missing paths print STALE and exit 1.
#   - Brace-expanded refs like `exporter/{exporter_ca65,exporter_nsf}.py`
#     expand to N paths and each is checked.
#   - Trailing `:NN` or `:NN-NN` line ranges are stripped before the
#     existence check (line numbers drift; the file must still exist).
#
# What it skips (not real repo paths):
#   - /tmp/...                 — runtime audit scratch
#   - *.mid / *.nes / *.nsf    — sample / generated binaries
#   - URLs (contain ://)
#   - bare basenames (no slash) — shorthand inside an established-dir paragraph
#
# Usage:
#   .claude/commands/_audit-validate.sh           # validate, exit 1 on stale
#   .claude/commands/_audit-validate.sh --verbose # list every ref checked

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

VERBOSE=0
[[ "${1:-}" == "--verbose" ]] && VERBOSE=1

EXT_RE='\.(py|md|yaml|yml|json|asm|cfg|s|sh|bat|txt)$'

should_skip() {
    local p="$1"
    [[ "$p" != */* ]] && return 0           # bare basename, no path info
    [[ "$p" == /tmp/* ]] && return 0
    [[ "$p" == *.mid || "$p" == *.nes || "$p" == *.nsf ]] && return 0
    [[ "$p" == *"://"* ]] && return 0
    [[ "$p" == *"*"* ]] && return 0          # glob pattern, not a literal path
    [[ "$p" == *"<"* || "$p" == *">"* ]] && return 0   # <TYPE>/<TODAY> placeholder
    return 1
}

# Expand `prefix{a,b,c}suffix` -> prefix-a-suffix ... (one brace pair).
expand_braces() {
    local path="$1"
    if [[ "$path" == *"{"*"}"* ]]; then
        local prefix="${path%%\{*}"
        local rest="${path#*\{}"
        local inner="${rest%%\}*}"
        local suffix="${rest#*\}}"
        local IFS=','
        for part in $inner; do
            echo "${prefix}${part}${suffix}"
        done
    else
        echo "$path"
    fi
}

strip_range() { echo "${1%%:[0-9]*}"; }

STALE=0
CHECKED=0

FILES=$(git ls-files '.claude/commands/audit-*/SKILL.md' \
                     '.claude/commands/fix-issue/SKILL.md' \
                     '.claude/commands/_audit-*.md' 2>/dev/null || true)

for f in $FILES; do
    # Pull every backticked token.
    while IFS= read -r tok; do
        [[ -z "$tok" ]] && continue
        # Only consider tokens that end in a known source/doc extension.
        # (A bare `dir/name` with no extension — repo slugs, slash-commands — is not a file ref.)
        [[ "$tok" =~ $EXT_RE ]] || continue
        while IFS= read -r expanded; do
            cand="$(strip_range "$expanded")"
            should_skip "$cand" && continue
            CHECKED=$((CHECKED+1))
            if [[ -e "$cand" ]]; then
                [[ $VERBOSE -eq 1 ]] && echo "  ok    $f -> $cand"
            else
                echo "STALE  $f -> $cand"
                STALE=$((STALE+1))
            fi
        done < <(expand_braces "$tok")
    done < <(grep -oE '`[^`]+`' "$f" | sed 's/`//g')
done

echo "Checked $CHECKED path refs across audit skills."
if [[ $STALE -gt 0 ]]; then
    echo "FAILED: $STALE stale path reference(s). Fix or un-backtick them."
    exit 1
fi
echo "OK: no stale path references."
