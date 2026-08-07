# #369 — EXP-2026-07-19-1: DPCM note in macro-bytecode stream clamped to 255, not the $00–$5F engine note range

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-19.md

**Dimension:** D4 Byte-Range Safety (cross-ref D5 Bytecode-Spec Conformance)
**Location:** `exporter/exporter_ca65.py:1082-1096` and emission `:1291`; engine dispatch `nes/audio_engine.asm:213-219`

## Description
In the macro-bytecode path, the DPCM channel's `note` (= `sample_id + 1`) is deliberately clamped only to a single byte (`if note > 255: note = 255`, `:1084`), citing #67 which correctly stopped collapsing high drum ids to 95. But DPCM events are emitted through the *same* length+note serializer as tone channels (`.byte ${(write_dur-1)+0x60}, ${note:02X}`, `:1291`), and the 6502 engine re-dispatches every stream byte by range: `< $60` → note, `$60–$7F` → length, `>= $80` → command (`audio_engine.asm:213-219`). `docs/AUDIO_BYTECODE_SPEC.md` §3 states notes occupy `$00–$5F` and that "DPCM sample triggers are encoded as regular note bytes". A DPCM `note` of `$60` or higher (i.e. `sample_id >= 95`) is therefore misread as a Length or Engine command, desyncing the entire DPCM stream from that point — not just one wrong hit.

## Evidence
`note` cap for dpcm is 255 (`:1083-1085`), tone notes cap at 95 (`:1086`). The note byte is emitted positionally after the `$6X` length byte but the engine loops back through `@read_next` and re-dispatches it by range (`@is_note` requires `< $60`, `audio_engine.asm:215-217`). The direct-export path has no such limit (DPCM notes live in a dedicated `dpcm_note` byte table read by index, not dispatched), so the two paths diverge on the maximum supported `sample_id` (direct: 254; bytecode: 94).

## Impact
Latent. Requires a single song with >94 distinct packed DPCM samples, which is unreachable on any real NES PRG/DPCM ROM budget (each sample is multiple KB). No current input triggers it. Blast radius if reached: DPCM channel only, bytecode path only.

## Related
#67 (dpcm 95-clamp removal), spec §3, EXP-07/#83 (bytecode dispatch).

