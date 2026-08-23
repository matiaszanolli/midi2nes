# NH-HW-2026-08-22-1: Same-pitch note-on retriggers with no gap frame are silently absorbed into the previous note

**Filed:** https://github.com/matiaszanolli/midi2nes/issues/481
**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-08-22.md

## Description
`compile_channel_to_frames` (`nes/emulator_core.py`) builds its `frames` dict purely from a per-frame `note` value; it has no onset marker. When two real, independent MIDI note-on events land on the same pitch with the second's start frame equal to the first's end frame (a common shape: a note-off paired to the next note-on's frame, or two notes with no rest between them — routine for repeated/staccato notes and gated ostinatos), the two events produce **adjacent frames carrying the identical `note` value with no frame gap**. Both downstream consumers key their retrigger logic on "did `note` change since the last frame/byte": `_build_song_bytecode`'s `if note != current_note` treats the whole span as one macro event (no `Length`/note byte boundary is ever emitted at the join), and direct-export's `cmp last_pulse1_note` / `beq @sustain` suppresses the $4003 rewrite the same way. If the two source notes also share a velocity (identical or velocity-to-volume-bucket-equal — routine for mechanically quantized/drum-pattern MIDI), the volume macro/control byte is flat across the join too, so **literally nothing** in the emitted ROM distinguishes two attacks from one long sustain.

## Location
`nes/emulator_core.py:52-126` (`compile_channel_to_frames`); consumed by `exporter/exporter_ca65.py:1297` (`_build_song_bytecode`'s `if note != current_note` event-boundary test) and by direct-export's `play_pulse1`/`play_pulse2` `cmp last_pulse1_note` / `beq @sustain` guard (`exporter/exporter_ca65.py:341-360`)

## Evidence
Reproduced against the live pipeline (no mocks) — two MIDI note-on events at pitch 60, velocities 100/100, note-off of the first exactly at the second's onset frame (frame 10). Feeding the resulting frames through `CA65Exporter._build_song_bytecode` (bytecode/patterned path) produced one `Length 20, Note 60` event instead of two. See the filed issue body for the full reproduction script and byte-level output.

## Hardware ref
`docs/APU_PULSE_REFERENCE.md` §3 "Critical Side Effects"; `docs/APU_ENVELOPE_REFERENCE.md` §4/§5

## Related
#439/EXP-2026-08-21-1, #449/ARR-2026-08-21-2, #296/ARR-NEW-4

## Suggested Fix
Give `compile_channel_to_frames` an explicit `retrigger` marker on the first frame of each source event, threaded through to `_build_song_bytecode`'s event-boundary test and direct-export's `last_pulse1_note` comparison, forcing a rewrite even when the note value is unchanged.
