# DP-DPCM-02
**Filed as:** #341

**Severity:** LOW · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-18.md

## Description
Real `dpcm_index.json` entries carry only `id` + `filename` (verified), so `allocate_sample` always defaults `length` to 1024 (`dpcm_sample_manager.py:34`) and `frequency` to 33144 (`:58`) for every sample. Every sample therefore has an identical fictional size, and the memory-limit/eviction machinery (`_get_total_memory`, `_optimize_sample_bank`) operates entirely on that placeholder. More importantly, the manager's allocation/eviction has **no effect on the packed ROM**: what gets packed is driven by frame references via `get_dpcm_sample_ids_from_frames`, not by `sample_manager.active_samples`. The `allocate_sample` calls (`enhanced_drum_mapper.py:308,381,462`) exist only "for usage/eviction side effects" (per the code comment), which never reach output.

## Evidence
`dpcm_sample_manager.py:34` `sample_data.get('length', 1024)`; `:58` `get('frequency', 33144)`; index probe shows keys `['id','filename']` only; packing path (`generate_dpcm_index.load_dpcm_index_into_packer`) reads real `os.path.getsize`, ignoring the manager entirely.

## Impact
The eviction subsystem is vestigial for real input — dead-weight complexity, not a correctness bug. Uniform 1024-byte accounting could evict the "wrong" sample, but since eviction doesn't gate packing, output is unaffected.

## Related
#71/D-08 (dead similarity code already removed), DP-DPCM-01.

## Suggested Fix
Either back-fill real `size`/`rate` from the `.dmc` files at index-generation time (so the manager reflects reality if it is ever wired into packing), or drop the now-inert allocate-for-side-effect calls and the size/eviction logic that never influences the ROM.

## Completeness Checks
- [ ] **SIBLING**: all three `allocate_sample` call sites handled consistently if removed
- [ ] **TESTS**: if back-filled, a test asserts the manager's size reflects the real `.dmc` size