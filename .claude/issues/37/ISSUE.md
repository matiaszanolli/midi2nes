# M-11: main.asm uses frame_counter but resolves it only via appended .include audio_engine.asm — fragile coupling

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
Non-debug `main.asm` references `frame_counter` in `reset` with no `.importzp frame_counter`. It resolves only because `audio_engine.asm` (which defines `frame_counter` in ZEROPAGE) is `.include`d at the end. The include is conditional (`engine_src.exists()`) while the `reset` reference is unconditional. The debug path does `.importzp … frame_counter`.

## Evidence
```
project_builder.py:495  if engine_src.exists(): main_content += '\n.include "audio_engine.asm"\n'
project_builder.py:553  sta frame_counter        # unconditional, in reset
audio_engine.asm:16     frame_counter:  .res 2   # defined only if engine included
```

## Impact
Latent: if `audio_engine.asm` is missing, `reset` references an undefined symbol while the include is skipped → assemble error. LOW.

## Related
M-1.

## Suggested Fix
Add `.importzp frame_counter` to main.asm unconditionally and `.exportzp` it from the engine, or assert the engine include is mandatory.
