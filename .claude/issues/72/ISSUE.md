# D-09: dmc_level is read but never produced by any stage (dead command path)

Issue: #72 — https://github.com/matiaszanolli/midi2nes/issues/72
Labels: bug, medium, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
The bytecode exporter reads `frame_data.get('dmc_level')` and emits `CMD_DMC_LEVEL ($87, level)`. The unclamped-byte risk flagged by the prior NH-04 is now fixed: `exporter_ca65.py:946-947` masks `dmc_level &= 0x7F`, and `emulator_core.py:128` clamps `max(0, min(127, e['dmc_level']))`. However, **no stage ever sets `dmc_level`** on a dpcm frame — the dpcm frame builder (`emulator_core.py:123-129`) only writes it when the incoming event already has `'dmc_level'`, and nothing upstream (drum mapper, arranger) produces it. So the entire `CMD_DMC_LEVEL` plumbing is unreachable on real input.

This is the residual half of prior NH-04 (`AUDIT_NES_HARDWARE_2026-06-28.md`): the clamp half is fixed by commit `5e155ee`; the dead-path half remains. Reported NEW (residual).

## Location
- `exporter/exporter_ca65.py:942-947,956-999,1083-1112`
- `nes/emulator_core.py:112-130`

## Evidence
Repo-wide, `dmc_level` is only ever read with `.get('dmc_level')` / guarded by `if 'dmc_level' in e`; the only writer is the pass-through at `emulator_core.py:127-128`.

## Impact
Dead code; no functional bug today. Worth tracking so the half-wired `$4011` direct-load feature is either completed or removed.

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §2 — `$4011` is a 7-bit direct-load register; the now-present `&0x7F` is correct.

## Related
prior NH-04 (clamp portion fixed by commit `5e155ee`).

## Suggested Fix
Either generate `dmc_level` for the `$4011` non-linear-mixer trick (`docs/APU_DMC_REFERENCE.md` §6) or remove the `CMD_DMC_LEVEL` path.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **TESTS**: A regression test pins the resolved behavior (path exercised or removed)
