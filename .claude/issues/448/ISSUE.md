# DPCM-2026-08-21-5: dpcm_converter residuals — 8-bit PCM fed into a 0-127-clamped +-1-step model, first delta bit never emitted

**GitHub Issue:** #448
**Source Report:** docs/audits/AUDIT_DPCM_2026-08-21.md
**Severity:** LOW · **Domain:** dpcm
**Filed:** 2026-08-21

**Status:** NEW (distinct from the sub-bugs closed under #342/DP-DPCM-03 — start level and rate defaults, both verified fixed — and from the constant-input downward-ramp residual already documented in the 2026-08-06 report as #342's accepted reduced scope).

## Description
Two previously-unreported model mismatches versus `docs/APU_DMC_REFERENCE.md` §3 (each bit adds/subtracts **2** on a **7-bit** 0–127 counter):

(a) **Range/step-scale mismatch** — the encoder's feedback tracker `prev` clips to 0–127 and steps ±1, but its input is unnormalized 8-bit PCM (0–255, silence = 128). Silence therefore sits *above* the tracker's ceiling, pinning `prev` at 127 and biasing the whole encode; and the ±1 step means the sigma-delta error feedback models half the amplitude hardware actually reconstructs (±2/step). The docstring's "Compress 7-bit values" contract is not what `convert_wav_to_unsigned_pcm` delivers.

(b) **First-bit drop** — `delta_encode` outputs post-step levels starting from init 0, but `dpcm_compress` derives bits only for `encoded[1:]` transitions, so the initial 0→`encoded[0]` step is never emitted; playback is offset by one step from the modeled reconstruction.

Note: the reference doc's "Reader → Buffer → Shifter" diagram does not state the shifter's bit order explicitly, so the LSB-first packing (`bit << j`) can only be verified against NESdev consensus (bit 0 first — it matches), not a doc citation; worth one added sentence in the doc.

Verified in current code (`dpcm_sampler/dpcm_converter.py`):
- `:14-43` `convert_wav_to_unsigned_pcm` — for `sampwidth==1` (8-bit source WAV) data is read directly as `np.uint8` (0-255) with no downstream re-normalization to 0-127.
- `:46-60` `delta_encode` — `prev = np.clip(prev + step, 0, 127)`, `step = 1 if delta > 0 else -1 if delta < 0 else 0` (±1 step, 0-127 clamp confirmed).
- `:63-84` `dpcm_compress` — `for i in range(1, len(encoded)):` confirmed; the transition from init `prev=0` to `encoded[0]` (the actual first `delta_encode` step) has no corresponding bit emitted.
- Module confirmed orphaned: `grep -rn "dpcm_converter\|convert_wav_to_unsigned_pcm\|dpcm_compress" --include="*.py"` across the repo (excluding the module itself and tests) returns no callers — `generate_dpcm_index.py` scans pre-made `.dmc` files directly, matching the module's own header comment.

## Evidence
```python
data = ((data + 32768) / 256).astype(np.uint8)  # 0-255, only on the sampwidth==2 branch
prev = np.clip(prev + step, 0, 127)
for i in range(1, len(encoded)):  # encoded[0]'s own step (0 -> encoded[0]) is never bit-emitted
```

## Impact
None in production (module has no caller; `.dmc` catalog is pre-made). Anyone regenerating the catalog with this tool gets top-pinned, half-scale-modeled encodes. LOW per the orphaned-code rule.

## Related
#342/DP-DPCM-03 (closed), #337/REG-18 (test coverage).

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §3 (±2 steps, 0–127 clamp, 7-bit counter), §1 (signal flow).

## Suggested Fix
Scale PCM to 0–127 (`data >> 1`) before `delta_encode`, step the tracker ±2, and emit bits from `encoded[0]` relative to the init level; add the explicit LSB-first sentence to the doc.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
