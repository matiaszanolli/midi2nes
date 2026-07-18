# DPCM / Drum-Sampling Audit — 2026-07-18

Audit of the DPCM/drum subsystem: GM-percussion → DPCM sample mapping, WAV→1-bit-delta
conversion, sample packing/addressing, and the DMC-facing edges of the channel pipeline
and CA65 exporter. Scope per `.claude/commands/audit-dpcm/SKILL.md`.

Hardware claims cite `docs/APU_DMC_REFERENCE.md` and `docs/NES_DMA_REFERENCE.md`.

Follow-up to `docs/audits/AUDIT_DPCM_2026-07-06.md`. `git log` confirms no commits have
touched `dpcm_sampler/`, `nes/emulator_core.py`'s DPCM branch, `tracker/track_mapper.py`'s
DPCM routing, `nes/mmc3_init.asm`, or `dpcm_index.json` since that report except
`d392ef6` (the `#295` ceiling fix, already reflected there). All five prior findings
(DP-01…DP-05) were re-verified against the current tree: DP-01 (length-register floor)
is **confirmed fixed** and demoted out of the active findings list; DP-02 through DP-05
are unchanged and re-reported below for continuity. This pass adds one previously
unfiled MEDIUM (asset-naming coverage gap, originally flagged as D-15 on
`AUDIT_DPCM_2026-07-03.md` and then dropped from the report chain without being closed
or re-filed) and one NEW LOW (dead/duplicate DPCM trigger code that has been
misidentified as live by two prior audits and one open issue).

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 5 |
| **Total**| **6** |

Highest-risk finding:

- **DP-07 (MEDIUM)** — 14 of the 40 distinct `DEFAULT_MIDI_DRUM_MAPPING` role names
  (GM notes 37, 54, 55, 58, 71-74, 76-81) have no matching key in the shipped
  `dpcm_index.json`, so those percussion notes still resolve to `None` and fall through
  to the noise channel — even though semantically equivalent samples exist in the
  catalog under different filenames (`whistle1`/`whistle2` vs. `whistle_short`/
  `whistle_long`, `guiro1`/`guiro2` vs. `guiro_short`/`guiro_long`, `tamborin` vs.
  `tambourine`, `mario_2_woodblock` vs. `woodblock_hi`/`woodblock_lo`, `cuica1`/`cuica2`
  vs. `cuica_mute`/`cuica_open`, `stickrim`/`sticks` vs. `side_stick`). This is the same
  26-of-40 coverage first measured in `AUDIT_DPCM_2026-07-05.md` (unchanged since); it
  was never filed as a GitHub issue and fell out of the `AUDIT_DPCM_2026-07-06.md`
  report without being marked fixed.

Verified fixed since last pass:

