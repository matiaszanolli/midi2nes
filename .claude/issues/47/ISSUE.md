# REG-07: No dedicated mapper tests — MapperFactory size-based auto-select (51%) and header/nes.cfg consistency unverified

**Severity:** MEDIUM · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-06-28.md

GitHub: https://github.com/matiaszanolli/midi2nes/issues/47
Labels: medium, regression, mappers, enhancement

## Description
Mappers exercised only indirectly via test_ca65_export.py. MapperFactory auto-select and each mapper's header/linker_config/capacity untested in isolation. No test asserts iNES header mapper number matches the nes.cfg the mapper emits (HIGH per severity doc).

## Evidence
grep -rln MapperFactory tests/ → only test_ca65_export.py. factory.py 51%, base.py 54%, nrom.py 64%. No tests/test_mappers.py.

## Impact
Wrong auto-selected mapper or header/linker drift ships unguarded; PRG-capacity-overrun (CRITICAL) untested.

## Suggested Fix
Add tests/test_mappers.py: auto-select across capacity thresholds (NROM→MMC1→MMC3); header↔cfg mapper-number consistency; capacity-overrun detection.
