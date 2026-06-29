# D-03: Standalone play_dpcm tests stale Z flag — rest sentinel triggers bogus sample $FF

Issue: #66 — https://github.com/matiaszanolli/midi2nes/issues/66
Labels: bug, high, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

**Severity:** HIGH · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
The direct-export (`export_direct_frames`, `standalone=True`, reachable via `--no-patterns`) `play_dpcm` routine:
```asm
lda (temp_ptr),y      ; A = note (sample_id+1, 0 = rest)
cmp last_dpcm_note    ; Z set iff note == last
beq @done             ; unchanged -> skip
sta last_dpcm_note    ; STA does NOT affect Z
beq @done             ; "note 0 -> nothing to trigger"  <-- tests stale cmp Z
; New sample: sample_id = note - 1
sec / sbc #1 / tay ...
```
The second `beq @done` (line 679) is meant to skip when the new note is 0, but `STA` leaves the flags from the preceding `CMP` untouched. Control only reaches line 678 when the `CMP` was *not* equal (the first `beq` at line 677 didn't branch), so Z=0 and the second `beq` **never** fires. A rest (`note == 0`) that differs from `last_dpcm_note` falls through to `sbc #1` → `y = $FF`, triggering `dpcm_*_table[$FF]` — out-of-table garbage.

## Location
`exporter/exporter_ca65.py:675-683`

## Evidence
`exporter_ca65.py:676-679`. Contrast the project-builder engine `nes/audio_engine.asm:314-316`, which correctly guards with `lda current_note,x / bne :+ / jmp @silence` *before* dispatching to `@write_dpcm`.

## Impact
In the `--no-patterns` direct-export ROM, every transition from a sample back to silence re-fires a wrong/garbage sample id, producing spurious DPCM noise. Project-builder bytecode path is unaffected.

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §3 (a `$4015` bit-4 trigger starts the reader from the programmed `$4012`/`$4013`; an out-of-range table index yields an arbitrary address/length).

## Suggested Fix
Reorder to test the note value, e.g. `lda (temp_ptr),y / cmp last_dpcm_note / beq @done / tax / sta last_dpcm_note / txa / beq @done`, or `pha`/`tax` to re-set Z from the note before the second branch.

## Completeness Checks
- [ ] **RANGE**: emitted sample index stays within the packed-table bounds (no $FF over-read)
- [ ] **SIBLING**: Same guard pattern checked in the project-builder engine path
- [ ] **TESTS**: A regression test pins this specific fix
