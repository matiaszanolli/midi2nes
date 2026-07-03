# DPCM / Drum-Sampling Audit — 2026-07-03

Audit of the DPCM/drum subsystem: GM-percussion → DPCM sample mapping, WAV→1-bit-delta
conversion, sample packing/addressing, and the DMC-facing edges of the channel pipeline
and CA65 exporter. Scope per `.claude/commands/audit-dpcm/SKILL.md`.

Hardware claims cite `docs/APU_DMC_REFERENCE.md` and `docs/NES_DMA_REFERENCE.md`.

This is a follow-up to `docs/audits/AUDIT_DPCM_2026-06-29.md` (D-01 … D-13). That report's
CRITICAL/HIGH findings (D-01 filename resolution, D-02 sample_id id-space, D-03 stale-Z
rest guard, D-04 note-95 clamp, D-05 oversized-sample abort) were confirmed fixed by
commits `be4d2bd`…`8225696` (issues #64–#74, #140) — re-verified below, all still hold.
D-12 (#75, `length_reg` floors) and D-13 (#76, `from_file` uncaught `TypeError`) remain
open and unchanged; not re-counted here.

The main result of this pass: verifying the *exact* edge case the prior audit's
Dimension-8 checklist flagged ("does `sample_id`/`velocity` survive correctly near the
254 ceiling?") turned up a **new CRITICAL** — the byte-width ceiling introduced by the
D-04 fix (255) is far below the real shipped `dpcm_index.json`'s id range (0–1922), and
every commonly-named drum sample in the shipped catalog sits above that ceiling.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 0 |
| MEDIUM   | 1 |
| LOW      | 1 |
| **Total**| **3** |

Highest-risk finding:

- **D-14 (CRITICAL, NEW)** — `sample_id` is carried through the pipeline as a single
  byte (`note = min(255, sample_id + 1)`), but the shipped `dpcm_index.json` has 1923
  entries (ids 0–1922). Every named drum sample the default mapper can actually resolve
  (`kick`=1318, `snare`=1620, `ride`=1526, `cowbell`=1119, `clap`=1096, `cabasa`=1083,
  `maracas`=1437, `claves`=1102) has an id ≥ 255, so **every one of them collapses to the
  same `note=255` → decoded `sample_id=254`** — one arbitrary sample (`22.dmc` in the
  shipped index) silently plays for every distinct percussion instrument, with zero
  warning anywhere in the pipeline.

---

## Findings

### D-14: `sample_id` byte ceiling (255) is far below the shipped index's real id range (0–1922) — all named drums alias to one sample
- **Severity**: CRITICAL
- **Dimension**: 8 (channel-pipeline integration) / 1 (mapping coverage)
- **Location**: `nes/emulator_core.py:209` (`"note": min(255, sample_id + 1)`);
  `exporter/exporter_ca65.py:984-986` (same clamp, direct/bytecode note-stream path);
  `dpcm_sampler/enhanced_drum_mapper.py:294,362,434` (`"sample_id": sample_data['id']`,
  the raw, unbounded index id fed into the clamp); `dpcm_sampler/generate_dpcm_index.py:105-117`
  (`get_dpcm_sample_ids_from_frames`, which only sees the already-collided `note` field
  by the time packing happens)
- **Status**: NEW (root cause distinct from, but a direct consequence of, the fix for the
  closed `D-04`/#67 — that fix correctly removed the old 0–95 MIDI-note ceiling and
  replaced it with a "byte format" ceiling of 255, but never checked that ceiling against
  the real shipped index's actual id range)
- **Description**: `EnhancedDrumMapper.map_drums`/`_handle_pattern_event`/`_handle_layered_samples`
  all emit `dpcm_events[...]["sample_id"] = sample_data['id']` — the *raw*
  `dpcm_index.json` id, unbounded (0–1922 in the shipped index; see Dimension 2 of the
  audit-dpcm skill, "index id... indexes the packer tables"). `nes/emulator_core.py:209`
  then encodes this into the single-byte frame `note` field as `min(255, sample_id + 1)`.
  Any `sample_id >= 254` collapses to `note = 255`; the trigger routine's
  `sample_id = note - 1` (`nes/project_builder.py` `seq_cmd_dpcm_play` /
  `exporter/exporter_ca65.py` `play_dpcm`) therefore recovers `sample_id = 254` for
  **every** original id ≥ 254, not just the true id-254 sample. Downstream,
  `get_dpcm_sample_ids_from_frames` (`dpcm_sampler/generate_dpcm_index.py:105-117`) reads
  frame `note` (already collapsed) to decide which samples to pack (#140's
  referenced-samples-only optimization) — so a song using `kick` and `snare` (ids 1318,
  1620) resolves `sample_ids = {254}`: the packer loads and includes exactly **one**
  physical `.dmc` file (whatever the shipped index happens to assign id 254 — `22.dmc`),
  and both the kick and the snare hit trigger that same file at runtime. No stage detects
  or warns about the collision; `main.py`'s pack step reports success
  (`loaded_samples > 0`) because a sample *did* load — just not the one requested.
- **Evidence**:
  ```
  $ python3 -c "
  import json; d = json.load(open('dpcm_index.json'))
  for name in ['kick','snare','ride','cowbell','clap','cabasa','maracas','claves']:
      print(name, d[name]['id'])
  "
  kick 1318
  snare 1620
  ride 1526
  cowbell 1119
  clap 1096
  cabasa 1083
  maracas 1437
  claves 1102
  # 1668 of 1923 shipped samples (87%) have id > 254.

  $ python3 -c "
  from nes.emulator_core import NESEmulatorCore
  core = NESEmulatorCore()
  tracks = {'dpcm': [{'frame': 0, 'sample_id': 1318, 'velocity': 100},   # kick
                      {'frame': 10, 'sample_id': 1620, 'velocity': 100}]} # snare
  print(core.process_all_tracks(tracks)['dpcm'])
  "
  {0: {'note': 255, 'volume': 15}, 10: {'note': 255, 'volume': 15}}
  # Both distinct instruments produce the identical frame — indistinguishable at
  # every later stage, including which .dmc file the packer includes.
  ```
  `id 254` in the shipped `dpcm_index.json` is `{"id": 254, "filename": "22.dmc"}` — an
  unnamed, arbitrary sample unrelated to either kick or snare.
  `tests/test_audio_fixes.py:147-157` (`test_high_sample_id_not_clamped_to_note_95`)
  documents `sample_id=9999 → note=255` as the *expected* result — the byte-format
  ceiling itself is intentional and tested, but no test exercises two distinct high ids
  colliding to the same decoded sample, so the aliasing was never caught.
- **Impact**: On the shipped `dpcm_index.json`, every song that uses more than one
  DPCM-mapped drum voice (which is the common case — kick + snare is the minimum useful
  drum kit) has all of its distinct percussion silently replaced by a single arbitrary
  sample, with the pipeline reporting success at every stage (`✓ Packed 1 DPCM samples
  across 1 banks`). This is a silent, total loss of intended percussion content — the
  song plays, but not the drums it was given. Blast radius: every ROM built through the
  default pipeline (or `export`) whose drums route to DPCM via the default/advanced
  mapping tables and the shipped 1923-sample index.
- **Related**: Regression-adjacent to closed `D-04`/#67 (raised the ceiling from 95 to
  255 but never validated it against the real index's 0–1922 range); compounds with the
  coverage gap in D-15 below (most GM notes fall through to noise anyway, but the ones
  that *do* resolve to DPCM are the ones broken here).
- **Suggested Fix**: Either (a) widen the wire format so `sample_id` is not squeezed into
  a single byte shared with the rest sentinel (e.g. a dedicated 2-byte `sample_id` field,
  or reserve `note=0` only and allow `note` up to the true max referenced id + 1 with a
  hard pipeline-time assertion that no referenced id exceeds 254), or (b) remap referenced
  index ids to a dense 0..N range at pack time (the `sample_ids` set already computed by
  `get_dpcm_sample_ids_from_frames` — assign each *referenced* sample a fresh 0-based id
  before this clamp is applied, so real catalogs larger than 255 entries still work as
  long as a single song references ≤ 255 distinct samples). At minimum, add a loud
  warning/error when `sample_id + 1 > 255` instead of silently aliasing.

### D-15: `DEFAULT_MIDI_DRUM_MAPPING`'s GM-wide coverage (#73) is code-complete but the shipped `dpcm_index.json` backs only 8 of 40 role names
- **Severity**: MEDIUM
- **Dimension**: 1 (mapping coverage) / 2 (index schema)
- **Location**: `dpcm_sampler/drum_engine.py:8-56` (`DEFAULT_MIDI_DRUM_MAPPING`);
  `dpcm_index.json` (shipped data)
- **Status**: NEW (the code fix for #73/D-10 is confirmed correct and not regressed —
  this flags a residual data/asset gap the code fix cannot address on its own)
- **Description**: `DEFAULT_MIDI_DRUM_MAPPING` now defines 47 generic role names across
  the full GM percussion range (35–81), and `_resolve_dpcm_sample_name`'s fallback chain
  correctly reaches it (re-verified: cascade order velocity-split → primary → default
  role name, each gated by `if name in self.sample_index`). However the *shipped*
  `dpcm_index.json` — the only index that ships with the repo — only contains 8 of the 40
  distinct role names the table can produce (`kick`, `snare`, `clap`, `ride`, `cowbell`,
  `cabasa`, `maracas`, `claves`); the other 32 (`tom_low`, `tom_mid`, `tom_high`,
  `hihat_closed`, `hihat_open`, `crash`, `china`, `ride_bell`, `tambourine`, `splash`,
  `vibraslap`, `bongo_hi/lo`, `conga_mute/open/lo`, `timbale_hi/lo`, `agogo_hi/lo`,
  `whistle_short/long`, `guiro_short/long`, `woodblock_hi/lo`, `cuica_mute/open`,
  `triangle_mute/open`, `side_stick`, `hihat_pedal`) are absent, so those GM notes still
  resolve to `None` and fall through to the noise channel.
- **Evidence**:
  ```
  $ python3 -c "
  import json; d = json.load(open('dpcm_index.json')); names = set(d)
  roles = [...40 DEFAULT_MIDI_DRUM_MAPPING values...]
  print(sum(1 for r in roles if r in names), 'of', len(roles), 'present')
  "
  8 of 40 present
  ```
- **Impact**: On the shipped catalog, 80% of GM percussion notes still degrade to the
  noise fallback rather than DPCM, even though the *code path* fix for #73 is verified
  correct. This is not a logic bug (the noise fallback is the documented, sane behavior
  for an unresolvable name) but it means the practical benefit of the GM-wide coverage
  fix is currently limited by asset naming, not code. Toms/hi-hats/cymbals/crash — the
  most audible non-kick/snare percussion — are all in the missing set.
- **Related**: D-14 above (the DPCM samples that *do* resolve are further broken by the
  id-ceiling collision).
- **Suggested Fix**: Either rename/alias a subset of the shipped `.dmc` files to the
  `DEFAULT_MIDI_DRUM_MAPPING` role names (even a handful of toms/hats/crash would move
  most real songs off the noise fallback), or add an index-generation step that maps
  role names to nearest-available samples by filename heuristics.

### D-16: `_handle_pattern_event` ignores the caller's `use_advanced` flag
- **Severity**: LOW
- **Dimension**: 1 (mapping coverage)
- **Location**: `dpcm_sampler/enhanced_drum_mapper.py:352`
- **Status**: NEW
- **Description**: `map_drums(midi_events, use_advanced)` threads `use_advanced` into
  the non-pattern path's `_resolve_dpcm_sample_name(midi_note, velocity, use_advanced)`
  (line 279), but the pattern-matched path's `_handle_pattern_event` calls
  `self._resolve_dpcm_sample_name(template_note, velocity)` (line 352) with no third
  argument, so it always uses the default `use_advanced=True` regardless of what the
  caller passed to `map_drums`.
- **Evidence**: `enhanced_drum_mapper.py:279` (`use_advanced` passed) vs. `:352`
  (omitted, defaults `True`).
- **Impact**: A caller that explicitly asks for `use_advanced=False` (e.g. to force the
  plain `DEFAULT_MIDI_DRUM_MAPPING` behavior everywhere) still gets advanced
  velocity-split resolution for any event that happens to land inside a detected drum
  pattern. Low reach — `map_drums_to_dpcm`'s only production call site
  (`tracker/track_mapper.py`) always uses the default `use_advanced=True`, so this is
  latent/API-surface only today.
- **Suggested Fix**: Pass `use_advanced` through: `self._resolve_dpcm_sample_name(template_note, velocity, use_advanced)`.

---

## Re-verified as fixed, not regressed (prior report D-01 … D-11)

- **D-01 (index filename resolution)** — `dpcm_sampler/generate_dpcm_index.py:12-35`
  (`resolve_dpcm_sample_path`) now re-joins `filename` against `<index_dir>/dmc/`; both
  packer call sites (`main.py:317-345`, `main.py:627-676`) go through the shared
  `load_dpcm_index_into_packer`. Confirmed.
- **D-02 (sample_id id-space)** — `map_drums` emits `sample_data['id']` (the raw index
  id), not the sample manager's allocation counter; the manager's own `id` (from
  `_next_id`) is only used for its internal eviction bookkeeping and is never leaked into
  `dpcm_events`. Confirmed — see D-14 above for the *new* problem this raw id causes.
- **D-03 (stale-Z rest guard)** — `exporter/exporter_ca65.py:709-713` now re-tests
  `cmp #0` on the note value after `sta last_dpcm_note` before branching on rest. Confirmed
  fixed; matches `docs/APU_DMC_REFERENCE.md` trigger semantics.
- **D-04 (note-95 clamp)** — the 0–95 MIDI-note clamp is gone from the DPCM path in both
  `nes/emulator_core.py:209` and `exporter/exporter_ca65.py:984-986`. Confirmed fixed as
  literally specified (closed #67) — see D-14 for the residual gap the fix left open.
- **D-05 (oversized sample aborts whole pack)** — `DpcmPacker.add_sample(..., truncate=True)`
  is the only call path used in production (`load_dpcm_index_into_packer:72-77`); an
  oversized `.dmc` truncates to 4081 bytes instead of raising. Confirmed.
- **D-06 (evicted id reuse)** — `DPCMSampleManager._next_id` is a monotonic counter
  (`dpcm_sample_manager.py:13,50-51`), never decremented on eviction. Confirmed fixed.
- **D-07 (memory limit never enforced)** — `allocate_sample` and `_get_total_memory` now
  share one accounting formula (`sum(metadata['size'])`), and the eviction check accounts
  for the pending sample's size up front (`dpcm_sample_manager.py:42-43,120-130`).
  Confirmed fixed.
- **D-08 (dead similarity/dedup on placeholder data)** — `_find_similar_sample`/
  `_calculate_sample_similarity` are gone (removed, not repaired), consistent with
  commit `5c032d2`. Confirmed, no regression.
- **D-09 (`dmc_level`/`CMD_DMC_LEVEL` dead path)** — `grep -rn "dmc_level"` across the
  repo returns no hits; the command path was fully removed. Confirmed, no regression.
- **D-10 (`ADVANCED_MIDI_DRUM_MAPPING` coverage)** — `DEFAULT_MIDI_DRUM_MAPPING` fallback
  chain in `_resolve_dpcm_sample_name` (`enhanced_drum_mapper.py:391-418`) is confirmed
  correct and reachable; GM note 47 (mid tom) resolves to role name `tom_mid` via the
  fallback (though `tom_mid` itself isn't in the shipped index — see new finding D-15).
- **D-11 (noise fallback silently discarded)** — `tracker/track_mapper.py:253-259` prints
  a warning with the exact drop count (`len(noise_events)`) when `noise` is already
  occupied. Confirmed fixed, count matches exactly.

## Confirmed still open (no new information; not re-counted)

- **#75 / D-12** — `dpcm_packer.py:79` `length_reg = (size-1)//16` still floors rather
  than padding/rounding up; unchanged since the prior report.
- **#76 / D-13** — `DrumMapperConfig.from_file` (`enhanced_drum_mapper.py:188-191`) still
  only catches `FileNotFoundError`/`json.JSONDecodeError`; a stray config key still raises
  an uncaught `TypeError`. Unchanged since the prior report.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-07-03.md
```
