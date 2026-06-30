**Severity:** HIGH · **Domain:** dpcm · **Source:** follow-up to #64/#65/#68/#84/#127

## Description
The DPCM packer packs the **entire shipped sample catalog** into every ROM, not the
samples a song actually uses. Both call sites hand the full `dpcm_index.json` (1923
entries) to `load_dpcm_index_into_packer`, which adds every resolvable sample to the
packer (`dpcm_sampler/generate_dpcm_index.py:55`). 1923 samples at several KB each far
exceed the 60 × 8 KB = 480 KB DPCM bank budget, so `DpcmPacker._pack_samples` raises
`OverflowError("Exceeded maximum allocated DPCM MMC3 banks (60 banks)")`
(`dpcm_sampler/dpcm_packer.py:69-70`). That escapes `generate_assembly`, is swallowed by
the broad `except` at each call site, and **no DPCM tables are appended** — so every
drummed song builds with silent percussion, reported only as a warning.

This is the last blocker in the percussion chain: #64 (paths resolve), #65 (correct
sample id), #68 (oversized samples no longer abort), and #84 (arranger emits DPCM frames)
are all fixed, but none of it reaches the ROM while the packer tries to ship the whole
catalog and overflows.

## Location
- `dpcm_sampler/generate_dpcm_index.py:38-69` (`load_dpcm_index_into_packer` — packs all entries)
- `main.py:289` (run_export) and `main.py:570` (run_full_pipeline) — both pass the full index
- `dpcm_sampler/dpcm_packer.py:69-70` (60-bank `OverflowError`)

## Evidence
```
# shipped catalog vs the budget
$ python -c "import json;print(len(json.load(open('dpcm_index.json'))))"   # 1923 entries
60 banks × 8192 bytes = 491,520 bytes max DPCM; 1923 samples >> that.
```
A real `python main.py <drummed>.mid out.nes` prints:
`⚠️ Warning: Failed to pack DPCM samples: Exceeded maximum allocated DPCM MMC3 banks (60 banks).`
and the linked ROM contains only the project-builder stub `dpcm_*_table` (all percussion silent).

## Impact
Every song built through the default pipeline (or `export`) that has drums ships with no
DPCM samples — percussion is silent. Wrong/empty output for common input → HIGH. Masked
as a warning rather than surfaced as an error, and not silent corruption (the ROM still
boots), which is why it is HIGH and not CRITICAL.

## Suggested Fix
Pack only the samples the song references. The DPCM frames already carry the sample id as
`note = sample_id + 1` (the canonical contract from #9/#65; both the legacy
`process_all_tracks` and the arranger #84 emit it). Before packing, collect the used ids
from the frames and filter the index:

```python
used_ids = {fd["note"] - 1 for fd in frames.get("dpcm", {}).values()
            if fd.get("note", 0) > 0}
used_index = {name: e for name, e in dpcm_index.items() if e["id"] in used_ids}
load_dpcm_index_into_packer(packer, used_index, dpcm_index_path, ...)
```

A typical song references a handful of drums, well within the 60-bank budget. If a song
ever does reference more than fits, the bank cap / capacity gate (#127) then reports a
clear budget error. Apply at both call sites (the shared loader makes this a one-line
filter at each).

## Related
#64, #65, #68 (DPCM chain), #84 (arranger DPCM frames), #127 (bank cap that becomes the
real guard once only-used samples are packed), #9 (the `note = sample_id+1` contract).

## Completeness Checks
- [ ] **CONTRACT**: used ids read from `frames['dpcm']` note values (sample_id = note - 1)
- [ ] **SIBLING**: filter applied at both packer call sites (run_export + run_full_pipeline)
- [ ] **TESTS**: a song using N drums packs N samples (not 1923) and stays under the bank budget
- [ ] **DOC**: note the "pack only referenced samples" behavior where the catalog is documented
