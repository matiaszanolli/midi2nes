# DPCM / Drum-Sampling Audit — 2026-08-06

Scope: `dpcm_sampler/` plus the DMC-facing edges of the channel pipeline
(`tracker/track_mapper.py`, `nes/emulator_core.py`, `nes/audio_engine.asm`,
`exporter/exporter_ca65.py`, `main.py` pack call sites). Hardware claims
verified against `docs/APU_DMC_REFERENCE.md` and `docs/NES_DMA_REFERENCE.md`.

`gh issue list` was unreachable from this sandbox (no network egress to
`api.github.com`); deduplication instead relied on the prior audit report
(`docs/audits/AUDIT_DPCM_2026-08-05.md`), the checked-in `.claude/issues/<N>/ISSUE.md`
snapshots, and `git log` against every commit that landed since 2026-08-05.

## 1. Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 0 |
| LOW      | 1 |
| **Total**| **1** |

New: 1 · Existing (re-confirmed still valid, unchanged): 8 · **Newly confirmed FIXED since the 2026-08-05 audit: 6** (#137, #167, #202, #348, #367, #380 — plus partial fixes folded into #341 and #342's still-open remainder).

**This was an unusually active cycle.** Five commits landed between the
2026-08-05 audit and now (`fe8c5b3`, `24e51d2`, `06e1e04`, `90b4582`, `20f627e`,
all dated 2026-08-05 23:18 through 2026-08-06 17:17), closing out most of the
DPCM-subsystem backlog the last several audits had been re-confirming as open:

- **#367/DP-DPCM-05 (was MEDIUM, open) — now FIXED.** `_emit_dpcm_proc`
  (`exporter/exporter_ca65.py:545-601`, part of today's `_emit_*` extraction)
  and the bytecode engine's `@write_dpcm` (`nes/audio_engine.asm:512-547`,
  fixed earlier in `24e51d2`) both now read `dpcm_len_table,y` and skip the
  trigger entirely (`beq @done`) when a dense id's slot is the unpacked `$00`
  placeholder, instead of firing the DMC on a 1-byte garbage read. `main.py`'s
  `pack_dpcm_into_asm` (`main.py:126-199`) also now names every dropped
  sample in a loud (non-verbose-gated) warning built from `skipped_details`,
  closing the "count discarded" half of this issue (`main.py:177-193`).
- **#380/TD-28 (was LOW, open) — now FIXED.** `run_export`/`run_full_pipeline`'s
  previously-duplicated, already-diverged DPCM-pack blocks are now both
  `pack_dpcm_into_asm(frames, asm_path, verbose=...)` calls (`main.py:709`,
  `main.py:1097`) sharing one `DpcmPackResult`-returning helper.
- **#348 (cross-filed, was open) — now FIXED.** Direct-export `init_music`
  and `reset` (`exporter/exporter_ca65.py:783-788`, `:944-948`) now zero
  `$4011` on entry, matching the bytecode engine's `audio_init`.
- **#202/D-16 (was open) — now FIXED.** `_handle_pattern_event`
  (`dpcm_sampler/enhanced_drum_mapper.py:385-410`) now takes and forwards
  `use_advanced` into `_resolve_dpcm_sample_name`, instead of silently always
  resolving pattern-matched hits with `use_advanced=True` regardless of what
  `map_drums`'s caller asked for.
- **#137/TD-08 (was open) — now FIXED.** The stale `.incbin`-not-yet-inserted
  TODO in the macro-bytecode `"DPCM"` segment (`exporter/exporter_ca65.py:1086-1096`)
  was replaced with an accurate comment explaining the segment is
  deliberately left empty.
- **#341/DP-DPCM-02 — partially fixed, already noted last cycle and
  re-confirmed still holding.** `length` now backfills the real on-disk size
  via `_real_sample_size`/`_allocate` (`enhanced_drum_mapper.py:227-261`); the
  "eviction has no effect on the packed ROM" characteristic is unchanged by
  design (packing is driven by frame references, not sample-manager state).

One new LOW finding surfaced while re-verifying the `_real_sample_size` cache
added for #341: it memoizes successful resolutions but not misses, so a
catalog sample whose backing `.dmc` file is missing gets re-resolved from
scratch on every occurrence in a song rather than the one-lookup guarantee
its own docstring promises. No data loss or crash results (the miss path is
tested and correctly falls back to the placeholder) — this is a documentation/
performance nit, not a correctness bug.

No pattern round-trip, hardware-range, or data-loss issue was found this
cycle. All hardware claims re-checked against `docs/APU_DMC_REFERENCE.md`
§§1-6 and `docs/NES_DMA_REFERENCE.md` §§1-6.

## 2. Findings

### DP-DPCM-07: `_real_sample_size` doesn't cache unresolvable (missing-file) lookups
- **Severity**: LOW
- **Dimension**: 2 (`dpcm_index.json` schema integrity) / 7 (sample-manager lifecycle)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:227-250` (`_real_sample_size`)
- **Status**: NEW
- **Description**: `_real_sample_size` caches a successfully-resolved size in
  `self._sample_size_cache[sample_name]` (line 249) before returning it, but
  both early-return `None` paths — no `filename` key (line 244) and
  `resolve_dpcm_sample_path` returning `None` (line 247) — return directly
  without writing anything to the cache. The method's own docstring/callsite
  comment (`_allocate`, lines 252-257, and the class-level comment at
  lines 222-225) both describe the cache as making a reused drum "cost one
  `os.path.getsize` call" per song, but that guarantee only holds for the
  resolved case. A catalog sample whose `filename` doesn't resolve to an
  existing file (index references a `.dmc` that was moved/deleted from the
  `dmc/` root) re-runs the full `resolve_dpcm_sample_path` candidate-path
  probe (up to 3 `Path.exists()` stats) on every single occurrence of that
  drum in the song, not just the first.
- **Evidence**:
  ```python
  def _real_sample_size(self, sample_name, sample_data):
      if sample_name in self._sample_size_cache:
          return self._sample_size_cache[sample_name]
      filename = sample_data.get('filename')
      if not filename:
          return None                      # <- not cached
      path = resolve_dpcm_sample_path(filename, self.dpcm_index_path)
      if path is None:
          return None                      # <- not cached
      size = os.path.getsize(path)
      self._sample_size_cache[sample_name] = size
      return size
  ```
  `tests/test_enhanced_drum_mapper.py:613-621` (`test_unresolvable_sample_falls_back_to_placeholder`)
  covers the correctness of the fallback (no crash, placeholder used) but not
  the repeated-call cost; `tests/test_enhanced_drum_mapper.py:623-630`
  (`test_repeated_allocation_reuses_cached_size`) only exercises the
  successful-resolution cache path.
- **Impact**: Purely a performance/documentation-accuracy gap, not a
  correctness issue — the fallback to the 1024-byte placeholder still
  happens correctly every time (per #341/DP-DPCM-02's design intent), and the
  extra filesystem stats are cheap relative to a full pipeline run. Worst
  case is a song that hits one missing/mislabeled drum sample dozens or
  hundreds of times, incurring a handful of extra `os.path.exists()` calls
  per hit instead of one. No blast radius beyond wasted I/O.
- **Related**: #341/DP-DPCM-02 (this cache was added to fix that issue's
  placeholder-size problem); #367/DP-DPCM-05 (the packer-side "partial miss"
  path this same missing-file scenario feeds into downstream).
- **Suggested Fix**: Cache the miss too (e.g. store `None` in
  `self._sample_size_cache[sample_name]` before returning on both early-exit
  paths, and have the cache-hit check distinguish "cached miss" from
  "not yet looked up" via `sample_name in self._sample_size_cache` — which
  already works correctly for a cached `None` value since `dict.__contains__`
  doesn't care about the stored value).

## 3. Re-verification detail (existing issues confirmed still open, unchanged)

### Dimension 1 — Drum-note → sample mapping & coverage
- **#340/DP-DPCM-01 (Existing, OPEN — reduced scope)**: `06e1e04` closed 3 of
  the 4 alias gaps this issue tracked. `DPCM_ROLE_ALIASES`
  (`dpcm_sampler/drum_engine.py:68-82`) now aliases `splash`→`crash`,
  `triangle_mute`/`triangle_open`→`"DPCM triangle"` (all three verified to
  resolve against the live `dpcm_index.json`). `vibraslap` (note 58) remains
  intentionally unaliased per the trailing comment (lines 63-67) — the
  catalog has no reasonably-close sample for its distinctive rattling
  timbre — and still falls through to noise. Re-verified live:
  `python3 -c "import json; idx=json.load(open('dpcm_index.json')); print('vibraslap' in idx)"` → `False`.
- Confirmed fixed, no regression: note 47 (mid tom) still resolves to
  `"tom_mid"` (`drum_engine.py:20`); the velocity→primary→role→alias
  fallback cascade in `_resolve_dpcm_sample_name`
  (`enhanced_drum_mapper.py:452-485`) is unchanged and still tries all
  candidates, including the alias, before returning `None`.

### Dimension 2 — `dpcm_index.json` schema integrity
- No change from 2026-08-05: `generate_dpcm_index.py:109-127` is still the
  sole writer, emitting only `id` + `filename`. `data`/`frequency` still
  always fall back to `DPCMSampleManager.allocate_sample`'s defaults
  (`dpcm_sample_manager.py:56,59`) — an accepted simplification, not a bug.
  `length` is the one field that's now backfilled from the real file, per
  #341 below (see DP-DPCM-07 above for the one gap found in that backfill).

### Dimension 3 — DPCM conversion correctness
- **#342/DP-DPCM-03 (Existing, OPEN — reduced scope)**: `90b4582` fixed the
  two assumption bugs this audit's Dimension 3 explicitly asked to verify:
  `delta_encode`'s start level is now `prev = 0x00`
  (`dpcm_sampler/dpcm_converter.py:54`, matching the engine's `$4011` silence
  init) instead of `0x40`, and both `convert_wav_to_unsigned_pcm`'s default
  `sample_rate` and `DpcmPacker.add_sample`'s default `pitch_rate` now derive
  from the same shared constants (`constants.DEFAULT_DMC_RATE_HZ` /
  `DEFAULT_DMC_PITCH_RATE`, both 33144 Hz / 15 — `dpcm_converter.py:5,14,87`),
  so the two can no longer silently drift apart at their defaults. The module
  is still orphaned (`grep -rn "dpcm_converter" --include="*.py" . 2>/dev/null | grep -v tests/`
  returns nothing outside `dpcm_converter.py` itself), and the untouched
  remainder of this issue's original scope stands: `dpcm_compress`
  (`dpcm_converter.py:63-71`) still derives its output bit purely from
  `encoded[i] > encoded[i-1]` rather than the ±1 step counter `delta_encode`
  actually walked, so a run of *constant* input (`step == 0`, `encoded[i] ==
  encoded[i-1]`) still encodes as bit `0` on every sample in the run. Per
  `docs/APU_DMC_REFERENCE.md`, hardware bit `0` means "subtract 2 from the
  output level" (there is no "hold" bit) — so a silent/constant passage still
  decodes to a continuous downward ramp on real hardware playback, not
  silence. This is unreachable in production (module has no caller) so it
  remains LOW/orphaned-code risk, unchanged from prior cycles, and is a
  distinct sub-bug from the two the sprint fixed under the same issue number.
- Bit-packing order (`dmc_bytes[i] |= (bits[i+j] << j)`, LSB-first, line 81)
  still matches `docs/APU_DMC_REFERENCE.md`'s "Reader → Buffer → Shifter"
  order. Unchanged, no regression.

### Dimension 4 — Sample size / address / DMC range constraints
- Confirmed fixed, no regression: `_place_sample`
  (`dpcm_sampler/dpcm_packer.py:77-98`) still computes
  `dpcm_length_val = max(0, (sample['size'] + 14) // 16)` — ceiling division
  — matching `docs/APU_DMC_REFERENCE.md`'s `(L*16)+1` read formula (#295/DP-01
  holds). `size` stays bounded to 4081 via the truncate-on-add path
  (`dpcm_packer.py:31-36`), so `length_reg ≤ 255` (8-bit safe). The only
  production `add_sample` call site (`generate_dpcm_index.py:99-104`) always
  passes `truncate=True`; no call site passes `truncate=False`.
- **#367/DP-DPCM-05 — CONFIRMED FIXED this cycle** (see Summary above for
  detail). `generate_assembly`'s `_table` helper
  (`dpcm_sampler/dpcm_packer.py:141-145`) still emits `$00` placeholders for
  unpacked dense ids, but both playback trigger routines now refuse to fire
  on a `$00` length, and `main.py` now surfaces the drop by name.
  `BANK_SIZE`/`START_ADDR` keep every bank inside a single MMC3 8KB window
  (`$C000`-`$DFFF`), so the `$FFFF`→`$8000` address-wrap quirk
  (`docs/APU_DMC_REFERENCE.md`) cannot occur — no sample can straddle the
  window boundary since packing never places a sample past `START_ADDR +
  BANK_SIZE`.

