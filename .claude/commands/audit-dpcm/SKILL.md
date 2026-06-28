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

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,4`). Default: all.

## Extra Per-Finding Field
- **Hardware ref**: the `docs/APU_DMC_REFERENCE.md` / `docs/NES_DMA_REFERENCE.md`
  section backing any hardware claim (omit for pure-software findings).

## Dimensions

### Dimension 1: Drum-note → sample mapping & coverage
The GM-note maps live in `dpcm_sampler/drum_engine.py`
(`DEFAULT_MIDI_DRUM_MAPPING`, `ADVANCED_MIDI_DRUM_MAPPING`). Check coverage and the
silent-drop path in `EnhancedDrumMapper.map_drums` (`dpcm_sampler/enhanced_drum_mapper.py`):
- `DEFAULT_MIDI_DRUM_MAPPING` covers only 7 notes (36/38/40/42/46/49/51); the GM
  percussion range is 35–81. A note absent from the map (and absent from
  `self.sample_index`) falls through to `noise_events` — confirm whether unmapped
  hits become noise or are dropped entirely, and whether velocity-0 note-offs are
  correctly skipped (`if e.get('velocity', 0) == 0: continue`).
- `ADVANCED_MIDI_DRUM_MAPPING` only fully defines notes 36 and 38 (with a trailing
  `# Add more mappings...` stub). When `use_advanced=True`, every other drum note
  hits `mapping.get(midi_note)` → `None`. Verify the fallback and whether this
  silently strips toms/cymbals — silently dropped audible hits ⇒ at least MEDIUM,
  HIGH if the noise fallback also doesn't fire.
- `_get_advanced_sample` selects by `velocity_ranges`; confirm a sample name it
  returns (e.g. `kick_soft`, `snare_rattle`) actually exists in the loaded index —
  a name not in `self.sample_index` is dropped at the `sample_name in self.sample_index`
  guard.

### Dimension 2: `dpcm_index.json` schema integrity
The index is loaded in three places against two different shapes:
- `EnhancedDrumMapper._load_sample_index` (`dpcm_sampler/enhanced_drum_mapper.py`)
  passes each entry as `sample_data` to `DPCMSampleManager.allocate_sample`, which
  reads `sample_data.get('length', 1024)`, `sample_data.get('data', [])`, and
  `sample_data.get('frequency', 33144)`.
- The real `dpcm_index.json` and `test_dpcm_index.json` entries only contain
  **`id`** and **`filename`** (verify: `python -c "import json;
  print(list(json.load(open('dpcm_index.json')).values())[0])"`). So `length`,
  `data`, and `frequency` always fall back to defaults — the sample manager's
  memory accounting and similarity comparison operate on placeholder data, not the
  real samples. Assess the correctness/severity of that disconnect.
- The packer path in `main.py` (`run_export` ~lines 104–121 and the full pipeline
  ~lines 372–411) reads `sample.get('pitch', 15)` and `sample['filename']` —
  `pitch` is also absent from the shipped index. Confirm the `id`/`filename` keys
  are the only ones any consumer can rely on, and whether `generate_dpcm_index`
  (`dpcm_sampler/generate_dpcm_index.py`) is the sole writer (it emits exactly
  `id` + `filename`).

### Dimension 3: DPCM conversion correctness (1-bit delta)
`dpcm_sampler/dpcm_converter.py` does WAV→PCM→delta→packed-bits:
- `delta_encode` walks a ±1 step counter, but `dpcm_compress` then re-derives the
  bit purely from `encoded[i] > encoded[i-1]`. Check that the two stages agree and
  that the bit polarity matches hardware: per `docs/APU_DMC_REFERENCE.md`, a `1`
  bit **adds 2** to the output level and `0` **subtracts 2** (the engine never sets
  a level, only nudges ±2). A constant-input run encodes all-zero bits ⇒ the level
  ramps *down* on playback — verify the start-level assumption (`prev = 0x40`).
