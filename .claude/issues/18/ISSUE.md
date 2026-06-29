# M-5: build.sh always MMC3-hardcoded, bypassing mapper.generate_build_script() and MMC1 vector fixup

**Severity:** HIGH · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`prepare_project` unconditionally calls `_create_build_script_mmc3()`, which writes a hardcoded MMC3 `build.sh` with no post-process step. The generic `_create_build_script()` (which would call `mapper.generate_build_script()` and thus the MMC1 `generate_post_process_commands` that relocates reset/NMI/IRQ vectors to file offset `0x2000A`) is defined but never invoked.

## Evidence
project_builder.py:498 self._create_build_script_mmc3()   # always; ignores self.mapper
project_builder.py:595 def _create_build_script(self):    # generic path: never called
project_builder.py:608 def _create_build_script_mmc3(self):
mmc1.py:116-120 generate_post_process_commands(...) # vector fixup at 0x2000A: never reached

## Suggested Fix
Call `self.mapper.generate_build_script(is_windows)` so each mapper contributes its own script + post-process; delete or fold `_create_build_script_mmc3` into `MMC3Mapper.generate_build_script`.
