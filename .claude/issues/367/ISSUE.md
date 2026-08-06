# DP-DPCM-05: Missing-file DPCM samples leave frames pointing at $00 placeholder slots

**URL:** https://github.com/matiaszanolli/midi2nes/issues/367
**Labels:** bug, medium, dpcm

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-19.md

**Dimension:** 4 (size/address/table integrity) + 8 (channel-pipeline integration)

**Location:**
- `dpcm_sampler/generate_dpcm_index.py:83-96` (silent skip)
- `main.py:650-657` and `main.py:1056-1063` (discard `skipped`)
- `dpcm_sampler/dpcm_packer.py:139-145` (`_table` `$00` placeholder)

## Description
Dense DPCM ids are assigned at the **frames** stage (`emulator_core.process_all_tracks`) purely from the `sample_id`s a song references — it never checks whether the `.dmc` file exists. File resolution happens later, in `load_dpcm_index_into_packer`, which **silently skips** any entry whose file does not resolve (`skipped += 1; continue`, only warns when `verbose=True`, and both pack call sites use the default/false verbose). The frame still encodes `note = dense_id + 1` for the skipped sample. In `generate_assembly`, `_table` emits `$00` for any id in `range(max_id+1)` not in `sample_metadata`, so the skipped dense_id's slot becomes `$00` across bank/pitch/addr/len — or, if it was the highest dense_id, it is dropped from `max_id` entirely and the frame indexes past the table into adjacent RODATA.

## Evidence
`main.py:651-657` handles only the all-missing case:
```python
loaded_samples, _ = load_dpcm_index_into_packer(packer, dpcm_index, dpcm_index_path, sample_ids=sample_ids)
if loaded_samples == 0 and sample_ids:
    dpcm_pack_warning = (... "the exported ASM has NO drums.")
```
The `skipped` return (second element, `_`) is discarded, so a partial miss (`loaded > 0` and `skipped > 0`) produces no warning and no reconciliation. At runtime `@write_dpcm` (`nes/audio_engine.asm:531-539`) loads `dpcm_len_table,y = $00` ⇒ `$4013 = 0` ⇒ `(0*16)+1 = 1` byte read from bank 0 / `$C000`, i.e. a 1-byte fragment of the first packed sample (`APU_DMC_REFERENCE.md` §2/§4) — a click/garbage trigger, not the intended drum.

## Impact
A drum hit the MIDI clearly intended is replaced by a click or a wrong-sample fragment (or an out-of-range read) whenever any referenced `.dmc` is missing at pack time. Blast radius: any song on a corrupted/custom install where `dpcm_index.json` lists a file not on disk. All 1941 shipped catalog files currently resolve, so shipped-default builds are unaffected — hence MEDIUM.

## Related
#140 (referenced-only packing introduced the sparse tables), #341 (manager decoupled from packing).

## Suggested Fix
Have `load_dpcm_index_into_packer` return the set of dense ids it actually packed (or reuse `skipped`), and at the pack call sites either (a) emit a non-verbose `[WARN]` naming the dropped drums, and/or (b) drop the corresponding frames back to a noise fallback so no frame indexes an unpacked slot. Minimally, stop discarding `skipped` and surface it like `loaded_samples == 0`.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **FALLBACK**: Skipped/missing DPCM ids drop to a clean noise fallback rather than a `$00` slot
- [ ] **SIBLING**: Both pack call sites (`main.py:651`, `main.py:1057`) handle the partial-miss case
- [ ] **TESTS**: A regression test pins the partial-miss warning/fallback behavior
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
