# SAFE-2026-08-21-1: song add crashes with a raw traceback on corrupt/missing MIDI, duplicate name, or full bank

**GitHub Issue:** #455
**Severity:** MEDIUM
**Domain:** safety
**Source:** docs/audits/AUDIT_SAFETY_2026-08-21.md
**Status at filing:** NEW

## Description
`run_song_add` guards loading an existing `--bank` file, then calls
`bank.add_song_from_midi(args.input, ...)` and `bank.export_bank(...)` with no
exception handling at all, and `main()`'s dispatch (`args.func(args)`,
`main.py:1655`) has no outer net. Every documented failure mode of those two calls —
a non-MIDI input file, a missing input file, re-adding an existing song name, a bank
with no remaining space — escapes as an uncaught exception and a raw traceback,
even though three of the four already raise clean typed messages
(`InvalidMIDIError`, `ValueError`).

## Location
`main.py:799-827` (`run_song_add`; unguarded `bank.add_song_from_midi` at `:822`,
unguarded `bank.export_bank` at `:826`); raisers: `tracker/parser_fast.py:16-21`
(`InvalidMIDIError`/`FileNotFoundError`), `nes/song_bank.py:124` (`ValueError: Song
'...' already exists`), `nes/song_bank.py:142`/`:160` (`ValueError: Not enough bank
space` / `No available bank space`)

## Evidence
Reproduced live:
```
$ printf 'not a midi file' > bad.mid
$ python3 main.py song add bad.mid --bank bank.json --name test
Traceback (most recent call last):
  ...
  File "tracker/parser_fast.py", line 21, in _open_midi_file
    raise InvalidMIDIError(str(midi_path), str(e)) from e
core.exceptions.InvalidMIDIError: Invalid MIDI file: .../bad.mid: MThd not found. Probably not a MIDI file
```

## Impact
`song add` is the entry point of the whole jukebox chain (#30/F-13); ordinary user
errors produce a stack trace instead of the actionable one-line message the
exceptions already carry.

## Related
#220/SAFE-09 (the bank-load half of this fix), the identical defect class in
`run_song_build`'s per-song parse (SAFE-2026-08-07-2, Existing/unfiled per this
report — not re-filed), #121/SAFE-02

## Suggested Fix
Wrap `:813-827` in `try/except (MIDI2NESError, FileNotFoundError,
ValueError) as e: print(f"[ERROR] {e}"); sys.exit(1)`, matching the `import_bank`
guard three lines above.

## Dedup check
`gh issue list --repo matiaszanolli/midi2nes --state open` (32 open issues,
fresh pull at publish time) — no match on `song add`, `add_song_from_midi`, or
this defect class.
