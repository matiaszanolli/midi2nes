# SAFE-2026-08-21-2: SongBank.export_bank rewrites the cumulative bank JSON non-atomically

**GitHub Issue:** #456
**Severity:** MEDIUM
**Domain:** safety
**Source:** docs/audits/AUDIT_SAFETY_2026-08-21.md
**Status at filing:** NEW

## Description
Unlike a `music.asm` or intermediate JSON — regenerable from the MIDI in one
command — `song_bank.json` is *cumulative* state built up across many `song add`
runs, and both `song add` and `song remove` overwrite it **in place** via a plain
`write_text`. A disk-full, quota, or kill mid-write leaves a truncated file where
the previous good bank was; `import_bank`'s #220 guard will then cleanly *reject*
it, but the data is already gone and every song must be re-added. The repo already
solved this failure mode with `atomic_write_text` (`exporter/base_exporter.py:22`),
applied to all three CA65 writers and both FamiStudio writers; the highest-value
persistent file was left out.

## Location
`nes/song_bank.py:187-198` (`Path(output_path).write_text(...)` at `:198`);
writers: `run_song_add` (`main.py:826`), `run_song_remove` (`main.py:874`)

## Evidence
`nes/song_bank.py:198` is a direct `write_text` on the final path;
`grep -rn atomic_write_text nes/` → no matches. Contrast
`exporter/exporter_ca65.py:999/:1532/:1672`.

## Impact
Low-probability event, but the blast radius is the user's entire song bank
(irreplaceable if the source MIDIs' recorded `midi_path`s have since moved), and
the two commands that trigger it are exactly the ones a user runs most often on a
bank they care about.

## Related
#385/SAFE-2026-07-19-3 (same pattern, exporters), #220/SAFE-09 (read-side guard
that makes corruption visible but not recoverable)

## Suggested Fix
`from exporter.base_exporter import atomic_write_text` (or move the helper to
`core/`/`utils/` to avoid nes→exporter coupling) and replace `:198` with
`atomic_write_text(output_path, json.dumps(bank_data, indent=2))`.

## Dedup check
`gh issue list --repo matiaszanolli/midi2nes --state open` (32 open issues,
fresh pull at publish time) — no match on `export_bank`, `song_bank.json`
atomicity, or this defect class.
