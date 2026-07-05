# #220 — SAFE-09: SongBank.import_bank() and song subcommands have no JSON existence/parse/key guard

**Severity:** MEDIUM · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-03.md

## Description
`SongBank.import_bank()` (`nes/song_bank.py:177`-182) has no existence/parse/key guard, and none of the three `song` CLI subcommands (`run_song_add`, `run_song_list`, `run_song_remove`) wrap it in a try/except. This is the exact bug class SAFE-01/#120 fixed for the pipeline subcommands, but the fix's `load_json_stage` helper was never applied to the `song` command family — a corrupt/malformed `--bank` file crashes with a raw traceback instead of a clean `[ERROR]` message.

## Location
`nes/song_bank.py:177`-182 (`import_bank`); call sites `main.py:404` (`run_song_add`), `main.py:429` (`run_song_list`), `main.py:452` (`run_song_remove`); dispatch at `main.py:918` (`args.func(args)`, no wrapping try/except)

## Evidence
`nes/song_bank.py:179`: `data = json.loads(Path(input_path).read_text())`; `:180`-182: `self.total_banks = data['bank_info']['total_banks']`; `self.max_bank_size = data['bank_info']['bank_size']`; `self.songs = data['songs']`. `main.py:398`-420 (`run_song_add`), `:422`-443 (`run_song_list`), `:445`-459 (`run_song_remove`): none wrap the `import_bank`/`add_song_from_midi` calls in try/except.

## Impact
A user re-running `song add`/`song list`/`song remove` against a hand-edited, truncated, or wrong-format `--bank` JSON file gets a raw `FileNotFoundError`/`JSONDecodeError`/`KeyError` traceback instead of an actionable message. Scope is the JSON song-bank storage feature only (`CLAUDE.md`: "JSON song-bank storage/analysis only — not compiled to ROM"), so there is no ROM-corruption blast radius, matching SAFE-01's original MEDIUM classification for the same defect class.

## Related
Same root cause and fix pattern as SAFE-01/#120 (closed) — that fix's helper (`load_json_stage`) was scoped to the pipeline subcommands only and never extended to `song`. Not a duplicate of any open issue (checked #30/F-13, #33/F-14, #111/P-03 — all cover different song-bank gaps: routing, parser drift, and a dropped `--config` flag respectively).

## Suggested Fix
Reuse `load_json_stage(args.bank, ['bank_info', 'songs'], 'song-bank')` inside `import_bank`'s three call sites (or move the guard into `import_bank` itself), and wrap `run_song_add`/`run_song_list`/`run_song_remove` bodies in the same `try/except Exception as e: print(f"[ERROR] ..."); sys.exit(1)` pattern used by every other subcommand.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #221 — SAFE-10: Second unguarded mido.MidiFile() call in parse_midi_to_frames_with_analysis

**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-03.md

## Description
SAFE-02 (#121, closed) guarded `mido.MidiFile(midi_path)` at `parser_fast.py:16` and `parser.py:13`, wrapping it in `try/except (EOFError, OSError, ValueError)` → `InvalidMIDIError`. `parse_midi_to_frames_with_analysis` (`parser_fast.py:150`-229) first calls the now-guarded `parse_midi_to_frames(midi_path)` (`:156`) to get `result`, but then — "to rebuild the tempo map" for pattern/loop analysis — calls `mido.MidiFile(midi_path)` again directly at `:180`, completely unguarded, with no try/except around it at all.

## Location
`tracker/parser_fast.py:180`

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