### Dimension 5 — DMC level handling & DMA-timing implications
- **#348 — CONFIRMED FIXED this cycle** (see Summary above). No producer
  emits `dmc_level`/`CMD_DMC_LEVEL` anywhere outside the regression test
  (`tests/test_ca65_export.py`) — the `$87` opcode path remains removed.
- `@write_dpcm` (`nes/audio_engine.asm:512-547`) still writes `$4015=$0F` →
  `$4010`/`$4012`/`$4013` → `$4015=$1F`, matching
  `docs/APU_DMC_REFERENCE.md` §6's trigger order; `_emit_dpcm_proc`
  (`exporter/exporter_ca65.py:545-601`, direct-export path) mirrors the same
  order exactly. `docs/NES_DMA_REFERENCE.md` §5's mandatory DPCM-safe
  controller-read warning is still present and unchanged; this subsystem
  still can't eliminate the DMA cost itself, only document it.

### Dimension 6 — Config robustness
- Confirmed fixed, no regression: `DrumMapperConfig.from_file`
  (`dpcm_sampler/enhanced_drum_mapper.py:163-195`) still catches `TypeError`
  from a stray config key and re-raises `ValueError` (lines 194-195) — #76/D-13
  remains fixed. `EnhancedDrumMapper.__init__` (lines 206-208) still calls
  `self.config.validate()` unconditionally before constructing
  `DPCMSampleManager`; no new direct-construction call site found outside
  `tests/test_dpcm_sample_manager.py`.

