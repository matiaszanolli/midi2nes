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

> **Note on prior findings**: Successive sprints closed #84–#87 and #89–#90 (ARR-01…ARR-04,
> ARR-06…ARR-07 below), the arranger drum/regression findings #205–#207 and #230–#232, and
> three newer allocator bugs — #251 (per-note routing so a drum track keeps both NOISE and
> DPCM), #252 (per-chord arpeggio phase so the root plays on the attack), #253 (hi-hat
> `noise_period=0` vs the rest sentinel) and #268/NH-30 (soft-note `max(1, …)` volume floor).
> They also added arranger test coverage (`tests/test_arranger.py`,
> `tests/test_arranger_drum_detection.py`, `tests/test_arranger_frame_contract.py`,
> `tests/test_voice_allocator.py`) — the "zero test coverage" gap previously tracked as REG-04
> is resolved for the paths those tests cover. Treat the corresponding dimensions below as
> **verify-the-fix / find edge cases**, not as live bugs. Only #88 and #91 (ARR-05, ARR-08)
> remain open; #92 (ARR-09) was fixed — verify it still holds. Confirm against current line
> numbers before filing, since fixes
> upstream in the same files can drift them.

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
(`arranger/pipeline_integration.py`, noise/DPCM conversion ~line 262-286) now emits the
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
- `analyze_midi_events` (`arranger/pipeline_integration.py:123-126`) now derives
  `track_program` from `next((e['program'] for e in events if e.get('program') is not None), 0)`
  — the first note's active GM program — and calls `analyzer.set_track_program(track_idx,
  track_program)`, so `get_instrument_mapping(program)` (Dimension 4's GM table) is live again.
  Confirm this depends on `tracker/parser_fast.py` actually carrying a `program` key per event
  (from MIDI program-change messages) — if the parser ever emits events without `program` for
  a track that *did* have a program change (e.g. the change arrives after the first note-on,
  or on a different channel), this silently falls back to program 0. Worth a targeted check of
  `parser_fast.py`'s program-change handling.
- Drum-track detection (`analyze_midi_events:108-116`) now checks
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
- **#360 (ARR-2026-07-19-2) is CLOSED**: `analyze_midi_events`
  (`arranger/pipeline_integration.py:84-88`) dropped its unused `ticks_per_beat`/`tempo`/`fps`
  parameters — frame numbers arrive pre-computed from `parser_fast` and density uses a fixed
  `VoiceRoleAnalyzer.tempo_fps` (60.0), so no caller ever needed them. Verify-the-fix: confirm
  no call site still passes them (would now raise `TypeError`) and no reintroduced parameter
  goes unused again.

### Dimension 3: Voice Allocation, Priority & Overflow
Two allocation layers: `VoiceRoleAnalyzer._assign_channels` (track→channel, build time) and
`VoiceAllocator.allocate_frame` (note→register, per frame) in `arranger/voice_allocator.py`.
A musically-wrong dropped voice is **MEDIUM** per `_audit-severity.md`.

Checklist:
- `_assign_channels` (`arranger/role_analyzer.py:302-394`) assigns each NES channel to **at
  most one track** (boolean `*_assigned` flags). With >4 pitched tracks, surplus tracks land
  in `plan.dropped_tracks`. Verify the drop order is priority-sorted
  (`plan.tracks.sort(key=lambda t: t.priority, reverse=True)` at line 288) and musically
  defensible. Cross-ref Dimension 4's note on `get_role_priority()` being unused here
  (ARR-05, #88) — the sort key is `TrackAnalysis.priority`, not that function.
  **#409/ARR-2026-08-06-2 is CLOSED**: the priority-sort invariant above used to be violated
  by the last-resort triangle-overflow fallback specifically — it was gated on `track.role !=
  MusicalRole.MELODY` (any non-MELODY role, including HARMONY/DECORATIVE, could claim
  triangle as a last resort), not `track.role == MusicalRole.BASS`, contradicting the
  "triangle is reserved for bass" invariant `tests/test_role_analyzer.py` already documented.
  Because the exclusion was role-based rather than priority-based, a HIGHER-priority MELODY
  track processed earlier could be dropped for lack of a channel while a LOWER-priority
  HARMONY/DECORATIVE track processed later still grabbed the now-idle triangle — the exact
  "drop order isn't musically defensible" failure mode this checklist item warns about, just
  with MELODY/HARMONY rather than the BASS/DECORATIVE pairing the old wording used as its
  example. The non-BASS branch of that fallback is now removed entirely — only the
  BASS-and-triangle-still-free branch earlier in the same if/elif chain can claim triangle: a
  non-BASS track that can't fit on pulse1/pulse2 now falls straight through to
  `dropped_tracks`, same as any other overflow. Verify-the-fix: confirm a mixed-role scenario
  (multiple MELODY/HARMONY/DECORATIVE tracks, no BASS) always drops in strict priority order
  with triangle staying empty, and that a genuine BASS track still spills to triangle
  correctly when pulse1/pulse2 are full.
- Drum tracks claim BOTH `noise` and `dpcm` (`arranger/role_analyzer.py:310-327`).
  **#205/ARR-10 is CLOSED**: a second drum track finding both already taken used to hit an
  unconditional `continue`, vanishing with no `dropped_tracks` entry and no `plan.notes`
  diagnostic, unlike every other overflow case. It now only skips the "couldn't be assigned"
  bookkeeping when it actually claimed noise and/or dpcm here (`assigned` tracked per-track,
  `:303-319`) — a starved second drum track still gets the standard drop diagnostic. **#330/
  ARR-NEW-6 is CLOSED**: a drum track that claimed noise/dpcm also now shares PULSE2
  non-exclusively (`:321-333`, deliberately never sets `pulse2_assigned`, so it can't block a
  melodic track from also claiming PULSE2) so `GM_DRUM_MAP`'s PULSE2-mapped percussion
  (agogo/cuica/mute+open triangle) can actually reach PULSE2 via `_route_note`
  (`arranger/voice_allocator.py`, now checks the mapped channel before the NOISE catch-all)
  instead of always collapsing onto NOISE regardless of the mapping table. TRIANGLE-mapped
  percussion (toms/whistles) is deliberately left on NOISE — `_allocate_triangle` is
  monophonic with no collision handling, so granting drums the triangle channel risks
  silently dropping real bass notes; those hits get a distinct `noise_period` per instrument
  instead of the generic "Unknown Drum" fallback so they stay differentiated. Verify-the-fix:
  confirm a PULSE2-mapped drum hit and a melodic PULSE2 track can coexist via
  `_allocate_pulse`'s arpeggiation without one silently starving the other, and that
  TRIANGLE-mapped percussion still never reaches the triangle channel.
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
- **STILL OPEN — #88 (ARR-05)**: `get_role_priority()` (`arranger/gm_instruments.py:1303-1312`)
  is re-exported via `arranger/__init__.py` but has no call site anywhere in `arranger/` — the
  actual drop-order decision uses `TrackAnalysis.priority` (an int set per-instrument in
  `GM_INSTRUMENT_MAP`/`GM_DRUM_MAP` and adjusted in `_determine_role`,
  `arranger/role_analyzer.py:204-283`), not the BASS=1…SFX=6 ordering `get_role_priority`
  returns. Confirm it is genuinely dead (grep for callers) and, if so, flag it as dead/misleading
  code — a maintainer could reasonably assume it governs drop order and be wrong.

### Dimension 5: Arpeggiation Correctness
`docs/arpeggio.md` documents the pattern semantics; `VoiceAllocator._allocate_pulse` /
`_order_arp_notes` implement them. Default `arp_speed=3` → "20Hz, classic NES" (the
`verbose` print computes `60 // arp_speed` = 20Hz).

