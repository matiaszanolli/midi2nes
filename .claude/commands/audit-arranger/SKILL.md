---
description: "Audit arranger mode — role analysis, GM mapping, voice allocation, arpeggiation"
argument-hint: "[--focus <dims>]"
---

# Arranger Audit

Audit the intelligent arranger (`--arranger` mode) — the `arranger/` subsystem that turns
polyphonic MIDI into the NES's 4 tone channels (+ DPCM) via role detection, GM-instrument
mapping, priority-based voice allocation, and arpeggiation. This is the alternative front
half of the pipeline: under `--arranger`, `arrange_for_nes` replaces the
`assign_tracks_to_nes_channels` + `NESEmulatorCore.process_all_tracks` path.

Shared protocol: `.claude/commands/_audit-common.md` — read the **Project Layout** (arranger
paths) and the **Inter-Stage Data Contracts** entry for the map/arrange handoff before you
start; do not restate them here. Severity: `.claude/commands/_audit-severity.md` — apply its
floors, especially the contract-mismatch (HIGH), dropped-voice (MEDIUM), and triangle
volume/duty (HIGH) rows.

This audit overlaps two subsystem audits at the seams — cross-reference rather than
duplicate: GM drum routing with `/audit-dpcm`, and hardware-range/triangle limits with
`/audit-nes-hardware`.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,5`). Default: all.

## Extra Per-Finding Field
- **Dimension**: one of the 8 below.

## Entry Point & Call Site (orient here first)

- CLI wiring: `main.py` `run_full_pipeline` sets `use_arranger = args.arranger` and calls
  `arrange_for_nes(midi_data["events"], arp_speed=3, verbose=args.verbose)` — note `arp_speed`
  is hardcoded to `3` at the call site even though `arrange_for_nes` accepts a parameter.
- Entry function: `arranger/pipeline_integration.py` → `arrange_for_nes(midi_events, arp_speed=3,
  verbose=False)`, which calls `analyze_midi_events` then `allocate_with_arpeggiation`.
- Re-exported via `arranger/__init__.py`.

## Dimensions

### Dimension 1: Downstream Contract Parity (frames structure)
The arranger output MUST be the same `frames`-compatible structure the non-arranger path
produces, because both feed the identical Step-4/5 code in `main.py` (pattern detection →
`CA65Exporter.export_tables_with_patterns`). A mismatch is **HIGH** (silent-empty / wrong
data) per `_audit-severity.md`.

Checklist:
- The non-arranger path emits `NESEmulatorCore.process_all_tracks` output (`nes/emulator_core.py`):
  `{channel_name: {frame_num: {note, volume, ...}}}`. Compare key-by-key against the `output`
  dict built in `arrange_for_nes` (`arranger/pipeline_integration.py`) — channel names
  (`pulse1`/`pulse2`/`triangle`/`noise`/`dpcm`), and per-frame keys (`note`, `volume`, `pitch`,
  `control`, `period`, `sample`). Any key the exporter / pattern step reads from the legacy
  frames but the arranger omits (or vice-versa) is a contract break.
- The Step-4 pattern-detection loop in `main.py` reads `frame_data.get('note', 0)` and
  `frame_data.get('volume', 0)` from every channel including `noise`/`dpcm` — confirm the
  arranger's `noise` frames (which carry `period`, not `note`) and `dpcm` frames (only
  `sample`) survive that loop without silently zeroing.
- `--no-patterns` builds its stub stats from `sum(len(ch) for ch in frames.values())` — verify
  the arranger's five-channel dict is shaped so that sum is meaningful.
- Confirm the exporter consumes `pitch`/`control` if present, or recomputes — i.e. whether the
  arranger pre-baking `pitch`/`control` (see Dimension 7) is even honored downstream or dead.

### Dimension 2: Role Detection Correctness
`arranger/role_analyzer.py` `VoiceRoleAnalyzer._determine_role` scores BASS/MELODY/HARMONY/
DECORATIVE from GM hint + pitch (`BASS_THRESHOLD=48`, `LOW_MID_THRESHOLD=60`,
`HIGH_THRESHOLD=72`), density (`SPARSE_DENSITY`/`DENSE_DENSITY`), velocity, and polyphony.

Checklist:
- `analyze_midi_events` (`arranger/pipeline_integration.py`) constructs every `NoteInfo` with
  `program=program` where `program` is a local hardcoded `0` and never updated from MIDI
  program-change events. So `get_instrument_mapping(0)` (Acoustic Grand Piano) is the GM hint
  for **every** non-drum track — verify whether GM-driven role/channel/duty selection is
  effectively dead, leaving only pitch/density/velocity heuristics. If so, the whole GM table
  (Dimension 4) is bypassed on the live path — significant finding.
- Drum-track detection keys on the track *name* containing `'drum'` or being `'9'`/`9`
  (`analyze_midi_events`); the fast parser's channel/track naming determines whether GM
  channel 10 is actually caught. Confirm a real drum track is flagged, else it is scored as a
  pitched voice.
- `confidence` is `best_role_score / total_score`; with ties `max()` picks the first by dict
  order — check determinism of role ties (see Dimension 8).
- Velocity threshold `> 100` / `< 60` operate on raw MIDI velocity (0–127); confirm the
  values flowing in are velocity, not an already-scaled volume (events use
  `velocity = event.get('velocity', event.get('volume', 100))`).

### Dimension 3: Voice Allocation, Priority & Overflow
Two allocation layers: `VoiceRoleAnalyzer._assign_channels` (track→channel, build time) and
`VoiceAllocator.allocate_frame` (note→register, per frame) in `arranger/voice_allocator.py`.
A musically-wrong dropped voice is **MEDIUM** per `_audit-severity.md`.

Checklist:
- `_assign_channels` assigns each NES channel to **at most one track** (boolean
  `*_assigned` flags). With >4 pitched tracks, surplus tracks land in `plan.dropped_tracks`.
  Verify the drop order is priority-sorted (`plan.tracks.sort(key=priority, reverse=True)`)
  and musically defensible — e.g. that BASS is not dropped while a DECORATIVE voice survives.
- Drum tracks claim BOTH `noise` and `dpcm` (`if track.is_drum_track: ... continue`) — so a
  second drum track, or a melodic voice that wanted noise/dpcm, is starved. Confirm intent.
- Per-frame overflow: when multiple tracks map to one pulse channel, `_allocate_pulse` merges
  all their pitches into one arpeggio (it does not steal/keep separate). Triangle
  (`_allocate_triangle`) always keeps the **lowest** pitch (drops the rest); noise
  (`_allocate_noise`) keeps the **highest velocity** hit. Verify these tie-breaks are
  deterministic and that dropped simultaneous notes are the musically-right ones to drop.
- `set_arrangement` maps assigned tracks; tracks in `dropped_tracks` get no entry and
  `allocate_frame` skips them (`channel is None: continue`) — confirm dropped notes vanish
  silently with no warning beyond the `verbose` print.

### Dimension 4: GM Instrument Mapping Coverage
`arranger/gm_instruments.py` `GM_INSTRUMENT_MAP` (programs 0–127) + `get_instrument_mapping`
fallback, and `GM_DRUM_MAP` + `get_drum_mapping` fallback.

Checklist:
- Confirm `GM_INSTRUMENT_MAP` covers all 0–127 (no gap silently hitting the
  `get_instrument_mapping` fallback that forces HARMONY/PULSE2). `grep` the literal keys.
- Verify every `InstrumentMapping` whose `channel` is `NESChannel.TRIANGLE` has **no `duty`**
  set (triangle can't honor duty — see Dimension 6 / `/audit-nes-hardware`). Same for
  `NESChannel.NOISE` and `DPCM` mappings carrying a `duty`.
- `DutyCycle.DUTY_75 = 3` is commented "Same as 25% (inverted)" — confirm no mapping relies on
  75% being audibly distinct from 25% (it is not on real hardware; see
  `docs/APU_PULSE_REFERENCE.md`).
- Cross-check the `get_role_priority()` ordering (BASS=1…SFX=6) against the priority actually
  used for drop decisions — `_assign_channels` sorts by `TrackAnalysis.priority` (an int set
  in `_determine_role`), NOT by `get_role_priority()`. Flag if `get_role_priority` is dead /
  inconsistent with the live drop order.

### Dimension 5: Arpeggiation Correctness
`docs/arpeggio.md` documents the pattern semantics; `VoiceAllocator._allocate_pulse` /
`_order_arp_notes` implement them. Default `arp_speed=3` → "20Hz, classic NES" (the
`verbose` print computes `60 // arp_speed` = 20Hz).