- Bit packing order: `byte |= (bits[i+j] << j)` packs LSB-first. Confirm against the
  DMC shifter order in `docs/APU_DMC_REFERENCE.md` ("Reader → Buffer → Shifter")
  — wrong bit order plays the sample bit-reversed (audible garbage).
- Resampling: `convert_wav_to_unsigned_pcm` uses `np.interp` linear resampling to a
  fixed `sample_rate=8000`, independent of the DMC rate index written elsewhere
  (`pitch`/`$4010`). Flag any mismatch between the conversion rate and the playback
  rate index that would pitch-shift samples.

### Dimension 4: Sample size / address / DMC range constraints
`dpcm_sampler/dpcm_packer.py` computes the `$4012`/`$4013` register values:
- `_place_sample`: `address_reg = (start_address - 0xC000) // 64` and
  `length_reg = (sample['size'] - 1) // 16`. Verify against
  `docs/APU_DMC_REFERENCE.md`: address = `$C000 + A*64`, length = `(L*16)+1` bytes.
  A `size` not of the form `16k+1` makes the round-trip lossy — the engine will
  read `(length_reg*16)+1` bytes, which can over- or under-read the sample. Assess
  whether the packer enforces the 16-byte+1 length quantization or just floors it.
- The 4081-byte cap appears in two places with different behavior:
  `dpcm_converter.dpcm_compress` **silently truncates** with `dmc_bytes[:4081]`,
  while `DpcmPacker.add_sample` **raises** `ValueError` on `size_bytes > 4081`.
  Silent truncation drops the tail of a long sample (audible) ⇒ at least MEDIUM.
- `START_ADDR = 0xC000`, `BANK_SIZE = 8192`, and the 60-bank ceiling
  (`OverflowError` in `_pack_samples`). Check `.align 64` in `generate_assembly`
  keeps every sample 64-byte aligned, and whether anything guards the
  `$FFFF`→`$8000` address-wrap quirk documented in `docs/APU_DMC_REFERENCE.md`
  (a sample bleeding past `$FFFF` plays garbage from `$8000`).

### Dimension 5: DMC level handling & DMA-timing implications
- DMC output level (`$4011`) is emitted by the CA65 exporter
  (`exporter/exporter_ca65.py`: `APU_DMC_LOAD = 0x4011`, the `dmc_level` plumbing
  around lines 765–826, and the `CMD_DMC_LEVEL` byte `$87` near line 939). Verify
  `dmc_level` is clamped to the 7-bit 0–127 range `$4011` accepts
  (`docs/APU_DMC_REFERENCE.md`) — an out-of-range value emitted as
  `${event["dmc_level"]:02X}` would corrupt the byte / wrap.
- Silence init: `docs/APU_DMC_REFERENCE.md` says init should write `$00` to `$4011`
  so the DMC counter doesn't muffle Triangle/Noise via the non-linear mixer. Confirm
  the generated init does this (`nes/mmc3_init.asm` writes `STA $4011`; check it is
  actually 0) and that `seq_cmd_dpcm_play` in `nes/project_builder.py` writes
  `$4010`/`$4012`/`$4013` in a valid order.
- DMA cost: `docs/NES_DMA_REFERENCE.md` notes each DMC DMA steals 3–4 CPU cycles and
  a heavy drum catalog fires constantly, delaying OAM DMA and corrupting
  side-effect reads (`$4016`/`$2007`/`$4015`). This subsystem can't avoid the cost,
  but flag if the generated engine/docs omit the mandatory DPCM-safe controller-read
  warning, or if rapid back-to-back triggers are emitted with no awareness of the
  cycle budget.

### Dimension 6: Config robustness (`DrumMapperConfig`)
`dpcm_sampler/enhanced_drum_mapper.py` defines `DrumMapperConfig`,
`DrumPatternConfig`, `SampleManagerConfig` with `validate()` / `to_file` /
`from_file`:
- `from_file` does `DrumPatternConfig(**config_data.get('pattern_detection', {}))` —
  an unexpected key in the JSON raises `TypeError` (not caught; only
  `FileNotFoundError`/`JSONDecodeError` are). Assess whether a hand-edited config
  with a stray/renamed key crashes ungracefully.
