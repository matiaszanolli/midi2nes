# D-06: Evicted sample id can be reused and mis-point earlier drum events

Issue: #69 — https://github.com/matiaszanolli/midi2nes/issues/69
Labels: bug, medium, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

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
