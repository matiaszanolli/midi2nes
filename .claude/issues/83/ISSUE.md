**Severity:** LOW · **Domain:** documentation · **Source:** AUDIT_EXPORTERS_2026-06-29.md

`docs/AUDIO_BYTECODE_SPEC.md` §3 contradicts the shipped engine/exporter on `$FE`, `$87`, and DPCM opcode.

## Description
The exporter and the shipped engine **agree** with each other but **disagree with the spec doc**: the exporter emits `$FE`+bank+ptr_lo+ptr_hi as `CMD_BANK_JUMP` (`exporter_ca65.py:1102`) and the engine decodes exactly that (`audio_engine.asm:260-276`); the exporter emits `$87`+level as `CMD_DMC_LEVEL` (`:1112`) and the engine decodes it (`:253-257`). But §2.3 defines `$FE` as the **macro-loop** control byte (true *inside macros*, a different namespace) and §3 lists **no** `$87` and no bank-jump opcode, while listing `$85 CMD_DPCM_PLAY` and `$84 CMD_JUMP` that the exporter never emits in this path. The doc is stale relative to the implemented sequencer commands.

## Location
`docs/AUDIO_BYTECODE_SPEC.md` §3 command table (lines ~65-73) and §2.3.

## Spec ref
`docs/AUDIO_BYTECODE_SPEC.md` §2.3 / §3 vs `nes/audio_engine.asm:253-276` and `exporter/exporter_ca65.py:1102, 1112, 1118`.

## Evidence
§3 table has `$80,$81,$82,$83,$84,$85,$86` and no `$87`/`$FE`-sequence-command rows; engine command dispatch handles `$FE` (`CMD_BANK_JUMP`, `:260`) and `$87` (`CMD_DMC_LEVEL`, `:253`).

## Impact
Documentation-only. Anyone implementing a second engine or tooling from the spec would mis-decode `$FE`/`$87`. No runtime effect because the exporter and engine match. LOW (doc-rot).

## Related
EXP-01 (the `$FE`/`$FF` macro-control collision is the *real* runtime issue in the macro namespace).

## Suggested Fix
Update §3 to document `$87 CMD_DMC_LEVEL` and the `$FE` four-byte sequence-level bank-jump (distinct from the in-macro `$FE` loop), and remove/realign the `$84`/`$85` rows that the implemented path does not use.

## Completeness Checks
- [ ] **DOC**: The `docs/*.md` is corrected to match the shipped engine/exporter
- [ ] **SIBLING**: Same doc-vs-code check applied to related opcode rows
