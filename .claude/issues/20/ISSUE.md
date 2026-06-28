# NH-04: Noise period table broken and never consulted; module/instance impls disagree

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #20

## Description
Two contradictory noise-period implementations, neither on the pipeline path (NH-01):
- Module `get_noise_period` (pitch_table.py:52) indexes `NOISE_PERIOD_TABLE = [0x0..0xF]` (identity list, not the hardware period table) and does not invert → higher note → lower frequency (backwards).
- `PitchProcessor._get_noise_period` (line 106) returns `15 - scaled` (correct inversion) but maps to a bare 0–15 index.

The real NTSC period table lives only as `NOISE_PERIODS` in exporter_ca65.py:47 and is unused.

## Evidence
`NOISE_PERIOD_TABLE = [0x0,…,0xF]` (line 47); `get_noise_period` no inversion (line 61) vs `_get_noise_period` `15 - …` (line 114).

## Impact
Once NH-01 is fixed, the non-inverted helper makes higher drum notes lower-pitched. Today dead, correctness trap.

## Hardware ref
`docs/APU_NOISE_REFERENCE.md` §2–§3.

## Related
NH-01.

## Suggested Fix
Delete the identity table/`get_noise_period`; keep one inverting MIDI→index mapper feeding the `$400E` low nibble; mode bit per drum.
