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

> **Note on prior findings**: A recent sprint closed #84–#87 (ARR-01…ARR-04 below) and added
> arranger test coverage (`tests/test_arranger.py`, `tests/test_arranger_drum_detection.py`,
> `tests/test_arranger_frame_contract.py`, `tests/test_voice_allocator.py`) — the "zero test
> coverage" gap previously tracked as REG-04 is resolved for the paths those tests cover.
> Treat the corresponding dimensions below as **verify-the-fix / find edge cases**, not as
> live bugs. #88–#92 (ARR-05…ARR-09) remain open — confirm against current line numbers
> before filing, since fixes upstream in the same files can drift them.

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

**#84 (ARR-01) is CLOSED** (commit `24dc0cb`) — `arrange_for_nes`
(`arranger/pipeline_integration.py`, noise/DPCM conversion ~line 261-283) now emits the
canonical keys the exporter actually reads instead of `period`/`sample`: noise frames carry
`note` (period, floored to 1 so it never collides with the bytecode rest sentinel), `control`
(mode bit), `volume` (floored to 1); DPCM frames carry `note` (`sample_id + 1`, clamped ≤95)
and `volume=15`. Verify-the-fix checklist:
- The non-arranger path emits `NESEmulatorCore.process_all_tracks` output (`nes/emulator_core.py`):
  `{channel_name: {frame_num: {note, volume, ...}}}`. Re-diff key-by-key against the `output`
  dict built in `arrange_for_nes` for all five channels (`pulse1`/`pulse2`/`triangle`/`noise`/
  `dpcm`) to confirm no other key drifted since the fix.
- The Step-4 pattern-detection loop in `main.py` reads `frame_data.get('note', 0)` and
  `frame_data.get('volume', 0)` from every channel — confirm noise/dpcm frames now round-trip
  through that loop with real (non-zero) values instead of silently zeroing.
- `--no-patterns` builds its stub stats from `sum(len(ch) for ch in frames.values())` — verify
  the arranger's five-channel dict is shaped so that sum is meaningful.
- `tests/test_arranger_frame_contract.py` covers the DPCM/noise key shape and cross-checks
  against the legacy contract — check it actually exercises the floor/clamp edge cases (period
  0 hit, sample index 95, volume 0 hit) rather than just a single happy-path frame.
- Confirm the exporter consumes `pitch`/`control` if present, or recomputes — i.e. whether the
  arranger pre-baking `pitch`/`control` (see Dimension 7) is even honored downstream or dead.

### Dimension 2: Role Detection Correctness
`arranger/role_analyzer.py` `VoiceRoleAnalyzer._determine_role` scores BASS/MELODY/HARMONY/
DECORATIVE from GM hint + pitch (`BASS_THRESHOLD=48`, `LOW_MID_THRESHOLD=60`,
`HIGH_THRESHOLD=72`), density (`SPARSE_DENSITY`/`DENSE_DENSITY`), velocity, and polyphony.

**#86 (ARR-03) and #85 (ARR-02) are CLOSED** (commits `e1be17d`, `556759a`). Verify-the-fix
checklist:
- `analyze_midi_events` (`arranger/pipeline_integration.py:104-125`) now derives
  `track_program` from `next((e['program'] for e in events if e.get('program') is not None), 0)`
  — the first note's active GM program — and calls `analyzer.set_track_program(track_idx,
  track_program)`, so `get_instrument_mapping(program)` (Dimension 4's GM table) is live again.
  Confirm this depends on `tracker/parser_fast.py` actually carrying a `program` key per event
  (from MIDI program-change messages) — if the parser ever emits events without `program` for
  a track that *did* have a program change (e.g. the change arrives after the first note-on,
  or on a different channel), this silently falls back to program 0. Worth a targeted check of
  `parser_fast.py`'s program-change handling.
- Drum-track detection (`analyze_midi_events:107-116`) now checks
  `event.get('channel')` for MIDI channel 9 (GM channel 10, 0-indexed) first, falling back to
  the track-name heuristic (`'drum' in name.lower()` or name `'9'`/`9`) only when no event
  carries channel info. `tests/test_arranger_drum_detection.py` covers channel-9 detection,
  non-drum channels, and the name-heuristic fallback — confirm it also covers the case where
  `channel` is present but not 9 AND the name heuristic would have matched (does channel info
  correctly override a misleading name, or vice versa?).
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
- `_assign_channels` (`arranger/role_analyzer.py:306-391`) assigns each NES channel to **at
  most one track** (boolean `*_assigned` flags). With >4 pitched tracks, surplus tracks land
  in `plan.dropped_tracks`. Verify the drop order is priority-sorted
  (`plan.tracks.sort(key=lambda t: t.priority, reverse=True)` at line 299) and musically
  defensible — e.g. that BASS is not dropped while a DECORATIVE voice survives. Cross-ref
  Dimension 4's note on `get_role_priority()` being unused here (ARR-05, #88) — the sort key
  is `TrackAnalysis.priority`, not that function.
- Drum tracks claim BOTH `noise` and `dpcm` (`arranger/role_analyzer.py:318-326`,
  `if track.is_drum_track: ... continue`) — so a second drum track, or a melodic voice that
  wanted noise/dpcm, is starved. Confirm intent.
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
- **STILL OPEN — #88 (ARR-05)**: `get_role_priority()` (`arranger/gm_instruments.py:1300-1309`)
  is re-exported via `arranger/__init__.py` but has no call site anywhere in `arranger/` — the
  actual drop-order decision uses `TrackAnalysis.priority` (an int set per-instrument in
  `GM_INSTRUMENT_MAP`/`GM_DRUM_MAP` and adjusted in `_determine_role`,
  `arranger/role_analyzer.py:215-287`), not the BASS=1…SFX=6 ordering `get_role_priority`
  returns. Confirm it is genuinely dead (grep for callers) and, if so, flag it as dead/misleading
  code — a maintainer could reasonably assume it governs drop order and be wrong.

### Dimension 5: Arpeggiation Correctness
`docs/arpeggio.md` documents the pattern semantics; `VoiceAllocator._allocate_pulse` /
`_order_arp_notes` implement them. Default `arp_speed=3` → "20Hz, classic NES" (the
`verbose` print computes `60 // arp_speed` = 20Hz).