Checklist:
- On-grid timing: since #252, arp phase is measured **per chord**, not off the global
  `frame_count`. `_allocate_pulse` resets `state.arp_index`/`state.arp_frame` to 0 when the
  chord changes and otherwise advances the index only when `state.arp_frame % self.arp_speed
  == 0` (`arranger/voice_allocator.py:254`), where `state.arp_frame` counts frames since the
  current chord started (`:253`). `self.frame_count` still increments once per `allocate_frame`
  (`:174`) but no longer gates the arp step. Verify the per-chord counter keeps note changes on
  the 60Hz frame grid (no float drift; this is integer, good).
  `tests/test_arranger.py::test_arpeggio_step_is_frame_aligned_at_arp_speed` covers the normal
  case at `arp_speed=3`, but does not cover `arp_speed=0`.
- **STILL OPEN — #91 (ARR-08)**: `arp_speed` is never validated. `arp_speed=0` makes
  `state.arp_frame % self.arp_speed` raise `ZeroDivisionError` (`arranger/voice_allocator.py:254`).
  Post-#252 the crash is on the **second** frame a multi-pitch chord persists on a pulse channel
  (the `else` branch), not the first — the first frame of a chord resets index/frame and never
  hits the modulo. Nothing in
  `arrange_for_nes` / `allocate_with_arpeggiation` / `VoiceAllocator.__init__` guards against
  0 (or negative) values. Confirm still unguarded and unclamped; a `--arranger` CLI flag or
  config surface that lets a user pass `arp_speed=0` (or a future one) would crash the whole
  pipeline. HIGH-leaning given "fails on common input" once any caller exposes the parameter.
