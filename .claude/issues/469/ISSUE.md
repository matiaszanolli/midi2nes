# TD-36: Jukebox 5-channel stride is a bare 5 with no shared named constant

Labels: enhancement, low, tech-debt

**Severity:** LOW · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** Carried from 2026-08-07 (TD-36) — unfixed, never filed as a GitHub issue — filing now.

## Description
The `song_table` stride (5 = `len(SEQUENCE_CHANNELS)`) is a contract shared between the Python exporter and the 6502 engine, expressed as raw shift/add math on one side and an f-string index on the other, with only comments tying them. Adding a 6th channel stream (e.g. DPCM variants) breaks playback silently.

## Evidence
`nes/audio_engine.asm:267-271`:
```asm
lda current_song
asl a
asl a               ; A = current_song * 4
clc
adc current_song    ; A = current_song * 5
```
`exporter/exporter_ca65.py:1624` — comment "song_index*5 + channel". No `.define`/constant on the asm side, no named constant referenced from both sides.

## Impact
Latent cross-language drift trap; also the code where siblings found the real 8-bit overflow bug this cycle.

## Suggested Fix
Emit `SONG_TABLE_STRIDE = 5` into the generated asm from `len(self.SEQUENCE_CHANNELS)` and use it in `audio_engine.asm`'s comments/math (and in the overflow fix's widened index computation).

## Related
NH-HW-2026-08-21-3 / PIPE-2026-08-21-3 (the `current_song*5` 8-bit overflow at 52+ songs, CRITICAL/MEDIUM — fixing those should introduce this constant as part of the remedy; PIPE-2026-08-21-3 is filed as #426).

## Completeness Checks
- [ ] **CONTRACT**: The stride constant is emitted from a single Python source (`len(SEQUENCE_CHANNELS)`) and consumed identically by the asm engine — no independent hardcoded `5` remains on either side
- [ ] **TESTS**: A regression test (or the #426 overflow fix's own test) exercises a channel-count change and confirms both sides stay in sync

