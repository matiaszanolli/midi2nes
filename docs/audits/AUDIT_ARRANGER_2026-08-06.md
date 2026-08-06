# Arranger Audit — 2026-08-06

Audit of the `--arranger` front-end (`arranger/`): role analysis, GM mapping, priority-based
voice allocation, and arpeggiation. Entry path traced: `main.py` `run_full_pipeline` →
`arrange_for_nes(events, arp_speed=3, verbose=args.verbose)` → `analyze_midi_events` →
`allocate_with_arpeggiation` → `VoiceAllocator` / `FrameByFrameAllocator`.

This is a re-verification pass on top of `docs/audits/AUDIT_ARRANGER_2026-08-05.md`. Since
that report, two more commits touched `arranger/`:

- `06e1e04` — routes PULSE2-mapped drum percussion correctly, drops dead `enhanced_track_mapper`
  export, closes 3 DPCM alias gaps (#330, #331, #340, #341)
- `90b4582` — splits Type-0/multi-channel MIDI tracks by channel before role analysis (#329,
  plus unrelated exporter/DPCM fixes #302/#311/#342)

Both commits are confirmed present in the current tree. All previously-open arranger findings
(#329, #330, #331, #340, and the earlier #84–#92, #205–#207, #230–#232, #251–#253, #268, #359,
#360, #391) are now **CLOSED** and re-verified fixed below. This pass also found **3 new
findings** in code paths those fixes did not touch: `VoiceRoleAnalyzer._determine_role`'s
channel override and `_assign_channels`'s last-resort triangle fallback.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 2 |
| LOW      | 1 |
| **Total (new)** | **3** |

- **NEW**: 3 (2 MEDIUM, 1 LOW)
- **Re-verified fixed / CLOSED** (not re-filed): #84–#92, #205–#207, #230–#232, #251–#253, #268,
  #329, #330, #331, #340, #341, #359, #360, #391.
- **Cross-referenced, owned by another domain** (not re-filed here): #340/DP-DPCM-01 (DPCM
  sample coverage), #369/EXP-2026-07-19-1 (macro-bytecode DPCM note byte range).

### Contract-parity verdict: **PASS**

`arrange_for_nes`'s five-channel `output` dict (`arranger/pipeline_integration.py:295-346`) was
re-diffed key-by-key against what `exporter/exporter_ca65.py` actually reads (both the direct
frame-table path, `exporter_ca65.py:243-274`, and the macro-bytecode pattern path,
`exporter_ca65.py:1170-1269`) and against the legacy `NESEmulatorCore.process_all_tracks`
contract. No drift: `note`/`pitch`/`volume`/`control` on pulse/triangle, `note`(period)/
`control`(mode bit)/`volume` on noise, `note`(sample+1, ≤255)/`volume`(15) on DPCM.

Also newly confirmed (Dimension 1's open question from the skill): the arranger's pre-baked
`pitch` value on pulse/triangle frames **is** consumed downstream, not dead — the macro-bytecode
exporter reads it directly (`pitch_val = frame_data.get('pitch', base_timer)`,
`exporter_ca65.py:1244`/`1263`) and encodes the delta from its own re-derived `base_timer` as a
pitch-macro offset, rather than recomputing pitch from scratch. So the arranger and the direct
frame-table exporter path agree on the authoritative pitch value.

### Highest-leverage new findings

1. **ARR-2026-08-06-1** (MEDIUM): 16 of 128 `GM_INSTRUMENT_MAP` entries have a curated `channel`
   (e.g. Ocarina/Whistle/Blown Bottle → TRIANGLE for a breathy timbre, several organs/pianos/pads
   → their own ANY_PULSE/PULSE1 choice) that `VoiceRoleAnalyzer._determine_role` unconditionally
   discards and replaces with a 4-bucket role→channel table, so that per-instrument curation
   never has any effect on the live path.
2. **ARR-2026-08-06-2** (MEDIUM): `_assign_channels`'s last-resort triangle fallback excludes
   only `MusicalRole.MELODY`, not "everything except BASS" as the sibling unit test's docstring
   claims ("triangle is reserved for bass") — so a lower-priority HARMONY/DECORATIVE track
   processed later in the priority-sorted list can claim triangle while a same-or-higher-priority
   MELODY track earlier in the list was already dropped for lack of a fallback, inverting the
   documented "sort by priority, highest first" drop order.

---

## Findings

### ARR-2026-08-06-1: GM_INSTRUMENT_MAP's curated `channel` is discarded by role-based override for 16/128 instruments
- **Severity**: MEDIUM
- **Dimension**: 2 (Role Detection Correctness) / 4 (GM Instrument Mapping Coverage)
- **Location**: `arranger/role_analyzer.py:204-276` (`_determine_role`), data in `arranger/gm_instruments.py` (`GM_INSTRUMENT_MAP`)
- **Status**: NEW
- **Description**: `_determine_role` seeds `analysis.preferred_channel = gm_mapping.channel`
  (`role_analyzer.py:210`) from the curated per-instrument GM table, but every non-drum track
  unconditionally falls through role scoring to one of exactly 4 roles (BASS/MELODY/HARMONY/
  DECORATIVE — the only keys `role_scores` initializes), and the `if/elif` chain at
  `:264-276` **always** re-overwrites `preferred_channel` based solely on that role:
  BASS→TRIANGLE, MELODY→PULSE1, HARMONY→PULSE2, DECORATIVE→PULSE2. The GM-curated `channel`
  value is read once at line 210 and never consulted again — it has no effect on final channel
  assignment for any track that reaches `_determine_role` (all non-drum tracks). `duty_cycle`,
  `play_style`, and `priority` are preserved/adjusted from the GM base, but `channel` is not.
- **Evidence**: Direct check against the live table —
  ```python
  from arranger.gm_instruments import GM_INSTRUMENT_MAP, MusicalRole, NESChannel
  role_to_channel = {MusicalRole.BASS: NESChannel.TRIANGLE, MusicalRole.MELODY: NESChannel.PULSE1,
                      MusicalRole.HARMONY: NESChannel.PULSE2, MusicalRole.DECORATIVE: NESChannel.PULSE2}
  mismatches = [(p, m.name, m.role, m.channel) for p, m in GM_INSTRUMENT_MAP.items()
                if role_to_channel.get(m.role) not in (None, m.channel)]
  # -> 16 of 128 entries, including:
  # (76, 'Blown Bottle', DECORATIVE, TRIANGLE)   -> actually routed to PULSE2
  # (78, 'Whistle',      DECORATIVE, TRIANGLE)   -> actually routed to PULSE2
  # (79, 'Ocarina',      MELODY,     TRIANGLE)   -> actually routed to PULSE1
  # (99, 'FX 4 (atmosphere)', DECORATIVE, NOISE) -> actually routed to PULSE2
  # (4, 'Electric Piano 1', HARMONY, ANY_PULSE)  -> actually routed to PULSE2 (harmless here)
  ```
  Ocarina/Whistle/Blown Bottle were specifically curated for TRIANGLE (a pure, breathy timbre
  well suited to those instruments) but never reach it; "FX 4 (atmosphere)" was curated for
  NOISE (a textural/atmospheric use of the noise channel) but always plays as a plain pulse tone
  instead.
- **Impact**: Any MIDI using one of these 16 GM programs gets a plausible-but-wrong channel
  assignment instead of the one the table's author specifically chose — an audible timbre
  mismatch, not a crash or data loss. `duty_cycle` still carries some of the original intent
  (e.g. Ocarina probably keeps a thinner duty even on PULSE1), softening but not eliminating the
  effect. Workaround: none from the user's side (MIDI program numbers aren't user-adjustable
  post-hoc); the fix is code-side.
- **Related**: Distinct from the drum-side version of this same class of bug (#330/ARR-NEW-6,
  now fixed, where `_route_note` ignored `GM_DRUM_MAP`'s mapped channel for percussion) — this
  finding is the melodic/`GM_INSTRUMENT_MAP` analogue, in a different function
  (`_determine_role` vs `_route_note`), and remains open.
- **Suggested Fix**: Either drop the `channel` field from `GM_INSTRUMENT_MAP` entries whose role
  already implies the outcome (to stop implying it's honored), or change `_determine_role` to
  only override `preferred_channel` when musical analysis meaningfully disagrees with the GM
  hint (e.g. keep `gm_mapping.channel` when `role_scores[gm_mapping.role]` already dominates),
  so a curated TRIANGLE/NOISE choice for a specific instrument survives when the role analysis
  doesn't contradict it.

### ARR-2026-08-06-2: Last-resort triangle fallback lets a lower-priority HARMONY/DECORATIVE track survive while a same-or-higher-priority MELODY track is dropped
- **Severity**: MEDIUM
- **Dimension**: 3 (Voice Allocation, Priority & Overflow)
- **Location**: `arranger/role_analyzer.py:380-397` (`_assign_channels` overflow block), specifically the `track.role != MusicalRole.MELODY` guard at `:394`
- **Status**: NEW
- **Description**: `create_arrangement_plan` sorts `plan.tracks` by `priority` descending
  before assignment (`:287-289`, comment: "the single live drop key"), so higher-priority
  tracks are supposed to get first claim on channels and any drop should fall to the
  lowest-priority contender. But the last-resort triangle slot (reached only after PULSE1 and
  PULSE2 are both full) is gated on `track.role != MusicalRole.MELODY` — not on priority, and
  not restricted to `MusicalRole.BASS` alone despite `tests/test_role_analyzer.py::test_third_melody_track_is_dropped_with_note`'s
  own docstring asserting "triangle is reserved for bass." In practice HARMONY and DECORATIVE
  roles are equally eligible for that fallback. Because the exclusion is role-based rather than
  priority-based, a MELODY track processed **earlier** (due to a numerically higher priority)
  can still be dropped when the two pulse channels fill up, while a HARMONY/DECORATIVE track
  processed **later** (lower priority) is still allowed to claim the now-idle triangle — the
  opposite of "highest priority survives."
- **Evidence**: Reproduced against the live pipeline (4 tracks: 3 MELODY at priority 8, no bass,
  1 chord-triggering HARMONY at priority 6):
  ```python
  from arranger.pipeline_integration import analyze_midi_events
  events = {
      'lead1': [{'frame':0,'note':76,'volume':110,'channel':0,'program':80},
                {'frame':60,'note':76,'volume':0,'channel':0,'program':80}],
      'lead2': [{'frame':0,'note':79,'volume':110,'channel':1,'program':80},
                {'frame':60,'note':79,'volume':0,'channel':1,'program':80}],
      'lead3': [{'frame':0,'note':81,'volume':110,'channel':2,'program':80},
                {'frame':60,'note':81,'volume':0,'channel':2,'program':80}],
      'pad':   [{'frame':0,'note':55,'volume':60,'channel':3,'program':4},
                {'frame':0,'note':58,'volume':60,'channel':3,'program':4},
                {'frame':0,'note':62,'volume':60,'channel':3,'program':4},
                {'frame':600,'note':55,'volume':0,'channel':3,'program':4},
                {'frame':600,'note':58,'volume':0,'channel':3,'program':4},
                {'frame':600,'note':62,'volume':0,'channel':3,'program':4}],
  }
  plan, _, _ = analyze_midi_events(events)
  # plan.tracks priorities: lead1=8, lead2=8, lead3=8 (MELODY); pad=6 (HARMONY)
  # pulse1: [0] (lead1)   pulse2: [1] (lead2)
  # triangle: [3] (pad, priority 6)   dropped: [2] (lead3, priority 8)
  ```
  `lead3` (priority 8) is dropped while `pad` (priority 6) keeps playing on triangle.
- **Impact**: On any MIDI with 3+ purely-melodic/harmonic voices and no distinct bass line — a
  common real-world case (three-part vocal/instrumental harmony with no separate bass part, or a
  synth-pad-heavy arrangement) — the arranger can silently drop a musically more important voice
  in favor of a less important one, contradicting its own stated priority-based drop policy.
  Playable but musically wrong; no crash or data corruption.
- **Related**: Distinct from `tests/test_role_analyzer.py::test_third_melody_track_is_dropped_with_note`
  and `test_bass_track_spills_to_triangle_when_pulses_full`, which each cover one side of this
  (MELODY correctly denied triangle; BASS correctly granted it) but never a mixed-role scenario
  where a *lower-priority, non-BASS* role claims the triangle ahead of a higher-priority MELODY
  track that was already dropped.
- **Suggested Fix**: Either (a) tighten line 394's condition to `track.role == MusicalRole.BASS`
  only, matching the test's documented intent, or (b) if HARMONY/DECORATIVE-on-triangle is
  intentional, make the fallback priority-aware — e.g. only let a later, lower-priority track
  claim triangle if no earlier, higher-priority track was dropped for lack of it — and update
  the test docstring to describe the real (broader) rule.

### ARR-2026-08-06-3: `_assign_channels`'s BASS/triangle overflow recheck is unreachable from the live analysis pipeline
- **Severity**: LOW
- **Dimension**: 3 (Voice Allocation, Priority & Overflow) / 4 (dead code, cf. #88)
- **Location**: `arranger/role_analyzer.py:382` (`if track.role == MusicalRole.BASS and not triangle_assigned:`)
- **Status**: NEW
- **Description**: This line is only reached (via the shared `if not assigned:` block at
  `:380-381`) after every earlier per-preferred-channel branch failed to assign the track. For a
  track whose `preferred_channel == NESChannel.TRIANGLE` (the TRIANGLE branch at `:342-346`),
  that only happens when `triangle_assigned` is already `True` — which makes the `:382` recheck
  of `not triangle_assigned` trivially `False` for any such track. Since
  `_determine_role` (`role_analyzer.py:264-266`) is the only place that ever sets
  `preferred_channel = NESChannel.TRIANGLE`, and it does so exactly when `role == MusicalRole.BASS`,
  every BASS track produced by the live `analyze_midi_events → create_arrangement_plan` pipeline
  has `preferred_channel == TRIANGLE` — so it can never reach line 382 with `triangle_assigned`
  still `False`. The branch is exercised today only via `tests/test_role_analyzer.py`'s
  hand-constructed `TrackAnalysis(preferred_channel=NESChannel.PULSE1, role=MusicalRole.BASS, ...)`
  (`test_bass_track_spills_to_triangle_when_pulses_full`), a role/preferred_channel combination
  `_determine_role` itself never produces. The same reasoning makes the `NESChannel.ANY_PULSE`/
  `NESChannel.FLEXIBLE` branch (`:370-378`) unreachable from the live pipeline too, since
  `_determine_role`'s role override always resolves to TRIANGLE/PULSE1/PULSE2 for the 4 roles it
  can produce.
- **Evidence**: `role_analyzer.py:264-276` is an exhaustive `if/elif` over the only 4 keys
  `role_scores` initializes (BASS, MELODY, HARMONY, DECORATIVE), and each branch sets
  `preferred_channel` to TRIANGLE/PULSE1/PULSE2/PULSE2 respectively — no path leaves it as
  ANY_PULSE, FLEXIBLE, or any other GM-curated value (see ARR-2026-08-06-1).
- **Impact**: Maintenance/confusion only — a reader could reasonably believe a real BASS track
  can hit this recheck and reasonably believe ANY_PULSE/FLEXIBLE tracks flow through the live
  system, when in fact both only exist for the sake of direct `_assign_channels` unit tests. No
  behavioral bug; existing tests pass because they call `_assign_channels` directly with
  synthetic inputs bypassing `_determine_role`.
- **Related**: Same spirit as the removed `get_role_priority()` (#88/ARR-05) — logic that looks
  load-bearing but has no live-path caller/producer.
- **Suggested Fix**: Either simplify `_assign_channels`'s overflow block to drop the
  now-redundant BASS/ANY_PULSE/FLEXIBLE special-casing (since `_determine_role` never produces
  those inputs), or, if `_assign_channels` is meant to remain independently robust to
  hand-built `TrackAnalysis` objects (as its own test suite exercises), add a one-line comment
  noting that these branches only matter for non-`_determine_role`-derived input.

---

## Verify-the-Fix Results (all confirmed holding)

- **#84 (ARR-01)** — noise/DPCM canonical frame keys: holds (`pipeline_integration.py:322-346`).
- **#85/#86 (ARR-02/03)** — channel-9 drum detection + `Counter.most_common` GM program:
  holds (`pipeline_integration.py:158-186`); `parser_fast.py:120-154` correctly tracks a
  per-channel `program` that updates on `program_change` and is read at note time, so a program
  change arriving after the first note-on is picked up correctly — no new gap found here.
- **#87 (ARR-04)** — drum routing via `GM_DRUM_MAP` in `_allocate_noise`/`_allocate_dpcm`:
  holds (`voice_allocator.py:323-380`).
- **#88 (ARR-05)** — `get_role_priority()`: confirmed removed; only a tombstone comment remains
  (`gm_instruments.py:1317-1321`). No callers.
- **#89/#90 (ARR-06/07)** — pitch via `nes/pitch_table.py`; noise never calls
  `midi_note_to_nes_pitch`: holds (`pipeline_integration.py:351-376`).
- **#91 (ARR-08)** — `arp_speed` clamp: confirmed fixed via a property setter
  (`voice_allocator.py:98-109`, `max(1, int(value))`), covering both `__init__` and
  `allocate_with_arpeggiation`'s reassignment. Well covered by
  `tests/test_voice_allocator.py::test_zero_arp_speed_is_clamped` and
  `test_zero_arp_speed_does_not_crash_arrangement`.
- **#92 (ARR-09)** — `_order_arp_notes` delegates to `tracker.track_mapper.apply_arpeggio_pattern`
  (`voice_allocator.py:285-295`); `ArpStyle` values match the accepted pattern keys; live path
  only ever uses `UP` (`arrange_for_nes` never sets `arp_style`). Holds.
- **#205 (ARR-10)** — second drum track drop bookkeeping: holds
  (`role_analyzer.py:304-338`, gated on `assigned`).
- **#251/#252/#253/#268** — per-note drum routing, per-chord arp phase, hi-hat sentinel,
  soft-note volume floor: all present and unchanged in effect.
- **#329 (ARR-NEW-5)** — Type-0/multi-channel MIDI split by channel before role analysis:
  confirmed fixed via `_split_events_by_channel` (`pipeline_integration.py:84-109`), called from
  `analyze_midi_events` (`:141-186`) so channel-9 drums and each pitched channel get independent
  drum-flag/GM-program analysis instead of one track-wide value skewed across channels.
  (Note: `#404/ARR-NEW-5-LEGACY` remains open for the *legacy* `track_mapper` front-end, which
  is out of scope for this arranger-mode audit.)
- **#330 (ARR-NEW-6)** — PULSE2-mapped drum percussion (agogo/cuica/mute+open triangle) reaches
  PULSE2 instead of collapsing to NOISE: confirmed fixed
  (`role_analyzer.py:321-338` shares PULSE2 non-exclusively; `voice_allocator.py:210-228`
  `_route_note` checks the mapped channel before the NOISE catch-all). TRIANGLE-mapped toms/
  whistles remain deliberately on NOISE with distinct curated `noise_period`s
  (`gm_instruments.py:1219-1232`, `:1267-1270`).
- **#331 (ARR-NEW-7)** — dead `enhanced_track_mapper` export: confirmed removed.
- **#340 (DP-DPCM-01)** — cross-domain, owned by `/audit-dpcm`; `DPCM_SAMPLE_SLOTS`'s slot-2
  fallback (`voice_allocator.py:317-321`) remains presently unreachable since `GM_DRUM_MAP` only
  flags notes 35/36/38 `use_sample=True` — unchanged, not re-filed here.
- **#359/#391 (ARR-2026-07-19-1 / ARR-2026-08-05-1)** — noise strike decay: confirmed fixed and
  the zero-gap re-attack regression from `#391` is now handled — `_apply_noise_strike_decay`
  (`voice_allocator.py:485-532`) breaks a strike on a raw-volume change as well as a frame gap
  or period change (`:519-523`), so back-to-back same-period/different-volume hits (e.g. fast
  hi-hats) each get their own decay instead of merging into one. A genuinely sustained
  flat-volume run still collapses to a single strike as intended.
- **#360 (ARR-2026-07-19-2)** — dead `ticks_per_beat`/`tempo`/`fps` params: confirmed removed;
  `analyze_midi_events(midi_events, sustain=True, sustain_gap=12)` (`pipeline_integration.py:112-116`).
- GM coverage: `GM_INSTRUMENT_MAP` covers all 128 programs 0-127 (verified programmatically, no
  gap hits the fallback). No TRIANGLE/NOISE/DPCM instrument or drum mapping carries a `duty`.
  `DutyCycle.DUTY_75` (documented as audibly identical to `DUTY_25` on hardware) has zero live
  users in either map. All clean.
- Noise-period fallback consistency: `_allocate_noise`'s fallback literal `5`
  (`voice_allocator.py:346-349`) still matches `get_drum_mapping`'s own "Unknown Drum" default
  (`gm_instruments.py:1308-1314`).
- Determinism (Dimension 8): parser dict insertion order → `analyze_midi_events` enumeration →
  stable `sort(key=priority, reverse=True)` → `max(role_scores, key=...)` first-by-dict-order.
  `ArpStyle.RANDOM` is note-seeded (`tracker/track_mapper.py:99-111`,
  `random.Random(seed).sample`) and unreachable on the live path (`arrange_for_nes` never sets
  `arp_style`). No wall-clock/global RNG found anywhere in `arranger/`.
- Hardware compliance (Dimension 7): triangle `control=0x81` with no duty bits; volume gate only
  (`15 if vel > 0 else 0`) — nothing downstream re-injects duty/volume for triangle. Pulse
  `control = (duty << 6) | 0x30 | volume` stays within a byte (max `0xF0 | 0x0F` = `0xFF`) with
  duty correctly in bits 6-7. Noise/DPCM byte ranges all clamp correctly at the arranger boundary
  (period `max(1, ... & 0x0F)`, volume `max(1, min(15, ...))`, DPCM note `min(255, ...)`).

---

## Notes (observations below the reporting bar)

- `#404/ARR-NEW-5-LEGACY` (the same Type-0/multi-channel splitting issue, but in the *legacy*
  `track_mapper` front-end rather than `--arranger`) is open and out of scope here — flagged for
  awareness since it's easy to conflate with the now-fixed `#329`.
- The DPCM `note = min(255, sample + 1)` value the arranger emits (`pipeline_integration.py:344`)
  intentionally matches the legacy `NESEmulatorCore` ceiling (`#196/EXP-08`), not the `$00-$5F`
  engine range `#369/EXP-2026-07-19-1` says the macro-bytecode path should enforce — that clamp
  gap is on the exporter side (shared by both front-ends) and is already tracked there; not
  re-filed as an arranger finding.
- No evidence of float frame-timing drift in the arranger: all frame-grid math (`arp_frame`,
  `frame_count`) is integer.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-08-06.md
```
