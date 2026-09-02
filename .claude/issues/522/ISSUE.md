**Severity:** HIGH · **Domain:** dpcm · **Source:** Retroactive filing (session investigation, 2026-08-24)

## Description
`DpcmPacker` always started bin-packing DPCM sample banks (`DPCM_NN`) at physical bank 0, with zero awareness of how much of bank 0 the song's own sequence bytecode (`BANK_NN`, emitted by `CA65Exporter._build_song_bytecode`) had already consumed. `BANK_NN` and `DPCM_NN` are deliberately linked into the same physical `PRG_BANK_NN` region for a given index (MMC3's bank-switching design, `mappers/mmc3.py`), so two independently-sized blobs both starting at bank 0 could collide in the same physical 8KB window and overflow it — even when dozens of the 60 available swap banks sat completely empty.

Concretely: `exporter/exporter_ca65.py`'s `_build_song_bytecode` computed `next_bank` (the first bank index the song's own bytecode didn't use) but the caller discarded it as `_next_bank` instead of threading it anywhere. `dpcm_sampler/dpcm_packer.py`'s `DpcmPacker` had no `start_bank` concept at all.

Repro: building `canyon.mid` (a dense, multi-channel MIDI file with real DPCM drum samples) through the default MMC3 pattern-compressed pipeline failed with `MapperError: Music data does not fit the MMC3 PRG layout: bank 0: 7,931 bytes BANK_00 + 8,177 bytes DPCM_00 = 16,108 bytes exceeds the shared 8 KB bank` — even though the actual content (song bytecode + 18 DPCM samples) only needed ~5 of the 60 available swap banks total.

## Impact
Any song whose sequence bytecode nearly fills `BANK_00` **and** references real DPCM samples fails to build entirely, with a misleading "shorten the song" message — even though the real content fits MMC3's swap-bank pool comfortably. Blast radius: the MMC3 pattern-compressed + DPCM combination specifically (direct-export and DPCM-free bytecode builds were unaffected).

## Fix (already applied and merged)
Commit `1803fa7` ("feat: enhance DPCM packing to support dynamic start bank for samples"):
- `CA65Exporter` now exposes `next_bank` as a real instance attribute (defaults to `0`, overwritten once the bytecode branch runs) instead of discarding it.
- `DpcmPacker.__init__` accepts a `start_bank` parameter; `_pack_samples`/`_place_sample`/`generate_assembly` offset every physical bank index by it, and the 60-bank overflow guard checks `start_bank + len(self.banks) >= 60` rather than the local packer-relative count.
- `main.py`'s `pack_dpcm_into_asm` accepts and forwards `start_bank`; both call sites (`run_export`, `export_frames_and_resolve_mapper`) pass `getattr(exporter, 'next_bank', 0)`, so DPCM packing starts right after wherever the song's own bytecode banks ended.

Verified fixed: `canyon.mid` now builds successfully end-to-end (song bytecode in `BANK_00`, DPCM samples starting at `DPCM_01`, no collision), and the fix was independently re-verified fresh (no defect found) by the 2026-08-24 `/audit-mappers` pass.

## Completeness Checks
- [x] **RANGE**: The 60-bank overflow guard correctly accounts for `start_bank` offset, so a physical bank index can't silently exceed the swap pool
- [x] **CONTRACT**: `next_bank` defaults to `0` and only the bytecode branch overwrites it, so a direct (`--no-patterns`) export — which never creates `BANK_NN` segments — correctly keeps `start_bank=0`
- [x] **SIBLING**: `MMC3Mapper.validate_segment_sizes`'s shared-bank summing (index-generic, groups by numeric suffix) continues to correctly catch an overflow whether or not `BANK_NN`/`DPCM_NN` for a given index collide
- [x] **TESTS**: `tests/test_main.py` updated to cover the new `start_bank` threading; a mock-exporter test's bare `Mock()` needed an explicit `next_bank = 0` to reflect the real contract
- [ ] **DOC**: None needed — this is an internal bank-allocation detail, not user-facing behavior

This issue is filed closed — retroactive documentation for traceability. Code comments citing `#519/DP-2026-08-23-1` (written before this issue existed) are being corrected to cite this issue's real number in a small follow-up commit.
