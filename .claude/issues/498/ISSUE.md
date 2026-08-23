# PAT-2026-08-23-1: detect-patterns subcommand's persisted JSON omits the documented variations key

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-08-23.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/498

## Description
`EnhancedPatternDetector.detect_patterns` returns the documented 4-key envelope
(`patterns`/`references`/`stats`/`variations`) — confirmed live via a fresh 208-assertion
round-trip harness in this audit — but the `detect-patterns` subcommand only persists three of
the four keys to disk (`main.py:834-838`):

```python
output = {
    "patterns": pattern_result["patterns"],
    "references": pattern_result["references"],
    "stats": pattern_result["stats"]
}
```

`pattern_result["variations"]` is silently discarded before `json.dumps`. This is distinct from
the already-fixed #258/PAT-09 (the in-memory `--no-patterns` stub, which does emit
`"variations": {}`, verified at `main.py:1184-1188`) — this gap is specifically in the on-disk
artifact written by the step-by-step `detect-patterns` subcommand.

## Evidence
`main.py:834-838`; contrast with `.claude/commands/_audit-common.md`'s documented contract:
"detect-patterns → dict with keys patterns, references, stats, variations".

## Impact
The on-disk stage artifact diverges from the documented inter-stage contract. Harmless today —
`run_export`'s `load_json_stage(..., ["patterns", "references"], ...)` only requires two keys
and never reads `variations` from the file. A future consumer that expects parity with the
in-memory envelope would `KeyError` only on this path.

## Related
#258 (PAT-09, fixed sibling: in-memory stub), #104 (envelope unification). Carried forward
unfixed from `docs/audits/AUDIT_PATTERNS_2026-08-21.md` (PAT-2026-08-21-5) and
`docs/audits/AUDIT_PATTERNS_2026-08-07.md` (PAT-2026-08-07-A) — never previously filed.

## Suggested Fix
Add `"variations": pattern_result["variations"]` to the `output` dict at `main.py:834-838` (or
amend `_audit-common.md`'s contract to explicitly scope the 4-key promise to the in-memory
return value, not the persisted file, if 3 keys on disk is intentional).

## Completeness Checks
- [ ] **CONTRACT**: If the stage's JSON shape changes, the consumer stage (`run_export` /
  `load_json_stage`) was checked for any new expectation on `variations`
- [ ] **TESTS**: A regression test asserts the on-disk `detect-patterns` JSON contains all 4 keys
- [ ] **DOC**: `_audit-common.md`'s detect-patterns contract description matches the fix
