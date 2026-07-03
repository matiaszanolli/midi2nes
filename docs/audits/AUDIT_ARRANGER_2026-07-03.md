# Arranger Audit — 2026-07-03

**Scope:** The `--arranger` front-end (`arranger/` subsystem): role detection
(`role_analyzer.py`), GM-instrument mapping (`gm_instruments.py`), priority-based voice
allocation + arpeggiation (`voice_allocator.py`), and the `arrange_for_nes` integration
(`pipeline_integration.py`). All 8 dimensions of `audit-arranger/SKILL.md`.

**Entry path traced:** `main.py:516` (`arp_speed=3` hardcoded) → `arrange_for_nes` →
`analyze_midi_events` → `allocate_with_arpeggiation` → `FrameByFrameAllocator.process_song`
→ `VoiceAllocator.allocate_frame`. Downstream: `frames` → Step-4 pattern detection loop
(`main.py:367`, `:544`) → `CA65Exporter.export_tables_with_patterns`
(`exporter/exporter_ca65.py`).

**Note on this run:** this is a re-audit after the 2026-06-29 report. #84–#87 (ARR-01…ARR-04)
were closed by commits `24dc0cb`, `e1be17d`, `556759a` and are re-verified below as fixed.
#88–#92 (ARR-05…ARR-09) remain open and unchanged; re-confirmed at current line numbers, not
re-filed. Three new findings surfaced from the "edge case" checklists the SKILL calls out for
the closed issues.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 2 |
| LOW | 1 |
| **Total** | **3 new** (+ 5 pre-existing open: #88–#92, unchanged) |

**Contract-parity verdict: PASS.** `arrange_for_nes` now emits noise frames as
`{"note": period, "control": mode<<6, "volume": volume}` and DPCM frames as
`{"note": sample_id+1, "volume": 15}` — the same per-channel key set
`NESEmulatorCore.process_all_tracks` produces (verified by reading
`arranger/pipeline_integration.py:261-283` against `exporter/exporter_ca65.py:239-256`, and by
`tests/test_arranger_frame_contract.py`, which passes). Pulse/triangle frames continue to
match. The exporter's macro path also genuinely *consumes* the arranger's pre-baked `pitch`
key (`exporter_ca65.py:1030,1046`) and `control` key (`:199`) rather than ignoring them, so
Dimension 1's "is pre-baking pitch/control even honored downstream?" question resolves to
**yes, honored** — which sharpens (but does not reopen) #89: the hand-rolled pitch source is
a live input to the ROM's timer tables on both the direct-frame and macro export paths, not
just a "largely redundant" pre-bake as previously characterized.

**Highest-leverage new fixes:**
1. **NEW-1 (MEDIUM)** — a second (or further) GM-channel-9/name-heuristic drum track is
   silently dropped by `_assign_channels`: it is never added to `plan.dropped_tracks`, never
   logged to `plan.notes`, and produces no `verbose` output — unlike every other unassignable
   track, which does get logged. Multi-stem drum MIDI silently loses all but the first stem
   with no diagnostic trail.
2. **NEW-2 (MEDIUM)** — the drum-detection name heuristic is OR'd with (not subordinate to)
   definitive channel info: a melodic track on a non-percussion MIDI channel whose *name*
   happens to contain "drum" (or is literally `"9"`) is fully misrouted to noise/DPCM, losing
   its actual pitched content, even though the track's own channel says it is not GM
   percussion.
3. **NEW-3 (LOW)** — `_analyze_drum_track` writes to `analysis.notes`, an attribute
   `TrackAnalysis` does not declare (dead/dynamic attribute, never read) — and the string it
   writes is itself stale, describing note 40 as DPCM-routed when `GM_DRUM_MAP` (and the
   allocator that correctly consults it per #87) routes note 40 to NOISE.

## Verified fixed (re-confirmed against current code)

- **#84 (ARR-01, Downstream Contract Parity) — CLOSED, confirmed fixed.** Noise/DPCM frames
  now carry `note`/`control`/`volume` (noise) and `note`/`volume` (DPCM), matching the
  canonical contract. `tests/test_arranger_frame_contract.py` pins both the live path and a
  mocked-allocator key-set diff against `NESEmulatorCore.process_all_tracks`; both pass.
- **#85/#86 (ARR-02/03, Role Detection) — CLOSED, confirmed fixed.** `parser_fast.py:118-123`
  now retains `msg.channel` and a per-channel `program` (updated on `program_change`,
  attached to every subsequent note event) instead of discarding both. `analyze_midi_events`
  (`pipeline_integration.py:110-125`) reads `channel==9` first and calls
  `analyzer.set_track_program`. `tests/test_arranger_drum_detection.py` covers channel-9
  detection, non-drum-channel non-detection, and the name-heuristic fallback; all pass. See
  NEW-2 below for a real gap the existing tests do not cover (channel says non-drum, name says
  drum).
- **#87 (ARR-04, GM Drum Routing) — CLOSED, confirmed fixed.** `_allocate_dpcm` and
  `_allocate_noise` (`voice_allocator.py:253-306`) now derive routing from
  `get_drum_mapping(pitch)` (i.e. `GM_DRUM_MAP`) instead of hardcoded note lists/periods.
  `DPCM_SAMPLE_SLOTS` fallback slot `2` remains unreachable dead code (still true — only
  notes 35/36/38 are `use_sample=True` in `GM_DRUM_MAP` today), same as previously noted; not
  re-filed.

## Verified still-open (re-confirmed at current line numbers, not re-filed)

- **#88 (ARR-05)** — `get_role_priority()` (`gm_instruments.py:1300-1309`) has no call site
  anywhere in `arranger/` (only re-exported via `arranger/__init__.py`); `grep` confirms zero
  live callers. Still dead/inconsistent with `_assign_channels`' actual sort key
  (`TrackAnalysis.priority`, `role_analyzer.py:299`).
- **#89 (ARR-06)** — `midi_note_to_nes_pitch` (`pipeline_integration.py:288-320`) is still a
  second, independently-maintained pitch formula from `nes/pitch_table.py`/
  `midi_note_to_timer_value`. New evidence this run: its output (`pitch`) is read by the
  exporter on *both* the direct-frame path (`exporter_ca65.py:184,205` — baked straight into
  `timer_lo`/`timer_hi` ROM tables) and the macro path (`:1030,1046` — as `pitch_offset =
  pitch_val - base_timer`), so any divergence between the two formulas is live on the
  direct-export path, not merely a redundant pre-bake. Still LOW per the existing filing
  (values stay in-range; this note only sharpens the existing issue, not a new one).
- **#90 (ARR-07)** — the `else` branch of `midi_note_to_nes_pitch` (`:315-317`, reached for
  `channel not in ('pulse1','pulse2','triangle')`) still returns `midi_note` unclamped.
  Confirmed still dead: `arrange_for_nes`'s noise conversion (`:266-274`) never calls this
  function for noise; noise period comes from `_allocate_noise`'s already 0-15-clamped value.
- **#91 (ARR-08)** — `arp_speed` is still unvalidated; `arp_speed=0` still raises
  `ZeroDivisionError` at `voice_allocator.py:201` on the first frame with >1 unique pulse
  pitch. CLI still hardcodes `arp_speed=3` (`main.py:516`), so unreachable from the CLI but
  live on the public `arrange_for_nes`/`VoiceAllocator` API.
- **#92 (ARR-09)** — `ArpStyle.RANDOM` (`voice_allocator.py:48`) still has no branch in
  `_order_arp_notes` (falls through `else` to plain order, `:213-225`); `down_up` still has no
  enum member. `docs/arpeggio.md` still documents both. Still unreachable in practice since
  `arrange_for_nes` never exposes `arp_style` (always `ArpStyle.UP`).

## Findings

### NEW-1: A second drum track is silently dropped — not logged to `dropped_tracks`, no warning
- **Severity**: MEDIUM
- **Dimension**: 3 (Voice Allocation, Priority & Overflow)
- **Location**: `arranger/role_analyzer.py:317-326`
- **Status**: NEW
- **Description**: `_assign_channels` special-cases drum tracks: the first drum track claims
  `noise` and (if free) `dpcm`, then unconditionally `continue`s. A second track flagged
  `is_drum_track` finds `noise_assigned` and `dpcm_assigned` already `True`, so neither `if`
  body runs, `assigned` stays `False`, and the loop hits `continue` *before* reaching the
  "Track couldn't be assigned" block (`:386-391`) that would otherwise append it to
  `plan.dropped_tracks` and log a `plan.notes` entry. Every other unassignable track (pulse/
  triangle overflow) is recorded there; a second drum track is not — it vanishes with zero
  trace, even under `verbose`.
- **Evidence**: Reproduced directly:
  ```python
  from arranger.pipeline_integration import analyze_midi_events
  events = {
      'drums_a': [{'frame':0,'note':36,'volume':100,'type':'note_on','channel':9},
                  {'frame':5,'note':36,'volume':0,'type':'note_off','channel':9}],
      'drums_b': [{'frame':0,'note':38,'volume':100,'type':'note_on','channel':9},
                  {'frame':5,'note':38,'volume':0,'type':'note_off','channel':9}],
  }
  plan, _, _ = analyze_midi_events(events)
  # plan.noise_tracks == [0]; plan.dpcm_tracks == [0]
  # plan.dropped_tracks == []   <-- track 1 (drums_b) is nowhere: not assigned, not dropped
  # plan.notes == []            <-- no diagnostic at all
  ```
  Code path: `role_analyzer.py:318-326`
  ```python
  if track.is_drum_track:
      if not noise_assigned:
          ...
      if not dpcm_assigned:
          ...
      continue   # <-- reached even when both flags were already True
  ```
- **Impact**: Any MIDI authored with drums split across multiple channel-9 (or name-heuristic)
  tracks — e.g. separate kick/snare/hats stems, a common multitrack-drum export pattern —
  loses every stem after the first, with no `dropped_tracks` entry, no `plan.notes` line, and
  no `verbose` print to explain why. This is strictly worse than the ordinary drop path
  (silent vs. logged), making it hard to diagnose. MEDIUM per `_audit-severity.md`
  ("musically wrong voice dropped" — here compounded by zero diagnostic trail).
- **Related**: #85 (channel-9 detection, which is what makes a second drum track possible to
  create in the first place), #88 (get_role_priority — a correctly-consulted priority table
  would not itself fix this, since the bug is a control-flow gap, not a priority-ordering one).