- In-range cycling: `state.arp_index = (state.arp_index + 1) % len(state.arp_notes)`
  (`:255`), and when the chord changes (`arp_notes != state.arp_notes`) the index is reset to 0
  outright (`:248-251`) rather than left to run off the end of a now-shorter list. Confirm the
  index never indexes out of range when `arp_notes` shrinks.
- **#92 (ARR-09) was fixed — verify it still holds**: Pattern parity with `docs/arpeggio.md`:
  `_order_arp_notes` (`arranger/voice_allocator.py:262`) no longer keeps a divergent partial
  copy — it now delegates to the canonical `tracker/track_mapper.py` `apply_arpeggio_pattern`,
  which implements all five patterns. `ArpStyle` gained a `DOWN_UP` member and its `UP_DOWN`
  value is now `"up_down"` (`:44-52`); `ArpStyle.RANDOM` is implemented deterministically via
  `_deterministic_arp_order` (seeded `random.Random(seed).sample`, `tracker/track_mapper.py`).
  Verify-the-fix: confirm `self.arp_style.value` still matches the pattern keys
  `apply_arpeggio_pattern` accepts (so no style silently falls through to plain up-order), and that
  the RANDOM seed keeps identical chords arpeggiating identically (determinism, Dimension 8).
- The default `arp_style` is `ArpStyle.UP` and `arrange_for_nes` never exposes it — confirm
  whether non-UP styles are reachable on the live path at all (they are not selected from
  `pipeline_integration.py`, so the live path only ever uses `UP`-order; the other four patterns
  are now implemented but exercised only by direct `VoiceAllocator`/`track_mapper` use and tests —
  note this reachability in severity reasoning).
- Arpeggiation only triggers when `len(unique_pitches) > 1` on a pulse channel; a chord routed
  to triangle is collapsed to its lowest note (not arpeggiated). Confirm that matches intent.

### Dimension 6: GM Drum Routing (consistency with /audit-dpcm)
The arranger has two drum-routing tables that must agree with each other and with the DPCM
subsystem (`dpcm_sampler/`, `dpcm_index.json`).