Checklist:
- On-grid timing: arp index advances only when `self.frame_count % self.arp_speed == 0`.
  `frame_count` is a single global counter incremented once per `allocate_frame` — verify it
  is not reset between songs and that the modulo keeps note changes on the 60Hz frame grid
  (no float drift; this is integer, good — but confirm `arp_speed` can't be 0 → ZeroDivision).
- In-range cycling: `state.arp_index = (state.arp_index + 1) % len(state.arp_notes)` with the
  extra `if state.arp_index >= len(state.arp_notes): state.arp_index = 0` guard for changed
  chords. Confirm the index never indexes out of range when `arp_notes` shrinks.
- Pattern parity with `docs/arpeggio.md`: `_order_arp_notes` implements `UP`, `DOWN`,
  `UP_DOWN` but the doc also describes `down_up` and `random` patterns — `ArpStyle.RANDOM`
  exists in the enum but `_order_arp_notes` has no branch for it (falls through `else` →
  plain order) and `down_up` has no enum member at all. Flag doc-vs-code drift (LOW/MEDIUM).
- The default `arp_style` is `ArpStyle.UP` and `arrange_for_nes` never exposes it — confirm
  whether non-UP styles are reachable on the live path at all.
- Arpeggiation only triggers when `len(unique_pitches) > 1` on a pulse channel; a chord routed
  to triangle is collapsed to its lowest note (not arpeggiated). Confirm that matches intent.

### Dimension 6: GM Drum Routing (consistency with /audit-dpcm)
The arranger has two drum-routing tables that must agree with each other and with the DPCM
subsystem (`dpcm_sampler/`, `dpcm_index.json`).

Checklist:
- `GM_DRUM_MAP` (`arranger/gm_instruments.py`) routes kicks 35/36 and snare 38 to
  `NESChannel.DPCM`, but `VoiceAllocator._allocate_dpcm` / `_allocate_noise`
  (`arranger/voice_allocator.py`) **re-derive** the routing with hardcoded note lists
  (`[35, 36]` → sample 0, `[38, 40]` → sample 1, else 2) and ignore `get_drum_mapping`
  entirely. `get_drum_mapping`/`GM_DRUM_MAP` are imported into `pipeline_integration.py` /
  `role_analyzer.py` but the actual per-frame allocation does not consult them — flag the
  duplicate/divergent routing (note `40` is DPCM-fallback in the allocator but NOISE in
  `GM_DRUM_MAP`).
- The hardcoded DPCM sample indices `0/1/2` in `_allocate_dpcm` are magic — cross-ref
  `dpcm_index.json` and `/audit-dpcm`: do indices 0/1/2 correspond to kick/snare/generic, or
  is the mapping arbitrary? An index with no backing sample is a playback bug.
- `_allocate_noise` maps pitch→period as `(note.pitch - 36) // 6` clamped 0–15, which throws
  away the curated `noise_period` values in `GM_DRUM_MAP`. Confirm whether the GM-specified
  periods are intended and being lost.

### Dimension 7: NES Hardware-Limit Compliance (cross-ref /audit-nes-hardware)
Where the arranger's Python values become APU register intent. Triangle volume/duty and
out-of-range timers are **HIGH** per `_audit-severity.md`.

Checklist:
- Triangle: `FrameByFrameAllocator.process_song` emits triangle `volume = 15 if vel > 0 else 0`
  (no real volume), and `arrange_for_nes` writes triangle `control = 0x81` with **no duty
  bits** — good. Verify nothing downstream re-injects a duty/volume for triangle (triangle has
  no volume control / no duty — `docs/APU_TRIANGLE_REFERENCE.md`).
- Pitch/timer range: `midi_note_to_nes_pitch` (`arranger/pipeline_integration.py`) computes a
  period and clamps `max(0, min(2047, period))` for pulse/triangle (11-bit) — confirm the
  clamp is correct vs `docs/APU_PITCH_TABLE_REFERENCE.md`, that it doesn't silently emit a
  wildly-off note when clamped, and that this hand-rolled formula matches the canonical
  `nes/pitch_table.py` the legacy path uses (two pitch sources is a divergence risk).
- Volume scaling: pulse/noise `volume = vel // 8` (MIDI 0–127 → 0–15). Confirm the result is
  always within the 4-bit APU volume range and that `vel // 8` of 127 = 15 (it is); flag the
  ad-hoc curve vs `nes/envelope_processor.py` used by the legacy path.
- Noise period from `midi_note_to_nes_pitch` returns `midi_note` directly for the noise branch
  (unclamped), but the arranger uses `_allocate_noise`'s clamped period instead — confirm the
  unclamped noise branch is dead and not reachable.
- `control = (duty << 6) | 0x30 | volume` for pulse — verify the byte stays in 0–255 and the
  duty bits land in bits 6–7 per `docs/APU_PULSE_REFERENCE.md`.

### Dimension 8: Determinism of Allocation
The same MIDI must arrange to the same frames every run (reproducible ROMs, stable pattern
detection).

Checklist:
- `analyze_midi_events` iterates `midi_events.items()` (insertion order in py3.7+) and assigns
  `track_idx` by enumeration — confirm stable ordering from the parser.
- Role ties: `max(role_scores, key=role_scores.get)` returns the first max by dict iteration
  order — deterministic given the fixed dict literal, but confirm.
- `_assign_channels` sorts `plan.tracks` by `priority` only (`reverse=True`); equal-priority
  tracks keep their pre-sort order (Python `sort` is stable) — confirm the pre-sort order
  (analysis append order = `self.tracks` dict order) is itself deterministic.
- No RNG on the live path: `ArpStyle.RANDOM` is unimplemented (good — no `random` import to
  introduce non-determinism), but verify nothing else seeds randomness.
- Frame-grid: integer modulo only (no float frame math in the arranger) — confirm no
  accumulation that could drift off 60Hz (contrast tempo path in `/audit-tempo`).

## Skeptical Checklist (run before writing findings)
- Default run `python main.py --arranger song.mid out.nes` — trace `arp_speed=3` from `main.py`
  → `arrange_for_nes` → `allocate_with_arpeggiation` → `VoiceAllocator.arp_speed`.
- Is `program` ever non-zero on the live path? If not, every GM-instrument finding must say so.
- Does `arrange_for_nes` output a key the exporter never reads (`pitch`/`control` baked early)?
- Re-read each call path before reporting; attempt to disprove (per `_audit-common.md`
  Methodology). Run the dedup step (`gh issue list` + scan `docs/audits/`).

## Output
Write to: **`docs/audits/AUDIT_ARRANGER_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — severity counts, the highest-leverage arranger fixes, and an explicit
   contract-parity verdict (does `arrange_for_nes` output match the legacy frames the exporter
   expects: PASS/FAIL).
2. **Findings** — base format (`_audit-common.md`) + `Dimension`.

Then suggest:
```
/audit-publish docs/audits/AUDIT_ARRANGER_<TODAY>.md
```
