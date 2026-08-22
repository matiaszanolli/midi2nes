# DPCM-2026-08-21-2: Arranger DPCM slot ids are packed as catalog ids — every --arranger kick plays "Hit 1", every snare plays a kick

**GitHub Issue:** #445
**Source Report:** docs/audits/AUDIT_DPCM_2026-08-21.md
**Severity:** HIGH · **Domain:** dpcm
**Filed:** 2026-08-21

**Severity:** HIGH · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-08-21.md

**Regression of:** #87 (ARR-04) — closed by `e1be17d`, but only divergence (a) (note-40 routing / noise periods) was fixed; divergence (b) ("the DPCM sample indices 0/1/2 do not match `dpcm_index.json`") was left as-is and the issue closed. Originally MEDIUM because unreachable (arranger drums were undetected, #86/ARR-01/02); those upstream bugs are now fixed, so the mis-mapping is live → HIGH.

## Description
The arranger's DPCM allocation returns a *slot* number (0 = kick, 1 = snare, unreachable fallback 2) with no relation to `dpcm_index.json`. `pipeline_integration` encodes it directly as `note = sample + 1` and emits **no** `dpcm_sample_map` side table. The pack stage's documented fallback (`get_dpcm_sample_ids_from_frames`: "its absence ... falls back to treating dense ids as catalog ids directly") then packs catalog entries with ids 0 and 1. In the shipped index, id 0 = `(Konami, Contra Force) Hit 1`, id 1 = `(Konami, Contra Force) Kick`, id 2 = `(Konami, Contra Force) Snare` (the real curated samples are `kick` = id 1318, `snare` = id 1620). The positional lookup tables are internally consistent, so playback "works" — it just plays the wrong drums: kick → a generic hit, snare → a kick.

Verified against current code:
- `arranger/voice_allocator.py:317-321` `DPCM_SAMPLE_SLOTS = {"Acoustic Bass Drum": 0, "Bass Drum 1": 0, "Acoustic Snare": 1}`; `:387` `return self.DPCM_SAMPLE_SLOTS.get(mapping.name, 2)` — no catalog lookup.
- `arranger/pipeline_integration.py:342-346` — `output['dpcm'][frame] = {'note': min(255, data['sample'] + 1), 'volume': 15}`, no `dpcm_sample_map` key ever emitted.
- `dpcm_sampler/generate_dpcm_index.py:155-161` (`get_dpcm_sample_ids_from_frames`) — confirmed fallback: `ids[dense_id] = int(sample_map.get(str(dense_id), dense_id))`, so an absent `dpcm_sample_map` makes dense id == catalog id.
- `dpcm_index.json`: id 0 = "(Konami, Contra Force) Hit 1", id 1 = "(Konami, Contra Force) Kick", id 2 = "(Konami, Contra Force) Snare"; id 1318 = "kick", id 1620 = "snare" — confirmed by direct lookup.

## Evidence
```python
# arranger/voice_allocator.py:317-321, 387
DPCM_SAMPLE_SLOTS = {"Acoustic Bass Drum": 0, "Bass Drum 1": 0, "Acoustic Snare": 1}
return self.DPCM_SAMPLE_SLOTS.get(mapping.name, 2)
# arranger/pipeline_integration.py:342-346 — no dpcm_sample_map:
output['dpcm'][frame] = {'note': min(255, data['sample'] + 1), 'volume': 15}
# dpcm_index.json: id 0 = "(Konami, Contra Force) Hit 1",
#                  id 1 = "(Konami, Contra Force) Kick"; kick=1318, snare=1620
```

## Impact
Every `--arranger` build whose MIDI has channel-9 kick/snare packs and triggers the wrong percussion samples. Wrong audio on realistic input, no warning anywhere (the pack succeeds — the referenced ids 0/1 resolve to real files). This is the arranger-path twin of the long-fixed legacy D-02/#65 id-space bug.

## Related
#87 (ARR-04), #65 (D-02), #200/D-14 (`dpcm_sample_map` mechanism the arranger path never adopted).

## Suggested Fix
Resolve slot names to real catalog entries the same way the legacy path does — look up `kick`/`snare` in the loaded index, emit the raw catalog id, and produce `frames['dpcm_sample_map']` (or emit `sample_id`-shaped events and reuse `NESEmulatorCore`'s dense remap). Add an end-to-end arranger test asserting the packed filename for a kick is the catalog's `kick.dmc`.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
