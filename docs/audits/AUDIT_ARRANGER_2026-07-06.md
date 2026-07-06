# Arranger Audit — 2026-07-06

**Scope:** The `--arranger` front-end (`arranger/` subsystem): role detection
(`role_analyzer.py`), GM-instrument mapping (`gm_instruments.py`), priority-based voice
allocation + arpeggiation (`voice_allocator.py`), and the `arrange_for_nes` integration
(`pipeline_integration.py`). All 8 dimensions of `audit-arranger/SKILL.md`.

**Entry path traced:** `main.py:786` (`arp_speed=3` hardcoded) → `arrange_for_nes`
(`arranger/pipeline_integration.py:190`) → `analyze_midi_events` (incl. `_apply_sustain`) →
`allocate_with_arpeggiation` → `FrameByFrameAllocator.process_song` →
`VoiceAllocator.set_arrangement` / `allocate_frame`. Downstream: `frames` → Step-4 pattern
detection (`main.py`) → `CA65Exporter.export_tables_with_patterns`.

**Note on this run:** re-audit after 2026-07-05. Since that report, all three findings it
raised were fixed: the CRITICAL drum-routing overwrite (ARR-NEW-1 → #251, commit `60ca688`),
the arp-root off-by-one (ARR-NEW-2 → #252, commit `b9b2cea`), and the period-0 noise floor
(ARR-NEW-3 → #253, documented). Both fixes were re-verified at runtime this run (drum kit now
emits noise frames; arpeggio now starts on the chord root). One genuinely new data-loss bug
surfaced this run in `_apply_sustain`, which no prior arranger audit exercised.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 0 |
| **Total** | **1 new** (+ 3 pre-existing open: #88, #91, #92, re-confirmed unchanged) |

**Contract-parity verdict: PASS.** `arrange_for_nes` emits all five channels
(`pulse1`/`pulse2`/`triangle`/`noise`/`dpcm`) with the canonical key set the exporter reads
(pulse: `note`/`pitch`/`volume`/`control`; triangle: `control=0x81` with no `duty`; noise:
`note`/`control`/`volume`; DPCM: `note`/`volume`). Re-diffed key-by-key against the legacy
`process_all_tracks` contract and confirmed at runtime. GM_INSTRUMENT_MAP covers all programs
0–127 with no coverage gap, and no TRIANGLE/NOISE/DPCM `InstrumentMapping` carries a `duty`
(both checked programmatically). The structural handoff to Step-4 is intact.

**Highest-leverage fix:**
1. **ARR-NEW-4 (MEDIUM)** — `_apply_sustain` (applied unconditionally on the live path) treats a
   fast *sequential monophonic* run as a series of staggered chords, extends each note to overlap
   the next, and the arpeggiator then drops the second note of every short false dyad. A melody
   whose notes are ≤2 frames apart loses roughly half its notes silently. Reproduced.

## Verified fixed (re-confirmed against current code + at runtime)

- **ARR-NEW-1 / #251 (drum routing) — FIXED.** `VoiceAllocator.track_assignments` is now
  `Dict[int, List[NESChannel]]` (`voice_allocator.py:91`); `set_arrangement` appends rather than
  overwrites (`:105-108`) and `_route_note` (`:175-202`) dispatches a drum track's notes to NOISE
  or DPCM per pitch. Runtime repro of a 6-hit kit now yields **14 noise frames + 8 DPCM frames**
  (was 0 noise). The CRITICAL from 2026-07-05 is resolved.
- **ARR-NEW-2 / #252 (arp root) — FIXED.** `_allocate_pulse` (`voice_allocator.py:239-254`) now
  measures arp phase with a per-chord counter `state.arp_frame`, resetting `arp_index=0` on chord
  change and advancing only on `arp_frame % arp_speed == 0`. Runtime repro of chord `[60,64,67]`
  now plays `[60,60,60,64,64,64,67]` — root first.
- **ARR-NEW-3 / #253 (period-0 floor) — accepted + documented.** The `max(1, period & 0x0F)`
  floor and its rest-sentinel rationale are now documented at
  `pipeline_integration.py:262-268` and `voice_allocator.py:319-321`.
- **#84–#90, #205–#207, #268 — CLOSED, still fixed.** Frame-key contract, channel-9 + GM-program
  detection, GM_DRUM_MAP-driven noise/DPCM routing, canonical pitch-table delegation, second-drum
  drop bookkeeping, and the `max(1, vel//8)` pulse volume floor all confirmed present.

## Verified still-open (re-confirmed at current line numbers, not re-filed)

- **#88 (ARR-05)** — `get_role_priority()` (`gm_instruments.py:1303`) still has no live caller;
  `grep` shows only the `arranger/__init__.py:36,82` re-export. Dead / inconsistent with the
  actual `TrackAnalysis.priority` sort key at `role_analyzer.py:288`.
- **#91 (ARR-08)** — `arp_speed` still unvalidated; `arrange_for_nes(events, arp_speed=0)`
  reproduced a `ZeroDivisionError: integer modulo by zero` at `voice_allocator.py:251`. CLI
  hardcodes `arp_speed=3` (`main.py:788`), so unreachable from the CLI but live on the public API.
- **#92 (ARR-09)** — `ArpStyle.RANDOM` (`voice_allocator.py:49`) still has no `_order_arp_notes`
  branch (falls through `else` → plain up-order); `down_up` still has no enum member;
  `docs/arpeggio.md` still documents both. Unreachable in practice (`arrange_for_nes` never
  exposes `arp_style`, default `UP`).

## Findings

### ARR-NEW-4: `_apply_sustain` merges fast sequential notes into false chords and the arpeggiator drops half of them
- **Severity**: MEDIUM
- **Dimension**: 5 (Arpeggiation Correctness)
- **Location**: `arranger/pipeline_integration.py:15-69` (`_apply_sustain`), reached
  unconditionally via `analyze_midi_events` (`:174-175`, `sustain=True` default) →
  `arrange_for_nes` (`:210`); the drop then happens in `_allocate_pulse`
  (`arranger/voice_allocator.py:236-254`).
- **Status**: NEW
- **Description**: `_apply_sustain` groups notes whose start frames fall within
  `chord_tolerance = 2` frames of the group's first note (`:35`) and extends **every** note in
  that group to the group's `max_end` (`:47-67`). This is intended to repair genuinely staggered
  chords, but it cannot distinguish a staggered chord from a fast *sequential monophonic* run: if
  a melody's notes are ≤2 frames apart, each adjacent pair is treated as a 2-note "chord". The
  earlier note is stretched so it now **overlaps** the later note, manufacturing polyphony where
  the source is monophonic. `_allocate_pulse` then arpeggiates the false dyad; because the
  overlap window is only ~2 frames while the arp holds each step for `arp_speed=3` frames, the
  arp never advances past the root, and the second note of every pair is **never emitted on any
  channel**. The notes are silently lost — no `plan.notes` entry, no `verbose` diagnostic.
- **Evidence**: Reproduced. Input melody `[60,62,64,65,67,69,71,72]`, each note 2 frames long,
  played strictly sequentially (note *i* at frame *i*·2), single track, channel 0:
  ```
  spacing=2  sustain=ON  (default): pulse1 set = [60, 64, 67, 71]   # 62,65,69,72 DROPPED
  spacing=2  sustain=OFF          : pulse1 set = [60,62,64,65,67,69,71,72]  # all present
  spacing=3+ sustain=ON           : all 8 notes present
  ```
  Per-frame trace of the 4-note case `[60,62,64,65]` after sustain shows the manufactured
  overlap:
  ```
  after sustain: pitch=60 start=0 end=4   # was end=2; stretched to overlap 62
                 pitch=62 start=2 end=4
                 pitch=64 start=4 end=8   # was end=6; stretched to overlap 65
                 pitch=65 start=6 end=8
  pulse1 per frame: f0=60 f1=60 f2=60 f3=60  f4=64 f5=64 f6=64 f7=64   # 62 and 65 never sound
  ```
  `sustain` is not exposed by `arrange_for_nes` or the CLI, so the user has no way to turn it off.
  No arranger test exercises `_apply_sustain` (`grep` of `tests/test_arranger*.py`,
  `tests/test_voice*.py` is empty), and no prior audit report mentions it.
- **Impact**: On the live `python main.py --arranger song.mid out.nes` path, any pulse-routed
  melodic passage with notes ≤2 frames (≈33 ms) apart — fast runs, trills, grace/ornament notes,
  32nd-notes at high tempo — silently loses about every other note. The ROM still boots and plays,
  and most moderate-tempo material is unaffected (the trigger is narrow: >2-frame spacing is
  clean), so this is MEDIUM rather than HIGH — but it is genuine, unwarned MIDI-note data loss
  with no user workaround, and escalates in severity for fast-passage-heavy material.
- **Related**: #92/ARR-09 (arpeggiation semantics), #252 (arp phasing — this is a distinct root
  cause upstream in `_apply_sustain`, not an arp-index bug). Contrast the legacy front-end, which
  does not run `_apply_sustain`.
- **Suggested Fix**: Only bridge/extend notes that are actually simultaneous (true chords), not
  ones that merely start within 2 frames of each other — e.g. require the earlier note's original
  `end_frame` to be at/after the next note's `start_frame` before extending, so a sequential run
  (each note ending exactly as the next begins) is left untouched. Alternatively expose `sustain`
  as an `arrange_for_nes`/CLI parameter so it can be disabled. Add a test asserting a fast
  sequential monophonic run round-trips every note.

---

*Generated by `/audit-arranger`. Deduplicated against `/tmp/audit/issues.json`
(matiaszanolli/midi2nes open issues, 29 entries) and `docs/audits/` prior reports
(`AUDIT_ARRANGER_2026-06-29/07-03/07-05.md`). #88/#91/#92 are OPEN and re-confirmed unchanged
(not re-filed); #84–#90, #205–#207, #251–#253, #268 are CLOSED and re-verified fixed. ARR-NEW-4
is new and has no matching open issue.*

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-07-06.md
```
