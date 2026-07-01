# D-08: Index length/data/frequency always fall back to defaults — similarity/dedup inert

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`_load_sample_index` passes each raw index entry as `sample_data` to `allocate_sample`, which reads `sample_data.get('length', 1024)`, `sample_data.get('data', [])`, and `sample_data.get('frequency', 33144)`. The shipped `dpcm_index.json` and all `test_dpcm_index.json` fixtures contain only `id` and `filename`, so `length`/`data`/`frequency` are **always** the defaults. `_calculate_sample_similarity` and `_find_similar_sample` then compare empty `data` arrays — `max_len==0` ⇒ `length_similarity=1.0`, `min_length==0` ⇒ `waveform_similarity=1.0`, so every pair is "100% similar" / the path is inert. The dedup/similarity subsystem does nothing on production data.

## Location
- `dpcm_sampler/enhanced_drum_mapper.py:286-292`
- `dpcm_sampler/dpcm_sample_manager.py:34,56,59,166-193`

## Evidence
`python -c` over `dpcm_index.json` → keys union `{'filename','id'}` (confirmed: 1923 entries, keys `{id, filename}`); `dpcm_sample_manager.py:34` `get('length', 1024)`, `:56` `get('data', [])`, `:59` `get('frequency', 33144)`; `:166-193` similarity over empty arrays.

## Impact
Memory accounting and dedup operate on placeholder data; the "smart sample allocation" is effectively a no-op. Cosmetic/over-engineered rather than wrong output.

## Related
D-07.

## Suggested Fix
Either enrich the index with real `length`/`frequency` (and load `data` lazily), or delete the similarity/dedup machinery as dead-on-real-input.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (similarity over real data)

