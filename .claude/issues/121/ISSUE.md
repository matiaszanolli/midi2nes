**Severity:** MEDIUM · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-06-29.md

## Description
A truncated, empty, or non-MIDI input file makes `mido.MidiFile(path)` raise a raw `mido`-internal exception (`EOFError`, `OSError`, `ValueError`) which propagates unwrapped. The project defines `InvalidMIDIError(filepath, reason)` in `core/exceptions.py:38` for exactly this, but it is never raised anywhere (only imported/exported in `core/__init__.py`). `run_full_pipeline` validates only `input_midi.exists()` (`main.py:389`), so a 0-byte or `.txt`-renamed-to-`.mid` file reaches `parse_fast` and crashes inside `mido`. On the default path the outer `except Exception` (`main.py:637`) converts it to `[ERROR] Pipeline failed: <raw mido message>` — better, but still not a typed `InvalidMIDIError`; on the `parse` subcommand (`run_parse`) there is no outer handler at all.

## Location
- `tracker/parser_fast.py:14` (and `:116`)
- `tracker/parser.py:11`
- `nes/song_bank.py:71` (via `parse_midi_to_frames`)
- pipeline entry checks only `Path.exists()` at `main.py:389`

## Evidence
`parser_fast.py:14`: `mid = mido.MidiFile(midi_path)` — first statement, no guard. `parser.py:11` identical. `core/exceptions.py:38` `class InvalidMIDIError(ParsingError)` exists; grep confirms it is never raised (only `core/__init__.py` import/export).

## Impact
Non-MIDI / corrupt input produces a confusing `mido` stack trace (`run_parse`) or an opaque message rather than "Invalid MIDI file: <path>". Common user error (wrong file). No ROM corruption. Cross-refs the exception-type-discipline theme (raises raw type instead of the available typed one).

## Related
- #33 (F-14) notes `SongBank.add_song_from_midi` uses the full parser (parser drift); this finding is orthogonal (input-guard, all parsers).
- SAFE-08 (config exception discipline) shares the "typed exception exists but unused" theme.

## Suggested Fix
Wrap `mido.MidiFile(midi_path)` in `try/except (OSError, EOFError, ValueError)` and `raise InvalidMIDIError(midi_path, str(e))`. Add the guard once in a shared helper since three call sites need it.

## Completeness Checks
- [ ] **SIBLING**: Guard applied at all three call sites (`parser_fast.py`, `parser.py`, song_bank path)
- [ ] **TESTS**: A regression test pins this fix (0-byte / non-MIDI input → `InvalidMIDIError`, not raw mido traceback)