- **DP-01 (was MEDIUM)** — `dpcm_packer._place_sample` (`dpcm_sampler/dpcm_packer.py:88`)
  now ceils the `$4013` length register: `dpcm_length_val = max(0, (sample['size'] + 14)
  // 16)`. Confirmed against `docs/APU_DMC_REFERENCE.md` §2/§4 and against
  `tests/test_dpcm_packer.py`, which passes. The prior floor-truncation regression (#75 →
  regressed → re-fixed as #295, commit `d392ef6`) holds on this tree.

---

## Findings

### DP-07: `DEFAULT_MIDI_DRUM_MAPPING` role names still don't match the shipped `dpcm_index.json`'s actual filenames for 14 of 40 GM percussion roles
- **Severity**: MEDIUM
- **Dimension**: 1 (mapping coverage) / 2 (index schema)
- **Location**: `dpcm_sampler/drum_engine.py:8-56` (`DEFAULT_MIDI_DRUM_MAPPING`);
  `dpcm_index.json` (shipped data, 1941 entries)
- **Status**: Existing: D-15 (`docs/audits/AUDIT_DPCM_2026-07-03.md`) — never filed as a
  GitHub issue; the same 26/40-present count was re-confirmed in
  `AUDIT_DPCM_2026-07-05.md` (as an aside inside the now-fixed D-17/#254 finding), then
  silently dropped from `AUDIT_DPCM_2026-07-06.md`'s report without being marked fixed.
  Re-verified NEW-to-this-report-chain (no open issue tracks it).
- **Description**: `_resolve_dpcm_sample_name`'s fallback cascade (velocity-split →
  advanced `"primary"` → `DEFAULT_MIDI_DRUM_MAPPING` role name, each gated by `if name in
  self.sample_index`) is correct and reaches every candidate — that part of #73/D-10 is
  solid. But the shipped `dpcm_index.json` catalog only contains 26 of the 40 distinct
  role-name strings the mapping table can produce. The other 14
  (`side_stick`, `tambourine`, `splash`, `vibraslap`, `whistle_short`, `whistle_long`,
  `guiro_short`, `guiro_long`, `woodblock_hi`, `woodblock_lo`, `cuica_mute`,
  `cuica_open`, `triangle_mute`, `triangle_open`) never resolve, so those GM notes
  (37, 54, 55, 58, 71, 72, 73, 74, 76, 77, 78, 79, 80, 81 — 14 of the 47-note GM
  percussion range) always fall to the noise-channel fallback. This is not a logic bug
  (the noise fallback is the documented, sane degrade path — `enhanced_drum_mapper.py:
  312-321`) and it is not a full silent drop (noise still sounds on the hit's frame), so
  it stays below HIGH per `_audit-severity.md`'s "at least MEDIUM ... HIGH when it
  silently strips a hit" rule — noise substitution is audible, just the wrong timbre.
  What makes this worth re-surfacing now is that four of the "missing" instruments
  *do* have real samples in the catalog, just under different filenames the role-name
  cascade never tries (`guiro1`/`guiro2`, `whistle1`/`whistle2`, `cuica1`/`cuica2`,
  `tamborin`, `mario_2_woodblock`, `stickrim`/`sticks`) — an index-generation-time alias
  step (or a second, filename-similarity fallback tier) could close a meaningful chunk of
  this gap without touching any Python resolution logic.
- **Evidence**:
  ```
  $ python3 -c "
  import json
  from dpcm_sampler.drum_engine import DEFAULT_MIDI_DRUM_MAPPING
  d = json.load(open('dpcm_index.json'))
  names = set(d)
  roles = sorted(set(DEFAULT_MIDI_DRUM_MAPPING.values()))
  present = [r for r in roles if r in names]
  missing = [r for r in roles if r not in names]
  print(len(roles), 'distinct roles;', len(present), 'present,', len(missing), 'missing')
  print('missing:', missing)"
  40 distinct roles; 26 present, 14 missing
  missing: ['cuica_mute', 'cuica_open', 'guiro_long', 'guiro_short', 'side_stick',
            'splash', 'tambourine', 'triangle_mute', 'triangle_open', 'vibraslap',
            'whistle_long', 'whistle_short', 'woodblock_hi', 'woodblock_lo']

  $ python3 -c "
  import json
  d = json.load(open('dpcm_index.json'))
  for kw in ['tambo','whistle','guiro','woodblock','cuica','stick']:
      print(kw, [k for k in d if kw.lower() in k.lower()][:5])"
  tambo ['tamborin']
  whistle ['whistle1', 'whistle2']
  guiro ['guiro1', 'guiro2']
  woodblock ['mario_2_woodblock']
  cuica ['cuica1', 'cuica2']
  stick ['Sticks_1', 'stickrim', 'sticks']
  ```
  Confirmed via `EnhancedDrumMapper._resolve_dpcm_sample_name` directly (not just set
  membership): iterating GM notes 35-81 through the live mapper on the shipped index
  returns `None` for exactly `[37, 54, 55, 58, 71, 72, 73, 74, 76, 77, 78, 79, 80, 81]`
  (14 notes).
- **Impact**: On the shipped catalog, roughly 30% of the GM percussion key range
  (side-stick, tambourine, splash, vibraslap, whistles, guiros, woodblocks, cuicas,
  triangle mute/open) still degrades to noise-channel percussion instead of the sampled
  drum. This is a data/asset-naming gap, not a code defect — the #73/D-10 code fix is
  confirmed correct and unregressed. Splash/vibraslap/triangle mute-open genuinely have
  no matching sample anywhere in the catalog (not just a naming mismatch); the other six
  roles (guiro, whistle, woodblock, cuica, tambourine, side_stick) have real but
  differently-named samples sitting unused in the same index.
- **Related**: D-15 (`AUDIT_DPCM_2026-07-03.md`), D-10/#73 (the code-path fix this data
  gap doesn't undermine).
- **Suggested Fix**: Either (a) add filename aliases to `dpcm_index.json` (or a small
  static alias table in `drum_engine.py`) mapping `tambourine→tamborin`,
  `whistle_short/long→whistle1/whistle2`, `guiro_short/long→guiro1/guiro2`,
  `cuica_mute/open→cuica1/cuica2`, `woodblock_hi/lo→mario_2_woodblock`,
  `side_stick→stickrim`, closing 6 of the 14 gaps immediately with no code-path risk; or
  (b) accept the remaining true asset gaps (splash, vibraslap, triangle mute/open) as a
  documented limitation of the shipped catalog.

### DP-02: `DrumMapperConfig.from_file` raises an uncaught `TypeError` on a stray/renamed config key
- **Severity**: LOW
- **Dimension**: 6 (config robustness)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:168-173` (splat into
  `DrumPatternConfig`/`SampleManagerConfig`), `:187-190` (only `FileNotFoundError` /
  `json.JSONDecodeError` caught)
- **Status**: Existing: #76 (OPEN, code unchanged)
- **Description**: `from_file` does `DrumPatternConfig(**config_data.get('pattern_detection',
  {}))` and the equivalent for `SampleManagerConfig`. An unexpected or renamed JSON key
  raises `TypeError` from the dataclass constructor, which is not among the two exception
  types the method catches, so it propagates raw.
- **Evidence**: `enhanced_drum_mapper.py:187-190` catches only `FileNotFoundError` and
  `json.JSONDecodeError`; the two `**kwargs` splats at lines 168 and 171 are the raising
  sites (confirmed unchanged by direct read against current tree).
- **Impact**: Low reach today — the CLI `--config` flag that fed this path was removed
  (#13), so `from_file` is public-API-only (exercised by `tests/test_drum_mapper_config.py`).
  Still an ungraceful failure mode on public API surface.
- **Related**: #76; prior D-13.
- **Suggested Fix**: Wrap the two dataclass constructions and re-raise a typed `ValueError`
  naming the offending key, or filter `config_data` to known fields before splatting.

### DP-03: `_handle_pattern_event` ignores the caller's `use_advanced` flag
- **Severity**: LOW
- **Dimension**: 1 (mapping coverage)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:364`
- **Status**: Existing: #202 (OPEN, code unchanged)
- **Description**: `map_drums(midi_events, use_advanced)` threads `use_advanced` into the
  non-pattern path (`_resolve_dpcm_sample_name(midi_note, velocity, use_advanced)`, lines
  283-285) but the pattern-matched path calls `self._resolve_dpcm_sample_name(template_note,
  velocity)` (line 364) with no third argument, so it always uses the default
  `use_advanced=True` regardless of the caller's request.
- **Evidence**: line 283-285 (flag passed) vs. line 364 (omitted, defaults `True`) —
  confirmed unchanged.
- **Impact**: A caller explicitly requesting `use_advanced=False` still gets advanced
  velocity-split resolution for any event inside a detected drum pattern. Latent/API-only:
  the sole production call site (`tracker/track_mapper.py`) always uses the default.
- **Related**: #202; prior D-16.
- **Suggested Fix**: Pass the flag through:
  `self._resolve_dpcm_sample_name(template_note, velocity, use_advanced)`.

### DP-04: `run_map` subcommand crashes with a raw traceback when `dpcm_index.json` is missing, unlike the packer path
- **Severity**: LOW
- **Dimension**: 8 (channel-pipeline integration)
- **Location**: `main.py:104-112` (`run_map`) → `assign_tracks_to_nes_channels(...,
  dpcm_index_path)` → `EnhancedDrumMapper._load_sample_index`
  (`enhanced_drum_mapper.py:210-224`) raises `FileNotFoundError`
- **Status**: Existing: #256 (OPEN, code unchanged)
- **Description**: `run_map` guards its *input* JSON via `load_json_stage` (line 106) but then
  passes a hardcoded default `'dpcm_index.json'` (line 108) into
  `assign_tracks_to_nes_channels` with no try/except around the call. If that index file is
  absent, `_load_sample_index` raises an uncaught `FileNotFoundError` and the standalone
  `map` subcommand exits with a raw traceback — in contrast to the DPCM *packer* path
  (`run_export` / `run_full_pipeline`, `main.py:590-626`, `:961-1012`), which handles a
  missing index gracefully ("No dpcm_index.json found, skipping"), and to every other
  step-by-step guard in `main.py` (`load_json_stage`, #120). `run_full_pipeline` also calls
  `assign_tracks_to_nes_channels` directly with no local guard (`main.py:819-820`), but
  fares better only because its entire body sits inside one outer `try/except Exception`
  (`main.py:798`/`:1096`) that turns any crash into a clean `[ERROR] Pipeline failed: ...`
  message rather than a raw traceback — though the pipeline still aborts entirely instead
  of degrading to a drumless build.
- **Evidence**: `main.py:104-112` — no try/except around the mapper call, confirmed
  unchanged; packer call sites at `main.py:590-626` and `:961-1012` remain guarded.
- **Impact**: Low — the index ships with the repo, so this only bites a user who deletes or
  relocates it while using the step-by-step `map` subcommand. Cosmetic UX asymmetry (raw
  traceback vs. clean degrade), not a data-loss path.
- **Related**: #256, #120; prior D-18.
- **Suggested Fix**: Wrap the mapper call in `run_map` to catch a missing index and either
  emit a clean `[ERROR]` message or degrade to a drumless map (parity with the packer path).

### DP-05: DMC "layering" emits a duplicate of the primary sample that the same-frame collapse then discards with a misleading "note dropped" warning
- **Severity**: LOW
- **Dimension**: 1 (mapping coverage) / tech-debt
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:304-311` (`_handle_layered_samples`
  call) + `:435-451` (`_handle_layered_samples`); `dpcm_sampler/drum_engine.py:64,72`
  (`layers` lists); `nes/emulator_core.py:212` (same-frame collapse) + `:42-45` (warning
  text)
- **Status**: Existing: #300 (OPEN, code unchanged)
- **Description**: For a note in `ADVANCED_MIDI_DRUM_MAPPING` whose entry has a `layers`
  list (only 36/kick and 38/snare), `map_drums` appends the primary DPCM event and then
  calls `_handle_layered_samples`, which appends a **second** event on the same frame for
  every layer name present in the index. The layer lists are `["kick", "kick_sub"]` and
  `["snare", "snare_rattle"]` — the first element is the primary itself (guaranteeing a
  duplicate), and the second (`kick_sub`/`snare_rattle`) is absent from the shipped index
  (confirmed: not in `dpcm_index.json`), so only the duplicate fires. Downstream,
  `_collapse_same_frame_events` (`nes/emulator_core.py:212`) collapses the two identical
  events to one and prints a "note(s) dropped" warning — a false alarm, since nothing
  musical was lost. Layering is also physically impossible on the DMC: it is a single
  monophonic channel, so two simultaneous samples can never both sound.
- **Evidence**: unchanged from prior report; re-confirmed `kick_sub`/`snare_rattle` are
  still absent from the current 1941-entry `dpcm_index.json`.
- **Impact**: No audible corruption (the collapse keeps one copy of the correct sample),
  but a spurious "note dropped" warning misleads users into thinking polyphony was lost,
  and the layering feature is inert on the DMC regardless.
- **Related**: #300, #96 (same-frame collapse warning); DP-03 (same advanced-mapping path).
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §1 — the DMC is a single monophonic
  channel (Reader → Buffer → Shifter → Output); simultaneous sample layering on it is not
  possible.
- **Suggested Fix**: Remove `_handle_layered_samples` and the `layers` lists (the DMC can't
  layer), or dedupe against the primary so the collapse warning stays truthful.

### DP-06: `seq_cmd_dpcm_play` in `nes/project_builder.py` is dead/unreachable code — a duplicate DPCM trigger with a different register order that two prior audits mistook for the live implementation
- **Severity**: LOW
- **Dimension**: 8 (channel-pipeline integration) / tech-debt
- **Location**: `nes/project_builder.py:136-167` (`.global seq_cmd_dpcm_play` proc,
  appended to `music_content` whenever `is_bytecode`); actual live handler at
  `nes/audio_engine.asm:231-257` (`@cmd_dpcm_play`, dispatched inline from the `$85`
  opcode branch of the sequencer's command loop, `audio_engine.asm:219-220`)
- **Status**: NEW
- **Description**: `NESProjectBuilder.prepare_project` unconditionally appends a
  `.global seq_cmd_dpcm_play` procedure into `music.asm` whenever the export is bytecode
  mode (the default, pattern-compressed path). It is never called: `grep -rn
  "seq_cmd_dpcm_play"` across the entire repo finds only its own definition, `.global`
  declaration, and its own comment header — no `jsr`, `.import`, or reference from any
  `.asm` file, `main.py`, `exporter/exporter_ca65.py`, or the test suite. The real `$85`
  (`CMD_DPCM_PLAY`) opcode dispatch lives entirely inline inside
  `nes/audio_engine.asm`'s `@cmd_dpcm_play` label (`audio_engine.asm:231-257`), reached via
  a direct `beq @cmd_dpcm_play` in the command-byte dispatcher — it does not call out to
  `project_builder.py`'s proc at all. Both implementations do reach a hardware-correct end
  state (registers set before the final `$4015` bit-4 trigger write), but they differ in
  internal ordering: `audio_engine.asm` disables DMC first (`$4015=$0F`), then loads
  `$4010`/`$4012`/`$4013`, then re-enables (`$4015=$1F`); the dead `project_builder.py`
  copy loads `$4010`/`$4012`/`$4013` first, then disables, then re-enables. Both prior
  audits that examined this trigger (`AUDIT_DPCM_2026-07-03.md`, citing
  `nes/project_builder.py seq_cmd_dpcm_play` alongside `exporter_ca65.py play_dpcm` as the
  two live trigger routines; `AUDIT_MAPPERS_2026-07-05.md`, describing it as "the
  equivalent bytecode-engine trigger... correctly gated `if is_bytecode`") and the closed
  issue `.claude/issues/281/ISSUE.md` (whose fix checklist says "verify the fix mirrors
  the existing MMC3-only gate already used at `seq_cmd_dpcm_play`") all treated this dead
  proc as the live bytecode-engine implementation. The actual live implementation
  (`audio_engine.asm`) was not examined by any of them for the same property.
- **Evidence**:
  ```
  $ grep -rn "seq_cmd_dpcm_play" --include="*.py" --include="*.asm" .
  nes/project_builder.py:141:; seq_cmd_dpcm_play ($85)
  nes/project_builder.py:144:.global seq_cmd_dpcm_play
  nes/project_builder.py:145:seq_cmd_dpcm_play:
  # (no call sites anywhere)

  $ grep -n "cmd_dpcm_play\|\\$85" nes/audio_engine.asm
  219:    cmp #$85
  220:    beq @cmd_dpcm_play
  231:@cmd_dpcm_play:
  # ... full inline trigger implementation, independent of project_builder.py's proc
  ```
- **Impact**: No playback bug — the dead proc is never executed, so its (functionally
  equivalent, differently-ordered) register writes never run. Impact is entirely on audit/
  maintenance accuracy: the dead code occupies a handful of PRG-ROM bytes in every
  bytecode-mode build, and it has already caused two independent audits and one GitHub
  issue to reason about the wrong code path when verifying MMC3-only gating and DMC
  trigger-order correctness for the actual live engine. A future change to
  `audio_engine.asm`'s real trigger could go unverified if a reviewer edits/audits the
  dead copy instead.
- **Related**: prior misattributions in `AUDIT_DPCM_2026-07-03.md` and
  `AUDIT_MAPPERS_2026-07-05.md`; closed issue `#281`.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §6 (engine implementation notes) — both
  the dead and live orderings satisfy the documented `$4010`→`$4012`→`$4013`→trigger
  sequence; this finding is about reachability, not hardware correctness.
- **Suggested Fix**: Delete `seq_cmd_dpcm_play` from `nes/project_builder.py` (lines
  136-167, including its `.import switch_dpcm_bank`) since `audio_engine.asm` already owns
  `$85` dispatch, or if a standalone callable trigger is intentionally wanted for some
  other caller, wire it in and add a test that exercises it via `jsr`/`.import` from
  somewhere real.

---

## Re-verified as fixed / not reported

- **DP-01 / #75 → #295 (length-register floor)** — `dpcm_sampler/dpcm_packer.py:88` uses
  ceiling division (`max(0, (size + 14) // 16)`); `tests/test_dpcm_packer.py` passes,
  including the explicit boundary-size assertions. No regression.
- **`MAX_SAFE_SAMPLE_ID` guard (#254/D-17)** — confirmed absent (`grep -rn
  "MAX_SAFE_SAMPLE_ID"` finds only a historical comment at
  `enhanced_drum_mapper.py:281` explaining why it was removed). `map_drums` on the
  shipped index still emits real DPCM events for kick/snare/hi-hat.
- **Dense-remap round-trip (#200)** — `nes/emulator_core.py:214-235` renumbers referenced
  catalog ids to a dense `0..N-1` range and emits `dpcm_sample_map`; both packer call
  sites pass `get_dpcm_sample_ids_from_frames(frames)` into
  `load_dpcm_index_into_packer(sample_ids=...)`. `tests/test_audio_fixes.py`'s
  `test_two_high_sample_ids_get_distinct_notes_not_aliased` and
  `test_dense_remap_still_hits_byte_ceiling_past_255_distinct_ids` both pass — the latter
  documents, as an accepted and tested limitation rather than a silent bug, that a song
  referencing **more than 255** distinct DPCM samples can still alias two dense ids onto
  `note=255`. This is unreachable in practice given the mapper's realistic sample-name
  space (≈50 possible role names total), and is intentionally tested rather than hidden,
  so it is not re-reported as a new finding.
- **`$4011` silence init / register write order** — `nes/mmc3_init.asm:69-70` writes `$00`
  to `$4011` before `$4010`, matching `docs/APU_DMC_REFERENCE.md`'s "Silence
  Initialization" note. Both the direct-export trigger (`exporter_ca65.py:787-827`,
  `play_dpcm`) and the live bytecode trigger (`nes/audio_engine.asm:231-257`,
  `@cmd_dpcm_play`) write `$4010`→`$4012`→`$4013` before the final `$4015` trigger,
  matching §6's documented order.
- **DPCM converter (`dpcm_sampler/dpcm_converter.py`)** — `convert_wav_to_dmc` /
  `dpcm_compress` / `delta_encode` still have no callers outside the module and tests
  (`grep` confirmed no other reference), so the bit-polarity/start-level/resample
  assumptions flagged in prior audits remain non-shipping-ROM paths. Not re-filed.
- **Sample manager (#69/#70/#71)** — monotonic `_next_id`, unified `metadata['size']`
  memory accounting, and the removed similarity/dedup code all remain in place; no
  regression.
- **`dpcm_index.json` schema** — still exactly `id` + `filename` per entry (1941 entries,
  confirmed via direct load); `length`/`data`/`frequency`/`pitch` still fall back to
  defaults on real input, consistent with the removed dead code that depended on them.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-07-18.md
```
