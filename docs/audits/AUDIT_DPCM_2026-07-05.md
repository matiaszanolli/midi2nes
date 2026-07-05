# DPCM / Drum-Sampling Audit — 2026-07-05

Audit of the DPCM/drum subsystem: GM-percussion → DPCM sample mapping, WAV→1-bit-delta
conversion, sample packing/addressing, and the DMC-facing edges of the channel pipeline
and CA65 exporter. Scope per `.claude/commands/audit-dpcm/SKILL.md`.

Hardware claims cite `docs/APU_DMC_REFERENCE.md` and `docs/NES_DMA_REFERENCE.md`.

This is a follow-up to `docs/audits/AUDIT_DPCM_2026-07-03.md`. That report's flagship
CRITICAL (D-14: raw catalog `sample_id` clamped to a single byte, aliasing every drum
onto one wrong sample) was addressed by commit `b49a649` ("fix: dense per-song DPCM
sample id remap, expand drum role coverage (#200, #201)"). This pass verifies that fix
end-to-end and finds it is **internally self-defeating**: the same commit added a
`MAX_SAFE_SAMPLE_ID = 254` guard in the drum mapper that drops every hit the dense-remap
was meant to rescue, and every named drum in the (now larger) shipped index sits above
that guard — so DPCM percussion is entirely non-functional on the shipped catalog.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 1 |
| MEDIUM   | 1 |
| LOW      | 3 |
| **Total**| **5** |

Highest-risk finding:

- **D-17 (HIGH, NEW)** — The D-14 fix shipped two contradictory mitigations in the same
  commit. `nes/emulator_core.py` renumbers a song's referenced catalog ids to a dense
  `0..N-1` range so high catalog ids survive the single-byte `note` ceiling, but
  `EnhancedDrumMapper` (the earlier `map` stage) *also* drops any hit whose raw catalog id
  exceeds `MAX_SAFE_SAMPLE_ID = 254` to the noise channel **before** the remap can run.
  All 26 resolvable drum-role names in the shipped 1941-sample `dpcm_index.json` have ids
  ≥ 1083, so **every** drum hit is routed to noise; `map_drums` emits **zero** DPCM
  events, and the dense-remap code is dead for the shipped catalog. DPCM percussion is
  effectively disabled.

---

## Findings

### D-17: `MAX_SAFE_SAMPLE_ID = 254` guard in the drum mapper defeats the dense-remap fix — all shipped-catalog drums are routed to noise, DPCM is disabled
- **Severity**: HIGH
- **Dimension**: 8 (channel-pipeline integration) / 1 (mapping coverage)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:202` (`MAX_SAFE_SAMPLE_ID = 254`),
  `:298-304` (non-pattern hit → noise when id > 254), `:389-392` (pattern path),
  `:471-476` (layered path); vs. the dense-remap it pre-empts at
  `nes/emulator_core.py:213-235`; shipped `dpcm_index.json` (named drums at ids 1083–1940)
- **Status**: NEW (regression-adjacent to closed #200/D-14 — introduced by the same fix
  commit `b49a649`)
- **Description**: Commit `b49a649` (#200, #201) fixed D-14 by (a) adding named drum
  samples to `dpcm_index.json` (ids 1923–1940, addressing the D-15 asset gap), and (b)
  renumbering each song's *referenced* catalog ids to a compact song-local `0..N-1`
  "dense" range in `NESEmulatorCore.process_all_tracks` before the single-byte `note`
  encoding (`note = min(255, dense_id + 1)`), emitting a `dpcm_sample_map`
  (dense→catalog) side table so the export/pack stage can recover the real `.dmc` files.
  This is the correct fix: a real song references far fewer than 255 distinct drums, so
  the byte ceiling is never hit and no aliasing occurs.

  But the **same commit** also added a `MAX_SAFE_SAMPLE_ID = 254` guard in
  `EnhancedDrumMapper` that runs in the earlier `map` stage and drops any hit whose *raw
  catalog* id exceeds 254 to the noise fallback (lines 298-304, 389-392, 471-476),
  incrementing `_oversized_sample_id_count`. The guard's premise — "this id would collide
  with another sample once clamped to a single byte downstream" (line 299-302 comment) —
  is exactly the collision the dense-remap already prevents. Because the guard fires in
  `map_drums` (map stage) *before* `process_all_tracks` (frames stage), it removes the
  high-id hits before the dense-remap can renumber them, so the remap never sees them.

  The shipped `dpcm_index.json` now has 1941 samples, and **all 26 resolvable drum-role
  names sit at ids ≥ 1083** (kick=1318, snare=1620, hihat_closed=1926, tom_mid=1924,
  crash=1929, ride=1526, cowbell=1119, clap=1096, …). Every one exceeds 254, so every
  resolvable drum hit is routed to noise. `map_drums` emits **zero** DPCM events on the
  shipped catalog, and `nes/emulator_core.py:213-235`'s dense-remap is dead code for it.
- **Evidence**:
  ```
  $ python3 -c "
  from dpcm_sampler.enhanced_drum_mapper import EnhancedDrumMapper
  m = EnhancedDrumMapper(dpcm_index_path='dpcm_index.json')
  events = {'drums':[{'frame':0,'note':36,'velocity':100},   # kick
                     {'frame':10,'note':38,'velocity':100},   # snare
                     {'frame':20,'note':42,'velocity':100}]}  # closed hi-hat
  dpcm, noise = m.map_drums(events)
  print('DPCM:', dpcm); print('NOISE:', noise)"
  Warning: 3 drum hit(s) resolved to a DPCM sample id > 254 (out of 1941 in
      dpcm_index.json) — routed to noise instead of risking aliasing ...
  DPCM: []
  NOISE: [{'frame': 0, 'note': 36, 'velocity': 100}, {'frame': 10, ...}, ...]
  ```
  All three named drums resolve to real sample names (`kick`, `snare`, `hihat_closed`),
  but their catalog ids (1318, 1620, 1926) all exceed 254, so all three drop to noise.
  ```
  $ python3 -c "import json; d=json.load(open('dpcm_index.json'))
  print([ (n,d[n]['id']) for n in ['kick','snare','hihat_closed','crash','tom_mid'] ])"
  [('kick',1318),('snare',1620),('hihat_closed',1926),('crash',1929),('tom_mid',1924)]
  # 0 of the 26 resolvable role names have id <= 254.
  ```
  The dense-remap the guard pre-empts is proven correct in isolation
  (`tests/test_audio_fixes.py:160,165`: `sample_id=200 → dpcm_sample_map {'0':200}`,
  `sample_id=9999 → {'0':9999}`) — but no test drives it end-to-end **through**
  `map_drums`, so the guard swallowing every hit was never caught.
- **Impact**: On the shipped `dpcm_index.json`, every song built through the default
  pipeline (or `export`) loses **all** of its DPCM percussion — every drum hit plays as
  noise instead of the sampled drum the mapping resolved. A stdout warning is printed
  (so not fully silent), but the drums are gone from DPCM and the recently-added named
  samples + the dense-remap infrastructure are both inert. Blast radius: every drummed
  song on the shipped catalog. Kept below CRITICAL only because playback still produces
  audible (noise) percussion rather than a broken ROM.
- **Related**: #200/D-14 (the fix this defeats), #201 (the role-name samples added at
  ids >254 that this guard then discards), prior D-15 (asset gap — now data-present but
  guard-blocked), D-18 below.
- **Hardware ref**: n/a (pure-software pipeline contradiction; the byte ceiling itself is
  `note`-format, not an APU constraint).
- **Suggested Fix**: Remove the `MAX_SAFE_SAMPLE_ID` guard from `EnhancedDrumMapper`
  (lines 298-304, 389-392, 471-476) — the dense-remap in `process_all_tracks` already
  guarantees no catalog id reaches the byte encoding unremapped, and `map_drums` output
  always flows through `process_all_tracks` before export. If a belt-and-suspenders check
  is still wanted, move it to the *dense* id after remapping (assert `dense_id + 1 <= 255`,
  i.e. a song references ≤ 254 distinct drums) rather than the raw catalog id. Add an
  end-to-end test that drives `map_drums` → `process_all_tracks` with the real shipped
  index and asserts a kick+snare song produces two distinct non-noise DPCM events.

### D-12 / #75: `length_reg = (size-1)//16` floors — truncates the sample tail for any size not of the form `16k+1`
- **Severity**: MEDIUM
- **Dimension**: 4 (sample size / DMC range constraints)
- **Location**: `dpcm_sampler/dpcm_packer.py:79`
- **Status**: Existing: #75 (code unchanged since prior reports; note #75 is not in the
  current open-issue snapshot at `/tmp/audit/issues.json` — either closed-without-fix or
  renumbered; the code path is verifiably unchanged and still lossy, so re-reported)
- **Description**: `_place_sample` computes `dpcm_length_val = (sample['size'] - 1) // 16`.
  Per `docs/APU_DMC_REFERENCE.md` (`$4013` formula: sample length = `(L * 16) + 1` bytes),
  the DMC engine reads exactly `(length_reg * 16) + 1` bytes at playback. Flooring
  `(size-1)//16` yields `length_reg` such that the engine reads
  `floor((size-1)/16)*16 + 1 ≤ size` bytes — under-reading up to 15 bytes of the sample's
  tail for any `size` not exactly `16k+1`. Rounding up (`ceil`) would instead read a few
  bytes of the `.align 64` zero-padding, which holds the output level rather than
  truncating audible content.
- **Evidence**: `size = 100` → `length_reg = 99//16 = 6` → engine reads `6*16+1 = 97`
  bytes; the final 3 bytes (24 output deltas) are never played.
- **Impact**: Every packed sample whose byte length is not `≡ 1 (mod 16)` loses up to 15
  bytes (≈120 DMC output samples, ~15 ms at the default rate index 15) off its tail —
  an audible clip on short percussive samples. Not a full drop, so MEDIUM.
- **Related**: prior D-12 (`AUDIT_DPCM_2026-06-29.md`, `-2026-07-03.md`); #75.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` — `$4013` register / "Length calculation
  forces a 16-byte alignment plus 1 (`%LLLL LLLL0001`)".
- **Suggested Fix**: Use ceiling division: `dpcm_length_val = max(0, (size + 14) // 16)`
  (i.e. `ceil((size-1)/16)` guarded for `size==0`), and clamp to the 8-bit register max
  (`min(255, …)`), so the engine reads at least the whole sample.

### D-13 / #76: `DrumMapperConfig.from_file` raises an uncaught `TypeError` on a stray/renamed config key
- **Severity**: LOW
- **Dimension**: 6 (config robustness)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:169-174` (splat into
  `DrumPatternConfig`/`SampleManagerConfig`), `:188-191` (only `FileNotFoundError` /
  `json.JSONDecodeError` caught)
- **Status**: Existing: #76 (still open, code unchanged)
- **Description**: `from_file` does `DrumPatternConfig(**config_data.get('pattern_detection',
  {}))` and the equivalent for `SampleManagerConfig`. An unexpected or renamed JSON key
  raises `TypeError` from the dataclass constructor, which is not among the two exception
  types the method catches, so it propagates raw.
- **Evidence**: `enhanced_drum_mapper.py:188-191` catches only `FileNotFoundError` and
  `json.JSONDecodeError`.
- **Impact**: Low reach today — the CLI `--config` flag that fed this path was removed
  (#13), so `from_file` is public-API-only (exercised by `tests/test_drum_mapper_config.py`).
  Still an ungraceful failure mode on public API surface.
- **Related**: #76; prior D-13.
- **Suggested Fix**: Wrap the two dataclass constructions and re-raise a typed
  `ValueError` with the offending key, or filter `config_data` to known fields before
  splatting.

### D-16 / #202: `_handle_pattern_event` ignores the caller's `use_advanced` flag
- **Severity**: LOW
- **Dimension**: 1 (mapping coverage)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:387`
- **Status**: Existing: #202 (still open, code unchanged)
- **Description**: `map_drums(midi_events, use_advanced)` threads `use_advanced` into the
  non-pattern path (`_resolve_dpcm_sample_name(midi_note, velocity, use_advanced)`, line
  294-296) but the pattern-matched path calls `self._resolve_dpcm_sample_name(template_note,
  velocity)` (line 387) with no third argument, so it always uses the default
  `use_advanced=True` regardless of the caller's request.
- **Evidence**: line 294-296 (flag passed) vs. line 387 (omitted, defaults `True`).
- **Impact**: A caller explicitly requesting `use_advanced=False` still gets advanced
  velocity-split resolution for any event inside a detected drum pattern. Latent/API-only:
  the sole production call site (`tracker/track_mapper.py`) always uses the default.
- **Related**: #202; prior D-16.
- **Suggested Fix**: Pass the flag through:
  `self._resolve_dpcm_sample_name(template_note, velocity, use_advanced)`.

### D-18: `run_map` subcommand crashes with a raw traceback when `dpcm_index.json` is missing, unlike the packer path
- **Severity**: LOW
- **Dimension**: 8 (channel-pipeline integration)
- **Location**: `main.py:96-104` (`run_map`) → `assign_tracks_to_nes_channels(...,
  'dpcm_index.json')` → `EnhancedDrumMapper._load_sample_index` (`enhanced_drum_mapper.py`)
  raises `FileNotFoundError`
- **Status**: NEW
- **Description**: `run_map` guards its *input* JSON via `load_json_stage` (line 98) but
  passes a hardcoded default `'dpcm_index.json'` into `assign_tracks_to_nes_channels`
  (line 100-102). If that index file is absent, `_load_sample_index` raises an uncaught
  `FileNotFoundError` and the standalone `map` subcommand exits with a raw traceback —
  in contrast to the DPCM *packer* path (`run_export` / `run_full_pipeline`), which
  handles a missing index gracefully ("No dpcm_index.json found, skipping"), and to every
  other step-by-step guard in `main.py` (`load_json_stage`, #120).
- **Evidence**: `main.py:102` has no try/except around `assign_tracks_to_nes_channels`;
  the packer call sites explicitly catch/skip a missing index.
- **Impact**: Low — the index ships with the repo, so this only bites a user who deletes
  or relocates it while using the step-by-step `map` subcommand. Cosmetic UX asymmetry
  (raw traceback vs. clean degrade), not a data-loss path.
- **Related**: #120 (step-by-step JSON guards); Dimension 8 of the audit-dpcm skill.
- **Suggested Fix**: Wrap the mapper call in `run_map` to catch a missing index and either
  emit a clean `[ERROR]` message or degrade to a drumless map (parity with the packer
  path).

---

## Re-verified as fixed / not reported

- **D-14 dense-remap round-trip (#200)** — `nes/emulator_core.py:213-235` renumbers
  referenced catalog ids to a dense `0..N-1` range and emits `dpcm_sample_map`;
  `dpcm_sampler/generate_dpcm_index.py:123-153` (`get_dpcm_sample_ids_from_frames`) reads
  that map to recover catalog ids, and `load_dpcm_index_into_packer` (lines 68-97) keys the
  packer's positional lookup tables by dense id. The mechanism itself is correct and
  round-trips — its only defect is that D-17's guard prevents it from ever running on the
  shipped catalog. Not separately filed.
- **DPCM converter (`dpcm_sampler/dpcm_converter.py`)** — re-verified per
  `AUDIT_DPCM_2026-06-29.md`: `delta_encode`/`dpcm_compress` bit polarity agree, LSB-first
  packing matches the DMC shifter (`docs/APU_DMC_REFERENCE.md` §1), and the `prev = 0x40`
  start-level and fixed-8000-Hz resample assumptions are converter-side only —
  `convert_wav_to_dmc` is **not invoked by any pipeline path** (no imports outside the
  module/tests). Not a shipping-ROM bug; not re-filed.
- **D-01…D-11 (prior sprint fixes)** — spot-re-verified unchanged: index filename
  resolution (`generate_dpcm_index.py`), monotonic `_next_id` (`dpcm_sample_manager.py`),
  unified memory accounting, removed similarity/dedup, removed `dmc_level` path
  (`grep -rn dmc_level` → no hits), noise-fallback discard warning
  (`tracker/track_mapper.py`). No regressions.
- **`$4011` silence init** — `nes/mmc3_init.asm:68-69` writes `LDA #$00 / STA $4011`
  before `STA $4010`; matches `docs/APU_DMC_REFERENCE.md` §6. Not a gap.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-07-05.md
```
