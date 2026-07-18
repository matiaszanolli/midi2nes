# SAFE-11: ConfigManager.save() and validate() raise bare ValueError, not typed exceptions

**Severity:** LOW · **Domain:** safety

## Description
SAFE-08 (#125) narrowed `_load_from_file`'s catch to typed `ConfigurationError`. Its siblings weren't touched: `save()` raises `ValueError("No path specified for saving configuration")`, `validate()` raises `ValueError("Configuration validation failed:\n" + ...)`. Both bypass the typed hierarchy in `core/exceptions.py`.

## Location
`config/config_manager.py:241` (`save`), `config/config_manager.py:280` (`validate`)

## Suggested Fix
`save()` → `raise ConfigurationError(...)`; `validate()` → `raise ValidationError(..., checks_failed=errors)` (matches shape used in `compiler/compiler.py:60-63`).

## Completeness Checks
- [ ] TESTS: regression test pins this fix
- [ ] DOC: doc corrected if contradicted