Checklist:
- On-grid timing: arp index advances only when `self.frame_count % self.arp_speed == 0`
  (`arranger/voice_allocator.py:201`). `frame_count` is a single global counter incremented
  once per `allocate_frame` (`:161`) — verify it is not reset between songs and that the
  modulo keeps note changes on the 60Hz frame grid (no float drift; this is integer, good).
  `tests/test_arranger.py::test_arpeggio_step_is_frame_aligned_at_arp_speed` covers the normal
  case at `arp_speed=3`, but does not cover `arp_speed=0`.
- **STILL OPEN — #91 (ARR-08)**: `arp_speed` is never validated. `arp_speed=0` makes
  `self.frame_count % self.arp_speed` raise `ZeroDivisionError` on the very first frame with
  >1 unique pitch on a pulse channel (`arranger/voice_allocator.py:201`). Nothing in
  `arrange_for_nes` / `allocate_with_arpeggiation` / `VoiceAllocator.__init__` guards against
  0 (or negative) values. Confirm still unguarded and unclamped; a `--arranger` CLI flag or
  config surface that lets a user pass `arp_speed=0` (or a future one) would crash the whole
  pipeline. HIGH-leaning given "fails on common input" once any caller exposes the parameter.
- In-range cycling: `state.arp_index = (state.arp_index + 1) % len(state.arp_notes)` with the
  extra `if state.arp_index >= len(state.arp_notes): state.arp_index = 0` guard for changed
  chords. Confirm the index never indexes out of range when `arp_notes` shrinks.
- **STILL OPEN — #92 (ARR-09)**: Pattern parity with `docs/arpeggio.md`: `_order_arp_notes`
  (`arranger/voice_allocator.py:213-225`) implements `UP`, `DOWN`, `UP_DOWN` but the doc also
  describes `down_up` and `random` patterns — `ArpStyle.RANDOM` exists in the enum
  (`:48`) but `_order_arp_notes` has no branch for it (falls through `else` → plain
  up-order) and `down_up` has no enum member at all. Flag doc-vs-code drift (LOW/MEDIUM);
  either implement the two patterns or trim the doc to match shipped behavior.
- The default `arp_style` is `ArpStyle.UP` and `arrange_for_nes` never exposes it — confirm
  whether non-UP styles are reachable on the live path at all (they are not called from
  `pipeline_integration.py`, so ARR-09's dead `RANDOM` branch is currently unreachable in
  practice, not just unimplemented — note this in severity reasoning).
- Arpeggiation only triggers when `len(unique_pitches) > 1` on a pulse channel; a chord routed
  to triangle is collapsed to its lowest note (not arpeggiated). Confirm that matches intent.

### Dimension 6: GM Drum Routing (consistency with /audit-dpcm)
The arranger has two drum-routing tables that must agree with each other and with the DPCM
subsystem (`dpcm_sampler/`, `dpcm_index.json`).

**#87 (ARR-04) is CLOSED** (commit `e1be17d`) — `_allocate_dpcm` and `_allocate_noise`
(`arranger/voice_allocator.py`) no longer hardcode note lists; both now consult
`get_drum_mapping` (i.e. `GM_DRUM_MAP`) directly. Verify-the-fix / edge-case checklist:
- `_allocate_dpcm` (`arranger/voice_allocator.py:280-306`) filters candidate notes to those
  where `get_drum_mapping(note.pitch).use_sample and mapping.channel == NESChannel.DPCM`, then
  picks the highest-`priority` match and maps its `mapping.name` through the local
  `DPCM_SAMPLE_SLOTS = {"Acoustic Bass Drum": 0, "Bass Drum 1": 0, "Acoustic Snare": 1}`
  (`:247-251`), defaulting to slot `2` for any other `use_sample` drum not in that dict.
  Currently `GM_DRUM_MAP` only flags `use_sample=True` for notes 35/36/38, so slot `2` is
  presently unreachable dead code — confirm that stays true if `GM_DRUM_MAP` grows more
  `use_sample` entries, and cross-ref `/audit-dpcm` + `dpcm_index.json` to confirm slots 0/1
  actually have backing samples (an index with no backing sample is a playback bug).
