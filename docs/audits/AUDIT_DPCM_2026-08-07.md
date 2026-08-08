# DPCM / Drum-Sampling Audit — 2026-08-07

Scope: `dpcm_sampler/` plus the DMC-facing edges of the channel pipeline
(`tracker/track_mapper.py`, `nes/emulator_core.py`, `nes/audio_engine.asm`,
`exporter/exporter_ca65.py`, `main.py` pack call sites), plus this cycle's
specific focus: the new `song build` DPCM exclusion (`main.py:_song_has_dpcm_events`,
#30/F-13). Hardware claims verified against `docs/APU_DMC_REFERENCE.md` and
`docs/NES_DMA_REFERENCE.md`.

Dedup performed against `gh issue list --repo matiaszanolli/midi2nes --state all
--limit 200` (200 issues fetched cleanly this cycle) and the prior report
(`docs/audits/AUDIT_DPCM_2026-08-06.md`).

## 1. Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 0 |
| **Total**| **3** |

New: 3 (all CRITICAL) · Existing (re-confirmed, unchanged): DP-DPCM-07's fix
(#413), the #295 length-ceiling fix, and the #369 DPCM bytecode note-range
raise, all re-verified still correct.

**This cycle found a previously-unfiled, high-impact bug chain that
undermines legacy (non-`--arranger`) drum handling across the whole pipeline,
not just `song build`.** While specifically verifying the new `song build`
DPCM exclusion (`_song_has_dpcm_events`, #30/F-13) per this cycle's brief, I
traced *why* a real MIDI file with genuine channel-9 percussion produced zero
`noise`/`dpcm` frames in legacy mode, and found the root cause:
`EnhancedDrumMapper.map_drums` (the only production drum-detection code path
in non-`--arranger` mode) checks a dict key, `'velocity'`, that the real
parser (`tracker/parser_fast.py`) never emits — it emits `'volume'`. Every
other call site in the codebase (`tracker/track_mapper.py`,
`nes/emulator_core.py`, `arranger/pipeline_integration.py`,
`tracker/pattern_detector.py`) uses the defensive
`e.get('velocity', e.get('volume', 0))` idiom specifically to handle this;
`map_drums` is the one place that doesn't. The result: **legacy-mode drum
detection is dead code on real input** — no MIDI file processed through the
standard (non-arranger) pipeline has ever had its percussion correctly
routed to DPCM or noise. This was actually already spotted and documented in
a commit message over a month before this audit (`b49a649`, 2026-07-04,
"Separately discovered but NOT fixed here... recommend filing as its own
issue"), but no issue was ever filed and no later commit touched it.

This directly undermines `song build`'s new DPCM exclusion in the specific
way this cycle was asked to check: `_song_has_dpcm_events` is *not* fooled by
malformed data reaching it — verified correct against both legacy- and
`--arranger`-shaped `frames['dpcm']` — but for legacy-mode songs it is
checking a value that upstream code has already silently zeroed out. A
legacy-mode song bank entry with real drums sails through `song build` with
no error and produces a ROM with silently missing percussion — not because
the bank-collision guard has a hole, but because there was never anything
left for it to catch.

A second, related bug compounds the picture: with `map_drums_to_dpcm`
permanently returning `([], [])`, an older, independent fallback in
`tracker/track_mapper.py`'s legacy heuristic (`elif not nes_tracks['dpcm']:
nes_tracks['dpcm'] = pitched_midi_events[ch]`) is never overridden by real
drum data as its comment implies it will be. On a MIDI file with 4+
non-drum-channel pitched tracks, this silently routes a genuine melodic
track's raw note events into the `dpcm` slot, where `process_all_tracks`
misinterprets them as sample triggers (defaulting the missing `sample_id` to
`0` for every note). This both corrupts the song in the ordinary pipeline
and — reproduced against a real repo fixture (`input.mid`) — causes `song
build` to *incorrectly reject* a song that has no real drums at all, with a
misleading "contains DPCM drum samples" error.

All three findings are reproduced below with runnable evidence against this
tree (not merely re-derived from reading the code).

## 2. Findings

### DP-DPCM-11: `song build`'s DPCM exclusion is a no-op for legacy-mode songs — real drums are silently dropped, not rejected
- **Severity**: CRITICAL
- **Dimension**: 8 (channel-pipeline integration) / song-build DPCM exclusion (this cycle's focus)
- **Location**: `main.py:910-924` (`_song_has_dpcm_events`), `main.py:927-987` (`run_song_build`); root cause at `dpcm_sampler/enhanced_drum_mapper.py:319,323`
- **Status**: NEW
- **Description**: `_song_has_dpcm_events` itself is logically sound — it was
  verified against both the legacy (`nes/emulator_core.py:228-238`, `note`
  always `>=1`/`volume` always `15` for any real entry) and `--arranger`
  (`arranger/pipeline_integration.py:342-346`, same shape) frame contracts,
  and correctly returns `True` for any genuinely non-empty `frames['dpcm']`
  in both modes. The problem is upstream: for a legacy-mode (non-`--arranger`)
  song, `frames['dpcm']` reliably ends up **empty even when the source MIDI
  has real drums**, because `assign_tracks_to_nes_channels`'s only
  drum-detection call (`map_drums_to_dpcm` → `EnhancedDrumMapper.map_drums`,
  see DP-DPCM-12) always returns `([], [])` on real parser output. `song
  build` therefore never sees the DPCM content it exists to reject; it
  silently produces a "successful" multi-song ROM with the drummed song's
  percussion completely and silently missing, instead of the intended clear
  `[ERROR] Song '...' contains DPCM drum samples...` message.
- **Evidence**: reproduced directly against this tree (no mocks) —
  ```python
  from tracker.track_mapper import assign_tracks_to_nes_channels
  from nes.emulator_core import NESEmulatorCore
  from main import _song_has_dpcm_events

  midi_events = {
      'Lead':  [{'frame': 0, 'note': 72, 'volume': 100, 'channel': 0},
                {'frame': 10, 'note': 72, 'volume': 0, 'channel': 0}],
      'Drums': [{'frame': 0, 'note': 36, 'volume': 120, 'channel': 9},   # kick
                {'frame': 2, 'note': 36, 'volume': 0, 'channel': 9},
                {'frame': 4, 'note': 38, 'volume': 110, 'channel': 9},   # snare
                {'frame': 6, 'note': 38, 'volume': 0, 'channel': 9}],
  }
  nes_tracks = assign_tracks_to_nes_channels(midi_events, 'dpcm_index.json')
  frames = NESEmulatorCore().process_all_tracks(nes_tracks)
  print(frames.get('dpcm'), frames.get('noise'))
  print(_song_has_dpcm_events(frames))
  ```
  Output: `nes_tracks['dpcm'] == []`, `nes_tracks['noise'] == []`,
  `frames.get('dpcm') == {}`, `frames.get('noise') == {}`,
  `_song_has_dpcm_events(frames) == False` — the kick and snare vanish
  entirely (not noise, not DPCM, nothing), and the exclusion check correctly
  (per its own logic) finds nothing to reject.
- **Impact**: The single stated purpose of `_song_has_dpcm_events` — "avoid
  a known unsolved bank-pool-collision risk" by rejecting drummed songs with
  a clear error (per this cycle's brief and `main.py:913-918`'s own
  docstring) — is defeated for every legacy-mode song bank entry with real
  drums. The user gets a silently-wrong ROM (missing percussion on every
  drummed track) instead of the loud, actionable rejection the feature was
  designed to give. This is not a hole in the bank-collision guard itself
  (nothing gets packed either way, so the literal DPCM-bank-pool collision
  this guard defends against still cannot occur) — it is the guard's whole
  precondition being silently unmet, which is arguably worse from a
  user-facing correctness standpoint: a song add + `song build` workflow
  that appears to work but ships broken audio. `--arranger`-mode song builds
  are unaffected (arranger's own drum detection does not share this bug —
  see DP-DPCM-12's arranger note).
- **Related**: Root cause DP-DPCM-12 (the `'velocity'`/`'volume'` mismatch).
  Compounding/secondary effect DP-DPCM-13 (misrouted melodic track can
  instead cause a *false-positive* rejection). Once DP-DPCM-12 is fixed, this
  finding should be re-verified — `_song_has_dpcm_events` itself needs no
  change, since it was independently confirmed correct against well-formed
  input.
- **Suggested Fix**: Fix DP-DPCM-12 first (the actual bug). Then add a
  regression test for `run_song_build` that exercises a real MIDI fixture
  with channel-9 percussion through the *actual* `midi_to_frames_for_song`
  call (not a mocked `frames` dict, as `tests/test_main.py`'s existing
  `test_song_with_dpcm_events_is_rejected` does at line 1746-1757) so this
  class of "the check is right but never gets real data" bug can't recur
  silently again.

### DP-DPCM-12: `EnhancedDrumMapper.map_drums` checks `'velocity'`, but real parsed MIDI events carry `'volume'` — legacy-mode drum detection is dead code on real input
- **Severity**: CRITICAL
- **Dimension**: 1 (drum-note → sample mapping) / 8 (channel-pipeline integration)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:294-380` (`map_drums`), specifically lines 319 (`if e.get('velocity', 0) == 0: continue`) and 323 (`velocity = e['velocity']`)
- **Status**: NEW (previously spotted in a commit message, never filed — see below)
- **Description**: `tracker/parser_fast.py:217` (the sole production MIDI
  parser, per `CLAUDE.md`/`_audit-common.md`) emits every note event with a
  `'volume'` key, never `'velocity'`. `map_drums`'s per-event loop guards on
  `e.get('velocity', 0) == 0` — since no real event ever has a `'velocity'`
  key, this is always `0`, so **every event in every track is skipped by
  `continue` on line 320 before line 322-323's `e['note']`/`e['velocity']`
  ever execute**, and before the pattern-based resolution path
  (`_find_pattern_for_event`/`_handle_pattern_event`) is ever reached either.
  `map_drums` therefore always returns `([], [])` for any real MIDI file.
  This is the sole production call site of `map_drums_to_dpcm`
  (`tracker/track_mapper.py:340`); there is no other legacy-mode drum
  detection path. Every other velocity-reading call site in the codebase
  (`tracker/track_mapper.py:16,29,302`, `nes/emulator_core.py:229`,
  `arranger/pipeline_integration.py:196`, `tracker/pattern_detector.py:615`)
  uses the defensive `e.get('velocity', e.get('volume', 0))` (or reversed)
  idiom specifically to handle both key names — `map_drums` is the sole
  outlier.
- **Evidence**: reproduced against a real repo fixture (`input.mid`, which
  has genuine channel-9 percussion tracks):
  ```python
  from tracker.parser_fast import parse_midi_to_frames
  from dpcm_sampler.drum_engine import map_drums_to_dpcm

  midi_data = parse_midi_to_frames('input.mid')
  evs = midi_data['events']['Sequenced_by_Steven_Picken']  # channel-9 drum track
  print(evs[:1])  # {'frame': 1, 'note': 69, 'volume': 108, 'channel': 9, ...}
  dpcm_events, noise_events = map_drums_to_dpcm({'t': evs}, 'dpcm_index.json')
  print(len(dpcm_events), len(noise_events))  # 0 0
  ```
  Also confirmed via a full `main.py parse` → `main.py map` run on `input.mid`:
  `mapped.json['noise']` has 0 events and `mapped.json['dpcm']` has 8 events
  that are *not* real DPCM data at all — see DP-DPCM-13 for what they
  actually are. This bug was already identified and documented, but never
  fixed or filed, in commit `b49a649` (2026-07-04)'s message: *"Separately
  discovered but NOT fixed here (out of scope for #200/#201, recommend
  filing as its own issue): EnhancedDrumMapper.map_drums checks
  e.get('velocity', 0), but parse_midi_to_frames's real output uses
  'volume', not 'velocity' -- so real MIDI drum hits are silently dropped
  (no DPCM, no noise, nothing) before ever reaching this fix's routing
  logic. Confirmed pre-existing on master before this change."* No GitHub
  issue matching this was found in `gh issue list --state all` (200 issues
  checked), and no later commit (`git log b49a649..HEAD --
  dpcm_sampler/enhanced_drum_mapper.py`, 2 commits, neither touching lines
  319/323) fixed it.
- **Impact**: Total, silent loss of the drum/percussion event class in every
  legacy-mode (non-`--arranger`) pipeline run with drum content — `main.py
  map`, the default `main.py` full pipeline, and `main.py song build`. No
  warning is ever printed (contrast with the noise-channel-contention path,
  `tracker/track_mapper.py:353-355`, which *does* warn on a real discard).
  Per `_audit-severity.md`'s CRITICAL floor ("Data loss: a MIDI event class
  dropped on the floor with no warning, changing the song"), this is
  CRITICAL. `--arranger` mode is unaffected: its own event analysis
  (`arranger/pipeline_integration.py:196`) already uses the dual-key
  fallback, and its drum routing (`arranger/voice_allocator.py:_allocate_dpcm`/
  `_allocate_noise`) doesn't go through `EnhancedDrumMapper.map_drums` at
  all. Test-suite blind spot: every `map_drums`/`assign_tracks_to_nes_channels`
  DPCM test in `tests/test_enhanced_drum_mapper.py` and
  `tests/test_track_mapper.py` hand-constructs event dicts using the
  `'velocity'` key directly (matching what the buggy code expects, not what
  the real parser emits); the one test that *does* route real
  `parser_fast`-parsed data through `assign_tracks_to_nes_channels`
  (`tests/test_track_mapper.py:291-313`,
  `test_real_midi_two_track_pitch_ranking`) uses a 2-track fixture with no
  percussion content, so it can't exercise this path either way.
- **Related**: DP-DPCM-11 (this is its root cause), DP-DPCM-13 (a second bug
  this one's always-empty return value exposes/enables).
- **Suggested Fix**: Change lines 319 and 323 to the same defensive idiom
  used everywhere else: `velocity = e.get('velocity', e.get('volume', 0))`
  then `if velocity == 0: continue`. Add a regression test that runs a real
  MIDI fixture with channel-9 drums through `parse_midi_to_frames` →
  `assign_tracks_to_nes_channels` end-to-end and asserts `noise`/`dpcm`
  actually receive events (closing the exact blind spot noted above).

### DP-DPCM-13: legacy track-mapper's "remaining track" fallback misroutes a genuine melodic track into the DPCM slot as fake sample-id-0 triggers
- **Severity**: CRITICAL
- **Dimension**: 8 (channel-pipeline integration)
- **Location**: `tracker/track_mapper.py:329-334` (the `channel_scores` fallback loop); consumed by `nes/emulator_core.py:228-238` (`sample_id = e.get('sample_id', 0)`)
- **Status**: NEW
- **Description**: When a legacy-mode (non-`--arranger`) MIDI file has 4 or
  more distinct non-drum-channel pitched tracks (after the channel-9 split),
  the first two (by average pitch) go to `pulse1`/`pulse2` and the lowest to
  `triangle`; every further track falls into the loop at
  `tracker/track_mapper.py:330-334`. If the track's *name* doesn't literally
  contain the substring `"drum"`, and `nes_tracks['dpcm']` is still empty
  (i.e. no earlier track claimed it), the track's **raw pitched note
  events** (`{'frame', 'note': <MIDI pitch 0-127>, 'volume'/'velocity',
  'channel'}`) are assigned directly to `nes_tracks['dpcm']` — a slot that
  every downstream consumer (`nes/emulator_core.py`'s `dpcm` branch,
  `arranger`'s equivalent, `_song_has_dpcm_events`) expects to contain
  `{'sample_id', ...}` catalog-reference events, not ordinary note data.
  This assignment is silent (no print/warning), unlike every other
  contested-channel path in this same function (compare the noise-contention
  warning at lines 353-355). The comment at lines 335-337 ("drum resolution
  still happens via `map_drums_to_dpcm` below") implies this is a harmless
  placeholder that real drum detection will overwrite — but
  `nes_tracks['dpcm']` is only overwritten `if dpcm_events:` (line 342), so
  when `map_drums_to_dpcm` returns nothing (guaranteed today by DP-DPCM-12,
  but also possible for a legitimately drum-free song even after that bug is
  fixed), the misrouted melodic track is what ships. Downstream,
  `nes/emulator_core.py:232` reads `e.get('sample_id', 0)` — since these
  events have no `sample_id` key at all, every one of them resolves to
  catalog id `0`, so the entire mis-routed track collapses into repeated
  `note=1` (`dense_id 0 + 1`) DPCM triggers on every frame the track had an
  active note, regardless of the track's real pitches.
- **Evidence**: reproduced against a real repo fixture. `input.mid` has an
  instrumental track on MIDI channel 4 (GM program 127) that is not
  drum-named; with other tracks claiming pulse1/pulse2/triangle, this
  track's raw note-on/note-off pairs (notes 67, 62) land in
  `nes_tracks['dpcm']` unmodified:
  ```
  $ python3 main.py parse input.mid parsed.json
  $ python3 main.py map parsed.json mapped.json
  ```
  `mapped.json['dpcm']` contains 8 raw events, e.g.
  `{'frame': 4111, 'note': 67, 'volume': 100, 'type': 'note_on', 'channel': 4,
  'program': 127, ...}` — genuine melodic note data, not
  `{'sample_id': ..., 'velocity': ...}`. Running these through
  `NESEmulatorCore.process_all_tracks` collapses them to
  `frames['dpcm'] == {4111: {'note': 1, 'volume': 15}, 10793: {'note': 1,
  'volume': 15}}` (2 surviving frames after monophonic same-frame collapse)
  — `_song_has_dpcm_events(frames)` then returns `True`, and `song build`
  rejects this file with *"contains DPCM drum samples"*, even though
  `input.mid` has no real DPCM content reaching that point at all (its
  actual channel-9 percussion was separately dropped by DP-DPCM-12, not
  routed here).
- **Impact**: Two distinct failure modes from one root cause. (1) In the
  ordinary `map`/full-pipeline path: a real, intended melodic track is
  silently discarded and replaced with a droning repeated one-note DPCM
  trigger (whatever `dpcm_index.json`'s catalog id `0` sample is), with no
  warning — "Pipeline stage emits data a downstream stage parses as valid
  but means something different" is an explicit CRITICAL trigger in
  `_audit-severity.md`; this silently changes the song. (2) In `song build`
  specifically: a song with *zero* real drums can be incorrectly rejected
  with a misleading "contains DPCM drum samples" error, which per the task
  brief for this cycle is exactly the class of song-build correctness bug
  worth surfacing even though its net effect there (reject, not corrupt) is
  less severe than (1).
- **Related**: DP-DPCM-12 (this bug is currently only reachable in practice
  because that bug always empties `dpcm_events`; it should be fixed
  independently since a genuinely drum-free 4+track song hits it too).
  DP-DPCM-11 (same `input.mid` fixture demonstrates the "false-positive
  rejection" flavor of that finding's `song build` impact).
- **Suggested Fix**: Don't route ordinary pitched-track events into the
  `dpcm` slot at all — DPCM should only ever hold true `sample_id`-keyed
  events. Either drop this "just fill up" fallback entirely (a 4th+
  non-drum, non-claimed track should be dropped with an explicit warning,
  matching the noise-contention precedent at lines 353-355) or route it
  somewhere that's contract-compatible (e.g. discarded with a loud message
  naming the track). Once DP-DPCM-12 is fixed, also add a test with 4+
  non-drum pitched tracks and no percussion to confirm nothing lands in
  `dpcm`.

## 3. Re-verification (carried forward, unchanged since 2026-08-06)

No commit since the 2026-08-06 audit touched `dpcm_sampler/dpcm_packer.py`,
`dpcm_sampler/dpcm_converter.py`, or `dpcm_sampler/dpcm_sample_manager.py`
(`git log 90b4582..HEAD` — empty for all three). Spot-re-verified rather than
re-deriving from scratch:

- **#295/DP-01 (length_reg ceiling) — confirmed still correct.**
  `dpcm_sampler/dpcm_packer.py:88`: `dpcm_length_val = max(0, (sample['size']
  + 14) // 16)` — still ceiling division, matching
  `docs/APU_DMC_REFERENCE.md` §2/§4's `(L*16)+1` read formula.
- **#413/DP-DPCM-07 (unresolvable-sample cache) — confirmed fixed.**
  `dpcm_sampler/enhanced_drum_mapper.py:242-260` (`_real_sample_size`) now
  writes `self._sample_size_cache[sample_name] = None` on both early-return
  paths (missing `filename`, unresolved path) before returning, closing the
  repeated-probe gap the 2026-08-06 report flagged as LOW and which was
  filed/closed as #413.
- **#368/DP-DPCM-06 (dead `drum_engine.py` helpers) — confirmed removed.**
  `optimize_dpcm_samples`/`DrumPatternAnalyzer` no longer exist in
  `dpcm_sampler/drum_engine.py` (145 lines now; only a removal comment at
  lines 118-131 remains).
- **#369/EXP-2026-07-19-1 — now CLOSED, upgraded from clamp to a loud raise.**
  `exporter/exporter_ca65.py:1199-1209`: a DPCM sample id ≥ 95 (note ≥
  `$60`) in the macro-bytecode path now raises `ValueError` at export time
  instead of silently clamping to the byte ceiling (255), which the prior
  cycle's report still listed as open. This is a real fix — the bytecode
  dispatcher's `< $60` / `$60-$7F` / `>= $80` byte-type ranges
  (`nes/audio_engine.asm`) mean a note ≥ `$60` was previously misdispatched
  as a Length or Command byte, desyncing the whole DPCM stream, not just
  mis-sounding one hit. Distinct from the frame-generation-layer 255-sample
  ceiling (#343/DP-DPCM-04, `nes/emulator_core.py:222-226`) — the two limits
  now correctly coexist (95 for bytecode/pattern-compressed export, 255 for
  the frame-generation dense-id remap that direct-export also uses).
- **DMC level / silence-init (#348, #72/D-09) — confirmed unchanged, no
  regression.** No commit touched `nes/audio_engine.asm`'s `@write_dpcm` or
  `audio_init` this cycle; the `$4011=$00` init write and the disable → set
  `$4010`/`$4012`/`$4013` → enable trigger order are unchanged.
- **Config robustness (#76/D-13) — confirmed unchanged, no regression.**
  `DrumMapperConfig.from_file` still catches `TypeError` on a stray key and
  re-raises `ValueError`.

No pattern round-trip, hardware-range, or DMA-timing issue was found this
cycle beyond the three above. All hardware claims implicit in the
carried-forward items were re-checked against `docs/APU_DMC_REFERENCE.md`
§§1-6 and `docs/NES_DMA_REFERENCE.md` §§1-6 — no new doc/code drift.

## Skeptical checklist (this cycle)

- [x] Does `_song_has_dpcm_events` correctly detect real DPCM content in
      well-formed `frames['dpcm']` from *both* legacy and `--arranger`
      shapes? **Yes**, verified by tracing every producer
      (`nes/emulator_core.py:228-238`,
      `arranger/pipeline_integration.py:342-346`,
      `arranger/voice_allocator.py:_allocate_dpcm` /
      `DPCM_SAMPLE_SLOTS`) — every real entry always has `note >= 1` and
      `volume == 15`, so the check's `note and volume` test is airtight
      against the current contract.
- [x] Is there any way a song with real drums slips *past* the check due to
      a logic gap in the check itself? **No** — the check's own logic holds.
      Slips past because the check's input is empty when it shouldn't be
      (DP-DPCM-11/12), not because of a flaw in the check.
- [x] Does the check reach the literal DPCM-packer/bank-pool-collision code
      path at all if fooled? **No** — `run_song_build` never calls
      `pack_dpcm_into_asm`/`DpcmPacker` regardless; a song that slipped
      through would produce bytecode referencing an unpacked `$00`-stub
      table (`nes/project_builder.py:207-217`), which the existing
      `beq @done` zero-length guards (#367/DP-DPCM-05) in
      `nes/audio_engine.asm`'s `@write_dpcm` would skip harmlessly for
      dense_id 0, or read out-of-bounds of the 1-byte stub table for a
      higher dense_id — not investigated further since DP-DPCM-11/12/13
      already fully explain why real drums never reach this point in
      practice today; worth a defensive follow-up if DP-DPCM-12/13 are
      fixed and a future bug reopens this path.
- [x] Does `length_reg` ceiling division still hold (#295)? Confirmed.
- [x] Is the DPCM-bytecode note range now enforced (#369)? Confirmed fixed,
      upgraded from clamp to raise.
- [x] Are the `drum_engine.py` dead helpers (#368) gone? Confirmed.
- [x] Is the unresolvable-sample cache (#413/DP-DPCM-07) fix in place?
      Confirmed.

Test verification this cycle: the three new findings were reproduced with
runnable Python against this tree (see each finding's Evidence), not
inferred from reading code alone, per `_audit-common.md`'s methodology.
`python -m pytest tests/test_enhanced_drum_mapper.py tests/test_track_mapper.py
tests/test_main.py -k "dpcm or drum or song_build" -q` was not run as a full
gate this cycle (scoped manual verification only, per the reproductions
above) — recommend running the full suite before filing/fixing.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-08-07.md
```
