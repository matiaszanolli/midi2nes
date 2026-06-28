# Direct/--no-patterns export path is unbuildable: missing bytecode-engine symbols

Labels: bug, high, pipeline

**Severity:** HIGH · **Domain:** pipeline/exporters · **Source:** surfaced while fixing #5/#7/#39

## Description
The direct-frame export path (`CA65Exporter.export_direct_frames`, used by `--no-patterns` and by empty/`{}` pattern input) produces a *self-contained, table-based* engine. But `NESProjectBuilder.prepare_project` unconditionally appends the **bytecode macro engine** (`seq_cmd_dpcm_play`, the `EVAL_MACRO` instrument engine, etc.) and links `nes/audio_engine.asm`, both of which `.import` symbols only the **patterns** path defines: `ntsc_period_low`/`ntsc_period_high`, `instrument_table`, `ptr1`, `temp1`, and the `*_sequence` labels. In direct mode none of these exist → `music.asm` fails to assemble.

This was masked until now by the `audio_engine.asm` branch-range error (#39) and the segment mismatch (#5); with those fixed, the default (patterns) pipeline builds a bootable ROM, but the direct path now fails outright.

## Evidence
```
$ python main.py --no-patterns test_midi/simple_loop.mid out.nes
[ERROR] Failed to assemble music.asm: music.asm(646): Error: Symbol 'ntsc_period_high' is undefined
  ... 'ntsc_period_low' ... 'temp1' ... 'ptr1' ... 'instrument_table' is undefined
[ERROR] ROM compilation failed
```
Also fails `tests/test_ca65_export.py::TestCA65CompilationIntegration::test_empty_project_compilation` (which builds the empty/direct path), and `export_direct_frames` (exporter_ca65.py:59) defines none of those symbols.

## Impact
The documented `--no-patterns` flag (full-fidelity direct export) cannot produce a ROM at all; same for any empty-pattern project. Default patterns path is unaffected. Blast radius: every `--no-patterns` invocation.

## Related
Unblocked by #5/#7/#39 (default patterns pipeline now builds). Keeps `test_empty_project_compilation` red.

## Suggested Fix
Two coherent options: (a) in direct mode, `prepare_project` should not inject the bytecode macro engine or link `audio_engine.asm` (the direct export is self-contained); or (b) `export_direct_frames` should emit the same engine symbols (ntsc tables, instrument_table stub, sequence stubs) so the macro engine resolves. (a) is cleaner — the two engines are different playback architectures and should not be merged. Add a `--no-patterns` end-to-end build test as the gate.
