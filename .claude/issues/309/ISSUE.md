# #309 — NH-HW-2026-07-17-2: orphan @cmd_dmc_level handler in the live playback engine (dead code)

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-17.md · **Status:** NEW

## Description
The `CMD_DMC_LEVEL` ($87) producer was removed (#72 / D-09) — no exporter path emits the opcode, guarded by regression test `tests/test_ca65_export.py::test_dmc_level_command_path_removed`. The **consumer** side still lives in `nes/audio_engine.asm`: the dispatch `beq @cmd_dmc_level` (`:222`) and the `@cmd_dmc_level` handler (`:259-260`) that reads a 7-bit operand and writes `$4011`. It is unreachable dead code — `$87` can never appear in the emitted bytecode stream. There is no real hardware "DMC volume" register, so this is correct to leave dead, but the orphan handler and its dispatch branch are pure residue.

## Evidence
```
$ grep -rn "CMD_DMC_LEVEL\|\$87" exporter/exporter_ca65.py
(no producer)
$ grep -n "cmd_dmc_level" nes/audio_engine.asm
222:    beq @cmd_dmc_level
259:@cmd_dmc_level:
```
The handler exists only on the consumer (engine) side; the producer was removed under #72.

## Impact
None at runtime (unreachable). Maintenance/clarity only — the orphan handler invites a future reader to wire up a `$4011` level write that hardware doesn't support as a per-channel volume.

## Suggested Fix
Delete the `@cmd_dmc_level` label/handler and its `beq @cmd_dmc_level` dispatch entry from `nes/audio_engine.asm`; keep the `$4011`-at-init DAC-zero write untouched.

## Completeness Checks
- [ ] **SIBLING**: same orphan-consumer pattern checked against the other tracked dead-code items (#203/NH-28, #204/NH-29, #107/NH-14)
- [ ] **TESTS**: the existing `test_dmc_level_command_path_removed` still passes; engine assembles after the handler is removed
- [ ] **DOC**: `$4011` semantics per `docs/APU_DMC_REFERENCE.md` §2–§3 (one-shot 7-bit DAC load, not per-note volume)
