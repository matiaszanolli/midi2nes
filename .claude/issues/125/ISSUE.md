**Severity:** LOW · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-06-29.md

## Description
`_load_from_file` wraps `open` + `yaml.safe_load` in `try/except Exception as e: raise ValueError(...)`. The project defines `ConfigurationError` (`core/exceptions.py:149`) for exactly this, but it is never used. Callers (`run_config_validate`, and `DrumMapperConfig.from_file`) cannot distinguish a missing/permission-denied file from malformed YAML, and catch only broad `Exception`. The broad `except Exception` also folds a genuine bug (e.g. a `TypeError` in config post-processing) into the same `ValueError`.

## Location
- `config/config_manager.py:113`–`119`

## Evidence
`config_manager.py:118`: `except Exception as e: raise ValueError(f"Failed to load configuration from {path}: {e}")`. `core/exceptions.py:149`: `class ConfigurationError(MIDI2NESError): pass` — defined, unused.

## Impact
Defense-in-depth / maintainability; callers can't branch on config-error type. No incorrect ROM. LOW.

## Related
- Same exception-discipline theme as SAFE-02 (parsers → `InvalidMIDIError`, also defined-but-unused).
- Distinct from #76 (D-13), which is `DrumMapperConfig.from_file` raising `TypeError` on a stray key — a different file/path.

## Suggested Fix
Catch `(OSError, yaml.YAMLError)` and `raise ConfigurationError(...)`; let other exceptions propagate as real bugs.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this fix (missing file vs malformed YAML → `ConfigurationError`)
