# MAP-1: MMC3 capacity pre-flight doesn't sum BANK_NN + DPCM_NN sharing the same physical bank — false-pass then ld65 link failure

- **Issue:** https://github.com/matiaszanolli/midi2nes/issues/212
- **Labels:** critical, mappers, bug
- **Source report:** `docs/audits/AUDIT_MAPPERS_2026-07-03.md`
- **Finding ID:** MAP-1
- **Severity:** CRITICAL

## Body filed

**Severity:** CRITICAL · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-03.md

## Description
`generate_linker_config()` deliberately maps `DPCM_NN` (DPCM sample data, written by
`dpcm_sampler/dpcm_packer.py`) and `BANK_NN` (sequence bytecode, written by
`exporter/exporter_ca65.py`'s bank-rollover logic) into the **same** `PRG_BANK_{i:02d}`
8 KB memory region for a given bank index `i` — this is intentional, documented sharing
(`mappers/mmc3.py:85-91`). But the two producers assign bank indices **independently**:
the exporter's sequence-bank rollover and the DPCM packer's `_pack_samples()` (First Fit
Decreasing, `dpcm_sampler/dpcm_packer.py:49-75`) both start numbering from bank 0 with no
coordination between them. `MMC3Mapper.validate_segment_sizes()` (`mappers/mmc3.py:203-220`)
iterates `segment_sizes` and checks **each** `BANK_NN`/`DPCM_NN` segment's size against
`PRG_WINDOW_SIZE` (8192) **independently** — it never groups by trailing bank index and
sums `BANK_NN` + `DPCM_NN` for the same `NN` before comparing to the 8 KB budget. When a
song's busiest sequence bank (bank 0, since sequence data always starts there) is already
close to 8 KB *and* the DPCM packer also places a sample in bank 0 (which it will for any
song with only a few small samples, since bank 0 is always tried first), the **combined**
region overflows even though each segment individually passes the check.

## Evidence
Reproduced end-to-end with the actual CC65 toolchain on `input.mid` via the default
single-command pipeline (`python main.py input.mid output.nes`, no flags):
```
[6/7] Preparing NES project...
  ✓ Music data 9,702 bytes fits the MMC3 PRG regions      <- pre-flight says OK
[7/7] Compiling NES ROM...
[ERROR] Failed to link ROM: ld65: Warning: .../nes.cfg(6): Segment 'BANK_00' overflows
        memory area 'PRG_BANK_00' by 560 bytes
ld65: Error: Cannot generate most of the files due to memory area overflow
```
Byte-level confirmation via `main.estimate_segment_sizes()` on the actual generated
`music.asm`:
```
BANK_00   7535 bytes   (sequence bytecode, from the exporter's bank rollover)
DPCM_00   1217 bytes   (1 packed DPCM sample, from dpcm_packer.py)
--------------------------------
combined  8752 bytes   vs PRG_WINDOW_SIZE = 8192   ->  overflow = 560 bytes
```
8752 − 8192 = **560**, exactly matching `ld65`'s reported overflow. Both `BANK_00` (7535)
and `DPCM_00` (1217) individually pass `mappers/mmc3.py:208`'s `size > self.PRG_WINDOW_SIZE`
check (both are `< 8192`), so `validate_segment_sizes()` returns no errors and
`check_mapper_capacity()` (`main.py:156-162`) never raises.

Confirmed against current code (2026-07-03): `MMC3Mapper.validate_segment_sizes()` in
`mappers/mmc3.py:203-220` loops over `segment_sizes.items()`, checks `startswith('BANK_')
or startswith('DPCM_')`, and compares each individually to `PRG_WINDOW_SIZE` — there is no
grouping/summing by trailing bank index anywhere in the function.

## Impact
The default, documented, single-command pipeline (`python main.py input.mid output.nes`)
**fails to produce a ROM at all** for ordinary MIDI input that combines moderately dense
sequence data with even a single DPCM sample — not an edge case requiring an unusually
large or long song. The specific capacity gate built by #126/#127 to replace a raw `ld65`
region-overflow with a clear budget message gives **false reassurance** ("✓ fits")
immediately before the exact failure it was designed to prevent. Blast radius: any song
using pattern compression (the default) with drums, where bank 0's sequence data is
already using a large fraction of its 8 KB. Not silent (the build aborts with a `ld65`
error, no corrupt ROM ships) but meets the CRITICAL floor "Music data exceeds mapper PRG
capacity without detection" — the detection mechanism specifically built for this
scenario does not detect it.

## Suggested Fix
In `MMC3Mapper.validate_segment_sizes()`, before checking individual segment sizes,
group `segment_sizes` by trailing bank index (`BANK_NN` and `DPCM_NN` for the same `NN`)
and sum them; compare the **combined** total per index to `PRG_WINDOW_SIZE`. Emit a
message naming both contributors (e.g. "bank 0: 7,535 bytes sequence + 1,217 bytes
DPCM = 8,752 bytes exceeds 8,192-byte bank"). Longer-term, consider having the DPCM
packer and the sequence-bank exporter share a single bank-index allocator so they don't
independently contend for bank 0.

**Related:** #126, #127 (the capacity-gate fix this is a gap in), MAP-4 (companion finding, same report).

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
