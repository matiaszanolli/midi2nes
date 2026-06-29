# ARR-01: Arranger noise/DPCM frames use keys (period/sample) the exporter never reads — silent drum loss

**Severity:** HIGH · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
The non-arranger path (`process_all_tracks`, the canonical `frames` contract hardened by #9) emits noise as `{"note": period, "control": mode<<6, "volume": vol}` and DPCM as `{"note": sample_id+1, "volume": 15}` — the period and sample id live in `note`, and DPCM carries a `volume`. The arranger instead emits noise as `{"period", "volume", "control"}` (period under `period`, **no `note`**) and DPCM as `{"sample"}` (**no `note`, no `volume`**). The CA65 exporter reads the noise period as `fd.get(\"note\", 0) & 0x0F` (always 0 for arranger frames) and gates DPCM emission on `fd.get(\"volume\", 0) == 0` (always true → every DPCM frame skipped). The macro path likewise reads `note`/`volume`, so arranger noise becomes all rest-sentinel (note 0) and DPCM all rests.

## Location
- `arranger/pipeline_integration.py:241-253` (producer)
- `exporter/exporter_ca65.py:214-249` (direct path consumer) and macro path consumer
- contrast `nes/emulator_core.py:88-130` (canonical contract)

## Evidence
Arranger producer:
```python
# pipeline_integration.py:242-253
output["noise"][frame] = {"period": data["period"], "volume": data["volume"], "control": ...}
output["dpcm"][frame]  = {"sample": data["sample"]}
```
Exporter consumer (direct path):
```python
# exporter_ca65.py:220-223
if not fd or fd.get("volume", 0) == 0: ... continue
period = fd.get("note", 0) & 0x0F          # arranger has no note -> 0
# DPCM
if not fd or fd.get("volume", 0) == 0: ... continue   # arranger has no volume -> skipped
```
Canonical contract (`emulator_core.py:106-126`): noise `{"note": period, ...}`, DPCM `{"note": sample_id+1, "volume": 15}`.

## Impact
On any `--arranger` run where a drum track *is* detected, every noise hit plays with period 0 (wrong pitch / lowest-period white noise) and every DPCM sample is silently dropped. Inter-stage key drift that yields wrong/empty output for valid input — HIGH per `_audit-severity.md`. Currently masked by ARR-02 (drums rarely detected) but is a latent contract break on both export paths.

## Related
ARR-02 (drum detection), #9 (the contract this diverges from), #44 (no arranger test coverage).

## Suggested Fix
In `arrange_for_nes`, emit noise as `{"note": period, "control": mode<<6, "volume": volume}` and DPCM as `{"note": sample_id+1, "volume": 15}` to match `process_all_tracks`. Add a contract test asserting arranger and legacy frames share the same per-channel key set.

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
