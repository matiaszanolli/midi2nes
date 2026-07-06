---
description: "Audit DPCM/drum sampling — drum mapping, sample conversion, DMC constraints"
argument-hint: "[--focus <dims>]"
---

# DPCM / Drum-Sampling Audit

Audit the DPCM/drum subsystem — how MIDI General-MIDI percussion notes become DPCM
samples, how `.wav` is converted/packed into NES 1-bit delta data, and how the DMC
channel is driven. This subsystem owns everything under `dpcm_sampler/` plus the
DMC-facing edges of the channel pipeline and the CA65 exporter.

Shared protocol (layout, dedup, finding format): `.claude/commands/_audit-common.md`.
Severity rubric: `.claude/commands/_audit-severity.md`. Do not restate them.

Hardware claims **must** cite `docs/APU_DMC_REFERENCE.md` (register map, the
`$C000 + A*64` address formula, the `(L*16)+1` length formula, 64-byte address
alignment, the 0–127 output-level clamp, the `$FFFF`→`$8000` address-wrap quirk) and
`docs/NES_DMA_REFERENCE.md` (DMC DMA steals 3–4 CPU cycles per byte and is the source
of the controller/`$2007`/`$4015` extra-read glitch). Prefer those docs over
re-deriving APU behavior from source.

A dropped or out-of-range drum sample removes audible content, so per
`_audit-severity.md` it is at least MEDIUM, and HIGH when it silently strips a hit
that the MIDI clearly intended.