### Dimension 7 — Sample-manager dedup & lifecycle
- Confirmed fixed, no regression: `_next_id` is still monotonic
  (`dpcm_sample_manager.py:14,51-52`); memory accounting is still unified
  around `metadata['size']` with the up-front `pending_size` check
  (lines 43,58,121-131); `_find_similar_sample`/`_calculate_sample_similarity`
  remain deleted.
- **#341/DP-DPCM-02 (Existing, OPEN — reduced scope)**: the `length`
  placeholder problem is fixed (see Summary), modulo the new DP-DPCM-07
  cache-miss nit above. The manager's eviction still has zero effect on what
  the packer ships (packing keys off frame `sample_id`, not
  `DPCMSampleManager.active_samples`) — this remains an accepted, by-design
  characteristic per the skill's own framing, not a bug in itself.

### Dimension 8 — Channel-pipeline integration
- Confirmed fixed, no regression: the noise-discard warning
  (`tracker/track_mapper.py:307-317`) still fires only in the
  already-occupied `else` branch, and its count is still exactly
  `len(noise_events)` — re-read in full this cycle, no other discard path
  found.
- Confirmed fixed, no regression: `run_map` (`main.py:226-241`) still guards
  a missing `dpcm_index.json` (honoring `--dpcm-index`) with a clean
  `[ERROR]` + exit before calling `assign_tracks_to_nes_channels` — #256/D-18
  remains fixed.
