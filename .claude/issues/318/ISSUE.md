# SAFE-14: main.py load_config silently falls back to defaults on a missing config path

**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-07-18.md
**Filed as:** #318

## Description
`load_config` treats a given-but-missing --config path the same as no path, silently returning DrumMapperConfig() defaults. Same class of bug #267 fixed elsewhere. Currently dead code (no production caller), so LOW.

## Location
`main.py:763-767`

## Suggested Fix
Delete as dead code, or raise ConfigurationError on a given-but-missing path (matching ConfigManager._load_config) and update tests/test_main.py:1737.

## Related
#267
