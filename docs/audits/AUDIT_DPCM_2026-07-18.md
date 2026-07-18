# DPCM / Drum-Sampling Audit — 2026-07-18

Scope: `dpcm_sampler/` (drum mapping, sample manager, converter, packer, index
generation) plus the DMC-facing edges of the channel pipeline
(`tracker/track_mapper.py`, `nes/emulator_core.py`, `nes/audio_engine.asm`,
`nes/project_builder.py`). Hardware claims cite `docs/APU_DMC_REFERENCE.md` and
`docs/NES_DMA_REFERENCE.md`.

## 1. Summary

The recent bug-fixing sprint plus the just-landed `DPCM_ROLE_ALIASES` change
(#315/DP-07) hold up well. Verified fixes (no regressions found):

- **#315/DP-07 (alias table)** — confirmed working. All 10 alias targets
  (`tamborin`, `whistle1/2`, `guiro1/2`, `cuica1/2`, `mario_2_woodblock`×2,
  `stickrim`) exist in the shipped `dpcm_index.json`, so notes for tambourine,
  whistles, guiros, cuicas, woodblocks and side-stick now resolve to real samples
  instead of falling to noise.
- **#73/D-10 cascade** — a mid note (47→`tom_mid`) and the velocity-split fallthrough
  both resolve. The advanced velocity-split names (`kick_soft/hard`,
  `snare_soft/hard`, `kick_sub`, `snare_rattle`) are all absent from the catalog, so
  the cascade correctly falls through to the `primary` name (`kick`/`snare`, both
  present). No event is dropped for a missing velocity-split candidate.
- **#295/DP-01 (length ceiling)** — `_place_sample` uses `(size+14)//16` (ceiling);
  `size` is bounded to 4081 by `add_sample`, so `length_reg` max = 255 (fits the
  8-bit `$4013`). Matches the `(L*16)+1` formula in `docs/APU_DMC_REFERENCE.md` §2.
- **#68 / #140** — oversized samples truncate to 4081 (both `add_sample` and
  `dpcm_compress`); packing is frame-filtered via `get_dpcm_sample_ids_from_frames`.