- **#381/SAFE-2026-07-19-1 (Existing, OPEN, unchanged)**: `run_full_pipeline`'s
  legacy branch (`main.py:924-927`) still calls `assign_tracks_to_nes_channels`
  against a hardcoded `'dpcm_index.json'` with no existence check before the
  call, unlike `run_map`. A missing index still aborts the whole pipeline via
  the outer `try/except` rather than degrading to a drumless build.
- **#380/TD-28 — CONFIRMED FIXED this cycle** (see Summary above).
- **#369/EXP-2026-07-19-1 (Existing, OPEN, unchanged)**: the macro-bytecode
  DPCM note clamp (`exporter/exporter_ca65.py:1186-1189`) still clamps to the
  byte ceiling (255) rather than the engine's actual note range; untouched by
  today's commits (all of which landed in `export_direct_frames`, not
  `export_tables_with_patterns`).
- **#137/TD-08 — CONFIRMED FIXED this cycle** (see Summary above).
- Confirmed fixed, no regression: the dense-id remap
  (`nes/emulator_core.py:204-241`) and `note = min(255, dense_id + 1)`
  encoding are unchanged; the 255-distinct-sample ceiling remains openly
  tracked as **#343/DP-DPCM-04**, with its warning (`emulator_core.py:220-224`)
  firing only when `len(referenced_ids) > 255`, verified against the
  dense-id arithmetic (`dense_id` max `254` for exactly 255 distinct samples
  never collides; `256`th+ distinct sample is where the collision starts).

