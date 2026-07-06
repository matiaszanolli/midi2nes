# DPCM / Drum-Sampling Audit — 2026-07-06

Audit of the DPCM/drum subsystem: GM-percussion → DPCM sample mapping, WAV→1-bit-delta
conversion, sample packing/addressing, and the DMC-facing edges of the channel pipeline
and CA65 exporter. Scope per `.claude/commands/audit-dpcm/SKILL.md`.

Hardware claims cite `docs/APU_DMC_REFERENCE.md` and `docs/NES_DMA_REFERENCE.md`.

Follow-up to `docs/audits/AUDIT_DPCM_2026-07-05.md`. That report's flagship **HIGH**
(D-17: `MAX_SAFE_SAMPLE_ID = 254` guard in `EnhancedDrumMapper` routed every
shipped-catalog drum to noise, disabling DPCM percussion) has been **fixed** — the guard
was removed (issue #254), and `map_drums` now emits raw catalog ids that the
`process_all_tracks` dense-remap renumbers before the single-byte `note` encoding. Verified
end-to-end below. This pass confirms that fix and re-examines the remaining, lower-severity
findings, plus one new LOW.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 4 |
| **Total**| **5** |

Highest-risk finding:

- **DP-01 (MEDIUM)** — `dpcm_packer._place_sample` still floors the `$4013` length register
  (`length_reg = (size-1)//16`). For any packed sample whose byte length is not `≡ 1
  (mod 16)`, the DMC engine reads fewer bytes than the sample contains, clipping up to 15
  bytes (~120 output deltas) off its tail. Issue #75 was closed but the fix is not on this
  working tree — the code path is unchanged and still lossy.

Verified fixed since last pass:

- **D-17 (was HIGH)** — `MAX_SAFE_SAMPLE_ID` guard removed. A kick+snare+hi-hat song on the
  shipped `dpcm_index.json` now produces DPCM events with real catalog ids
  (`kick=1318, snare=1620, hihat_closed=1926`) instead of routing all three to noise. The
  dense-remap (`nes/emulator_core.py:214-235`) and its `dpcm_sample_map` side table are wired
  through both packer call sites (`main.py:588-590`, `:953-956` via
  `get_dpcm_sample_ids_from_frames` → `load_dpcm_index_into_packer(sample_ids=...)`), so the
  round-trip from catalog id → dense `note-1` → packer positional tables holds.

---

## Findings

### DP-01: `length_reg = (size-1)//16` floors — truncates the sample tail for any size not of the form `16k+1`
- **Severity**: MEDIUM
- **Dimension**: 4 (sample size / DMC range constraints)
- **Location**: `dpcm_sampler/dpcm_packer.py:79`
- **Status**: Regression of #75 (closed on GitHub, but the closing fix is not present on this
  working tree — the code path is verifiably unchanged and still floors)
- **Description**: `_place_sample` computes `dpcm_length_val = (sample['size'] - 1) // 16`.
  Per `docs/APU_DMC_REFERENCE.md` (`$4013`: sample length = `(L * 16) + 1` bytes), the DMC
  engine reads exactly `(length_reg * 16) + 1` bytes at playback. Flooring `(size-1)//16`
  yields a `length_reg` such that the engine reads `floor((size-1)/16)*16 + 1 ≤ size`
  bytes — under-reading up to 15 bytes of the sample tail for any `size` not exactly
  `16k+1`. This value is emitted into `dpcm_len_table` and loaded into `$4013` by the
  generated `play_dpcm` trigger (`exporter/exporter_ca65.py:820-821`). Rounding up (`ceil`)
  would instead read a few bytes of the `.align 64` zero-padding, which merely holds the
  output level rather than truncating audible content.
- **Evidence**: `size = 100` → `length_reg = 99 // 16 = 6` → engine reads `6*16+1 = 97`
  bytes; the final 3 bytes (24 output deltas) never play. The `.align 64` padding
  (`dpcm_packer.py:100`) means the extra bytes a `ceil` would read are zero-pad, not
  neighbouring sample data. Max in-range value is safe: truncated samples cap at 4081 bytes
  → `(4081-1)//16 = 255`, fits the 8-bit register.
- **Impact**: Every packed sample whose byte length is not `≡ 1 (mod 16)` loses up to 15
  bytes (~120 DMC output samples, ~15 ms at rate index 15) off its tail — an audible clip on
  short percussive samples. Not a full drop, so MEDIUM. Blast radius: every drummed song
  whose `.dmc` files aren't coincidentally `16k+1` bytes.
