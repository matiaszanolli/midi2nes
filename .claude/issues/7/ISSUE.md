# M-2: APU frame counter $4017 never initialized; $4015 not enabled at init on the patterns path

**Severity:** CRITICAL · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
Boot path is `reset` → `jsr init_music`. On the default (patterns) path, `init_music` is `jmp audio_init`, and `audio_init` (audio_engine.asm:82) writes only `$4011` (DMC level) at init — never `$4015` nor `$4017`. `$4017` is written exactly once, at `exporter_ca65.py:217`, inside the `standalone` reset block the pipeline never emits (`main.py` passes `standalone=False`). `docs/NES_APU_REFERENCE.md` §3.2 states `$4017` must be initialized to `$40`. APU is effectively uninitialized at boot.

## Evidence
```
audio_engine.asm:120        sta $4011        ; only APU write in audio_init
audio_engine.asm:205,223    sta $4015        ; per-frame DPCM handlers, not init
exporter_ca65.py:217        sta $4017        ; standalone-only; not used by pipeline
exporter_ca65.py:969-973    init_music: jmp audio_init   (patterns path)
exporter_ca65.py:541-548    no-patterns init_music writes $4015 but still no $4017
```

## Impact
Per `_audit-severity.md` "APU never initialized → CRITICAL". On accurate emulators/hardware the frame counter can fire frame IRQs or clock units against the engine, producing no/garbage sound. Affects every ROM the pipeline builds.

## Related
M-1; issue #3 "Output seems silent". Hardware ref: `docs/NES_APU_REFERENCE.md` §3.1/§3.2.

## Suggested Fix
In `audio_init` (and no-patterns `init_music`), write `$4017=$40` and `$4015` enable mask before playback. Centralize APU init across branches.
