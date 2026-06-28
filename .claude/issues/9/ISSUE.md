# NH-01: Noise and DPCM channels never reach their APU registers (all percussion/samples silent)

**Severity:** CRITICAL · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #9

## Description
`NESEmulatorCore.process_all_tracks` builds noise frames as `{"noise_mode": 0, "volume": 15|0}` and DPCM frames as `{"sample_id": …, "volume": 15|0}` — with no `note`, no `period`, no `dmc_level`. Neither exporter path then turns these into APU register writes:
- `export_direct_frames` iterates only `['pulse1','pulse2','triangle']` (exporter_ca65.py:117) — noise (`$400C/$400E/$400F`) and DMC (`$4010-$4013`) are dropped on the floor.
- `export_tables_with_patterns` does loop noise/dpcm but reads `note = frame_data.get('note', 0)` (line 769); since noise/dpcm frames carry no `note`, every entry collapses to note 0 → silence, and the period index / `noise_mode` are never written.

## Evidence
```python
# nes/emulator_core.py:88-103 — no note/period/dmc_level produced
"noise_mode": 0, "volume": 15 if ... else 0
"sample_id": e.get('sample_id', 0), "volume": 15 if ... else 0
# exporter_ca65.py:117 — direct path ignores noise/dpcm entirely
for channel_name in ['pulse1', 'pulse2', 'triangle']:
```

## Impact
Every ROM with drums or samples plays no percussion and no DPCM. Blast radius: all four-on-the-floor / GM-drum MIDIs (the common case).

## Hardware ref
`docs/APU_NOISE_REFERENCE.md` §2, §6; `docs/APU_DMC_REFERENCE.md` §3; `docs/NES_APU_REFERENCE.md` §3.1.

## Related
Root cause for open issue #3 "Output seems silent" (distinct finding). Also NH-04, NH-05.

## Suggested Fix
Have `process_all_tracks` carry a `period` (0–15) and `noise_mode` bit into noise frames and a `dmc_level`/trigger into dpcm frames, and add noise/DPCM emission to both exporter paths.