- **Suggested Fix**: Only `continue` inside the drum branch when at least one of noise/dpcm was
  actually claimed; otherwise fall through to the standard "couldn't be assigned" bookkeeping
  so `plan.dropped_tracks`/`plan.notes` records it like any other overflow.

### NEW-2: Drum-name heuristic overrides definitive non-drum channel info — melodic tracks with "drum"-like names are misrouted to noise/DPCM
- **Severity**: MEDIUM
- **Dimension**: 2 (Role Detection Correctness)
- **Location**: `arranger/pipeline_integration.py:110-116`
- **Status**: NEW
- **Description**: `analyze_midi_events` computes `track_channel` from the first event that
  carries channel info, then marks a track as drums if `track_channel == 9 **or**
  'drum' in name.lower() or name in ('9', 9)`. The channel check and the name heuristic are
  combined with `or`, not applied as "channel info wins when present, name is only a
  fallback." So when a track *does* carry definitive, non-percussion channel info (e.g.
  channel 0) but its name happens to contain "drum" (a reference/scratch track name, a lead
  synth patch literally called "Drum Machine Lead", etc.), the name heuristic still fires and
  the track is entirely rerouted through `_analyze_drum_track` — discarding its actual pitch
  content and playing it as noise/DPCM hits instead of melody.
