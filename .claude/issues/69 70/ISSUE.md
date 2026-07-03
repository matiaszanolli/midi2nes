# Issue #69: D-06: Evicted sample id can be reused and mis-point earlier drum events

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`allocate_sample` sets `'id': len(self.active_samples)`. After `_optimize_sample_bank` / `_remove_sample` evicts an entry, `len(active_samples)` drops, so a subsequent allocation can produce an `id` already emitted into earlier `dpcm_events`. Two distinct samples then share one id; the emitted events that referenced the evicted sample now point at the survivor (or vice-versa).

## Location
- `dpcm_sampler/dpcm_sample_manager.py:54` + `195-205` (`_remove_sample`)

## Evidence
`dpcm_sample_manager.py:54` id derivation; `:110` eviction (`self._remove_sample(sample_to_remove)`); ids are never tracked as a monotonic allocator. `enhanced_drum_mapper.py:296` snapshots the id into an event at allocation time.

## Impact
On songs that exceed `max_samples` (default 16) and trigger eviction, earlier drum hits silently change to the wrong sample. Workaround: raise `max_samples`. Overlaps the deeper id-space confusion in D-02.

## Related
D-02 (id-space confusion).

## Suggested Fix
Use a monotonic `next_id` counter (never reused), or key events by the stable index id (per D-02) rather than the dynamic allocation order.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (eviction does not reuse an id)

---

# Issue #70: D-07: Memory limit is never enforced — two divergent accounting methods

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`allocate_sample` measures memory as `sum(s['metadata']['size'])`, where `size` defaults to the `length` placeholder 1024 (the shipped index has no `length`, see D-08). `_optimize_sample_bank`'s eviction loop instead gates on `_get_total_memory()`, which returns `sum(len(s['data'])//8)` — and `data` is `[]` for every real index entry, so it is **always 0**. The two notions of "memory used" never agree, and the one driving eviction is permanently 0, so `memory_limit` is never reached by that path; only the `max_samples` count check evicts.

## Location
`dpcm_sampler/dpcm_sample_manager.py:34,37-40,87-88,106,207-211`

## Evidence
`:37` `current_memory = sum(s['metadata']['size'] ...)`; `:211` `return sum(len(s.get('data', [])) // 8 ...)`; `:106` eviction loop gates on `_get_total_memory() > self.memory_limit`. Index entries carry only `id`+`filename`.

## Impact
The configurable `memory_limit` (1KB–16KB) is dead on real input; only the `max_samples` count bounds the bank. Sizing/eviction decisions are made on placeholder data, not real sample sizes. Defense-in-depth gap, not a crash.

## Related
D-08 (placeholder index schema).

## Suggested Fix
Populate real sample sizes into the index/metadata, or compute size from the on-disk `.dmc`, and use one consistent accounting function for both the allocate-time check and the eviction loop.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (memory_limit actually evicts)
