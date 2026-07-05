# PL-07: --config silently reverts to built-in defaults when the given path does not exist

**Issue:** #267
**Severity:** MEDIUM · **Domain:** pipeline · **Dimension:** 3 (Flag Routing)
**Source:** AUDIT_PIPELINE_2026-07-05.md
**Labels:** medium, pipeline, bug

## Description
`ConfigManager._load_config` treats a `--config` path that is passed but does not exist exactly like "no config given": it falls into the `else` branch and silently loads built-in defaults. Since `--config` was only recently wired to actually be consumed (#219), this silent no-op is newly reachable. No warning on any path.

Both the default `run_full_pipeline` (`--config` global flag) and `detect-patterns --config` route to `get_pattern_detection_caps`. `config validate` is the most user-visible manifestation.

## Location
- `config/config_manager.py:110-115` (`_load_config`)
- Wired at `main.py` `get_pattern_detection_caps`, default-path routing, consumers, `run_config_validate`.

## Evidence
```python
# config/config_manager.py:110-115
def _load_config(self):
    if self.config_path and self.config_path.exists():
        self._load_from_file(self.config_path)
    else:
        self._load_defaults()   # missing given path lands here silently
```
Live-reproduced: `python main.py config validate /tmp/does_not_exist_xyz.yaml` reports `[OK] ... is valid`.

## Impact
Bounded — `--config` only overrides pattern-detection sampling caps (compression analysis), never emitted ROM bytes. `config validate` false-positive is the sharper edge. Recoverable → MEDIUM.

## Suggested Fix
In `_load_config`, if `self.config_path` is set and does not exist, raise `ConfigurationError` (already imported at line 9) instead of falling through to `_load_defaults()`.
