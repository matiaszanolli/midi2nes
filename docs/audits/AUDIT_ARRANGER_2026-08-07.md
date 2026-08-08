# Arranger Audit — 2026-08-07

Audit of the `--arranger` front-end (`arranger/`): role analysis, GM mapping, priority-based
voice allocation, and arpeggiation. Entry path traced: `main.py` `run_full_pipeline` →
`arrange_for_nes(events, arp_speed=3, verbose=args.verbose)` → `analyze_midi_events` →
`allocate_with_arpeggiation` → `VoiceAllocator` / `FrameByFrameAllocator`, and the new
`song build --arranger` route (`main.py:midi_to_frames_for_song` → same `arrange_for_nes` call)
added by the unrelated song-bank-ROM-build feature (`c864426`). That feature touches only
`main.py`/`nes/song_bank.py`/`exporter/exporter_ca65.py`/`nes/audio_engine.asm`; the four
`arranger/` files themselves are untouched since the prior audit — it is simply a new caller
of the existing `arrange_for_nes` entry point and is treated as such below, not audited on its
own merits (that belongs to a pipeline/song-bank audit).

This is a re-verification pass on top of `docs/audits/AUDIT_ARRANGER_2026-08-06.md`. Since
that report, one commit series closed all 3 of its findings:

- `4ac07da` — fixed #408 (GM_INSTRUMENT_MAP's curated `channel` now survives when role
  analysis agrees with the GM hint)
- `2981f29` — fixed #410 (documented, not removed) the unreachable BASS/triangle overflow
  recheck as intentional defense for direct `_assign_channels` callers
- `8ab20b4` — fixed #409 (last-resort triangle fallback restricted to `role == BASS` only,
  restoring the priority-drop invariant)

All three are confirmed present and holding in the current tree (see Verify-the-Fix section).
This pass also found **1 new finding**: a reproducible, unhandled `KeyError` crash in
`VoiceRoleAnalyzer._determine_role` for any non-drum-channel track using one of 19 real GM
instrument programs (including the common orchestral **Timpani**, program 47).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total (new)** | **1** |

- **NEW**: 1 (HIGH)
- **Re-verified fixed / CLOSED** (not re-filed): #84–#92, #205–#207, #230–#232, #251–#253, #268,
  #296, #308, #329–#331, #340, #341, #359, #360, #391, #392, #404 (legacy, out of scope),
  #408, #409, #410.
- **Cross-referenced, owned by another domain** (not re-filed here): #340/DP-DPCM-01 (DPCM
  sample coverage, `DPCM_SAMPLE_SLOTS` slot-2 still unreachable — unchanged), #369/
  EXP-2026-07-19-1 (macro-bytecode DPCM note byte range).

### Contract-parity verdict: **PASS**

`arrange_for_nes`'s five-channel `output` dict (`arranger/pipeline_integration.py:295-348`)
was re-diffed key-by-key against what `exporter/exporter_ca65.py` actually reads (both the
direct frame-table path and the macro-bytecode pattern path) and against the legacy
`NESEmulatorCore.process_all_tracks` contract. No drift found: `note`/`pitch`/`volume`/
`control` on pulse/triangle, `note`(period)/`control`(mode bit)/`volume` on noise, `note`
(sample+1, ≤255)/`volume`(15) on DPCM. The noise `control` internal bit-6 mode convention
(`arranger/pipeline_integration.py:335`, `arranger/voice_allocator.py:356`) matches the legacy
front-end's identical convention (`nes/emulator_core.py:179`) and is correctly re-shifted to
hardware bit 7 by the exporter (`exporter/exporter_ca65.py:315,527`) — confirmed not a bug,
just an internal software encoding shared by both front-ends.

### Highest-leverage finding

