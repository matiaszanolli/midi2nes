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
> genuinely open (Dimension 6). #75 (the `length_reg` rounding) was closed on GitHub,
> then regressed, and was re-fixed on this tree as #295 (commit `d392ef6`) —
> `_place_sample` now ceils, so Dimension 4's item is fixed (#295); verify it holds.

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
  (`dpcm_sampler/enhanced_drum_mapper.py:468-500`) no longer stops at the first
  candidate — it tries the velocity-split name, then the advanced `"primary"` name,
  then the `DEFAULT_MIDI_DRUM_MAPPING` role name, in that order, and only returns
  `None` (→ noise fallback) if none of the three exist in `self.sample_index`.
  Verify this cascade actually reaches the index for a name like `kick_soft`
  that legitimately isn't present (falls through to `"kick"` then to the default
  role name) rather than silently dropping.
- **#DP-DPCM-12 is CLOSED**: the note-off skip in `map_drums` used to read
  `e.get('velocity', 0)` only. Real parsed MIDI events from `tracker/parser_fast.py`
  carry **`volume`**, not `velocity` — so the key defaulted to `0` on every real event
  and the whole legacy-mode drum-detection loop was dead code on real input, skipping
  every note as if it were a note-off. It now reads
  `velocity = event_velocity(e)` (`core/events.py`, migrated by #460/TD-40 from the
  hand-rolled `e.get('velocity', e.get('volume', 0))`) before the zero test. Verify-
  the-fix: this bug was invisible to the test suite because the fixtures used synthetic
  `velocity`-keyed events. Any check here must exercise **parser output**, not
  hand-built dicts — and the same grep (`get('velocity'` with no `event_velocity` call)
  should come back clean across `dpcm_sampler/`. A regression silently drops every drum
  in legacy mode.
- **#460/TD-40 is CLOSED**: the "defensive dual-key idiom" this bullet used to describe
  was hand-rolled separately at 15 sites across `tracker/`, `nes/`, `arranger/`, and
  `dpcm_sampler/`, and had already diverged on both key precedence and missing-key
  default — the very comment `ffccf51` added here claimed uniformity with
  `tracker/track_mapper.py` that didn't exist (that module was `volume`-first at the
  time; this one wrote `velocity`-first). All 15 sites now share one implementation,
  `core.events.event_velocity(event, default=0)`: `velocity` wins when both keys are
  present with different values, and a missing-both event defaults to 0 (silent/
  note-off) except at two call sites that deliberately override the default for their
  own semantics (`tracker/pattern_detector.py`'s drum-pattern similarity scorer keeps
  `default=100`, justified since a genuinely missing value there should read as
  "typical" not "silent"; `arranger/pipeline_integration.py`'s note-on/off read had its
  divergent `default=100` dropped to 0 at migration, since it had no comparable
  justification and defaulted a malformed event to a spurious note-on instead of a
  no-op). Verify-the-fix: grep for `get('velocity'.*get('volume'` /
  `get('volume'.*get('velocity'` — it should return nothing outside `core/events.py`
  and its own test file.
- `_get_advanced_sample` (`enhanced_drum_mapper.py:452-466`) selects by
  `velocity_ranges`; its result is now just one candidate in the fallback chain
  above rather than a hard commit — confirm a nonexistent velocity-split name no
  longer kills the whole event, only that one candidate.

### Dimension 2: `dpcm_index.json` schema integrity
The index is loaded in the same three places, still against two different shapes:
- `EnhancedDrumMapper._load_sample_index` (`dpcm_sampler/enhanced_drum_mapper.py:279-292`)
  reads the raw index; entries reach `DPCMSampleManager.allocate_sample`
  (`dpcm_sampler/dpcm_sample_manager.py:15-65`, reads `sample_data.get('length', 1024)`
  at line 34, `sample_data.get('data', [])` at line 55, `sample_data.get('frequency',
  33144)` at line 58) only through the shared `_allocate` helper (`enhanced_drum_mapper.py:
  263-272`), not directly.
