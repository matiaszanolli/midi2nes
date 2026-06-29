# P-02: run_map reads midi_data["events"] with no guard — bare KeyError on malformed parse JSON

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-29.md

## Description
`run_map` does `assign_tracks_to_nes_channels(midi_data["events"], …)` (`main.py:51`) directly on a user-supplied JSON. If the parse output is hand-edited or produced by a drifted/older tool without an `events` key, this throws an uncaught `KeyError: 'events'` with a raw traceback instead of a clean `[ERROR] parse output missing 'events'` message. In `run_full_pipeline` the same access (`main.py:432`, `:440`) is wrapped by the top-level `except Exception` (`main.py:637`) so it degrades gracefully; the step-by-step `run_map` has no such guard.

## Evidence
`main.py:47-51` — `midi_data = json.loads(...)` then `midi_data["events"]` with no `if "events" not in midi_data` check.

## Impact
Poor UX on a malformed intermediate; not reachable under the normal parser (which always writes `events`). No data corruption.

## Related
SKILL Dimension 1 ("a parse output with no `events` key fails loudly, not with a bare `KeyError`"). Distinct from the unrelated patterns-audit issue #104 (no-patterns stub stats keys).

## Suggested Fix
Guard with a clear message: `if "events" not in midi_data: print("[ERROR] Parse output missing 'events' key"); sys.exit(1)`.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked at `main.py:432`/`:440` (default path) and other JSON-loading handlers
- [ ] **TESTS**: A regression test pins this specific fix