- `_allocate_noise` (`:253-278`) now reads `get_drum_mapping(note.pitch).noise_period`
  (curated per-instrument value from `GM_DRUM_MAP`, e.g. closed hi-hat period 0 vs cowbell
  period 8) instead of a linear pitch formula, falling back to `5` when a routed-to-noise drum
  has no curated `noise_period` (matching `get_drum_mapping`'s own "Unknown Drum" default).
  Confirm the fallback value stays in sync with `get_drum_mapping`'s default (`:1291-1297`) if
  either changes independently — they are two separate literals (`5`) that must agree.
- `tests/test_voice_allocator.py` covers electric-snare-not-DPCM, kick→slot 0, acoustic
  snare→slot 1, kick-outranks-snare, no-eligible-notes, curated period usage, and the
  0–15 clamp — check it also asserts the slot-2 fallback path and the noise-period
  "no curated value" fallback (`5`) explicitly, since both are edge cases not exercised by a
  standard drum kit.

### Dimension 7: NES Hardware-Limit Compliance (cross-ref /audit-nes-hardware)
Where the arranger's Python values become APU register intent. Triangle volume/duty and
out-of-range timers are **HIGH** per `_audit-severity.md`.

Checklist:
- Triangle: `FrameByFrameAllocator.process_song` emits triangle `volume = 15 if vel > 0 else 0`
  (no real volume), and `arrange_for_nes` writes triangle `control = 0x81` with **no duty
  bits** — good. Verify nothing downstream re-injects a duty/volume for triangle (triangle has
  no volume control / no duty — `docs/APU_TRIANGLE_REFERENCE.md`).
- **STILL OPEN — #89 (ARR-06)**: Pitch/timer range: `midi_note_to_nes_pitch`
  (`arranger/pipeline_integration.py:288-320`) computes a period from `440.0 * 2**((note-69)/12)`
  and clamps `max(0, min(2047, period))` for pulse/triangle (11-bit). This is a second,
  hand-rolled pitch source that diverges from the canonical `nes/pitch_table.py` the legacy
  (`assign_tracks_to_nes_channels` / `NESEmulatorCore`) path uses — confirm the two produce the
  same timer value for the same note (they use different formulas/rounding: floating-point
  frequency math here vs. a lookup table there) and that the clamp doesn't silently emit a
  wildly-off note when hit. Two independently-maintained pitch sources is a standing divergence
  risk even if today's outputs happen to match.
- **STILL OPEN — #90 (ARR-07)**: The `else` branch of `midi_note_to_nes_pitch`
  (`:315-317`, reached when `channel` is not `'pulse1'`/`'pulse2'`/`'triangle'`, i.e. `'noise'`)
  returns `midi_note` directly — unclamped, and not actually an APU noise period. Confirm this
  branch is genuinely dead: `arrange_for_nes`'s noise conversion (`:266-274`) never calls
  `midi_note_to_nes_pitch`; it uses `_allocate_noise`'s already-clamped `period` value from
  Dimension 6. If dead, this is LOW (misleading dead code); if any caller is ever added that
  passes `channel='noise'`, it becomes a HIGH out-of-range-timer bug with no warning.
- Volume scaling: pulse/noise `volume = vel // 8` (MIDI 0–127 → 0–15). Confirm the result is
  always within the 4-bit APU volume range and that `vel // 8` of 127 = 15 (it is); flag the
  ad-hoc curve vs `nes/envelope_processor.py` used by the legacy path.
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
  introduce non-determinism), but verify nothing else seeds randomness. (See ARR-09, #92 —
  if `RANDOM` is ever implemented, it must seed deterministically or pattern detection breaks.)
- Frame-grid: integer modulo only (no float frame math in the arranger) — confirm no
  accumulation that could drift off 60Hz (contrast tempo path in `/audit-tempo`).

## Skeptical Checklist (run before writing findings)
- Default run `python main.py --arranger song.mid out.nes` — trace `arp_speed=3` from `main.py`
  → `arrange_for_nes` → `allocate_with_arpeggiation` → `VoiceAllocator.arp_speed`.
- `program` is no longer hardcoded (#86 fixed) — instead verify it is *correctly* non-zero on
  realistic MIDI: does `tracker/parser_fast.py` attach `program` to every event, and does a
  program change that arrives mid-track (not before the first note) get picked up (see
  Dimension 2)? If the parser's program-change handling has its own gap, that's a new finding,
  not a reopening of #86.
- `arrange_for_nes` no longer bakes an unread key into noise/DPCM frames (#84 fixed) — spot
  check by diffing the arranger's frame keys against what `CA65Exporter` actually reads for
  each of the 5 channels, per Dimension 1.
- Re-read each call path before reporting; attempt to disprove (per `_audit-common.md`
  Methodology). Run the dedup step (`gh issue list` + scan `docs/audits/`) — #84-#87 are
  CLOSED, #88-#92 are OPEN as of this writing; re-verify current state, don't trust this file.

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