**#87 (ARR-04) is CLOSED** (commit `e1be17d`) — `_allocate_dpcm` and `_allocate_noise`
(`arranger/voice_allocator.py`) no longer hardcode note lists; both now consult
`get_drum_mapping` (i.e. `GM_DRUM_MAP`) directly. Verify-the-fix / edge-case checklist:
- `_allocate_dpcm` (`arranger/voice_allocator.py:330-356`) filters candidate notes to those
  where `get_drum_mapping(note.pitch).use_sample and mapping.channel == NESChannel.DPCM`, then
  picks the highest-`priority` match and maps its `mapping.name` through the local
  `DPCM_SAMPLE_SLOTS = {"Acoustic Bass Drum": 0, "Bass Drum 1": 0, "Acoustic Snare": 1}`
  (`:293-297`), defaulting to slot `2` for any other `use_sample` drum not in that dict.
  Currently `GM_DRUM_MAP` only flags `use_sample=True` for notes 35/36/38, so slot `2` is
  presently unreachable dead code — confirm that stays true if `GM_DRUM_MAP` grows more
  `use_sample` entries, and cross-ref `/audit-dpcm` + `dpcm_index.json` to confirm slots 0/1
  actually have backing samples (an index with no backing sample is a playback bug).
- `_allocate_noise` (`:299-328`) now reads `get_drum_mapping(note.pitch).noise_period`
  (curated per-instrument value from `GM_DRUM_MAP`, e.g. closed hi-hat period 0 vs cowbell
  period 8) instead of a linear pitch formula, falling back to `5` when a routed-to-noise drum
  has no curated `noise_period` (matching `get_drum_mapping`'s own "Unknown Drum" default).
  Confirm the fallback value stays in sync with `get_drum_mapping`'s default (`:1295-1299`) if
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
- **#89 (ARR-06) is CLOSED**: Pitch/timer range: `midi_note_to_nes_pitch`
  (`arranger/pipeline_integration.py:291-316`) no longer hand-rolls a `440.0 * 2**((note-69)/12)`
  formula. It clamps `midi_note` to 0–127 and delegates to the canonical `nes/pitch_table.py`
  tables (`NES_TRIANGLE_TABLE` for triangle, `NES_NOTE_TABLE` otherwise) — a single
  authoritative pitch source shared with the legacy (`NESEmulatorCore`) path and the exporter,
  including the floor-8 clamp the old float formula did not enforce. Verify-the-fix: confirm
  both tables are indexable across the full 0–127 range (no IndexError on extreme notes), that
  triangle vs pulse pick the right table, and that no other call site reintroduces float pitch
  math.
- **#90 (ARR-07) is CLOSED**: `midi_note_to_nes_pitch` no longer has an `else`/`'noise'` branch
  that returns a raw, unclamped `midi_note`. Non-triangle channels now return
  `NES_NOTE_TABLE[midi_note]` on the 0–127-clamped index (`:313-316`); noise is documented as
  never routing through this function — its period comes from `_allocate_noise`'s 0–15 clamp
  (Dimension 6). Verify-the-fix: confirm `arrange_for_nes`'s noise conversion (`:269-277`) still
  never calls `midi_note_to_nes_pitch`, so no path can feed a noise value into the pulse table.
- Volume scaling: pulse `volume = max(1, vel // 8)` and noise final `volume = max(1, min(15,
  vel // 8))` (MIDI 0–127 → 1–15). The `max(1, …)` floor was added in #268/NH-30 so a soft
  (`vel` 1–7) note is not silenced to volume 0 despite an active pitch write (triangle stays
  `15 if vel > 0 else 0`). Confirm the result is always within the 4-bit APU volume range and
  that `vel // 8` of 127 = 15 (it is); flag the ad-hoc curve vs `nes/envelope_processor.py`
  used by the legacy path.
- **#359 (ARR-2026-07-19-1) is CLOSED**: the per-frame loop above used to emit this same flat
  `vel // 8` volume for every frame a noise/percussion hit was active, so a drum note played as
  a sustained hiss burst instead of a crisp strike — unlike the legacy `NESEmulatorCore` path,
  which ramps each hit down over ~100ms (both front-ends force constant-volume+halt on `$400C`,
  so there is no hardware envelope to lean on). `FrameByFrameAllocator.process_song`
  (`arranger/voice_allocator.py:472`) now post-processes `frames["noise"]` through
  `_apply_noise_strike_decay` (`:477-511`), which finds each contiguous same-period run (one
  strike), ramps it down over `NOISE_DECAY_FRAMES` via the shared
  `nes/envelope_processor.noise_strike_decay_volume` helper — so both front-ends sound alike —
  and truncates it to that length. Verify-the-fix: confirm period/control are untouched (only
  volume is scaled, and only downward, so it can't leave the 4-bit range), that a gap, a
  period change, or a raw-volume change starts a fresh strike, and that
  `allocate_with_arpeggiation` (the live entry point) is what actually calls `process_song` —
  not a dead/parallel code path.
- **#391 (ARR-2026-08-05-1) is CLOSED**: the boundary check above originally only broke a
  strike on a frame gap or period change, so `_apply_sustain`'s zero-gap bridging routinely
  merged back-to-back same-period hits (e.g. fast repeated hi-hats) into one strike, discarding
  every hit after the first. `_apply_noise_strike_decay` now also breaks the strike whenever
  the raw (pre-decay) volume changes between contiguous frames — safe because each discrete
  note's frames carry one flat volume for its whole duration (`_allocate_noise` picks a single
  fixed `NoteInfo.velocity`), so a volume change mid-run can only be a different note taking
  over. Verify-the-fix: a genuinely sustained flat-volume run must still collapse to one
  strike (not fragment per-frame), while a same-period run with a volume change mid-run must
  yield one strike per distinct volume segment.
- `control = (duty << 6) | 0x30 | volume` for pulse — verify the byte stays in 0–255 and the
  duty bits land in bits 6–7 per `docs/APU_PULSE_REFERENCE.md`.

### Dimension 8: Determinism of Allocation
The same MIDI must arrange to the same frames every run (reproducible ROMs, stable pattern
detection).

Checklist:
- `analyze_midi_events` iterates `midi_events.items()` (insertion order in py3.7+) and assigns
  `track_idx` by enumeration — confirm stable ordering from the parser.
- Role ties: `max(role_scores, key=role_scores.get)` returns the first max by dict iteration
  order. **#ARR-2026-08-07-1 is CLOSED**: `role_scores` is now a
  `defaultdict(float, {...4 buckets...})` (`arranger/role_analyzer.py:223-228`) rather than a
  plain dict literal. It had to change because `GM_INSTRUMENT_MAP` curates 19/128 programs
  (Timpani, Orchestra Hit, Agogo, Woodblock, …) with `role=PERCUSSION` or `SFX` — neither of
  which is one of the four scoring buckets — so `role_scores[gm_mapping.role] += 3.0`
  (`:231`) raised `KeyError` for any non-drum-channel track using one of those programs.
  Verify-the-fix, on both axes: **(a) determinism** — insertion order still starts with the
  four seeded buckets, so a tie still resolves to the same bucket every run, and an
  out-of-bucket GM role only ever *appends* a key that scored the GM bonus alone (never
  enough to win against a real signal) — confirm that cannot now become the `max`;
  **(b) coverage** — a `defaultdict` converts what used to be a loud crash into a silent
  default, so any *new* out-of-bucket key reaching this dict will no longer announce itself.
  Spot-check the GM map's non-bucket roles against the scoring branches.
- `_assign_channels` sorts `plan.tracks` by `priority` only (`reverse=True`); equal-priority
  tracks keep their pre-sort order (Python `sort` is stable) — confirm the pre-sort order
  (analysis append order = `self.tracks` dict order) is itself deterministic.
- No live-path RNG divergence: `ArpStyle.RANDOM` is now implemented (#92), and
  `tracker/track_mapper.py`'s `import random` is used only via `_deterministic_arp_order`, which
  seeds `random.Random(seed)` from the note set so identical chords arpeggiate identically. The live
  `arrange_for_nes` path never selects `RANDOM` (default `ArpStyle.UP`), so no non-determinism
  reaches pattern detection — verify the seed derivation stays note-derived (not wall-clock/global
  `random`) and that nothing else seeds randomness.
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
  Methodology). Run the dedup step (`gh issue list` + scan `docs/audits/`) — #84-#87 and
  #89-#90 are CLOSED (as are #205-#207, #230-#232, #251-#253, #268, and now #92); only #88 and #91
  remain OPEN as of this writing; re-verify current state, don't trust this file.

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
