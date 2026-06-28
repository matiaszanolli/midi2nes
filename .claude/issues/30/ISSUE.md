# F-13: Song-bank path is disjoint from the pipeline — no song → ROM route

**Severity:** MEDIUM · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #30

## Description
SongBank exposes only JSON bank read/write and size estimation (add_song_from_midi, add_song, export_bank, import_bank, get_bank_data, get_bank_size — no compile/build). No method turns a bank into a .nes, and no pipeline entry consumes a bank. The song subcommands are a dead-end relative to ROM generation. ROADMAP/WORK_PLAN make no multi-song-ROM promise — a feature gap, not doc-rot.

## Evidence
grep "def " nes/song_bank.py shows no build/compile method; subcommands list and run_full_pipeline never reference a bank.

## Impact
Multi-song banks can be assembled and listed but never compiled into a ROM — feature half-wired. No active corruption → MEDIUM.

## Related
F-14

## Suggested Fix
Add a song build <bank> <out.nes> route through the project builder/compiler, or document the song bank as analysis/storage-only.

**Location:** `nes/song_bank.py`; `main.py:159-221`