- `validate()` enforces weight sums ≈ 1 and ranges, but `EnhancedDrumMapper.__init__`
  only calls `self.config.validate()` for the default/passed config — confirm a
  config loaded via `from_file` is validated before use.
- `SampleManagerConfig.memory_limit` is bounded 1KB–16KB and `max_samples` 1–64, but
  `DPCMSampleManager.__init__` defaults (`max_samples=16, memory_limit=4096`) are set
  independently. Check the config bounds actually reach the manager and aren't
  bypassed by the direct constructor defaults.

### Dimension 7: Sample-manager dedup & lifecycle
`dpcm_sampler/dpcm_sample_manager.py`:
- `allocate_sample` assigns `'id': len(self.active_samples)` — after a
  `_remove_sample`/`_optimize_sample_bank` eviction, a later allocation can **reuse
  an id already referenced** by emitted `dpcm_events` (the events carry
  `allocated_sample['id']`). Trace whether an evicted-then-reallocated id makes a
  drum event point at the wrong sample ⇒ wrong sound, at least MEDIUM.
- Memory accounting is inconsistent: `allocate_sample` sums
  `s['metadata']['size']` (defaults to the `length` placeholder, 1024) while
  `_get_total_memory` returns `len(s['data'])//8` (data is `[]` for the shipped
  index ⇒ always 0). Two different notions of "memory used" — assess which one
  drives eviction and whether the limit is ever actually enforced.
- `_find_similar_sample` / `_calculate_sample_similarity` compare `data` arrays that
  are empty for real index entries — the similarity/dedup path is effectively
  inert on production data. Flag as dead-on-real-input behavior.

### Dimension 8: Channel-pipeline integration (noise vs DMC)
`tracker/track_mapper.py` `assign_tracks_to_nes_channels(midi_events, dpcm_index_path)`
(called from `main.py` `run_map` and the full pipeline, always with the literal
`'dpcm_index.json'`):
- It calls `map_drums_to_dpcm` and routes results: `nes_tracks['dpcm'] =
  dpcm_events` (overwriting any prior dpcm assignment) and
  `noise_events` only land on `noise` **if** `noise` is empty
  (`if noise_events and not nes_tracks['noise']`). Verify drum noise-fallback isn't
  silently discarded when a real noise track already exists ⇒ dropped hits.
- The hardcoded `'dpcm_index.json'` path in `main.py` means a missing file raises
  inside `_load_sample_index` — confirm whether the map stage degrades gracefully or
  hard-fails when no index is present (contrast with the packer path, which prints
  "No dpcm_index.json found, skipping").
- Downstream, `dpcm_events` carry `{frame, sample_id, velocity}` but the exporter
  channel loop (`exporter/exporter_ca65.py`, the `'dpcm'` channel) and the
  frame-generation contract from `_audit-common.md` expect `{note, volume, ...}`.
  Trace whether `sample_id`/`velocity` survive into `music.asm` correctly or are
  dropped/mistranslated — a contract break here is at least HIGH.

## Skeptical checklist
- [ ] Does an unmapped GM drum note become noise, or vanish? Confirm by tracing a
      note like 47 (mid tom) through `map_drums`.
- [ ] Does `use_advanced=True` silently drop every note except 36/38?
- [ ] Do `length`/`data`/`frequency` ever come from the index, or always defaults?
- [ ] Is `length_reg = (size-1)//16` lossy for a sample not sized `16k+1`?
- [ ] Converter truncates >4081 silently; packer raises — which path runs in the
      default pipeline, and can a too-long sample reach playback?
- [ ] Is `dmc_level` clamped to 0–127 before `$4011`?
- [ ] Can an evicted sample id be reused and mis-point a drum event?
- [ ] Is the memory limit ever actually enforced given the two accounting methods?
- [ ] When a real noise track exists, are drum noise-fallback hits discarded?
- [ ] Does the `dpcm` channel's `sample_id`/`velocity` survive into `music.asm`?

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
