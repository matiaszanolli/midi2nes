# PL-07 / #267: --config silently reverts to built-in defaults when the given path does not exist

**Severity:** MEDIUM · **Domain:** pipeline · **Dimension:** 3 (Flag Routing) · **Source:** AUDIT_PIPELINE_2026-07-05.md

## Description
`ConfigManager._load_config` treats a `--config` path that is *passed but does not exist* exactly like "no config given": it falls into the `else` branch and silently loads built-in defaults. Since `--config` was only recently wired to actually be consumed (#219, previously dropped), this silent no-op is newly reachable from the pipeline. There is no warning on any path.

Both entry points are affected: the default `run_full_pipeline` (`--config` global flag) and the `detect-patterns --config` subcommand both route to `get_pattern_detection_caps`. The `config validate` subcommand is the most user-visible manifestation.

## Location
- `config/config_manager.py:110-115` (`_load_config`)
- Wired at `main.py` `get_pattern_detection_caps`, default-path `--config` routing, consumers, and `run_config_validate`.

## Evidence
```python
# config/config_manager.py:110-115
def _load_config(self):
    """Load configuration from file or use defaults."""
    if self.config_path and self.config_path.exists():
        self._load_from_file(self.config_path)
    else:
        self._load_defaults()   # a MISSING given path lands here silently
```
Live-reproduced:
```
$ python main.py config validate /tmp/does_not_exist_xyz.yaml
[OK] Configuration file is valid: /tmp/does_not_exist_xyz.yaml
```

## Impact
Bounded. `--config` currently overrides only `processing.pattern_detection.max_events` / `max_pattern_events` (compression-analysis event-sampling caps). Every emitted ROM byte still derives from the full `frames` dict, so a silently-ignored `--config` never changes the song — only compression stats/telemetry. The `config validate` false-positive is the sharper edge: it green-lights a path that isn't there. MEDIUM per _audit-severity.md.

## Suggested Fix
In `_load_config`, distinguish "no path given" from "path given but missing": if `self.config_path` is set and does not exist, raise `ConfigurationError` (already imported, used in `_load_from_file`) instead of falling through to `_load_defaults()`.

## Completeness Checks
- [ ] CONTRACT, TESTS, DOC (see GitHub issue body)

---

# NH-30 / #268: Arranger pulse channels silence the softest notes -- vel // 8 floors to volume 0 with no max(1, ...) guard

**Severity:** MEDIUM · **Domain:** nes-hardware · **Dimension:** 6 (Velocity -> 4-bit volume) · **Source:** AUDIT_NES-HARDWARE_2026-07-05.md

## Description
In `--arranger` mode the pulse1/pulse2 per-frame volume is derived as `vel // 8` from the MIDI velocity (0-127) with **no floor**. Any note with velocity 1-7 integer-divides to `0`, so the 4-bit volume nibble is `0`: pitch and duty are written but the channel plays at zero amplitude -- the note is inaudible.

The legacy `emulator_core` front-end deliberately avoids this with `max(1, int(15 * math.pow(velocity / 127.0, 1.5)))`. The arranger applies neither the floor nor the power curve. Sibling arranger channels *do* floor (noise, triangle), so only the pulse channels are exposed.

## Location
- `arranger/voice_allocator.py:362,370` -- `"volume": vel // 8`
- Consumed at `arranger/pipeline_integration.py:256-257`

## Evidence
`voice_allocator.py:362` `"volume": vel // 8` (127//8 = 15 max, 7//8 = 0); `pipeline_integration.py:256-257` copies `data['volume']` straight into both the `volume` field and the control byte low nibble with no `max(1, ...)`.

## Impact
On `--arranger` arrangements, every pulse note softer than MIDI velocity 8 (ppp phrasing, fade-ins/outs, ghost notes) is emitted silently. Blast radius: pulse1/pulse2 in arranger mode only.

## Suggested Fix
Floor the pulse volume at 1 for any active note, mirroring the legacy path -- e.g. `"volume": max(1, vel // 8)` in `voice_allocator.py:362,370`.

## Completeness Checks
- [ ] RANGE, CHANNEL, SIBLING, TESTS, DOC (see GitHub issue body)