## Suggested Fix
Either clamp DPCM `note` to `0x5F` in the bytecode path (accepting the same collapse #67 removed, but only for the >94-sample edge), or — better — assert `sample_id < 95` and raise a clear `ValueError` (mirroring the instrument/bank-budget guards) so an impossible song fails loudly instead of emitting a stream that decodes to garbage. Document the 94-sample bytecode ceiling next to the `:1083` comment.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **ROUNDTRIP**: If pattern/compression code changes, decompressed playback == original
- [ ] **SIBLING**: Same pattern checked in related files (direct-export path, other channels)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #370 — EXP-2026-07-19-2: FamiStudio export uses direct event[...] subscripts where the CA65 path uses defensive .get()

**Severity:** LOW · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-07-19.md

**Dimension:** D7 Cross-Exporter Consistency
**Location:** `exporter/exporter_famistudio.py:105-107`

## Description
For `pulse1/pulse2/triangle` frames the FamiStudio emitter reads `event['note']` and `event['volume']` via direct subscript. The CA65 emitter reads the same fields defensively (`frame_data.get('note', 0)`, `frame_data.get('volume', 0)`), and the DPCM branch here was already hardened to `.get()` in #82. A frame dict that is missing `note` or `volume` (which the CA65 path tolerates) raises `KeyError` from the FamiStudio path, so the two exporters disagree on what counts as a valid `frames` input.

## Evidence
`note = midi_note_to_famistudio(event['note'])` and `volume = min(15, event['volume'])` (`:105-107`) vs. `frame_data.get('pitch', 0)` / `.get('note', 0)` / `.get('volume', 0)` in `exporter_ca65.py:334-341`.

## Impact
Low and non-default: `generate_famistudio_txt` is not wired to any CLI subcommand (`--format` offers only `ca65`), and `NESEmulatorCore` always populates `note`/`volume`, so no current pipeline input hits the `KeyError`. It is a latent robustness/consistency gap reachable only via direct API use or a future producer that omits a key.

## Related
#82 (dpcm branch hardening in the same function), D7.

## Suggested Fix
Switch the tone-channel reads to `event.get('note', 0)` / `event.get('volume', 0)` to match the CA65 path's tolerance.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #395 — REG-25: test_drum_engine.py::test_main_execution_success never executes drum_engine.py's actual __main__ block

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-08-05.md

## Description
`drum_engine.py`'s CLI entry point (`if __name__ == "__main__":`, only reachable via `python -m dpcm_sampler.drum_engine` or direct script execution — never on import) is not exercised at all. `test_main_execution_success` mocks `builtins.open`, `json.load`, and `json.dumps`, then **reimplements the `__main__` block's logic inline** in the test body rather than invoking the module, and wraps the whole thing in a blanket `try: ... except Exception: pass`. Because `builtins.open` is mocked, the literal `'test_midi.json'` path is never touched, and the bare `except Exception: pass` means the test passes even if every assertion inside it were wrong or the reimplemented logic diverged from the real `__main__` block. A companion test, `test_main_execution_insufficient_args`, has the same shape: it hand-simulates the argument-count check rather than calling the module.

## Location
`tests/test_drum_engine.py:497-546` (`TestDrumEngineMainExecution::test_main_execution_success`); target is `dpcm_sampler/drum_engine.py:168-179` (`if __name__ == "__main__":` block)

## Evidence
```python
# tests/test_drum_engine.py:544-546
        except Exception:
            # Main execution might not be directly testable
            pass
```

## Impact
Zero regression protection on `drum_engine.py`'s actual CLI entry point — a broken `sys.argv` handling, a wrong `map_drums_to_dpcm` call signature, or a crash on real file I/O there would not be caught by either test. Low impact in practice since this entry point is a standalone debug script, not on the `main.py` pipeline path.

## Related
Distinct from #368's dead-code framing of the `DrumPatternAnalyzer` class in the same file — this finding is about the untested `__main__` block.

## Suggested Fix
Use `runpy.run_path(..., run_name="__main__")` or `subprocess.run([sys.executable, "-m", "dpcm_sampler.drum_engine", ...])` against a real temp-dir JSON fixture (per `tests/conftest.py`'s `temp_dir` pattern) so the test exercises the actual code path, and narrow the `except` (or remove it) so a real failure surfaces as a test failure instead of a silent pass.

## Completeness Checks
- [ ] **RANGE**: n/a
- [ ] **CHANNEL**: n/a
- [ ] **CONTRACT**: n/a
- [ ] **ROUNDTRIP**: n/a
- [ ] **FALLBACK**: n/a
- [ ] **CC65**: n/a
- [ ] **SIBLING**: n/a
- [x] **TESTS**: This finding is about test quality itself; fix rewrites the test to exercise real code
- [ ] **DOC**: n/a

---

# #396 — TEMPO-19: tracker/parser.py builds its EnhancedTempoMap without passing ticks_per_beat, hardcoding PPQ 480

**Severity:** LOW · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-08-05.md

## Description
`tracker/parser.py` — the older full parser, confirmed on no production pipeline path and imported only by tests (TD-26/#346) — builds its tempo map as:
```python
tempo_map = EnhancedTempoMap(
    initial_tempo=500000,  # 120 BPM
    validation_config=config,
    optimization_strategy=None  # Disable optimization
)
```
with no `ticks_per_beat` argument, so it silently takes `EnhancedTempoMap.__init__`'s default of 480 (`tracker/tempo_map.py:229`) instead of `mid.ticks_per_beat` — even though `mid = mido.MidiFile(midi_path)` is opened two lines earlier and the real value is available. This is the same class of bug already fixed on the live path (`tracker/parser_fast.py:38` passes `ticks_per_beat=mid.ticks_per_beat`) but was never applied here.

This tempo map in `parser.py` **is** fed real tick data via `add_tempo_change` and **is** used for every note's `get_frame_for_tick` call (`tracker/parser.py:46-50, 62`), so if PPQ ≠ 480 for a parsed file, every frame index it produces would be wrong by the ratio `480 / actual_ticks_per_beat` — a genuine cumulative-drift bug, not an inert one. Distinct from TD-26/#346, which flags the whole module as unreachable in general but does not call out this specific PPQ defect.

## Location
`tracker/parser.py:30-34`

## Evidence
`tracker/parser.py:30-34` vs. the fixed sibling `tracker/parser_fast.py:36-41` (which explicitly comments "CRITICAL: Use the MIDI file's ticks_per_beat for accurate timing"). A `grep -rn "ticks_per_beat" tracker/parser.py` returns no hits — the value is never read from `mid`.

## Impact
None on shipped ROMs today — confirmed via `grep -rln "from tracker.parser import\|tracker\.parser\."` that no non-test module imports `tracker/parser.py` (TD-26/#346). It only matters if a test happens to load a MIDI fixture with PPQ ≠ 480 through this module (producing silently wrong frame numbers in that test's assertions) or if the module is ever reconnected to a live pipeline stage without this being noticed first.

## Related
TD-26/#346 (parser.py production-dead, general); #93/#95 (the PPQ guards this module's `TempoMap.__init__` still correctly enforces `ticks_per_beat >= 1`, just with the wrong default value).

## Suggested Fix
Either delete `tracker/parser.py` per #346's recommendation, or, if it is kept for tests, pass `ticks_per_beat=mid.ticks_per_beat` at line 30 to match `parser_fast.py`.

## Completeness Checks
- [ ] **RANGE**: n/a
- [ ] **CHANNEL**: n/a
- [ ] **CONTRACT**: n/a
- [ ] **ROUNDTRIP**: n/a
- [ ] **FALLBACK**: n/a
- [ ] **CC65**: n/a
- [ ] **SIBLING**: `tracker/parser_fast.py` (the live-path sibling) already passes `ticks_per_beat` correctly
- [ ] **TESTS**: A test loading a non-480-PPQ fixture through `parser.py` would catch this
- [ ] **DOC**: n/a