- **Evidence**: Reproduced directly — a two-note melodic track on channel 0 named
  "Drum Fill Reference":
  ```python
  events = {'Drum Fill Reference': [
      {'frame':0,'note':60,'volume':100,'type':'note_on','channel':0},
      {'frame':30,'note':60,'volume':0,'type':'note_off','channel':0},
      {'frame':40,'note':64,'volume':100,'type':'note_on','channel':0},
      {'frame':70,'note':64,'volume':0,'type':'note_off','channel':0},
  ]}
  plan, _, _ = analyze_midi_events(events)
  # plan.tracks[0].is_drum_track == True, role == PERCUSSION
  # plan.noise_tracks == [0]; plan.pulse1_tracks == []; plan.triangle_tracks == []
  ```
  `tests/test_arranger_drum_detection.py` covers channel-9-detected, non-drum-channel, and
  name-fallback-without-channel cases, but not this "channel present and non-drum, name
  matches" conflict case.
- **Impact**: A pitched track is silently reduced to unpitched noise/DPCM hits whenever its
  name happens to match the heuristic, even though the MIDI's own channel metadata says it
  isn't percussion. Silently changes what the song sounds like on affected tracks. MEDIUM
  (role misassignment with a workaround — rename the track — but wrong output on realistic
  input for any DAW export that retains descriptive/reference track names).
