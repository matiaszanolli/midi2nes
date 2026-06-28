# M-5: build.sh always MMC3-hardcoded, bypassing mapper.generate_build_script() and MMC1 vector fixup

**Severity:** HIGH · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`prepare_project` unconditionally calls `_create_build_script_mmc3()`, which writes a hardcoded MMC3 `build.sh` with no post-process step. The generic `_create_build_script()` (which would call `mapper.generate_build_script()` and the MMC1 `generate_post_process_commands` vector relocation to file offset `0x2000A`) is defined but never invoked. An MMC1 project built via `build.sh` would link with vectors in the wrong place and brick on hardware. The MMC1 fixup offset (`0x1C010 + ($FFFA-$C000) = 0x2000A`) is correct — the bug is that it is unreachable.

## Evidence
```
project_builder.py:498   self._create_build_script_mmc3()   # always; ignores self.mapper
project_builder.py:595   def _create_build_script(self):    # generic path: never called
mmc1.py:116-120          generate_post_process_commands(...) # never reached
```

## Impact
Any non-MMC3 mapper through `NESProjectBuilder` gets an MMC3 build script. For MMC1: missing vector relocation → brick if used. Latent trap; HIGH because pipeline currently always passes MMC3.

## Related
M-7, M-8. Hardware ref: `docs/MAPPER_MMC1_REFERENCE.md`.

## Suggested Fix
Call `self.mapper.generate_build_script(is_windows)`; fold `_create_build_script_mmc3` into `MMC3Mapper.generate_build_script`. Have `compiler/` run the mapper post-process too.