> **Sprint note**: a large bug-fixing pass (commits `be4d2bd`…`8225696`) closed most
> of the issues this audit used to lead with (#64–#74, #140). The dimensions below
> describe the **current** (fixed) behavior and ask you to verify the fix holds up
> under edge cases, rather than re-discovering the original bugs. #76 remains
> genuinely open (Dimension 6). #75 is marked CLOSED on GitHub, but its fix (the
> `length_reg` rounding commit) has **not** merged to `master`, so on this working
> tree the bug is still live — verify Dimension 4 against the code, not the tracker.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,4`). Default: all.

## Extra Per-Finding Field
- **Hardware ref**: the `docs/APU_DMC_REFERENCE.md` / `docs/NES_DMA_REFERENCE.md`
  section backing any hardware claim (omit for pure-software findings).

## Dimensions

### Dimension 1: Drum-note → sample mapping & coverage
The GM-note maps live in `dpcm_sampler/drum_engine.py`
(`DEFAULT_MIDI_DRUM_MAPPING` lines 8-56, `ADVANCED_MIDI_DRUM_MAPPING` lines 58-78).
Mapping resolution is in `EnhancedDrumMapper._resolve_dpcm_sample_name` and
`map_drums` (`dpcm_sampler/enhanced_drum_mapper.py`):
- **Fixed (#73/D-10, verify)**: `DEFAULT_MIDI_DRUM_MAPPING` now covers the full GM
  percussion range 35–81 with generic role names (kick/snare/tom/cymbal/etc, not
  just 7 notes). `ADVANCED_MIDI_DRUM_MAPPING` still only hand-tunes velocity splits
  for notes 36 and 38; every other note relies on the `DEFAULT_MIDI_DRUM_MAPPING`
  fallback by design (see the trailing comment at
  `dpcm_sampler/drum_engine.py:75-77`). Confirm a mid-range note (e.g. 47, mid tom)
  still resolves to a real sample name and not `None`.
- **Fixed (verify)**: `_resolve_dpcm_sample_name`
  (`dpcm_sampler/enhanced_drum_mapper.py:390-418`) no longer stops at the first
  candidate — it tries the velocity-split name, then the advanced `"primary"` name,
  then the `DEFAULT_MIDI_DRUM_MAPPING` role name, in that order, and only returns
  `None` (→ noise fallback) if none of the three exist in `self.sample_index`.
  Verify this cascade actually reaches the index for a name like `kick_soft`
  that legitimately isn't present (falls through to `"kick"` then to the default
  role name) rather than silently dropping.
- Velocity-0 note-offs are correctly skipped
  (`if e.get('velocity', 0) == 0: continue`, `enhanced_drum_mapper.py:254-255`).
- `_get_advanced_sample` (`enhanced_drum_mapper.py:374-388`) selects by
  `velocity_ranges`; its result is now just one candidate in the fallback chain
  above rather than a hard commit — confirm a nonexistent velocity-split name no
  longer kills the whole event, only that one candidate.

### Dimension 2: `dpcm_index.json` schema integrity
The index is loaded in the same three places, still against two different shapes:
- `EnhancedDrumMapper._load_sample_index` (`dpcm_sampler/enhanced_drum_mapper.py:211-224`)
  passes each entry as `sample_data` to `DPCMSampleManager.allocate_sample`
  (`dpcm_sampler/dpcm_sample_manager.py:15-65`), which reads
  `sample_data.get('length', 1024)` (line 34), `sample_data.get('data', [])`
  (line 55), and `sample_data.get('frequency', 33144)` (line 58).
- **Still true** (this is not a bug that was "fixed", just the current shape of the
  data): the real `dpcm_index.json` entries only contain **`id`** and **`filename`**
  (verify: `python -c "import json;
  print(list(json.load(open('dpcm_index.json')).values())[0])"`). So `length`,
  `data`, and `frequency` still always fall back to defaults on real input. What
  *did* change (#70/#71, see Dimension 7) is that the sample manager now uses one
  consistent accounting formula for those defaults instead of two divergent ones,
  and the now-dead similarity/dedup code that also depended on `data` was removed
  outright rather than left silently inert. Assess whether relying on constant
  placeholder size/frequency for every sample is still an acceptable simplification
  or worth back-filling from the real `.dmc` files at index-generation time.
- The packer path moved: `dpcm_sampler/generate_dpcm_index.py:load_dpcm_index_into_packer`
  (lines 38-79) is now the single shared call site (used from both
  `main.py:run_export` ~lines 317-345 and `main.py:run_full_pipeline` ~lines
  625-670) and reads `sample.get('pitch', 15)` (line 75) and `sample['filename']`
  (line 66) — `pitch` is still absent from the shipped index. Confirm `id`/`filename`
  remain the only keys any consumer can rely on, and that `generate_dpcm_index`
  (`dpcm_sampler/generate_dpcm_index.py:82-102`) is still the sole writer (it emits
  exactly `id` + `filename`).

### Dimension 3: DPCM conversion correctness (1-bit delta)
`dpcm_sampler/dpcm_converter.py` does WAV→PCM→delta→packed-bits. This file has not
changed in the recent fix sprint — the following are still open, unverified claims:
- `delta_encode` (lines 34-42) walks a ±1 step counter, but `dpcm_compress`
  (lines 45-66) then re-derives the bit purely from `encoded[i] > encoded[i-1]`.
  Check that the two stages agree and that the bit polarity matches hardware: per
  `docs/APU_DMC_REFERENCE.md`, a `1` bit **adds 2** to the output level and `0`
  **subtracts 2** (the engine never sets a level, only nudges ±2). A constant-input
  run encodes all-zero bits ⇒ the level ramps *down* on playback — verify the
  start-level assumption (`prev = 0x40`, line 36).
- Bit packing order (line 63): `byte |= (bits[i+j] << j)` packs LSB-first. Confirm
  against the DMC shifter order in `docs/APU_DMC_REFERENCE.md` ("Reader → Buffer →
  Shifter") — wrong bit order plays the sample bit-reversed (audible garbage).
- Resampling: `convert_wav_to_unsigned_pcm` (line 7) uses `np.interp` linear
  resampling to a fixed `sample_rate=8000`, independent of the DMC rate index
  written elsewhere (`pitch`/`$4010`). Flag any mismatch between the conversion
  rate and the playback rate index that would pitch-shift samples.

### Dimension 4: Sample size / address / DMC range constraints
`dpcm_sampler/dpcm_packer.py` computes the `$4012`/`$4013` register values:
- **Still live on `master` (#75/D-12 is CLOSED on GitHub but its fix is unmerged
  here)**: `_place_sample` (lines 77-89) computes
  `address_reg = (start_address - 0xC000) // 64` (line 78) and
  `length_reg = (sample['size'] - 1) // 16` (line 79). Verify against
  `docs/APU_DMC_REFERENCE.md`: address = `$C000 + A*64`, length = `(L*16)+1` bytes.
  `length_reg` still **floors** rather than rounding up — a `size` not of the form
  `16k+1` makes the round-trip lossy: the engine reads `(length_reg*16)+1` bytes,
  which under-reads the true tail of the sample (truncated playback) for anything
  not exactly `16k+1` bytes. The rounding+`.res`-padding fix that closed #75 lives
  on an unmerged branch, so `master` still floors and is unguarded; confirm against
  the current code and reopen #75 (or land the fix) if so.
- **Fixed (verify)**: the 4081-byte oversized-sample path no longer aborts the pack.
  `DpcmPacker.add_sample` (lines 13-47) now truncates to 4081 bytes when
  `truncate=True` (lines 31-36) instead of always raising `ValueError` — and the
  shared call site `load_dpcm_index_into_packer`
  (`dpcm_sampler/generate_dpcm_index.py:72-77`) always passes `truncate=True`, so
  in practice a too-long sample is clamped, not fatal (#68). `add_sample` still
  raises if a caller explicitly passes `truncate=False`; confirm no current call
  site does that. `dpcm_converter.dpcm_compress` (line 66) independently truncates
  with `dmc_bytes[:4081]` at conversion time — the two truncation points are
  consistent (both clamp to 4081), not contradictory.
- `START_ADDR = 0xC000`, `BANK_SIZE = 8192` (lines 5-6), and the 60-bank ceiling
  (`OverflowError` at line 70). Check `.align 64` in `generate_assembly` (line 100)
  keeps every sample 64-byte aligned, and whether anything guards the
  `$FFFF`→`$8000` address-wrap quirk documented in `docs/APU_DMC_REFERENCE.md`
  (a sample bleeding past `$FFFF` plays garbage from `$8000`).
- **Fixed, verify no regression (#140)**: the packer used to receive the *entire*
  1923-sample catalog regardless of what a song used, overflowing the 60-bank
  budget and silencing percussion on every drummed song. It's now filtered via
  `get_dpcm_sample_ids_from_frames` (`dpcm_sampler/generate_dpcm_index.py:105-117`,
  reads frame `note = sample_id + 1`) passed as `sample_ids=` into
  `load_dpcm_index_into_packer`, so only samples the exported song actually
  references get packed. `generate_assembly` (lines 91-147) now emits sparse
  lookup tables sized to `max_id + 1` with `$00` placeholders for unpacked ids
  (lines 123-146) — verify those placeholder slots are provably unreachable (no
  frame indexes an id that wasn't packed) rather than merely "usually" unreachable.

### Dimension 5: DMC level handling & DMA-timing implications
- **Fixed, verify no regression (#72/D-09)**: the DMC output level (`$4011`)
  `CMD_DMC_LEVEL` ($87) emitter path was removed entirely (commit `5c032d2`) — no
  stage ever produced `dmc_level`, so the branch was dead. Confirm it hasn't been
  re-added; if it is re-added for the `$4011` non-linear-mixer trick
  (`docs/APU_DMC_REFERENCE.md` §6), re-check the level is clamped to the 7-bit
  0–127 range `$4011` accepts before emission.
- Silence init: `docs/APU_DMC_REFERENCE.md` says init should write `$00` to `$4011`
  so the DMC counter doesn't muffle Triangle/Noise via the non-linear mixer.
  Confirmed present: `nes/mmc3_init.asm:68-69` writes `LDA #$00` / `STA $4011`
  before `STA $4010`. `seq_cmd_dpcm_play`
  (`nes/project_builder.py:138-160`) writes `$4010` → `$4012` → `$4013` in that
  order, matching `docs/APU_DMC_REFERENCE.md`; re-verify this order is still
  correct if the trigger routine changes.
- DMA cost: `docs/NES_DMA_REFERENCE.md` notes each DMC DMA steals 3–4 CPU cycles and
  a heavy drum catalog fires constantly, delaying OAM DMA and corrupting
  side-effect reads (`$4016`/`$2007`/`$4015`). This subsystem can't avoid the cost,
  but flag if the generated engine/docs omit the mandatory DPCM-safe controller-read
  warning, or if rapid back-to-back triggers are emitted with no awareness of the
  cycle budget.

### Dimension 6: Config robustness (`DrumMapperConfig`)
`dpcm_sampler/enhanced_drum_mapper.py` defines `DrumPatternConfig` (line 12),
`SampleManagerConfig` (line 53), `DrumMapperConfig` (line 95) with `validate()` /
`to_file` / `from_file` (line 163):
- **Still open (#76/D-13)**: `from_file` (lines 163-191) does
  `DrumPatternConfig(**config_data.get('pattern_detection', {}))` (line 170) and the
  equivalent for `SampleManagerConfig` (line 172) — an unexpected/renamed key in the
  JSON raises `TypeError` (not caught; only `FileNotFoundError` and
  `json.JSONDecodeError` are handled, lines 188-191). No commit in the recent sprint
  touched this. Note the current blast radius: the CLI `--config` flag that used to
  feed `main.py:load_config` (`main.py:462-466`) into this path was intentionally
  removed (`main.py:772-774`, #13) because nothing wired it to
  `assign_tracks_to_nes_channels` — so today `from_file` is reachable only via
  direct API use (and is exercised by `tests/test_drum_mapper_config.py`), not the
  CLI. Still worth fixing/hardening since it's public API surface.
- `validate()` (`DrumMapperConfig.validate`, line 110) enforces weight sums ≈ 1 and
  ranges. `EnhancedDrumMapper.__init__` (line 196) calls `self.config.validate()`
  unconditionally on whatever config object it holds, so a config passed in after
  `DrumMapperConfig.from_file(...)` **is** validated before use, so long as it's
  routed through `EnhancedDrumMapper.__init__` — confirm there's no path that uses
  a `from_file`-loaded config directly without going through that constructor.
- `SampleManagerConfig.memory_limit` is bounded 1KB–16KB and `max_samples` 1–64
  (lines 77-80), but `DPCMSampleManager.__init__` defaults
  (`max_samples=16, memory_limit=4096`) are declared independently
  (`dpcm_sampler/dpcm_sample_manager.py:5`). In the current codebase the only
  production instantiation site is `EnhancedDrumMapper.__init__`
  (`enhanced_drum_mapper.py:203-206`), which always passes the validated config
  values through — direct unvalidated construction only happens in
  `tests/test_dpcm_sample_manager.py`. Low residual risk; flag only if a new
  production call site constructs `DPCMSampleManager` directly.

### Dimension 7: Sample-manager dedup & lifecycle
`dpcm_sampler/dpcm_sample_manager.py` (130 lines):
- **Fixed, verify (#69/D-06)**: `allocate_sample` (lines 15-65) now assigns ids from
  a monotonic `self._next_id` counter (line 13, incremented at line 51) instead of
  `len(self.active_samples)`, so an evicted id is never handed out again to a later
  allocation. Confirm `dpcm_events` emitted before an eviction still resolve to the
  sample that was live when they were created (i.e. nothing re-keys already-emitted
  events).
- **Fixed, verify (#70/D-07)**: memory accounting is now unified — `allocate_sample`
  checks `self._get_total_memory() + sample_size > self.memory_limit` up front
  (line 42, accounting for the pending sample before it's inserted) and
  `_get_total_memory` (lines 120-130) sums `s['metadata']['size']`, the same field
  `allocate_sample` populates (line 57) — previously these used two different
  formulas (one of which, `len(data)//8`, was always 0 for real index data).
  `_optimize_sample_bank` (lines 67-111) now triggers on memory pressure alone, not
  just the sample-count limit (condition at lines 79-81). Verify a
  few-but-large-samples scenario (small `max_samples`, large `metadata.size`) still
  evicts correctly.
- **Removed as dead code, not "fixed to use real data" (#71/D-08)**:
  `_find_similar_sample` / `_calculate_sample_similarity` no longer exist in this
  file — they were deleted (commit `5c032d2`) rather than repaired, since the
  underlying `data` arrays are always empty for real index entries (Dimension 2)
  and the comparison was permanently inert. If similarity-based dedup is
  reintroduced, it needs real waveform data from the index to do anything useful.

### Dimension 8: Channel-pipeline integration (noise vs DMC)
`tracker/track_mapper.py:assign_tracks_to_nes_channels(midi_events, dpcm_index_path)`
(line 179; called from `main.py:run_map` and the full pipeline):
- It calls `map_drums_to_dpcm` (line 244) and routes results:
  `nes_tracks['dpcm'] = dpcm_events` (line 246-247, still overwrites any prior dpcm
  assignment) and `noise_events` only land on `noise` if it's still empty
  (lines 249-251). **Fixed, but only partially (#74/D-11)**: when `noise` is
  already occupied, the drum noise-fallback events are still discarded (this is
  physically unavoidable — NES has one Noise channel, per
  `docs/APU_NOISE_REFERENCE.md`) — but this is no longer silent: a `print(...)`
  warning now reports how many events were dropped and why
  (`tracker/track_mapper.py:253-259`). Verify the count in the warning matches
  `len(noise_events)` exactly and that this is the only discard path for these
  events.
- The hardcoded default `'dpcm_index.json'` path means a missing file still raises
  inside `_load_sample_index` (`enhanced_drum_mapper.py:216-219`,
  `FileNotFoundError`). This is **not caught** in the standalone `map` subcommand
  (`main.py:run_map`, lines 74-82) — that path still crashes with a raw traceback,
  unlike every other step-by-step guard in `main.py` (`load_json_stage`, #120).
  `run_full_pipeline` fares better only because its whole body is wrapped in one
  outer `try/except Exception` (`main.py:~992-997`) that turns any such crash into
  a clean `[ERROR] Pipeline failed: ...` message — but the pipeline still aborts
  entirely rather than degrading to a drumless build, in contrast to the DPCM
  *packer* path (`main.py:run_export`/`run_full_pipeline`), which explicitly
  handles a missing index file gracefully ("No dpcm_index.json found, skipping").
  Assess whether `run_map` should get the same guard as the packer path.
- **Fixed, verify (#9, #66, #67)**: `dpcm_events` carry `{frame, sample_id,
  velocity}`; the frame-generation stage
  (`nes/emulator_core.py:188-212`) now encodes `note = sample_id + 1` (0 stays the
  rest sentinel) with a byte ceiling `min(255, sample_id + 1)` (line 209) rather
  than the old 0-95 tone-note clamp that used to collapse every id ≥ 94 to one
  sample (#67). The exporter (`exporter/exporter_ca65.py:263-273`, `~975-991`)
  applies the same byte-ceiling logic for the `'dpcm'` channel specifically
  (clamped to 255, not 95) and the generated trigger routine
  (`nes/project_builder.py:~692-716`) recovers `sample_id = note - 1`. Confirm this
  round-trip still holds for `sample_id` values near the 254 ceiling
  (`sample_id + 1` must stay ≤ 255).

## Skeptical checklist
- [ ] Does an unmapped/rare GM drum note (e.g. 47, mid tom) still resolve through
      `DEFAULT_MIDI_DRUM_MAPPING`, or does it now silently fail some other way?
- [ ] Does the velocity → primary → default fallback chain in
      `_resolve_dpcm_sample_name` ever return a name that isn't actually in
      `self.sample_index` (a logic gap in the final `for name in candidates` loop)?
- [ ] Do `length`/`data`/`frequency` ever come from the real index, or always
      defaults — and does that still matter now that the dead similarity/dedup
      code that depended on `data` has been removed?
- [ ] Is `length_reg = (size-1)//16` still lossy for a sample not sized `16k+1`
      (#75 closed on GitHub, but its fix is unmerged so `master` still floors)?
- [ ] Does `DrumMapperConfig.from_file` still raise an uncaught `TypeError` on a
      stray config key (#76, unfixed)?
- [ ] Can an evicted sample id still be reused now that `_next_id` is monotonic —
      or is there an edge case (overflow, reset) that reintroduces reuse?
- [ ] Is the memory limit actually enforced end-to-end now that both call sites use
      `metadata['size']`, including the up-front `pending_size` check?
- [ ] When a real noise track exists, are drum noise-fallback hits still discarded
      — and is the new warning message accurate?
- [ ] Does the `dpcm` channel's `sample_id`/`velocity` still survive correctly into
      `music.asm` at the top of the id range (near 254)?
- [ ] Does packing only referenced samples (#140) ever leave a frame pointing at an
      id that wasn't packed (a `$00` placeholder misread as a real sample)?

For every hardware claim, re-open the cited `docs/APU_DMC_REFERENCE.md` /
`docs/NES_DMA_REFERENCE.md` line and confirm before reporting. Attempt to disprove
each finding (per `_audit-common.md`) before including it.

## Output
Write the report to: **`docs/audits/AUDIT_DPCM_<TODAY>.md`** (YYYY-MM-DD).

Structure:
1. **Summary** — finding counts by severity, the highest-risk drop/round-trip issues.
2. **Findings** — base format from `_audit-common.md` plus the `Hardware ref` field.

Then suggest:
```
/audit-publish docs/audits/AUDIT_DPCM_<TODAY>.md
```
</content>