- **#72/D-09 + silence init** — `$4011` silence init is present and correct in the
  *live* engine path: `nes/audio_engine.asm:124-128` loads `#$00` then `sta $4011`
  before APU enable (the skill cited `nes/mmc3_init.asm`, which is dead code per
  open #203 — the real init is in `audio_engine.asm`). The DPCM trigger writes
  `$4010`→`$4012`→`$4013`→`$4015` (audio_engine.asm:245-254), matching
  `docs/APU_DMC_REFERENCE.md` §6, and a `read_joypad_safe` double-read macro is
  emitted for the DMA glitch (`docs/NES_DMA_REFERENCE.md` §5).
- **#69/#70/#71 (sample manager)** — `_next_id` is monotonic; memory accounting is
  unified on `metadata['size']`; the dead similarity/dedup code is gone.
- **#74/D-11 (noise discard warning)** — the warning at `track_mapper.py:315-317`
  reports exactly `len(noise_events)` and is the only discard path.
- **#76/D-13 (config `TypeError`)** — appears **fixed on this tree** (commit
  8a2457a, #318): `DrumMapperConfig.from_file` now catches `TypeError` and re-raises
  it as `ValueError` (`enhanced_drum_mapper.py:192-193`). The skill lists this as
  still-open; it is no longer reproducible.
- **$8000 address-wrap quirk** — structurally impossible: samples are confined to a
  single 8 KB bank (`$C000–$DFFF`), so the address counter never approaches `$FFFF`
  (`docs/APU_DMC_REFERENCE.md` §4).

Confirmed still-open (dedup, not re-counted): **#256/D-18** — `run_map` guards its
input JSON (`load_json_stage`) but not a missing `dpcm_index.json`;
`_load_sample_index` still raises a raw `FileNotFoundError` there while the packer
path degrades gracefully.

### Finding counts
- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 4

No drop/round-trip issue rises above LOW; the highest-value residual is the
dense-remap byte ceiling (DP-DPCM-04), which silently aliases only the 256th-plus
distinct drum in a single song.

## 2. Findings

### DP-DPCM-01: Four GM percussion roles have no sample and no alias (fall to noise)
- **Severity**: LOW
- **Dimension**: 1 (drum-note → sample coverage)
- **Location**: `dpcm_sampler/drum_engine.py:7-73` (mapping + `DPCM_ROLE_ALIASES`)
- **Status**: NEW
- **Description**: After the #315 alias fix, four `DEFAULT_MIDI_DRUM_MAPPING` roles
  still have no identically-named catalog entry and no alias: `splash` (note 55),
  `vibraslap` (58), `triangle_mute` (80), `triangle_open` (81). Verified against the
  live `dpcm_index.json` (1941 entries) — none of those four names, nor an obvious
  alias, exists. `_resolve_dpcm_sample_name` returns `None` for these, so they route
  to the noise fallback rather than DPCM.
- **Evidence**: catalog probe — `splash`, `vibraslap`, `triangle_mute`,
  `triangle_open` all MISSING; the drum_engine comment (`drum_engine.py:57-61`)
  explicitly documents them as a deliberate asset gap.
- **Impact**: Songs using a splash cymbal, vibraslap, or MIDI triangle get a noise
  burst instead of a sample. Audible content is preserved (noise is a reasonable NES
  substitute), so not a data-loss case — a coverage/asset gap. Blast radius: any
  drummed song touching those four GM keys.
- **Related**: #315/DP-07 (alias table), DP-DPCM-02.
- **Suggested Fix**: Either add `.dmc` assets + index entries for these four, or
  extend `DPCM_ROLE_ALIASES` to the nearest existing catalog sound (e.g.
  `splash`→a crash variant). No code change needed once assets/aliases exist.

### DP-DPCM-02: DPCMSampleManager runs on placeholder sizes and never affects output
- **Severity**: LOW
- **Dimension**: 2 / 7 (index schema, sample-manager lifecycle)
- **Location**: `dpcm_sampler/dpcm_sample_manager.py:34,58`;
  `dpcm_sampler/enhanced_drum_mapper.py:308,381,462`
- **Status**: NEW
- **Description**: Real `dpcm_index.json` entries carry only `id` + `filename`
  (verified), so `allocate_sample` always defaults `length` to 1024 and `frequency`
  to 33144 for every sample. Every sample therefore has an identical fictional size,
  and the memory-limit/eviction machinery (`_get_total_memory`,
  `_optimize_sample_bank`) operates entirely on that placeholder. More importantly,
  the manager's allocation/eviction has **no effect on the packed ROM**: what gets
  packed is driven by frame references via `get_dpcm_sample_ids_from_frames`, not by
  `sample_manager.active_samples`. The `allocate_sample` calls exist only "for
  usage/eviction side effects" (per the code comment), which never reach output.
- **Evidence**: `dpcm_sample_manager.py:34` `sample_data.get('length', 1024)`;
  `:58` `get('frequency', 33144)`; index probe shows keys `['id','filename']` only;
  packing path (`generate_dpcm_index.load_dpcm_index_into_packer`) reads real
  `os.path.getsize`, ignoring the manager entirely.
- **Impact**: The eviction subsystem is vestigial for real input — dead-weight
  complexity, not a correctness bug. Uniform 1024-byte accounting could evict the
  "wrong" sample, but since eviction doesn't gate packing, output is unaffected.
- **Related**: #71/D-08 (dead similarity code already removed), DP-DPCM-01.
- **Suggested Fix**: Either back-fill real `size`/`rate` from the `.dmc` files at
  index-generation time (so the manager reflects reality if it is ever wired into
  packing), or drop the now-inert allocate-for-side-effect calls and the
  size/eviction logic that never influences the ROM.

### DP-DPCM-03: dpcm_converter is orphaned; its rate/start-level assumptions would mis-pitch samples if used
- **Severity**: LOW
- **Dimension**: 3 (DPCM conversion correctness)
- **Location**: `dpcm_sampler/dpcm_converter.py:5,34,67`
- **Status**: NEW
- **Description**: `dpcm_converter.py` is not referenced anywhere in the codebase
  (grep for `dpcm_converter` / `convert_wav_to_dmc` finds only the module itself and
  its `__main__`); `generate_dpcm_index` scans pre-made `.dmc` files directly. Bit
  packing (`byte |= bits[i+j] << j`, LSB-first) and polarity (`1`=level-up) both
  match `docs/APU_DMC_REFERENCE.md` §1/§3, so the encoder is correct in isolation.
  However, two assumptions would produce wrong output if the tool were ever wired in:
  (a) it resamples to a fixed `sample_rate=8000` Hz independent of the playback rate
  index, while the packer defaults `pitch_rate=15` (NTSC rate index 15 ≈ 33144 Hz),
  so a sample encoded at 8 kHz played at rate 15 runs ~4× fast (pitched up ~2
  octaves); (b) `delta_encode` assumes a reconstruction start level of `prev=0x40`
  (64), but the hardware output level starts at `$00` (the engine's `$4011` silence
  init), producing a startup DC ramp on every sample.
- **Evidence**: `dpcm_converter.py:5` `sample_rate=8000`; `dpcm_packer.add_sample`
  `pitch_rate=15` default; `docs/APU_DMC_REFERENCE.md` §2 (rate index) / §3 (output
  level start); grep shows zero non-self callers.
- **Hardware ref**: `docs/APU_DMC_REFERENCE.md` §2 (`$4010` rate index), §3
  (output level starts from the current `$4011` value, add/subtract 2).
- **Impact**: Currently none (dead tool). Latent: anyone using it to regenerate the
  `.dmc` catalog would get pitch-shifted samples and an attack transient.
- **Related**: DP-DPCM-02.
- **Suggested Fix**: If keeping the converter, derive its target sample rate from the
  intended DMC rate index (or write a matching `pitch` into the index), and start
  `delta_encode` at 0 to match the `$4011`-init playback level. Otherwise mark it
  clearly experimental / remove it.

### DP-DPCM-04: Dense-remap byte ceiling silently aliases the 256th+ distinct drum with no warning
- **Severity**: LOW
- **Dimension**: 8 (channel-pipeline integration / round-trip)
- **Location**: `nes/emulator_core.py:220`
- **Status**: NEW
- **Description**: The dense remap encodes `note = min(255, dense_id + 1)`. For a
  song referencing N distinct DPCM samples, `dense_id` ranges 0..N-1. At N ≤ 255 the
  round-trip is exact (max `note` = 255). At N ≥ 256, `dense_id = 255` also encodes
  to `note = 255` and collides with `dense_id = 254`; every `dense_id ≥ 255` becomes
  unreachable and its hits play sample #254 instead. The `min()` clamp prevents an
  out-of-range byte (no crash), but the aliasing is silent — no warning, unlike the
  same-frame-collapse drop counters nearby. This is the residual of #200/D-14 pushed
  to the dense level rather than the raw-catalog level.
- **Evidence**: `emulator_core.py:207-223` builds `dense_id_of` and encodes
  `min(255, dense_id + 1)` with no branch/warning when `len(referenced_ids) > 255`.
- **Impact**: A song with 256+ distinct drum samples (packable — 256 tiny 64-byte
  samples fit in ~2 banks) silently plays the wrong sample for the overflow drums.
  Musically near-unreachable, but the failure mode is silent wrong-content.
- **Related**: #200/D-14 (raw-catalog aliasing, fixed by this remap).
- **Suggested Fix**: When `len(referenced_ids) > 255`, emit a warning (mirroring the
  same-frame-collapse drop count) so the aliasing is visible; optionally document the
  255-distinct-drum ceiling.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-07-18.md
```
