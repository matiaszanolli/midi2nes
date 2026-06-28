# M-6: MMC3 generate_header_asm() emits its own .segment HEADER, double-declaring the project builder segment

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`_generate_main_asm` emits `.segment "HEADER"` then `{mapper.generate_header_asm()}`. For NROM/MMC1 the mapper returns bare `.byte`; for MMC3 it returns a block that begins with its own `.segment "HEADER"` — main.asm gets two consecutive HEADER directives. `ca65` tolerates re-opening a segment so it is not a hard error, but it is an inconsistency between mapper contracts and a latent trap.

## Evidence
```
mmc3.py:26-35           generate_header_asm opens its own .segment "HEADER"
project_builder.py:527  return f'.segment "HEADER"\n{self.mapper.generate_header_asm()}'
```

## Impact
Currently benign; a maintenance trap. MEDIUM, defense-in-depth/contract consistency.

## Related
M-1.

## Suggested Fix
Make `MMC3Mapper.generate_header_asm()` return bare `.byte` lines like NROM/MMC1.
