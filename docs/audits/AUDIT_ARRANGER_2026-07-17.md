# Arranger Audit — 2026-07-17

**Scope:** The `--arranger` front-end (`arranger/` subsystem): role detection
(`role_analyzer.py`), GM-instrument mapping (`gm_instruments.py`), priority-based voice
allocation + arpeggiation (`voice_allocator.py`), and the `arrange_for_nes` integration
(`pipeline_integration.py`). All 8 dimensions of `audit-arranger/SKILL.md`.

**Entry path traced:** `main.py` `run_full_pipeline` (`arp_speed=3` hardcoded at the call
site) → `arrange_for_nes` (`arranger/pipeline_integration.py:201`) → `analyze_midi_events`
(incl. `_apply_sustain`) → `allocate_with_arpeggiation` →
`FrameByFrameAllocator.process_song` → `VoiceAllocator.set_arrangement` / `allocate_frame`.
Downstream: `frames` → Step-4 pattern detection (`main.py`) →
`CA65Exporter.export_tables_with_patterns`.

**Note on this run:** re-audit after 2026-07-06. Since that report, the two remaining
correctness bugs the arranger tracked were fixed and re-verified at runtime this run:
**#92/ARR-09** (arp patterns unified + deterministic RANDOM) and **ARR-NEW-4** (the
`_apply_sustain` false-chord data-loss bug, closed via #295/#296). What remains are the two
long-standing open items (#88 dead code, #91 unvalidated `arp_speed`) and one new low-severity
role-accuracy gap surfaced this run.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 1 |
| **Total** | **1 new** (+ 2 pre-existing open: #88, #91, re-confirmed unchanged) |

**Contract-parity verdict: PASS.** `arrange_for_nes` emits all five channels
(`pulse1`/`pulse2`/`triangle`/`noise`/`dpcm`) with the canonical key set the exporter reads:
pulse `note`/`pitch`/`volume`/`control`; triangle `note`/`pitch`/`volume`/`control=0x81` with
no `duty`; noise `note`(4-bit period, floored to 1)/`control`(mode bit 6)/`volume`; DPCM
`note`(=sample_id+1)/`volume`. Re-diffed key-by-key against the legacy `process_all_tracks`
contract and against the exporter's actual `frame_data.get(...)` reads
(`exporter/exporter_ca65.py:334-360`, `:394-424`) — the pre-baked `pitch` IS honored (not dead)
in both the direct-frames and MMC3-bytecode paths. Verified at runtime: a 3-track song
(lead/bass/drums) populates `pulse1`, `triangle`, `noise`, and `dpcm` correctly and is bit-for-bit
deterministic across two runs. `GM_INSTRUMENT_MAP` covers all programs 0–127 with no gap, and no
`TRIANGLE`/`NOISE`/`DPCM` `InstrumentMapping` carries a `duty` (both checked programmatically).

**Highest-leverage item:** none of the new findings are correctness bugs. The most impactful
still-open item is **#91 (ARR-08)** — `arp_speed=0` raises `ZeroDivisionError` (reproduced this
run); it is unreachable from the CLI (hardcoded `arp_speed=3`) but live on the public
`arrange_for_nes` API. Left as-is per dedup protocol (already tracked).

## Verified fixed (re-confirmed against current code + at runtime)

- **#92 (ARR-09) — FIXED, verified.** `_order_arp_notes` (`arranger/voice_allocator.py:262-272`)
  now delegates to the canonical `tracker/track_mapper.py:apply_arpeggio_pattern` (`:114-140`).
  All five `ArpStyle` values map to a real pattern key with no silent fall-through to up-order:
  runtime check on `[60,64,67]` yields `UP=[60,64,67]`, `DOWN=[67,64,60]`,
  `UP_DOWN=[60,64,67,64]`, `DOWN_UP=[67,64,60,64,67]`, `RANDOM=[67,60,64]`. `RANDOM` is
  deterministic via `_deterministic_arp_order` (seed derived from note values, `random.Random`,
  `tracker/track_mapper.py:99-111`) — the same chord arpeggiates identically across runs. The
  live path still only ever selects the default `ArpStyle.UP` (`arrange_for_nes` does not expose
  `arp_style`), so the other four patterns are reachable only via direct `VoiceAllocator` use / tests.
- **ARR-NEW-4 (`_apply_sustain` false chords) — FIXED, verified.** The merge condition now
  requires real temporal overlap (`overlaps_chord = any(note.start_frame < member.end_frame ...)`,
  `arranger/pipeline_integration.py:44-46`, #295/#296), so a fast sequential monophonic run is no
  longer manufactured into false polyphony. Runtime repro of the exact prior failing case
  (8 notes, 2-frame spacing, monophonic) now emits **all 8 notes** on pulse1 (was 4 dropped).
- **#251/#252/#253 — still fixed.** Per-note drum routing (`track_assignments: Dict[int,
  List[NESChannel]]`, `_route_note` `:178-205`), per-chord arp phase (`state.arp_frame`,
  `:248-255`), and the period-0/volume rest-sentinel floors (`:281-282`) all confirmed present.
- **#84–#90, #205–#207, #268 — still fixed.** Frame-key contract, channel-9 + GM-program
  detection, `GM_DRUM_MAP`-driven noise/DPCM routing, canonical pitch-table delegation
  (`midi_note_to_nes_pitch` `:302-327`, tables indexable across 0–127, floor-8 clamp), second-drum
  drop bookkeeping (`role_analyzer.py:312-320`), and the `max(1, vel//8)` pulse volume floor all
  confirmed. `parser_fast.py:122-152` attaches `channel` and channel-scoped `program` to every note.

## Verified still-open (re-confirmed at current line numbers, NOT re-filed)

- **#88 (ARR-05)** — `get_role_priority()` (`arranger/gm_instruments.py:1303-1312`) still has no
  live caller. `grep` shows only the `arranger/__init__.py:36,82` re-export; the actual drop order
  uses `TrackAnalysis.priority` (`role_analyzer.py:288` sort key), not the BASS=1…SFX=6 ordering
  this function returns. Dead and misleading. Severity LOW.
- **#91 (ARR-08)** — `arp_speed` still unvalidated. `arrange_for_nes(events, arp_speed=0)`
  reproduced `ZeroDivisionError: integer modulo by zero` at `arranger/voice_allocator.py:254`
  (second frame a multi-pitch chord persists on a pulse channel). No guard in `arrange_for_nes` /
  `allocate_with_arpeggiation` / `VoiceAllocator.__init__`. Unreachable from the CLI (hardcoded
  `arp_speed=3`), live on the public API. HIGH-leaning per the SKILL once any caller exposes the
  parameter; tracked, left as-is.

## Findings

### ARR-NEW-5: Track GM-program hint ignores program changes that arrive after the first note
- **Severity**: LOW
- **Dimension**: 2 (Role Detection Correctness)
- **Location**: `arranger/pipeline_integration.py:134-137` (`track_program = next((e['program']
  for e in events if e.get('program') is not None), 0)`), consumed by
  `VoiceRoleAnalyzer._determine_role` → `get_instrument_mapping(analysis.program)`
  (`arranger/role_analyzer.py:207`).
- **Status**: NEW
- **Description**: `parser_fast.py` correctly stamps each note event with the channel's
  *currently active* GM program (`channel_programs.get(msg.channel, 0)`, `:151`), so a program
  change mid-track is faithfully carried per event. But the arranger collapses a track to a single
  representative program by taking the **first** event whose `program` is not `None`. Because the
  parser always sets `program` (defaulting to 0), `is not None` is always true, so `next()` always
  returns the *first note's* program and never looks further. If a `program_change` message arrives
  **after** the first note-on (or the track's first note precedes its program assignment), the
  track is analyzed as program 0 (Acoustic Grand Piano) even though its real instrument is set
  moments later. The GM role/timbre/duty hint (`role_scores[gm_mapping.role] += 3.0`) is then keyed
  off the wrong instrument.
- **Evidence**: Reproduced. Track whose first note carries `program=0` and whose later notes carry
  `program=38` yields `track program used: 0` from `analyze_midi_events`. The in-code comment
  ("GM programs are conventionally set once per track before any notes") documents the assumption,
  but MIDI does not guarantee it, and the parser already preserves the correct per-note program that
  this selection discards.
- **Impact**: Role detection for such tracks leans on the wrong GM hint. Because `_determine_role`
  also weights pitch/density/velocity/polyphony, the final role is often still reasonable, and
  channel allocation stays playable — hence LOW, not MEDIUM. No data loss; ROM boots and plays.
  Blast radius: only tracks that set/​change their patch after their first note (uncommon in
  well-formed GM files, more likely in DAW exports with a leading pickup note).
- **Related**: #86 (the program-plumbing fix this builds on — this is an arranger-side selection
  gap, not a reopening of #86). Dimension 2 of `audit-arranger/SKILL.md` explicitly flagged this
  case for a targeted check.
- **Suggested Fix**: Pick the most frequently-occurring (mode) program across the track's note
  events, or the program active at the track's densest region, rather than the first event's value;
  or, at minimum, prefer the first *non-zero* program when one exists. Add a test covering a
  program change that arrives after the first note-on.

---

*Generated by `/audit-arranger`. Deduplicated against `/tmp/audit/issues.json`
(matiaszanolli/midi2nes open issues) and `docs/audits/` prior reports
(`AUDIT_ARRANGER_2026-06-29/07-03/07-05/07-06.md`). #88 and #91 are OPEN and re-confirmed
unchanged (not re-filed). #92 and ARR-NEW-4 are now CLOSED/FIXED and re-verified at runtime;
#84–#90, #205–#207, #251–#253, #268 remain fixed. ARR-NEW-5 is new and has no matching open
issue.*

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-07-17.md
```
