# DP-DPCM-05: Missing-file DPCM samples leave frames pointing at $00 placeholder slots

**Issue:** #367
**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-19.md
**Labels:** medium, dpcm, bug

**Dimension:** 4 (size/address/table integrity) + 8 (channel-pipeline integration)

**Location:**
- `dpcm_sampler/generate_dpcm_index.py:83-96` (silent skip)
- `main.py:650-657` and `main.py:1056-1063` (discard `skipped`)
- `dpcm_sampler/dpcm_packer.py:139-145` (`_table` `$00` placeholder)

## Description
Dense DPCM ids are assigned at the frames stage purely from referenced `sample_id`s and never check whether the `.dmc` file exists. File resolution happens later in `load_dpcm_index_into_packer`, which silently skips any entry whose file does not resolve (`skipped += 1; continue`, warns only when `verbose=True`). The frame still encodes `note = dense_id + 1` for the skipped sample. `_table` emits `$00` for any missing id, or drops the highest id from `max_id` so the frame indexes past the table into adjacent RODATA.

## Evidence
`main.py:651-657` only guards the all-missing case (`loaded_samples == 0`); the `skipped` return (second element) is discarded, so partial misses produce no warning. At runtime `dpcm_len_table,y = $00` ⇒ `$4013 = 0` ⇒ 1-byte read from bank 0 / `$C000` — a click/garbage trigger.

## Impact
An intended drum hit is replaced by a click, wrong-sample fragment, or out-of-range read whenever a referenced `.dmc` is missing at pack time. Blast radius: corrupted/custom installs. All 1941 shipped catalog files resolve, so shipped-default builds unaffected — hence MEDIUM.

## Related
#140, #341

## Suggested Fix
Return the packed dense-id set (or reuse `skipped`) and at pack call sites emit a non-verbose `[WARN]` and/or drop affected frames to a noise fallback. Minimally, stop discarding `skipped`.

## Status as filed: NEW / CONFIRMED
