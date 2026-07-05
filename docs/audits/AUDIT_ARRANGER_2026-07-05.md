# Arranger Audit — 2026-07-05

**Scope:** The `--arranger` front-end (`arranger/` subsystem): role detection
(`role_analyzer.py`), GM-instrument mapping (`gm_instruments.py`), priority-based voice
allocation + arpeggiation (`voice_allocator.py`), and the `arrange_for_nes` integration
(`pipeline_integration.py`). All 8 dimensions of `audit-arranger/SKILL.md`.

**Entry path traced:** `main.py:689` (`arp_speed=3` hardcoded) → `arrange_for_nes`
(`arranger/pipeline_integration.py:197`) → `analyze_midi_events` →
`allocate_with_arpeggiation` → `FrameByFrameAllocator.process_song` →
`VoiceAllocator.set_arrangement` / `allocate_frame`. Downstream: `frames` → Step-4 pattern
detection (`main.py:712`) → `CA65Exporter.export_tables_with_patterns`.

**Note on this run:** re-audit after 2026-07-03. Since that report, several prior findings
were fixed (see "Verified fixed"). `midi_note_to_nes_pitch` was rewritten to delegate to the
canonical `nes/pitch_table.py` tables (closing #89/ARR-06 and #90/ARR-07, which are no longer
in the open-issue list). The 2026-07-03 NEW findings were filed and fixed (#205/ARR-10 drum
drop bookkeeping, #206/ARR-11 channel-authoritative drum detection, and the dead
`analysis.notes` write). Three genuinely new findings surfaced this run, including a
**CRITICAL silent-data-loss bug in drum routing** that all prior arranger audits missed.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 1 |
| **Total** | **3 new** (+ 3 pre-existing open: #88, #91, #92, unchanged) |

**Contract-parity verdict: PASS.** `arrange_for_nes` emits all five channels
(`pulse1`/`pulse2`/`triangle`/`noise`/`dpcm`) with the canonical key set the exporter reads
(verified at runtime: pulse frames carry `note`/`pitch`/`volume`/`control`; triangle carries
`control=0x81` with no `duty`; noise carries `note`/`control`/`volume`; DPCM carries
`note`/`volume`). The structural handoff to Step-4 is intact. The CRITICAL finding below is
*not* a contract-shape break — the frames dict is well-formed; the problem is that an entire
class of drum notes never makes it *into* that dict.

**Highest-leverage new fixes:**
1. **ARR-NEW-1 (CRITICAL)** — every `--arranger` run with a drum track silently drops **all**
   noise-routed percussion (closed/open/pedal hi-hats, cymbals, toms-on-noise, electric
   snare). `VoiceAllocator.track_assignments` is a `Dict[int, NESChannel]` — one channel per
   track — but a drum track is placed in *both* `plan.noise_tracks` and `plan.dpcm_tracks`, and
   `set_arrangement` writes NOISE then overwrites it with DPCM under the same track-id key. The
   noise channel receives nothing; only kick/snare DPCM samples survive. Reproduced.
2. **ARR-NEW-2 (MEDIUM)** — arpeggios never start on the chord root: the arp index is advanced
   *before* the first read (frame 0 satisfies `frame_count % arp_speed == 0`), so a chord
   `[60,64,67]` plays `64,64,64,67,67,67,60,…` — the root trails every cycle. Reproduced.
3. **ARR-NEW-3 (LOW)** — the closed hi-hat's curated `noise_period = 0` is floored to `1` by
   the rest-sentinel floor in the noise conversion; its intended top-frequency timbre shifts.
   Currently masked by ARR-NEW-1 (noise never emits at all); becomes live once ARR-NEW-1 is
   fixed.

## Verified fixed (re-confirmed against current code)

- **#84 (ARR-01) / #85–#86 (ARR-02/03) / #87 (ARR-04) — CLOSED, still fixed.** Frame-key
  contract, channel-9 + GM-program detection, and `GM_DRUM_MAP`-driven noise/DPCM routing all
  confirmed present. GM_INSTRUMENT_MAP verified to cover all 0–127 (no fallback gap). No
  TRIANGLE/NOISE/DPCM `InstrumentMapping` carries a `duty` (checked programmatically).
- **#89 (ARR-06) / #90 (ARR-07) — CLOSED, confirmed fixed.** `midi_note_to_nes_pitch`
  (`pipeline_integration.py:296-321`) now clamps the note to 0–127 and indexes
  `NES_TRIANGLE_TABLE`/`NES_NOTE_TABLE` (both length 128, verified), eliminating both the
  hand-rolled float formula (#89) and the unclamped `else`-returns-`midi_note` noise branch
  (#90). Neither issue is in the current open-issue list.
- **#205 (ARR-10) — CLOSED, confirmed fixed.** `_assign_channels` (`role_analyzer.py:316-324`)
  no longer has the unconditional `continue`; a second drum track that finds noise+dpcm both
  taken now falls through to the `dropped_tracks`/`plan.notes` bookkeeping.
- **#206 (ARR-11) — CLOSED, confirmed fixed.** `analyze_midi_events`
  (`pipeline_integration.py:115-122`) makes channel info authoritative: `is_drum_track =
  track_channel == 9` when any event carries a channel; the name heuristic is only the fallback.
- **`_analyze_drum_track` dead `analysis.notes` write — fixed.** `role_analyzer.py:178-186`
  now returns cleanly with no ad-hoc attribute write.

## Verified still-open (re-confirmed at current line numbers, not re-filed)

- **#88 (ARR-05)** — `get_role_priority()` (`gm_instruments.py:1300`) still has no live caller
  (`grep` shows only the `arranger/__init__.py` re-export). Dead / inconsistent with the actual
  `TrackAnalysis.priority` sort key at `role_analyzer.py:292`.
- **#91 (ARR-08)** — `arp_speed` still unvalidated; `arrange_for_nes(events, arp_speed=0)`
  reproduced a `ZeroDivisionError` at `voice_allocator.py:201`. CLI hardcodes `arp_speed=3`
  (`main.py:691`), so unreachable from the CLI but live on the public API.
- **#92 (ARR-09)** — `ArpStyle.RANDOM` (`voice_allocator.py:48`) still has no `_order_arp_notes`
  branch; `down_up` still has no enum member; `docs/arpeggio.md:25,48,50,56` still documents
  both. Unreachable in practice (`arrange_for_nes` never exposes `arp_style`).

## Findings

### ARR-NEW-1: Drum tracks lose all noise percussion — DPCM assignment overwrites NOISE in `set_arrangement`
- **Severity**: CRITICAL
- **Dimension**: 3 (Voice Allocation, Priority & Overflow)
- **Location**: `arranger/voice_allocator.py:89-101` (`set_arrangement`), enabled by
  `arranger/role_analyzer.py:316-324` (drum track added to both channel lists)
- **Status**: NEW
- **Description**: `_assign_channels` puts a drum track into **both** `plan.noise_tracks` and
  `plan.dpcm_tracks` (it claims noise, and dpcm if free). `set_arrangement` then maps tracks to
  channels through a single `Dict[int, NESChannel]` keyed by `track_id`, assigning NOISE first
  and DPCM second — so the DPCM write **overwrites** the NOISE write for that same track id.
  The result is `track_assignments == {drum_track: DPCM}`. In `allocate_frame`, that track's
  notes are therefore collected only under `NESChannel.DPCM`; `_allocate_noise` always receives
  an empty list and returns `None`, so the noise channel emits **zero** frames. Every drum whose
  `GM_DRUM_MAP` routing is NOISE (all hi-hats, cymbals, toms mapped to noise, electric snare,
  etc.) is silently discarded. Only the kick/snare that `_allocate_dpcm` accepts
  (`use_sample and channel == DPCM`, i.e. notes 35/36/38) survive.
- **Evidence**: Reproduced with a 6-hit drum kit (kick 36, closed-hat 42, snare 38, open-hat
  46, elec-snare 40, pedal-hat 44) via `arrange_for_nes`:
  ```
  noise frames: 0    dpcm frames: 8
  track_assignments: {0: 'dpcm'}      # NOISE overwritten by DPCM
  noise_tracks [0]   dpcm_tracks [0]  # same track in both lists
  ```
  The four noise drums (42/46/40/44) produced no output on any channel. Overwrite site
  (`voice_allocator.py:98-101`):
  ```python
  for track_id in plan.noise_tracks:
      self.track_assignments[track_id] = NESChannel.NOISE   # written
  for track_id in plan.dpcm_tracks:
      self.track_assignments[track_id] = NESChannel.DPCM    # overwrites same key
  ```
  `tests/test_voice_allocator.py` misses this because every test calls `_allocate_noise` /
  `_allocate_dpcm` **directly** with hand-built note lists and never routes through
  `set_arrangement`, so the overwrite is never exercised end-to-end.
- **Impact**: On the live `python main.py --arranger song.mid out.nes` path, any song with a
  drum track — i.e. essentially every drum-bearing MIDI — loses its entire noise percussion
  layer (hi-hats drive the groove) with no warning, no `plan.notes` entry, and no `verbose`
  diagnostic. Only kick/snare DPCM hits remain. This is the CRITICAL "a MIDI event class dropped
  on the floor with no warning, changing the song" case in `_audit-severity.md`. The ROM still
  boots (so not a hardware-crash CRITICAL), but a whole percussion class silently vanishes on
  realistic input.
- **Related**: #205/ARR-10 (drop-bookkeeping for a *second* drum track — a different symptom of
  the same "drum claims two channels" design); ARR-NEW-3 (period-0 floor, masked by this bug);
  cross-ref `/audit-dpcm` for whether the surviving DPCM slots 0/1 have backing samples.
- **Suggested Fix**: A drum track needs to occupy noise *and* DPCM simultaneously.
  `track_assignments` cannot be a 1:1 `Dict[int, NESChannel]`. Either (a) give drum tracks a
  dedicated routing that dispatches their notes to *both* `_allocate_noise` and `_allocate_dpcm`
  (per-note by `get_drum_mapping(pitch).channel`), or (b) key channel assignment by a
  `(track_id, channel)` pair / `Dict[int, List[NESChannel]]` so the DPCM entry does not clobber
  NOISE. Add an end-to-end `set_arrangement`→`allocate_frame` test with a mixed noise+DPCM kit.

### ARR-NEW-2: Arpeggio never starts on the chord root — index advanced before first read (off-by-one)
- **Severity**: MEDIUM
- **Dimension**: 5 (Arpeggiation Correctness)
- **Location**: `arranger/voice_allocator.py:200-208`
- **Status**: NEW
- **Description**: In `_allocate_pulse`, the arp index is advanced *before* the current note is
  read: `if self.frame_count % self.arp_speed == 0: state.arp_index = (state.arp_index + 1) %
  len(...)`, then `current_note = state.arp_notes[state.arp_index]`. `frame_count` starts at 0
  and is incremented at the **end** of `allocate_frame` (`:161`), so on the very first frame of
  an arpeggiated chord `0 % arp_speed == 0` is true and `arp_index` steps from 0 to 1 before the
  first read. The chord's root (index 0, the lowest sorted pitch) is therefore never the first
  note played and only appears after a full cycle wraps.
- **Evidence**: Reproduced — chord `[60,64,67]` at `arp_speed=3`:
  ```
  ARP first 7 notes on pulse1: [64, 64, 64, 67, 67, 67, 60]
  ```
  The root (60) first sounds at frame 6, not frame 0; the arp runs 2nd→3rd→1st every cycle.
  `tests/test_arranger.py::test_chord_becomes_alternating_single_notes` asserts only that the
  *set* of tones over the window is `{60,64,67}` and
  `test_arpeggio_step_is_frame_aligned_at_arp_speed` checks only the step *cadence*, so neither
  catches the wrong starting phase.
- **Impact**: Every polyphonic chord routed to a pulse channel plays its arpeggio phase-shifted
  by one step, de-emphasizing the root on the attack. All pitches still cycle at the correct
  20Hz rate, so it is a musical-correctness defect, not data loss — MEDIUM (wrong output on
  common input, no user workaround, but subtle and cyclic).
- **Related**: #91/ARR-08 (same `frame_count % arp_speed` expression), `docs/arpeggio.md`.
- **Suggested Fix**: Read the current note before advancing, or gate the advance on
  `self.frame_count > 0` (so the root plays for the first step), or initialize `arp_index = -1`.
  Add a test asserting the first emitted arp note equals the lowest chord tone.

### ARR-NEW-3: Closed hi-hat's curated `noise_period = 0` is floored to 1 by the rest-sentinel floor
- **Severity**: LOW
- **Dimension**: 6 (GM Drum Routing) / 7 (Hardware-Limit Compliance)
- **Location**: `arranger/pipeline_integration.py:274-282` (noise conversion) vs.
  `arranger/gm_instruments.py` (`GM_DRUM_MAP` closed hi-hat `noise_period = 0`)
- **Status**: NEW
- **Description**: `GM_DRUM_MAP[42]` (Closed Hi-Hat) curates `noise_period = 0` (top noise
  frequency); the code comment in `_allocate_noise` explicitly calls out "closed hi-hat (period
  0)". But the noise-frame conversion floors the period to 1 —
  `period = max(1, data['period'] & 0x0F)` — because period 0 is the bytecode rest sentinel.
  So the one drum that *wants* period 0 can never emit it; its timbre shifts to period 1.
- **Evidence**: `get_drum_mapping(42).noise_period == 0` (verified); conversion at
  `pipeline_integration.py:275` is `max(1, data['period'] & 0x0F)`. Currently unobservable
  because ARR-NEW-1 drops the noise channel entirely; it becomes live once ARR-NEW-1 is fixed.
- **Impact**: A single drum's timbre is subtly wrong (period 1 instead of 0). LOW — cosmetic
  timbral shift on one instrument, and it is an inherent tension with the rest sentinel, not a
  crash or dropped note. Worth documenting so a maintainer does not "fix" the curated 0 and
  reintroduce a rest-collision.
- **Related**: ARR-NEW-1 (masks this today); #84 (the rest-sentinel floor rationale).
- **Suggested Fix**: Decide explicitly how period-0 drums should render (accept the period-1
  shift and note it in `GM_DRUM_MAP`, or remap sentinel handling so period 0 is representable).
  At minimum, align the `GM_DRUM_MAP` comment with the floored reality.

---

*Generated by `/audit-arranger`. Deduplicated against `/tmp/audit/issues.json`
(matiaszanolli/midi2nes open issues, 36 entries) and `docs/audits/` prior reports
(`AUDIT_ARRANGER_2026-06-29.md`, `AUDIT_ARRANGER_2026-07-03.md`). #88/#91/#92 are OPEN and
re-confirmed unchanged (not re-filed); #84–#87, #89, #90, #205, #206 are CLOSED and re-verified
fixed. ARR-NEW-1/2/3 are new and have no matching open issue.*

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-07-05.md
```
