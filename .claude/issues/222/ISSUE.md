# SAFE-11: ConfigManager.save() and validate() raise bare ValueError, not typed exceptions

- **GitHub Issue**: https://github.com/matiaszanolli/midi2nes/issues/222
- **Severity**: LOW
- **Domain**: safety
- **Source**: docs/audits/AUDIT_SAFETY_2026-07-03.md
- **Dimension**: 7 — Exception-Type Discipline
- **Location**: `config/config_manager.py:241` (`save`), `config/config_manager.py:280` (`validate`)
- **Status**: NEW (filed)

## Description
SAFE-08 (#125, closed) narrowed `_load_from_file`'s catch from bare `except Exception` to `(OSError, yaml.YAMLError)` and switched it to raise `ConfigurationError` (`config_manager.py:120`-126). That fix was explicitly scoped to *load* failures only. Its two siblings in the same class were not touched: `save()` raises `raise ValueError("No path specified for saving configuration")` when no path is available, and `validate()` raises `raise ValueError("Configuration validation failed:\n" + ...)` on a failed validation. Both bypass the typed hierarchy in `core/exceptions.py` (`ConfigurationError`, `ValidationError`) that callers elsewhere in the codebase can already branch on.

## Evidence
`config_manager.py:240`-241: `if not save_path: raise ValueError("No path specified for saving configuration")`. `config_manager.py:279`-280: `if errors: raise ValueError("Configuration validation failed:\n" + "\n".join(...))`.

## Impact
Defense-in-depth / maintainability only — `run_config_validate` (`main.py:996`-1012) catches broad `Exception` anyway, so no user-facing regression; a caller that specifically wants to distinguish "config invalid" from "any other bug" can't. No incorrect ROM output.

## Related
Same theme as the closed SAFE-08/#125 (`_load_from_file`) and SAFE-02/#121 (typed `InvalidMIDIError`) — this report just confirms the two siblings SAFE-08 intentionally left out of scope are still open.

## Suggested Fix
`save()` → `raise ConfigurationError(...)`; `validate()` → `raise ValidationError(..., checks_failed=errors)` (matching the `ValidationError(message, checks_failed=...)` shape already used in `compiler/compiler.py:60`-63).

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