- The real `dpcm_index.json` entries only contain **`id`** and **`filename`** (verify:
  `python -c "import json;
  print(list(json.load(open('dpcm_index.json')).values())[0])"`) — `data` and `frequency`
  still always fall back to `allocate_sample`'s defaults on real input; there is no wav
  data or per-sample frequency anywhere in the index to backfill them from. **#341/
  DP-DPCM-02 is CLOSED for `length`**, though: it used to fall back to the same 1024-byte
  placeholder for every sample, making memory-limit/eviction accounting operate on
  identical fictional sizes. `_allocate` (`enhanced_drum_mapper.py:252-261`) now resolves
  each sample's real on-disk size via `_real_sample_size` (`:229-260`, mirrors
  `generate_dpcm_index.resolve_dpcm_sample_path` — the same resolution the packer itself
  uses, cached per sample name in `self._sample_size_cache` so a drum reused many times in
  one song costs one `os.path.getsize` call) and injects it into `sample_data['length']`
  before calling `allocate_sample`, through the one shared call site both `map_drums`
  callers use (`:350`, `:416`) so a fix to one path can't silently miss the other. Note
  this only makes `DPCMSampleManager`'s own internal accounting reflect reality — the
  eviction machinery still has no effect on what actually gets packed into the ROM
  (packing is driven by frame references via `pack_dpcm_into_asm`, not
  `sample_manager.active_samples`); that remains unchanged and out of scope here.
  **#413/DP-DPCM-07 is CLOSED**: the "costs one `os.path.getsize` call" cache guarantee
  above only held for the successfully-resolved case -- both early-return `None` paths (no
  `filename` key, and `resolve_dpcm_sample_path` returning `None`) returned directly
  without writing to `self._sample_size_cache`, so a catalog sample that never resolves
  (a `.dmc` moved/deleted from the `dmc/` root) re-ran the full candidate-path probe (up to
  3 `Path.exists()` stats) on every occurrence in the song, not just the first. Both paths
  now cache `None` before returning; the cache-hit check (`sample_name in
  self._sample_size_cache`) already worked correctly for a cached `None` since
  `dict.__contains__` doesn't inspect the stored value. Verify-the-fix: confirm
  `_real_sample_size` returns `None` (falls back to the 1024 placeholder, not a crash) when
  `resolve_dpcm_sample_path` can't find the file, and that `data`/`frequency` are still
  correctly understood as permanent placeholders, not a second instance of the same bug.
  What *did* change earlier (#70/#71, see Dimension 7) is that the sample manager uses one
  consistent accounting formula for those remaining defaults instead of two divergent ones,
  and the now-dead similarity/dedup code that also depended on `data` was removed outright
  rather than left silently inert.
- The packer path moved: `dpcm_sampler/generate_dpcm_index.py:load_dpcm_index_into_packer`
  (lines 38-79) is now called from a single shared `main.py:pack_dpcm_into_asm`
  helper (`main.py:126-215`), not duplicated inline at the two call sites. **#380/TD-28
  is CLOSED**: `run_export` and `run_full_pipeline` previously had copy-pasted,
  already-diverged DPCM-pack blocks (`run_export` never passed `verbose=`) — both now
  just call `pack_dpcm_into_asm(frames, asm_path, verbose=...)` (`main.py:709` and
  `main.py:1250` respectively) and format their own status line from the returned
  `DpcmPackResult`. It reads `sample.get('pitch', 15)` (line 75) and `sample['filename']`
  (line 66) — `pitch` is still absent from the shipped index. Confirm `id`/`filename`
  remain the only keys any consumer can rely on, that `generate_dpcm_index`
  (`dpcm_sampler/generate_dpcm_index.py:82-102`) is still the sole writer (it emits
  exactly `id` + `filename`), and that no future edit re-forks the two call sites back
  into separate copies.

### Dimension 3: DPCM conversion correctness (1-bit delta)
`dpcm_sampler/dpcm_converter.py` does WAV→PCM→delta→packed-bits. It remains
orphaned (nothing in the pipeline calls it; `generate_dpcm_index` scans pre-made
`.dmc` files directly) but its known assumption bugs were fixed (#342/DP-DPCM-03,
#448/DPCM-2026-08-21-5):
- `delta_encode` walks a ±2 step counter (per `docs/APU_DMC_REFERENCE.md`, a `1`
  bit **adds 2** to the output level and `0` **subtracts 2** — the engine never
  sets a level, only nudges ±2). Its input is 8-bit unsigned PCM (0-255) from
  `convert_wav_to_unsigned_pcm`, halved (`sample >> 1`) onto the tracker's own
  0-127 scale before each comparison. **Fixed (#448, verify)**: it previously
  stepped ±1 and compared the raw unnormalized 0-255 `sample` directly against
  the 0-127 `prev` — PCM silence (128) sat entirely above the tracker's ceiling,
  so any signal near silence permanently pinned `prev` at 127 and biased the
  whole encode, and the ±1 step modeled half the amplitude hardware actually
  reconstructs.
  **Fixed (#342, verify)**: the start-level assumption was `prev = 0x40`
  (mid-range); the engine's init routine writes `$00` to `$4011` before any
  sample plays (docs/APU_DMC_REFERENCE.md §5), so `prev` now starts at `0x00` to
  match the real hardware level a played-back sample reconstructs from, instead
  of producing a startup DC ramp/attack transient that doesn't exist on the
  actual playback path.
- `dpcm_compress` derives one bit per `encoded` value, including the transition
  from `delta_encode`'s own init level (0) into `encoded[0]`. **Fixed (#448,
  verify)**: it previously started the loop at `encoded[1]`, so that first real
  step was never bit-emitted and playback started one step offset from the
  modeled reconstruction.
- Bit packing order: `byte |= (bits[i+j] << j)` packs LSB-first, matching the DMC
  shifter's actual consumption order (`docs/APU_DMC_REFERENCE.md` §3, now stated
  explicitly there per #448) — wrong bit order plays the sample bit-reversed
  (audible garbage).
- Resampling: `convert_wav_to_unsigned_pcm` (line 7) uses `np.interp` linear
  resampling to `sample_rate`, independent of the DMC rate index written elsewhere
  (`pitch`/`$4010`). **Fixed (#342, verify)**: the default was a fixed
  `sample_rate=8000` regardless of the packer's playback rate, so a sample
  converted then packed at both defaults played ~4x too fast (~2 octaves sharp).
  Both `dpcm_converter`'s default `sample_rate` and `DpcmPacker.add_sample`'s
  default `pitch_rate=15` now derive from the same shared constants
  (`constants.DEFAULT_DMC_RATE_HZ` / `DEFAULT_DMC_PITCH_RATE`, 33144 Hz), so the
  two defaults can't silently drift apart again — but the module still has no
  NTSC rate-index table for the other 15 `pitch_rate` values; a caller targeting
  a different rate must pass a matching `sample_rate` explicitly (documented in
  `convert_wav_to_dmc`'s docstring). Flag any remaining mismatch between the
  conversion rate and the playback rate index that would pitch-shift samples.

### Dimension 4: Sample size / address / DMC range constraints
`dpcm_sampler/dpcm_packer.py` computes the `$4012`/`$4013` register values:
- **Fixed (#75 → regressed → #295/DP-01) — verify it holds**: `_place_sample`
  computes `dpcm_address_val = (start_address - 0xC000) // 64` and
  `dpcm_length_val = self._length_reg(sample['size'])` (the ceiling/floor-at-1
  formula factored into the `_length_reg` static method by #446/#447, shared
  with `add_sample`'s block-sizing — see below). Verify against
  `docs/APU_DMC_REFERENCE.md`: address = `$C000 + A*64`, length = `(L*16)+1`
  bytes. `length_reg` uses **ceiling** division (`(size + 14) // 16` =
  ceil((size-1)/16)) so a `size` not of the form `16k+1` still gets its full
  tail read. This is the flooring bug originally closed as #75 that
  regressed and was re-fixed as #295 (commit `d392ef6`); confirm the ceiling
  still holds and that `size` stays bounded to 4081 so the 8-bit register
  can't overflow.
- **Fixed (#446/DPCM-2026-08-21-3, verify)**: the `.align 64` gap comment used
  to claim the ceiling read's extra bytes were "safe zero-pad" — false when
  `size` lands exactly on (or just under) a 64-byte boundary: `.align 64`
  inserts nothing when already aligned, so the next sample starts immediately
  at the read's overrun offset, and a bank-ending sample's overrun instead
  reads an arbitrary byte from the fixed PRG bank. `add_sample` now sizes each
  sample's `aligned_size` block to `max(ceil(size/64)*64, ceil(read_length/64)*64)`
  where `read_length = length_reg*16+1`, guaranteeing the reserved block always
  covers the engine's actual read. Verify no code path still assumes
  `aligned_size == ceil(size/64)*64` alone is sufficient.
- **Fixed (#447/DPCM-2026-08-21-4, verify)**: `length_reg == 0` is reused
  elsewhere (`generate_assembly`'s positional lookup tables, below) as the
  "never packed" sentinel for a sparse catalog. A genuinely packed 0- or
  1-byte sample's own `(size+14)//16` formula also computed 0, making it
  indistinguishable from an unpacked slot and silently un-triggerable.
  `_length_reg` now floors at 1 for any packed sample (`max(1, ...)`), so
  `length_reg` can only be 0 for a slot `_place_sample` never wrote --
  confirm no packed sample can still produce 0.
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
  Live on the bytecode path: `nes/audio_engine.asm:181` writes `LDA #$00` / `STA $4011`
  at `audio_init`. **#348/NH-HW-1 is CLOSED**: the direct-export `init_music`/`reset`
  no longer omits it — see `/audit-nes-hardware` Dimension 4 for the exact
  `exporter/exporter_ca65.py` line numbers across all three `init_music`/`reset`
  variants; nes/mmc3_init.asm, which also had this write, was deleted as dead
  code, #203. The live DPCM trigger is `@write_dpcm` (`nes/audio_engine.asm`, ~line
  512), which writes `$4010` → `$4012` → `$4013` then toggles `$4015`
  (disable-then-enable-with-DMC), matching `docs/APU_DMC_REFERENCE.md`; re-verify this
  order is still correct if the trigger routine changes. (The old
  `seq_cmd_dpcm_play`/`seq_cmd_instrument` copies in `nes/project_builder.py` were
  removed as dead code — #314/EXP-12; only the live `fetch_sequence_byte` remains.)
- DMA cost: `docs/NES_DMA_REFERENCE.md` notes each DMC DMA steals 3–4 CPU cycles and
  a heavy drum catalog fires constantly, delaying OAM DMA and corrupting
  side-effect reads (`$4016`/`$2007`/`$4015`). This subsystem can't avoid the cost,
  but flag if the generated engine/docs omit the mandatory DPCM-safe controller-read
  warning, or if rapid back-to-back triggers are emitted with no awareness of the
  cycle budget.

### Dimension 6: Config robustness (`DrumMapperConfig`)
`dpcm_sampler/enhanced_drum_mapper.py` defines `DrumPatternConfig` (line 13),
`SampleManagerConfig` (line 54), `DrumMapperConfig` (line 96) with `validate()` /
`to_file` / `from_file` (line 164):
- **Fixed (#76/D-13, verify)**: `from_file` (lines 164-196) does
  `DrumPatternConfig(**config_data.get('pattern_detection', {}))` (line 171) and the
  equivalent for `SampleManagerConfig` (line 174) — an unexpected/renamed key in the
  JSON used to raise an uncaught `TypeError` (only `FileNotFoundError` and
  `json.JSONDecodeError` were handled). It now also catches `TypeError` and re-raises
  a clear `ValueError` (`except TypeError as e: raise ValueError(f"Invalid
  configuration key in {config_path}: {e}")`, lines 195-196), and `result.validate()`
  still runs before the constructed config is returned (line 189) — fixed in `3b905fc`
  (2026-07-18), covered by
  `tests/test_drum_mapper_config.py::test_stray_key_raises_clear_error`. Verify-the-fix:
  confirm the `except TypeError` clause is still present and still wraps the same
  `TypeError` a stray/renamed key raises (not narrowed to catch less), and that
  `result.validate()` hasn't been reordered to run before construction can fail. Note
  the current blast radius: the CLI `--config` flag that used to feed
  `main.py:load_config` into this path was intentionally removed (#13) because nothing
  wired it to `assign_tracks_to_nes_channels` — so today `from_file` is reachable only
  via direct API use (and is exercised by `tests/test_drum_mapper_config.py`), not the
  CLI.
- `validate()` (`DrumMapperConfig.validate`, line 111) enforces weight sums ≈ 1 and
  ranges. `EnhancedDrumMapper.__init__` (line 207) calls `self.config.validate()`
  unconditionally on whatever config object it holds (line 209), so a config passed in
  after `DrumMapperConfig.from_file(...)` **is** validated before use, so long as it's
  routed through `EnhancedDrumMapper.__init__` — confirm there's no path that uses
  a `from_file`-loaded config directly without going through that constructor.
- `SampleManagerConfig.memory_limit` is bounded 1KB–16KB and `max_samples` 1–64
  (lines 78-81), but `DPCMSampleManager.__init__` defaults
  (`max_samples=16, memory_limit=4096`) are declared independently
  (`dpcm_sampler/dpcm_sample_manager.py:5`). In the current codebase the only
  production instantiation site is `EnhancedDrumMapper.__init__`
  (`enhanced_drum_mapper.py:216-219`), which always passes the validated config
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
(line 238; called from `main.py:run_map` and the full pipeline):
- It calls `map_drums_to_dpcm` and routes results: `nes_tracks['dpcm'] = dpcm_events`
  (line 351, still overwrites any prior dpcm assignment) and `noise_events` only land on
  `noise` if it's still empty (lines 354-355). **Fixed, but only partially (#74/D-11)**:
  when `noise` is already occupied, the drum noise-fallback events are still discarded
  (this is physically unavoidable — NES has one Noise channel, per
  `docs/APU_NOISE_REFERENCE.md`) — but this is no longer silent: a `print(...)`
  warning now reports how many events were dropped and why
  (`tracker/track_mapper.py:361-363`). Verify the count in the warning matches
  `len(noise_events)` exactly and that this is the only discard path for these
  events.
- **#DP-DPCM-13 is CLOSED — the dpcm slot is no longer a dumping ground.** The
  leftover-track loop used to route any remaining *pitched* track into
  `nes_tracks['dpcm']` when that slot was empty ("try noise + dpcm if drum-like or just
  fill up"). But the dpcm slot's downstream consumers (`nes/emulator_core.py`, and now
  `_song_has_dpcm_events` in `main.py`) expect `{'sample_id', ...}` catalog-reference
  events, not raw pitched note data — so a genuine melodic track landing there collapsed
  into bogus repeated sample-id-0 triggers with no trace. The loop now routes only
  drum-named tracks to `noise` and drops anything else with a loud per-track warning
  (`tracker/track_mapper.py:334-343`). Verify-the-fix: the two event shapes that share
  this dict are still structurally distinguishable, and nothing else in the codebase
  writes non-`sample_id` events into `nes_tracks['dpcm']` — a single such write is
  CRITICAL (it corrupts the channel *and* now trips the `song build` DPCM rejection for
  a song that has no real drums).
- **#256/D-18 is CLOSED** (fixed in `7853aa4`, predates this sync but the prose here
  was never updated): the hardcoded default `'dpcm_index.json'` path used to raise a
  bare `FileNotFoundError` out of `_load_sample_index`
  (`enhanced_drum_mapper.py:216-219`) uncaught inside the standalone `map` subcommand.
  `run_map` (`main.py:226-242`) now checks `Path(dpcm_index_path).exists()` up front
  (honoring `--dpcm-index` too, #13) and exits with a clean `[ERROR] DPCM index not
  found: ...` message instead of a raw traceback — matching every other step-by-step
  guard in `main.py` (`load_json_stage`, #120). `run_full_pipeline`'s outer
  `try/except Exception` (`main.py:1346-1347`, `[ERROR] Pipeline failed: ...`) is
  still the backstop for anything `run_map`'s own guard doesn't catch, and the pipeline
  still aborts entirely there rather than degrading to a drumless build — in contrast
  to the DPCM *packer* path (`main.py:pack_dpcm_into_asm`, shared by `run_export`/
  `run_full_pipeline`, see the packer-path note above), which explicitly handles a
  missing index file gracefully ("No dpcm_index.json found, skipping"). Verify-the-fix:
  confirm `run_map` still exits 1 (not a partial/degraded mapped.json) on a missing
  index, and that `--dpcm-index` pointing at a nonexistent path hits the same guard.
- **Fixed, verify (#9, #66, #67, #200/D-14, #254)**: `dpcm_events` carry `{frame,
  sample_id, velocity}`; the frame-generation stage (`nes/emulator_core.py:188-235`)
  remaps the raw catalog `sample_id`s a song actually references to a dense,
  song-local `0..N-1` range (`dense_id_of`, line 218) and encodes
  `note = min(255, dense_id + 1)` (line 227; 0 stays the rest sentinel), emitting a
  `dpcm_sample_map` (dense_id → catalog_id) side table (lines 232-235) so the pack
  stage can resolve the real sample files. This replaced both the old 0-95 tone-note
  clamp (#67) and the raw `min(255, sample_id + 1)` that aliased every catalog id
  ≥ 255 onto note 255 (#200/D-14); the `MAX_SAFE_SAMPLE_ID = 254` guard that used to
  pre-empt the remap and route all shipped-catalog drums to noise is also gone (#254).
  The exporter (`exporter/exporter_ca65.py`) applies the same byte-ceiling for the
  `'dpcm'` channel and the generated trigger routine (`nes/project_builder.py`)
  recovers the sample via `note - 1`. Confirm the round-trip holds when a song
  references near 254 *distinct* drums (`dense_id + 1` must stay ≤ 255), not merely
  when a raw catalog id is near 254.

## Skeptical checklist
- [ ] Does an unmapped/rare GM drum note (e.g. 47, mid tom) still resolve through
      `DEFAULT_MIDI_DRUM_MAPPING`, or does it now silently fail some other way?
- [ ] Does the velocity → primary → default fallback chain in
      `_resolve_dpcm_sample_name` ever return a name that isn't actually in
      `self.sample_index` (a logic gap in the final `for name in candidates` loop)?
- [ ] Do `length`/`data`/`frequency` ever come from the real index, or always
      defaults — and does that still matter now that the dead similarity/dedup
      code that depended on `data` has been removed?
- [ ] Does `DpcmPacker._length_reg` (`max(1, (size+14)//16)`, ceiling with a
      floor-at-1) read the full sample tail for a sample not sized `16k+1`
      (#75 regressed, re-fixed as #295 — verify), and does every packed
      sample's `aligned_size` block still cover that read even when `size`
      lands on a 64-byte boundary (#446, verify)?
- [ ] Does `DrumMapperConfig.from_file` still raise an uncaught `TypeError` on a
      stray config key (#76, unfixed)?
- [ ] Can an evicted sample id still be reused now that `_next_id` is monotonic —
      or is there an edge case (overflow, reset) that reintroduces reuse?
- [ ] Is the memory limit actually enforced end-to-end now that both call sites use
      `metadata['size']`, including the up-front `pending_size` check?
- [ ] When a real noise track exists, are drum noise-fallback hits still discarded
      — and is the new warning message accurate?
- [ ] Does the `dpcm` channel's dense-remapped id survive correctly into `music.asm`
      when a song references near 254 *distinct* drums (`dense_id + 1` must stay ≤ 255)?
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
