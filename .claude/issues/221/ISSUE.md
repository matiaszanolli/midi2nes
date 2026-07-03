# SAFE-10: Second unguarded mido.MidiFile() call in parse_midi_to_frames_with_analysis

- **GitHub Issue**: https://github.com/matiaszanolli/midi2nes/issues/221
- **Severity**: LOW
- **Domain**: safety
- **Source**: docs/audits/AUDIT_SAFETY_2026-07-03.md
- **Dimension**: 2 — Malformed-Input Resilience
- **Location**: `tracker/parser_fast.py:180`
- **Status**: NEW (filed)

## Description
SAFE-02 (#121, closed) guarded `mido.MidiFile(midi_path)` at `parser_fast.py:16` and `parser.py:13`, wrapping it in `try/except (EOFError, OSError, ValueError)` → `InvalidMIDIError`. `parse_midi_to_frames_with_analysis` (`parser_fast.py:150`-229) first calls the now-guarded `parse_midi_to_frames(midi_path)` (`:156`) to get `result`, but then — "to rebuild the tempo map" for pattern/loop analysis — calls `mido.MidiFile(midi_path)` again directly at `:180`, completely unguarded, with no try/except around it at all.

## Evidence
`parser_fast.py:180`: `mid = mido.MidiFile(midi_path)` — bare, no try/except, no `InvalidMIDIError` import used at this call site (the module-level import at `:7` is only used by the guarded call at `:16`).

## Impact
In practice this is low-risk: by the time execution reaches line 180, `parse_midi_to_frames` at line 156 has already successfully opened and parsed the same `midi_path`, so a *content*-validity failure can't recur — the only realistic trigger is a TOCTOU race (file deleted/replaced between the two calls) or a resource issue (e.g. an FD/memory limit hit on the second open), which would raise a raw `mido`/`OSError` instead of `InvalidMIDIError`. This function is not reachable from the production pipeline (`main.py` only imports and calls `parse_midi_to_frames`); it is exercised only via the module's own `__main__` CLI block (`parser_fast.py:232`-end, `--with-analysis` flag) and `tests/test_parser_fast.py`.

## Related
Same fix pattern as SAFE-02/#121; not a duplicate since #121's scope (verified via its closed diff) only touched the two production parse entry points.

## Suggested Fix
Reuse the same guard (or better, avoid re-opening the file — pass the already-parsed `mid` object, or at least the `ticks_per_beat`, from the first call instead of re-parsing) so the second read is either eliminated or wrapped identically to the first.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