- **Related**: #75; prior DPCM audits D-12 (`AUDIT_DPCM_2026-06-29.md`, `-07-03.md`,
  `-07-05.md`).
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2/§4 — `$4013` "Length calculation forces a
  16-byte alignment plus 1 (`%LLLL LLLL0001`)".
- **Suggested Fix**: Use ceiling division: `dpcm_length_val = max(0, (size + 14) // 16)`
  (i.e. `ceil((size-1)/16)` guarded for `size==0`), and clamp to `min(255, …)` so the engine
  reads at least the whole sample. Land or re-apply the #75 fix on `master`.

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
  sites.
- **Impact**: Low reach today — the CLI `--config` flag that fed this path was removed (#13),
  so `from_file` is public-API-only (exercised by `tests/test_drum_mapper_config.py`). Still
  an ungraceful failure mode on public API surface.
- **Related**: #76; prior D-13.
- **Suggested Fix**: Wrap the two dataclass constructions and re-raise a typed `ValueError`
  naming the offending key, or filter `config_data` to known fields before splatting.

### DP-03: `_handle_pattern_event` ignores the caller's `use_advanced` flag
- **Severity**: LOW
- **Dimension**: 1 (mapping coverage)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:364`
- **Status**: Existing: #202 (OPEN, code unchanged)
- **Description**: `map_drums(midi_events, use_advanced)` threads `use_advanced` into the
  non-pattern path (`_resolve_dpcm_sample_name(midi_note, velocity, use_advanced)`, line
  283-285) but the pattern-matched path calls `self._resolve_dpcm_sample_name(template_note,
  velocity)` (line 364) with no third argument, so it always uses the default
  `use_advanced=True` regardless of the caller's request.
- **Evidence**: line 283-285 (flag passed) vs. line 364 (omitted, defaults `True`).
- **Impact**: A caller explicitly requesting `use_advanced=False` still gets advanced
  velocity-split resolution for any event inside a detected drum pattern. Latent/API-only:
  the sole production call site (`tracker/track_mapper.py`) always uses the default.
- **Related**: #202; prior D-16.
- **Suggested Fix**: Pass the flag through:
  `self._resolve_dpcm_sample_name(template_note, velocity, use_advanced)`.

### DP-04: `run_map` subcommand crashes with a raw traceback when `dpcm_index.json` is missing, unlike the packer path
- **Severity**: LOW
- **Dimension**: 8 (channel-pipeline integration)
- **Location**: `main.py:104-108` (`run_map`) → `assign_tracks_to_nes_channels(...,
  dpcm_index_path)` → `EnhancedDrumMapper._load_sample_index`
  (`enhanced_drum_mapper.py:215-218`) raises `FileNotFoundError`
- **Status**: Existing: #256 (OPEN)
- **Description**: `run_map` guards its *input* JSON via `load_json_stage` (line 106) but then
  passes a hardcoded default `'dpcm_index.json'` (line 108) into
  `assign_tracks_to_nes_channels`. If that index file is absent, `_load_sample_index` raises
  an uncaught `FileNotFoundError` and the standalone `map` subcommand exits with a raw
  traceback — in contrast to the DPCM *packer* path (`run_export` / `run_full_pipeline`),
  which handles a missing index gracefully, and to every other step-by-step guard in
  `main.py` (`load_json_stage`, #120).
- **Evidence**: `main.py:104-108` has no try/except around the mapper call; the packer call
  sites (`main.py:588-590`, `:953-956`) sit inside guarded blocks that degrade to a drumless
  build.
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
  (`layers` lists); `nes/emulator_core.py:212` (same-frame collapse) +
  `:43-45` (warning text)
- **Status**: NEW
- **Description**: For a note in `ADVANCED_MIDI_DRUM_MAPPING` whose entry has a `layers`
  list (only 36/kick and 38/snare), `map_drums` appends the primary DPCM event and then calls
  `_handle_layered_samples`, which appends a **second** event on the same frame for every
  layer name present in the index. The layer lists are `["kick", "kick_sub"]` and
  `["snare", "snare_rattle"]` — the first element is the *primary itself* (guaranteeing a
  duplicate), and the second (`kick_sub`/`snare_rattle`) is absent from the shipped index (so
  skipped). Net effect on the shipped catalog: a kick/snare hit always emits two identical
  DPCM events on one frame. Downstream, `_collapse_same_frame_events`
  (`nes/emulator_core.py:212`) collapses them to one and prints
  `"Warning: N note(s) on dpcm dropped — multiple notes quantized to the same 60Hz frame
  (monophonic channel; use --arranger to arpeggiate polyphony)."` — a false alarm, since
  nothing musical was lost; the "dropped" event was a self-inflicted duplicate of the same
  sample. Layering is also physically impossible on the DMC anyway: it is a single
  monophonic channel (`docs/APU_DMC_REFERENCE.md` §1 — one Reader/Buffer/Shifter/Output
  unit), so two simultaneous samples can never both sound.
- **Evidence**:
  ```
  events = {'drums':[{'frame':0,'note':36,'velocity':100}]}   # kick
  dpcm, noise = EnhancedDrumMapper('dpcm_index.json').map_drums(events)
  # dpcm == [{'frame':0,'sample_id':1318,...}, {'frame':0,'sample_id':1318,...}]
  #   -> two identical events; process_all_tracks collapses to one and warns
  #      "1 note(s) on dpcm dropped".
  ```
- **Impact**: No audible corruption (the collapse keeps one copy of the correct sample), but:
  (a) a spurious "note dropped" warning misleads users into thinking polyphony was lost;
  (b) wasted allocation/accounting work in the sample manager; (c) the layering feature is
  inert — it can only ever duplicate the primary or reference nonexistent samples, and the
  DMC cannot layer regardless. Dead/misleading code.
- **Related**: #96 (same-frame collapse warning); DP-03 (same advanced-mapping path).
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §1 — the DMC is a single monophonic channel;
  simultaneous sample layering on it is not possible.
- **Suggested Fix**: Remove `_handle_layered_samples` and the `layers` lists (the DMC can't
  layer), or — if a "layer" is meant as an alternate/fallback sample — dedupe against the
  primary and never emit two DPCM events on one frame so the collapse warning stays truthful.

---

## Re-verified as fixed / not reported

- **D-17 / #254 (`MAX_SAFE_SAMPLE_ID` guard)** — removed. Confirmed end-to-end: `map_drums`
  on the shipped index emits DPCM events for kick/snare/hi-hat (ids 1318/1620/1926) rather
  than routing them to noise. Not re-filed.
- **Dense-remap round-trip (#200)** — `nes/emulator_core.py:214-235` renumbers referenced
  catalog ids to dense `0..N-1` and emits `dpcm_sample_map`; both packer call sites
  (`main.py:588-590`, `:953-956`) pass `get_dpcm_sample_ids_from_frames(frames)` as
  `sample_ids=` into `load_dpcm_index_into_packer`, which keys the positional lookup tables
  by dense id. Exporter clamps the `dpcm` `note` to 255 (not the 95 tone ceiling) in both the
  bytecode (`exporter_ca65.py:427`) and direct-frames (`:1072-1074`) paths; trigger recovers
  `sample_id = note - 1` (`:803-806`). Correct and consistent.
- **`$4011` silence init / register write order** — `nes/mmc3_init.asm` writes `$00` to
  `$4011` before `$4010`; the generated `play_dpcm` trigger writes `$4010`→`$4012`→`$4013`
  then triggers via `$4015`, matching `docs/APU_DMC_REFERENCE.md` §6. Sample data stays
  within the 8KB R6 window ($C000–$DFFF, `BANK_SIZE=8192`), so the `$FFFF`→`$8000` wrap quirk
  (§4) is not reachable. Not a gap.
- **DPCM converter (`dpcm_sampler/dpcm_converter.py`)** — `convert_wav_to_dmc` /
  `dpcm_compress` / `delta_encode` have no callers outside the module and tests
  (`grep` confirmed), so their bit-polarity/start-level/resample assumptions are not
  shipping-ROM paths. Not re-filed.
- **Sample manager (#69/#70/#71)** — monotonic `_next_id`, unified `metadata['size']` memory
  accounting, and removed similarity/dedup remain in place. No regression.
- **`dpcm_index.json` schema** — entries still carry only `id` + `filename`;
  `length`/`data`/`frequency`/`pitch` still fall back to defaults on real input, consistent
  with the removal of the dead code that depended on them. Acceptable simplification; not a
  bug.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-07-06.md
```
