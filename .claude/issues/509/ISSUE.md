# EXP-2026-08-23-2: export_song_bank_bytecode has no self-contained DPCM guard

**Severity:** MEDIUM · **Domain:** exporters
**Source:** AUDIT_EXPORTERS_2026-08-23.md (carried from EXP-2026-08-07-2 / EXP-2026-08-21-4, never previously filed)
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/509

## Description
Calling `export_song_bank_bytecode` directly with DPCM-bearing frames (bypassing
`main.py`'s `run_song_build`) silently emits a real `song{i}_dpcm_sequence`, while no
`DpcmPacker` runs in the jukebox path — the engine then indexes the project builder's
1-byte stub `dpcm_*_table`s past their end, feeding garbage into a live DMC DMA
trigger. Every other hard invariant in this method raises `ValueError` internally;
DPCM presence is the one that doesn't.

## Evidence
- `exporter/exporter_ca65.py:1245-1600` (`_build_song_bytecode`) — only a per-note
  range guard (`:1353-1362`), not a channel-presence guard.
- `exporter/exporter_ca65.py:1719-1912` (`export_song_bank_bytecode`) — no
  DPCM-presence check anywhere.
- Sole enforcement: `main.py:984` `_song_has_dpcm_events`, called only from
  `run_song_build`.

## Impact
Confined to non-CLI callers (library/test/future paths); out-of-bounds DMA table
reads if triggered.

## Related
#30/F-13, #425 (caller-side guard this depends on); #508, #510, #511, #512 (same audit).

## Suggested Fix
Raise `ValueError` from `export_song_bank_bytecode`/`_build_song_bytecode` for any
non-empty `dpcm` channel, mirroring `_song_has_dpcm_events`.