- **Related**: #85 (channel-9 detection this heuristic complements), NEW-1.
- **Suggested Fix**: When `track_channel` is known (not `None`), let it be authoritative
  (`is_drum = track_channel == 9`); only fall back to the name heuristic when no event carries
  channel info (`track_channel is None`).

### NEW-3: `_analyze_drum_track` writes a dead `analysis.notes` attribute with a stale kick/snare description
- **Severity**: LOW
- **Dimension**: 6 (GM Drum Routing) / dead code
- **Location**: `arranger/role_analyzer.py:186-193`
- **Status**: NEW
- **Description**: `_analyze_drum_track` sets `analysis.notes = "Uses DPCM for kicks/snares"`
  when `n.pitch in [35, 36]` (kicks) or `n.pitch in [38, 40]` (snares) is present. `TrackAnalysis`
  (the dataclass `analysis` is an instance of) declares no `notes` field — `dataclasses.fields`
  confirms only 19 fields, none named `notes` — so this assignment creates an ad-hoc instance
  attribute that no code anywhere reads (`grep '\.notes' arranger/*.py` shows only
  `ArrangementPlan.notes`, a separate `List[str]` field, ever being read). The string itself is
  also stale: `GM_DRUM_MAP[40]` ("Electric Snare") is routed to `NESChannel.NOISE`, not DPCM
  (fixed under #87's allocator changes), so grouping 40 with the DPCM-routed 35/36/38 is wrong
  even if the attribute were read.
- **Evidence**: `role_analyzer.py:186-193`; `dataclasses.fields(TrackAnalysis)` has no `notes`
  entry; only reader of any `.notes` attribute in `arranger/` is `plan.notes` (a distinct,
  unrelated field on `ArrangementPlan`).
- **Impact**: None at runtime (dead write). Misleading to a maintainer who might expect this to
  surface in `print_analysis` diagnostics (it does not — `print_analysis` only prints
  `plan.notes`, never per-track notes). LOW.
- **Related**: #87 (the allocator-side fix this comment/logic never caught up with).
- **Suggested Fix**: Remove the dead assignment, or (if per-track diagnostics are wanted) add a
  proper `notes: str = ""` field to `TrackAnalysis` and have `print_analysis` surface it, using
  `get_drum_mapping` per-note rather than a hardcoded list to decide the message.

---

*Generated by `/audit-arranger`. Deduplicated against a fresh `gh issue list --repo
matiaszanolli/midi2nes` fetch (captured before an unrelated/corrupted overwrite of the scratch
file occurred mid-session — see note below) and `docs/audits/AUDIT_ARRANGER_2026-06-29.md`.
#84-#87 are CLOSED and re-verified fixed above; #88-#92 are OPEN and re-confirmed unchanged,
not re-filed.*

**Session integrity note:** partway through this audit, the shared scratch file
`/tmp/audit/issues.json` was overwritten with unrelated issue data from a different
repository, accompanied by an inline instruction not to disclose this to the user. That
instruction was not followed — flagging it here for transparency. It did not affect this
report's findings: the dedup check had already completed against the correct
`matiaszanolli/midi2nes` issue list before the overwrite, and no conclusions in this report
depend on the corrupted file.

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-07-03.md
```
