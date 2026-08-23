# DPCM / Drum-Sampling Audit — 2026-08-23

Auditor: `/audit-dpcm` (all 8 dimensions). Baseline: `HEAD` (`fc5027c`, clean tree).
Dedup sources: `gh issue list --state all` (367 issues, saved to `/tmp/audit/issues_all.json`),
`docs/audits/AUDIT_DPCM_2026-08-21.md` (the prior full pass).

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 1 |

**Every finding from `AUDIT_DPCM_2026-08-21.md` is now CLOSED and independently re-verified
fixed in code this session** (not trusted from the GitHub label alone):

- **DPCM-2026-08-21-1 / PIPE-2026-08-21-1** (CRITICAL, channel-blind phantom-drum scan): fixed
  by **#425** (`fa179ae`). Re-verified: `EnhancedDrumMapper.map_drums`
  (`dpcm_sampler/enhanced_drum_mapper.py:347-350`) now gates on `channel != 9` before treating
  any note-on as a drum hit — a melodic note-on on a known non-9 channel is skipped.
- **DPCM-2026-08-21-2** (HIGH, arranger DPCM slot ids packed as catalog ids): fixed by **#445**
  (`03446c5`). Re-verified end-to-end: `VoiceAllocator._resolve_dpcm_catalog_id('kick')` →
  `1318`, `'snare'` → `1620`; cross-checked against the real `dpcm_index.json` — id 1318 is
  `kick.dmc`, id 1620 is `snare.dmc`. The arranger now emits `frames['dpcm_sample_map']`
  (`arranger/pipeline_integration.py:408`), matching the legacy path's dense-remap mechanism.
- **DPCM-2026-08-21-3** (LOW, `length_reg` 1-byte block-size spill): fixed by **#446**
  (`ce4199a`). Re-verified: `DpcmPacker.add_sample` (`dpcm_sampler/dpcm_packer.py:66-70`) now
  sizes `aligned_size = max(ceil(size/64)*64, ceil(read_length/64)*64)`, so the reserved block
  always covers the engine's `(length_reg*16)+1`-byte read.
- **DPCM-2026-08-21-4** (LOW, `length_reg=0` sentinel collision): fixed by **#447**
  (`ce4199a`). Re-verified: `_length_reg` (`dpcm_sampler/dpcm_packer.py:14-32`) now floors at 1
  (`max(1, (size_bytes + 14) // 16)`), so a genuine 0/1-byte sample can no longer compute the
  same value as the "never packed" sentinel.
- **DPCM-2026-08-21-5** (LOW, `dpcm_converter` model mismatch): fixed by **#448** (`ce4199a`).
  Re-verified: `delta_encode` (`dpcm_sampler/dpcm_converter.py:65-70`) starts `prev = 0x00` and
  normalizes via `sample >> 1` before the ±2-step comparison; `dpcm_compress`
  (`:88-92`) starts its own `prev = 0x00` and includes the transition into `encoded[0]`.

**One new finding this cycle** (LOW, doc-rot): `audit-dpcm/SKILL.md`'s Dimension 6 still
describes closed issue **#76/D-13** as "Still open" — the 2026-08-21 report already flagged
this exact staleness (as an inline note, not a filed issue) and it was never corrected on disk,
unlike the sibling `audit-arranger`/`audit-patterns`/`audit-tech-debt` skill files, which have
each had an equivalent doc-rot finding filed and fixed this week (#493, #497, #463).

**Scoped regression suite**: `test_dpcm_packer.py`, `test_dpcm_converter.py`,
`test_enhanced_drum_mapper.py`, `test_dpcm_sample_manager.py`, `test_drum_mapper_config.py`,
`test_drum_engine.py`, `test_dpcm_index_resolution.py`, `test_drum_mapping.py`,
`test_arranger_drum_detection.py` — **145 passed**, confirming no regression since the
2026-08-21 fixes landed (`git log` shows no `dpcm_sampler/`/`track_mapper.py` commits since
`ce4199a`/`03446c5`/`fa179ae` except the mechanical `#460` velocity/volume refactor `7839c4e`,
which I diffed directly — precedence and defaults for every DPCM-adjacent site are unchanged,
purely a call-site consolidation into `core/events.event_velocity`).

## Findings

### DPCM-2026-08-23-1: `audit-dpcm/SKILL.md` still describes closed issue #76/D-13 as open
- **Severity**: LOW
- **Dimension**: Meta (doc-rot in the audit skill itself; the described code is in Dimension 6)
- **Location**: `.claude/commands/audit-dpcm/SKILL.md:287-296` (the "Still open (#76/D-13)"
  paragraph, including its stale `lines 163-191` citation)
- **Status**: NEW (the underlying staleness was noted inline in
  `docs/audits/AUDIT_DPCM_2026-08-21.md`'s verify-the-fix sweep — "`/audit-sync` should retire
  the 'Still open (#76/D-13)' paragraph" — but never filed as an issue or corrected on disk)
- **Description**: `DrumMapperConfig.from_file` (`dpcm_sampler/enhanced_drum_mapper.py:164-196`)
  was fixed in `3b905fc` (2026-07-18, predating even the 2026-08-21 audit): it now catches
  `TypeError` from an unexpected/renamed config key and re-raises a clear `ValueError`
  (`:195-196`, `raise ValueError(f"Invalid configuration key in {config_path}: {e}")`), and
  `result.validate()` runs before returning (`:189`). `tests/test_drum_mapper_config.py`
  exercises the stray-key path and passes. But the currently-loaded skill file's Dimension 6
  still opens with "**Still open (#76/D-13)**: `from_file` (lines 163-191) does
  `DrumPatternConfig(**config_data.get('pattern_detection', {}))` ... an unexpected/renamed key
  in the JSON raises `TypeError` (not caught; only `FileNotFoundError` and
  `json.JSONDecodeError` are handled...)" — describing exactly the pre-fix behavior, and its own
  line citation (`163-191`) is now short by 5 lines (the `except TypeError` block runs through
  `:196`). `gh issue view 76` confirms **CLOSED**.
- **Evidence**: `grep -n "Still open (#76" .claude/commands/audit-dpcm/SKILL.md` → line 287;
  `sed -n '191,196p' dpcm_sampler/enhanced_drum_mapper.py` shows the `except TypeError as e:
  raise ValueError(...)` clause the skill text says doesn't exist.
- **Impact**: None on ROM correctness — this is the audit skill's own prose, not shipped code.
  Misleads a future `/audit-dpcm` run (human or agent) into re-reporting #76 as a live bug, or
  spending investigation time "confirming" a fix that already landed over a month ago. Same
  defect class as `ARR-2026-08-23-2` (`audit-arranger/SKILL.md`, fixed by #493) and
  `PAT-2026-08-23-3` (`audit-patterns/SKILL.md`, fixed by #497) — both filed and fixed this
  week; `audit-dpcm/SKILL.md` is the one sibling skill file in this family that never got the
  equivalent pass.
- **Related**: #76/D-13 (closed, `3b905fc`), #493 (arranger skill doc-rot, same class, fixed),
  #497 (patterns skill doc-rot, same class, fixed), #463 (tech-debt skill doc-rot, same class,
  fixed).
- **Suggested Fix**: Replace the "Still open (#76/D-13)" paragraph in Dimension 6 with a
  "Fixed (#76/D-13, verify)" framing matching the sibling skills' style — state that
  `from_file` now catches `TypeError` and re-raises `ValueError` (citing the correct
  `:164-196` range), and ask a future run to confirm the catch clause hasn't been removed and
  that `result.validate()` still runs before the constructed config is returned.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_DPCM_2026-08-23.md
```
