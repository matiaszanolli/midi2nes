# Issue #37: M-11: main.asm uses frame_counter but resolves it only via appended .include audio_engine.asm — fragile coupling

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
Non-debug `main.asm` references `frame_counter` in `reset` with **no** `.importzp frame_counter`. It resolves only because `audio_engine.asm` (which *defines* `frame_counter` in ZEROPAGE) is `.include`d into the same `main.o` at the end. If the engine include is ever removed/relocated, or the file is absent (`engine_src.exists()` guards the include at `:495`), the `frame_counter` reference becomes undefined — and crucially the include is conditional while the `reset` reference is unconditional. The debug path *does* `.importzp … frame_counter` (`:103`), so the dependency is acknowledged elsewhere.

## Evidence
```
project_builder.py:495  if engine_src.exists(): main_content += "\n.include \"audio_engine.asm\"\n"
project_builder.py:553  sta frame_counter        # unconditional, in reset
audio_engine.asm:16     frame_counter:  .res 2   # defined only if engine included
```
Verified against current tree (include at :495, reset write at :553-554, debug importzp at :103).

## Impact
Latent: if `audio_engine.asm` is missing, `reset` references an undefined symbol while the include that defines it is skipped → assemble error. LOW (the file ships in-repo).

## Related
M-1.

## Suggested Fix
Add `.importzp frame_counter` to main.asm unconditionally and let the engine `.exportzp` it (decouple definition from use), or assert the engine include is mandatory.

## Completeness Checks
- [ ] **CONTRACT**: main.asm imports frame_counter unconditionally; engine exports it
- [ ] **SIBLING**: Debug and non-debug main.asm paths consistent
- [ ] **TESTS**: A regression test pins the symbol resolution when the engine include is conditional

---

# Issue #38: NH-10: Additive pitch modification in the dead duplicate core re-opens the 11-bit clamp

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

## Description
The duplicate `NESEmulatorCore.compile_channel_to_frames` in `nes/envelope_processor.py` adds vibrato (`modified_pitch += pitch_mod`) **after** the pitch was clamped, with **no re-clamp**; the exporter then masks (`& 0xFF` / `& 0x07`) rather than clamps, so an out-of-range value wraps silently. This would be HIGH on a live path, but this `NESEmulatorCore` is **dead** — `main.py` imports `nes/emulator_core.py`, whose live `compile_channel_to_frames` applies no pitch_mod. Filed LOW as a latent trap + duplication.

## Evidence
`main.py:18` imports `from nes.emulator_core import NESEmulatorCore` (instantiated at main.py:50, 287). The vibrato path exists only in `nes/envelope_processor.py`'s copy: `class NESEmulatorCore` (line 162), `modified_pitch += pitch_mod` (line 206), emitted at lines 218 and 231 with no re-clamp. Confirmed in current tree.

## Impact
None today (dead); becomes HIGH if this copy is ever wired in.

## Hardware ref
`docs/APU_PITCH_TABLE_REFERENCE.md` §1 (11-bit range); `docs/APU_PULSE_REFERENCE.md` §3 (`t < 8` silence).

## Related
NH-08; duplication of `NESEmulatorCore`.

## Suggested Fix
Delete the duplicate `NESEmulatorCore` in `envelope_processor.py`; if vibrato is wanted, add it to the live core with a re-clamp to `[8, 0x7FF]`.

## Completeness Checks
- [ ] **RANGE**: If vibrato is moved to the live core, the modified pitch is re-clamped to `[8, 0x7FF]`
- [ ] **SIBLING**: No other duplicate `NESEmulatorCore` remains after removal
- [ ] **TESTS**: A regression test pins re-clamp behavior if vibrato is added to the live core
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