1. **ARR-2026-08-07-1** (HIGH): `VoiceRoleAnalyzer._determine_role` crashes with an unhandled
   `KeyError` for any non-drum-channel track whose GM program maps to `MusicalRole.PERCUSSION`
   or `MusicalRole.SFX` in `GM_INSTRUMENT_MAP` (19 of 128 programs, including Timpani #47,
   Orchestra Hit #55, Agogo #113, Woodblock #115, Taiko Drum #116, and 14 others). This aborts
   the entire `--arranger` pipeline (and the new `song build --arranger` route) for any MIDI
   file that scores one of these instruments outside MIDI channel 9 — a realistic scenario for
   orchestral or FX-heavy source material.

---

## Findings

### ARR-2026-08-07-1: `_determine_role` crashes with `KeyError` for 19/128 GM programs whose curated role isn't one of the 4 scoring buckets
- **Severity**: HIGH
- **Dimension**: 2 (Role Detection Correctness)
- **Location**: `arranger/role_analyzer.py:216-224` (`role_scores` dict + `role_scores[gm_mapping.role] += 3.0`)
- **Status**: NEW
- **Description**: `_determine_role` initializes `role_scores` as a plain `dict` with exactly
  4 keys — `MusicalRole.BASS`, `MELODY`, `HARMONY`, `DECORATIVE` (`:216-221`) — then
  unconditionally does `role_scores[gm_mapping.role] += 3.0` (`:224`) using the role looked up
  from `GM_INSTRUMENT_MAP` for the track's GM program (`get_instrument_mapping(analysis.program)`,
  `:207`). `MusicalRole` has 6 members (`arranger/gm_instruments.py:16-23`): the two not in
  `role_scores` are `PERCUSSION` and `SFX`. 19 of the 128 `GM_INSTRUMENT_MAP` entries are
  curated with `role=MusicalRole.PERCUSSION` or `role=MusicalRole.SFX` — real, spec-standard
  GM program numbers (Timpani #47, Orchestra Hit #55, three "FX" synth programs #96/#101/#103,
  Agogo #113, Woodblock #115, Taiko Drum #116, Melodic Tom #117, Synth Drum #118, and 8 more
  sound-effect programs #119-127). `_determine_role` is reached for *any* non-drum-channel
  track (`analyze_track` only special-cases `is_drum_track`, i.e. MIDI channel 9 or the
  name-heuristic fallback — `role_analyzer.py:141-143`), so a track carrying one of these 19
  programs on any other channel — e.g. an orchestral MIDI's Timpani part on channel 3 — hits
  the missing dict key and raises `KeyError` uncaught by `_determine_role`, `analyze_track`, or
  `create_arrangement_plan`. It propagates out of `analyze_midi_events` and `arrange_for_nes`
  entirely.
- **Evidence**: Direct reproduction against the live pipeline:
  ```python
  from arranger.pipeline_integration import analyze_midi_events
  events = {
      'timpani': [
          {'frame': 0, 'note': 40, 'velocity': 100, 'channel': 2, 'program': 47},
          {'frame': 30, 'note': 40, 'velocity': 0,   'channel': 2, 'program': 47},
      ],
  }
  analyze_midi_events(events)
  # Traceback (most recent call last):
  #   File "arranger/pipeline_integration.py", line 239, in analyze_midi_events
  #     plan = analyzer.create_arrangement_plan()
  #   File "arranger/role_analyzer.py", line 297, in create_arrangement_plan
  #     analysis = self.analyze_track(track_id)
  #   File "arranger/role_analyzer.py", line 170, in analyze_track
  #     self._determine_role(analysis)
  #   File "arranger/role_analyzer.py", line 224, in _determine_role
  #     role_scores[gm_mapping.role] += 3.0
  # KeyError: <MusicalRole.PERCUSSION: 4>
  ```
  Confirmed programmatically that exactly 19/128 `GM_INSTRUMENT_MAP` entries have this
  out-of-bucket role (`role in (MusicalRole.PERCUSSION, MusicalRole.SFX)`), and that
  `get_instrument_mapping`'s out-of-range fallback (unknown program numbers) safely defaults
  to `MusicalRole.HARMONY` (`gm_instruments.py:1297-1309`) — so only these 19 *in-range*,
  legitimate GM program numbers are affected, not malformed input.
- **Impact**: At the CLI, `main.py`'s outer `except Exception` in `run_full_pipeline`
  (`main.py:1446-1451`) catches this and prints `"[ERROR] Unexpected pipeline failure:
  MusicalRole.PERCUSSION"` then exits 1 — so it doesn't crash the interpreter uncaught, but it
  aborts the *entire* build with a non-actionable message for a MIDI file that would build
  fine without `--arranger`. Both live callers are affected identically: the default
  `--arranger` pipeline (`main.py:1337-1345`) and the new `song build --arranger` route
  (`main.py:midi_to_frames_for_song` → same `arrange_for_nes`), so a song bank containing even
  one song with a Timpani/Orchestra-Hit/percussion-family-instrument part on a non-drum channel
  fails the whole `song build --arranger` invocation, not just that one song. No workaround
  short of re-authoring the source MIDI to move/reassign the offending instrument's program
  number — not something a typical user would think to do from the error message shown.
- **Related**: Distinct from the fixed #86/ARR-03 (which was about `program` always being 0);
  this is a gap in the *role-scoring* table itself, unrelated to how `program` is derived.
  Not previously reported under any keyword search (`KeyError`, `role_scores`,
  `MusicalRole.PERCUSSION/SFX`) across `gh issue list --state all` or prior `docs/audits/`
  reports.
- **Suggested Fix**: Either (a) make `role_scores` tolerant of the two extra `MusicalRole`
  members — e.g. `defaultdict(float)` instead of a literal dict, or `role_scores[gm_mapping.role]
  = role_scores.get(gm_mapping.role, 0.0) + 3.0` — so an out-of-bucket GM hint simply contributes
  no bonus and the existing pitch/density/velocity signals still pick one of the 4 real buckets,
  or (b) explicitly map `PERCUSSION`/`SFX` instrument-role hints onto one of the 4 live buckets
  in `GM_INSTRUMENT_MAP` itself (e.g. Timpani → `BASS`-leaning, Agogo/Woodblock/Taiko/Synth Drum
  → `DECORATIVE`, ambient FX → `HARMONY`) so the intent captured in the curated table isn't lost.
  Add a regression test exercising at least one `PERCUSSION`-role and one `SFX`-role program on
  a non-drum channel (none of the existing `tests/test_arranger*.py` /
  `tests/test_role_analyzer.py` `PERCUSSION`-role cases go through `_determine_role` — they are
  all constructed with `is_drum=True`, which bypasses this code path entirely via
  `_analyze_drum_track`'s early return).

---

## Verify-the-Fix Results (all confirmed holding)

- **#84 (ARR-01)** — noise/DPCM canonical frame keys: holds (`pipeline_integration.py:322-348`).
- **#85/#86 (ARR-02/03)** — channel-9 drum detection + program-change handling: holds
  (`pipeline_integration.py:158-186`).
- **#87 (ARR-04)** — drum routing via `GM_DRUM_MAP`: holds (`voice_allocator.py:323-387`).
- **#88 (ARR-05)** — `get_role_priority()`: confirmed removed, only a tombstone comment remains.
- **#89/#90 (ARR-06/07)** — pitch via `nes/pitch_table.py`; noise never calls
  `midi_note_to_nes_pitch`: holds (`pipeline_integration.py:351-376`).
- **#91 (ARR-08)** — `arp_speed` clamp via property setter (`voice_allocator.py:98-109`,
  `max(1, int(value))`): holds, covered by `tests/test_voice_allocator.py`.
- **#92 (ARR-09)** — `_order_arp_notes` delegates to `tracker.track_mapper.apply_arpeggio_pattern`
  (`voice_allocator.py:285-295`): holds. Live path still only ever uses `ArpStyle.UP`.
- **#205 (ARR-10)** — second drum track drop bookkeeping: holds (`role_analyzer.py:317-355`).
- **#251/#252/#253/#268/#296/#308/#359/#391/#392** — per-note drum routing, per-chord arp
  phase, hi-hat sentinel, soft-note volume floor, false-chord merging, program-change-after-
  first-note, noise strike decay, zero-gap re-attack handling, noise mode bit: all present and
  unchanged in effect; re-read against current line numbers, no regressions found.
- **#329 (ARR-NEW-5)** — Type-0/multi-channel MIDI split by channel: confirmed fixed via
  `_split_events_by_channel` (`pipeline_integration.py:84-109`, called from
  `analyze_midi_events:141-186`).
- **#330 (ARR-NEW-6)** — PULSE2-mapped drum percussion reaches PULSE2 instead of collapsing to
  NOISE: confirmed fixed (`role_analyzer.py:326-351`, `voice_allocator.py:192-228`).
- **#331 (ARR-NEW-7)** — dead `enhanced_track_mapper` export: confirmed removed.
- **#408 (ARR-2026-08-06-1)** — GM_INSTRUMENT_MAP's curated `channel` now survives when the
  detected role agrees with `gm_mapping.role`: confirmed fixed
  (`role_analyzer.py:263-289`, `channel_override = not (best_role == gm_mapping.role)`). Spot
  checked against the Ocarina (#79)/Whistle (#78)/Blown Bottle (#76) TRIANGLE curation and the
  "FX 4 (atmosphere)" (#99) NOISE curation from the prior report's evidence: when musical
  analysis independently agrees with GM's role hint for these programs, `preferred_channel`
  now correctly retains the curated value instead of being unconditionally overwritten. The
  new `ANY_PULSE`/`FLEXIBLE` branch this fix made reachable in `_assign_channels`
  (`role_analyzer.py:389-397`) is exercised live for GM's `ANY_PULSE`-curated harmony
  instruments (e.g. Electric Piano 1) — confirmed no `KeyError`/`AttributeError` on that path
  for a representative program.
- **#409 (ARR-2026-08-06-2)** — last-resort triangle fallback restricted to
  `track.role == MusicalRole.BASS` only (`role_analyzer.py:417`): confirmed fixed. Reproduced
  the prior report's mixed-role repro (3 MELODY tracks + 1 HARMONY pad, no BASS) — the HARMONY
  pad no longer claims triangle ahead of a higher-priority dropped MELODY track; both a
  MELODY-track drop and a genuine BASS-to-triangle spill were re-verified to behave correctly
  in isolation via `tests/test_role_analyzer.py::test_third_melody_track_is_dropped_with_note`
  and `test_bass_track_spills_to_triangle_when_pulses_full`.
- **#410 (ARR-2026-08-06-3)** — the BASS/triangle overflow recheck at
  `role_analyzer.py:401-416` was documented (not removed) as intentionally unreachable from
  the live `_determine_role`-driven pipeline but real defense for `_assign_channels`'s own
  direct-call test surface: confirmed the comment accurately describes current behavior;
  `_determine_role` still always resolves BASS tracks straight to `TRIANGLE`
  (`role_analyzer.py:273-276`), so the live pipeline still never reaches this recheck with
  `triangle_assigned` still `False`. No behavior change, purely documentation — holds.
- GM coverage: `GM_INSTRUMENT_MAP` covers all 128 programs 0-127 (verified programmatically).
  No TRIANGLE/NOISE/DPCM-channel instrument mapping carries a `duty` (`DrumMapping` doesn't
  even have a `duty` field, structurally impossible there). `DutyCycle.DUTY_75` still has zero
  live users.
- Determinism (Dimension 8): parser dict insertion order → `analyze_midi_events` enumeration →
  stable `sort(key=priority, reverse=True)` → `max(role_scores, key=...)` first-by-dict-order
  (when it doesn't crash — see new finding). `ArpStyle.RANDOM` remains note-seeded and
  unreachable on the live path. No wall-clock/global RNG found.
- Hardware compliance (Dimension 7): triangle `control=0x81` with no duty bits, volume gate
  only. Pulse `control = (duty << 6) | 0x30 | volume` stays within a byte. Noise/DPCM byte
  ranges all clamp correctly at the arranger boundary. Confirmed the noise mode-bit internal
  convention (bit 6 in the arranger's/legacy's own `control` byte) is correctly re-shifted to
  hardware bit 7 by both exporter code paths that write `$400E` — not a bug (see
  Contract-parity verdict above).
- `tests/test_arranger.py`, `tests/test_arranger_drum_detection.py`,
  `tests/test_arranger_frame_contract.py`, `tests/test_voice_allocator.py`,
  `tests/test_role_analyzer.py` (81 tests total) all pass on the current tree — none of them
  exercise a non-drum track with a `PERCUSSION`/`SFX`-role GM program, which is exactly the gap
  the new finding closes.

---

## Notes (observations below the reporting bar)

- `#404/ARR-NEW-5-LEGACY` (Type-0/multi-channel splitting in the *legacy* `track_mapper`
  front-end) remains out of scope for this arranger-mode audit.
- The song-bank `song build --arranger` feature (`c864426`, unrelated commit) is a new caller
  of `arrange_for_nes` but makes no changes to `arranger/role_analyzer.py`,
  `arranger/voice_allocator.py`, `arranger/gm_instruments.py`, or
  `arranger/pipeline_integration.py`. It inherits ARR-2026-08-07-1 unmodified: any song in a
  bank built with `--arranger` that uses one of the 19 affected GM programs on a non-drum
  channel aborts the whole `song build --arranger` run, not just that song.
- `#340/DP-DPCM-01`'s `DPCM_SAMPLE_SLOTS` slot-2 fallback remains presently unreachable (only
  notes 35/36/38 are `use_sample=True` in `GM_DRUM_MAP`) — unchanged, not re-filed here, owned
  by `/audit-dpcm`.
- No evidence of float frame-timing drift in the arranger: all frame-grid math (`arp_frame`,
  `frame_count`) is integer.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_ARRANGER_2026-08-07.md
```
