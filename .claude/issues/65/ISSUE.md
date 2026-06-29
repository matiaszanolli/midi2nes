# D-02: sample_id is an allocation counter, not the packer table index — wrong sample plays

Issue: #65 — https://github.com/matiaszanolli/midi2nes/issues/65
Labels: bug, critical, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

**Severity:** CRITICAL · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`allocate_sample` assigns `'id': len(self.active_samples)` — a sequential 0,1,2… counter in *allocation order*. `EnhancedDrumMapper.map_drums` propagates this as `dpcm_events[...]["sample_id"]`, which `emulator_core` turns into `note = sample_id + 1` and the engine recovers as `y = note - 1` to index `dpcm_bank_table,y / dpcm_pitch_table,y / dpcm_addr_table,y / dpcm_len_table,y`. But the packer builds those tables ordered by `sorted(metadata.keys(), key=int)` — the `dpcm_index.json` `id` field (0..1922), an entirely different numbering. The allocation counter and the index id only coincide by accident.

## Location
- `dpcm_sampler/dpcm_sample_manager.py:54` (`'id': len(self.active_samples)`)
- `dpcm_sampler/enhanced_drum_mapper.py:296`
- `dpcm_sampler/dpcm_packer.py:94-115`

## Evidence
`dpcm_sample_manager.py:54` `'id': len(self.active_samples)`; `dpcm_packer.py:94` `ordered_ids = sorted(self.sample_metadata.keys(), key=lambda x: int(x))` where keys are `str(sample['id'])` from `main.py:550`. The drum mapper never consults the index `id`; the packer never consults the allocation order.

## Impact
As soon as samples actually load (after D-01 is fixed), the first drum hit allocated (`id=0`) indexes packer table entry 0 — whatever sample has index id 0 (`(Konami…) Hit 1`), not the kick the MIDI asked for. Every drum event points at the wrong sample. Hardware-correct registers, wrong audio.

## Related
D-01 (masks this today since tables are dummy), D-06 (id reuse on eviction).

## Suggested Fix
Make the drum mapper carry the *index* `id` (`self.sample_index[name]['id']`) into `dpcm_events`, not the manager's allocation counter, so `sample_id` indexes the packer tables consistently.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same id-space mapping checked across drum mapper / emulator_core / engine
- [ ] **TESTS**: A regression test pins this specific fix
