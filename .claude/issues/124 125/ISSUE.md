# Issue #124: SAFE-07: Per-event except Exception: continue in fast parser can silently drop a note event

**Severity:** MEDIUM · **Domain:** safety · **Source:** AUDIT_SAFETY_2026-06-29.md

## Description
Inside the note loop of the fast parser, frame conversion + dict-build for each `note_on`/`note_off` is wrapped in `try: ... except Exception: continue` ("to avoid crashes"). If `tempo_map.get_frame_for_tick(...)` / `get_tempo_at_tick(...)` or any attribute access raises for a given event, that note is dropped with **no count and no warning** — per `_audit-severity.md` a dropped MIDI event class that changes the song is a CRITICAL floor.

Mitigated to MEDIUM: re-reading the path, `get_frame_for_tick` is pure arithmetic with no `raise`, and `get_tempo_at_tick` returns a stored tempo, so on realistic MIDI no note is actually dropped today — the catch is dead defense that *would* hide data loss if a future change made the hot path raise. It is the silent, uncounted nature (not a confirmed live drop) that keeps this open.

## Location
- `tracker/parser_fast.py:61`–`79` (the per-event `try`/`except Exception: continue` at `:77`)

## Evidence
`parser_fast.py:77`: `except Exception:` / `# Skip problematic events to avoid crashes` / `continue`. No counter, no warning — unlike the tempo-change skip elsewhere which is at least scoped to a specific exception.

## Impact
If the per-event path ever raises (e.g. a future tempo-map regression), notes vanish silently and the ROM plays the wrong song with no signal. Today: latent.

## Related
- Distinct from #106 (P-09), which is the per-chunk `except…continue` in the **parallel pattern detector** (`pattern_detector_parallel.py`) — different file, different code path.
- Cross-refs SAFE-02 (same file's top-level `mido` guard gap).

## Suggested Fix
Catch only the specific expected exception (or count drops and emit a warning if >0), so a real drop is surfaced rather than swallowed. Mirror the `was_sampled` warning pattern used elsewhere.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this fix (an event that would raise is counted/warned, not silently dropped)
- [ ] **SIBLING**: Same silent-drop pattern checked in the full parser (`tracker/parser.py`)

---

# Issue #125: SAFE-08: ConfigManager._load_from_file re-raises as generic ValueError, not ConfigurationError

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
