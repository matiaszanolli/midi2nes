# DP-01 / #295: length_reg = (size-1)//16 floors -- non-16k+1 DPCM samples under-read their tail (regression of #75)

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-06.md · **Regression of #75** (closed 2026-07-04; fix not present on master)

## Description
`dpcm_sampler/dpcm_packer.py:79` computes `dpcm_length_val = (sample['size'] - 1) // 16`. Per `docs/APU_DMC_REFERENCE.md` (`$4013`: sample length = `(L * 16) + 1` bytes), the DMC engine reads exactly `(length_reg * 16) + 1` bytes at playback. Flooring `(size-1)//16` makes the engine read `floor((size-1)/16)*16 + 1 <= size` bytes -- under-reading up to 15 bytes of the sample tail for any `size` not exactly `16k+1`.

This is the exact bug closed as #75, but the closing fix is not on the current working tree -- the code path is verifiably unchanged and still floors.

## Evidence
```
size = 100 -> length_reg = 99 // 16 = 6 -> engine reads 6*16+1 = 97 bytes; final 3 bytes (24 output deltas) never play.
```
The value flows into `dpcm_len_table` and is loaded into `$4013` by the generated `play_dpcm` trigger (`exporter/exporter_ca65.py:820-821`). The `.align 64` padding (`dpcm_packer.py:100`) means the extra bytes a `ceil` would read are zero-pad, not neighbouring sample data. Max in-range value stays safe: `(4081-1)//16 = 255`, fits the 8-bit register.

## Impact
Every packed sample whose byte length is not `= 1 (mod 16)` loses up to 15 bytes (~120 DMC output samples, ~15 ms at rate index 15) off its tail -- an audible tail clip on short percussive samples.

## Suggested Fix
Use ceiling division: `dpcm_length_val = max(0, (size + 14) // 16)` (i.e. `ceil((size-1)/16)`, guarded for `size==0`), clamped to `min(255, ...)`.

## Completeness Checks
- [ ] RANGE, SIBLING, TESTS, DOC (see GitHub issue body)

---

# ARR-NEW-4 / #296: _apply_sustain merges fast sequential notes into false chords; arpeggiator silently drops half of them

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-06.md · **Status:** NEW

## Description
`_apply_sustain` (`arranger/pipeline_integration.py:15-69`), reached unconditionally via `analyze_midi_events` (`:174-175`, `sustain=True` default) -> `arrange_for_nes` (`:210`), groups notes whose start frames fall within `chord_tolerance = 2` frames of the group's first note (`:35`) and extends every note in that group to the group's `max_end` (`:47-67`). This cannot distinguish a staggered chord from a fast sequential monophonic run: if a melody's notes are <=2 frames apart, each adjacent pair is treated as a 2-note "chord". The earlier note is stretched so it overlaps the later note, manufacturing false polyphony. `_allocate_pulse` then arpeggiates the false dyad; the arp never advances past the root before the overlap ends, and the second note of every pair is never emitted on any channel -- silently lost.

## Evidence
Input melody `[60,62,64,65,67,69,71,72]`, each note 2 frames long, sequential (note i at frame i*2):
```
spacing=2  sustain=ON  (default): pulse1 set = [60, 64, 67, 71]   # 62,65,69,72 DROPPED
spacing=2  sustain=OFF          : pulse1 set = [60,62,64,65,67,69,71,72]  # all present
spacing=3+ sustain=ON           : all 8 notes present
```
`sustain` is not exposed by `arrange_for_nes` or the CLI.

## Impact
Any pulse-routed melodic passage with notes <=2 frames (~33ms) apart -- fast runs, trills, grace/ornament notes, 32nd-notes at high tempo -- silently loses about every other note.

## Suggested Fix
Only bridge/extend notes that are actually simultaneous (true chords) -- require the earlier note's original `end_frame` to be at/after the next note's `start_frame` before extending.

## Completeness Checks
- [ ] CONTRACT, TESTS, SIBLING (see GitHub issue body)