### Cross-cutting (adjacent audits' DPCM-relevant issues, confirmed still open)
- **#366/PAT-B** — `DrumPatternDetector` emergent-scan self-overlap (pattern
  audit's primary territory); not touched by any commit since 2026-08-05,
  re-confirmed still open, not re-litigated here.
- **#368/DP-DPCM-06** — `drum_engine.py`'s dead `optimize_dpcm_samples`
  (`drum_engine.py:118-152`) / `DrumPatternAnalyzer` (`drum_engine.py:155-176`)
  still present, still unreferenced outside `tests/test_drum_mapping.py`
  (verified via `grep -rn "optimize_dpcm_samples\|DrumPatternAnalyzer"
  --include="*.py" .`), still LOW/dead-code risk only.

## Skeptical checklist (re-run this cycle)

- [x] Unmapped/rare GM drum note 47 still resolves via `DEFAULT_MIDI_DRUM_MAPPING` → `tom_mid`. Confirmed.
- [x] Velocity→primary→default→alias fallback chain reaches the index correctly; only `vibraslap` (the one genuine remaining gap, #340) returns `None`. Confirmed.
- [x] `length` now backfills from the real on-disk file for the resolvable case (#341); the unresolvable case still falls back to the 1024 placeholder correctly, but doesn't memoize the miss (new: DP-DPCM-07).
- [x] `length_reg` ceiling division still reads the full tail — #295 holds.
- [x] `DrumMapperConfig.from_file` still raises `ValueError` (not a bare `TypeError`) on a stray config key — #76 fixed, confirmed again.
- [x] `_next_id` monotonic — no reuse path found.
- [x] Memory limit enforced end-to-end via unified `metadata['size']` + up-front pending-size check — confirmed.
- [x] Noise fallback still discarded when noise is occupied, with an accurate warning (`len(noise_events)` exact) — confirmed.
- [x] Dense-id remap survives near-254-distinct-drum songs up to the documented 255 ceiling (#343 tracks the ceiling itself) — confirmed unchanged.
- [x] Packing only referenced samples (#140) can no longer leave a frame silently playing a `$00` placeholder as garbage — **#367 is now fixed**: both playback trigger routines skip on a zero length, and the pack-time warning names every dropped sample.
- [x] `_handle_pattern_event` now honors the caller's `use_advanced` flag instead of hardcoding `True` — **#202 is now fixed**, confirmed via `tests/test_enhanced_drum_mapper.py::test_pattern_event_honors_use_advanced_false` and `::test_map_drums_use_advanced_false_reaches_pattern_path`.

All hardware claims re-checked against `docs/APU_DMC_REFERENCE.md` §§1-6 and
`docs/NES_DMA_REFERENCE.md` §§1-6 as cited above; no doc/code drift found.

Test verification: `python -m pytest tests/test_enhanced_drum_mapper.py
tests/test_dpcm_sample_manager.py tests/test_dpcm_converter.py
tests/test_drum_mapper_config.py -q` → 92 passed;
`python -m pytest tests/test_ca65_export.py -q -m "not slow"` → 64 passed.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-08-06.md
```
