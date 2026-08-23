import argparse
import sys
import json
import tempfile
import shutil
from dataclasses import dataclass, field
from typing import Optional, Dict
from pathlib import Path

# Import version information
try:
    from midi2nes import __version__
except ImportError:
    # Fallback for development mode
    __version__ = "0.5.0-dev"

from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore, frames_to_events
from arranger import arrange_for_nes
from nes.project_builder import NESProjectBuilder, NES_CFG_MAPPER_MARKER
from nes.song_bank import SongBank
from exporter.exporter_ca65 import CA65Exporter

# Frozen copy of CA65Exporter.SEQUENCE_CHANNELS, captured at import time
# rather than read live off the class -- several tests patch
# `main.CA65Exporter` with a Mock() for unrelated reasons (asserting export
# call args, etc.), which would silently turn a live
# `CA65Exporter.SEQUENCE_CHANNELS` read inside load_json_stage's
# channel_shape guard into an empty MagicMock iterator, making the guard
# reject every input regardless of its actual channel keys.
_PIPELINE_CHANNEL_KEYS = tuple(CA65Exporter.SEQUENCE_CHANNELS)
from tracker.pattern_detector import (
    EnhancedPatternDetector, sample_events_for_detection, DETECTOR_MAX_EVENTS, MAX_PATTERN_EVENTS
)
from tracker.tempo_map import EnhancedTempoMap
from dpcm_sampler.enhanced_drum_mapper import DrumMapperConfig
from config.config_manager import ConfigManager
from core.exceptions import (
    ConfigurationError, MIDI2NESError, MapperError, ExportError,
    CompilationError, ValidationError,
)
from benchmarks.performance_suite import PerformanceBenchmark
from utils.profiling import get_memory_usage, log_memory_usage
from compiler import compile_rom

# Shared pattern-detection bounds. Both entry points (the `detect-patterns`
# subcommand and the default full pipeline) must use identical parameters so
# their `patterns`/`references` JSON artifacts agree for the same input (#19).
# Sourced from constants.py (a leaf module) so the benchmark can share the exact
# same bounds without a main.py <-> benchmarks import cycle (#262/PERF-11).
from constants import PATTERN_MIN_LENGTH, PATTERN_MAX_LENGTH

# Advisory large-file heads-up threshold, aligned with the parallel detector's
# sampling cap by default (#334/PERF-14) -- overridable in lockstep with the
# other two caps via processing.pattern_detection.large_file_threshold.
LARGE_FILE_THRESHOLD_DEFAULT = MAX_PATTERN_EVENTS

def get_pattern_detection_caps(config_path: Optional[str] = None):
    """Resolve the sequential/parallel pattern-detection event-sampling caps
    plus the advisory large-file threshold.

    Defaults to the hardcoded DETECTOR_MAX_EVENTS/MAX_PATTERN_EVENTS/
    LARGE_FILE_THRESHOLD_DEFAULT constants; when `config_path` is given,
    `processing.pattern_detection.max_events` / `max_pattern_events` /
    `large_file_threshold` override them (#219, #334) — this is the single
    place both the `detect-patterns` subcommand and the default full pipeline
    resolve these caps from, so they stay in sync.
    """
    max_events = DETECTOR_MAX_EVENTS
    max_pattern_events = MAX_PATTERN_EVENTS
    large_file_threshold = LARGE_FILE_THRESHOLD_DEFAULT
    if config_path:
        try:
            config_manager = ConfigManager(config_path)
        except ConfigurationError as e:
            # Clean [ERROR] + exit, matching load_json_stage's convention --
            # main.py has no outer caller to catch this for every subcommand
            # that reaches here (#267/PL-07).
            print(f"[ERROR] {e}")
            sys.exit(1)
        max_events = config_manager.get("processing.pattern_detection.max_events", DETECTOR_MAX_EVENTS)
        max_pattern_events = config_manager.get(
            "processing.pattern_detection.max_pattern_events", MAX_PATTERN_EVENTS)
        large_file_threshold = config_manager.get(
            "processing.pattern_detection.large_file_threshold", LARGE_FILE_THRESHOLD_DEFAULT)
    return max_events, max_pattern_events, large_file_threshold

def load_json_stage(path, required_keys, stage_name, channel_shape=False):
    """Load an inter-stage JSON artifact with an existence/parse/key guard.

    Every step-by-step subcommand did `json.loads(Path(input).read_text())`
    then immediately indexed a hard-coded key, so a missing file, a
    truncated/garbage file, or a file from the wrong pipeline stage all
    surfaced as a raw traceback (FileNotFoundError / JSONDecodeError /
    KeyError) on the documented step-by-step debugging path instead of a
    clear message (#120). Exits with a clean [ERROR] message and code 1,
    matching every other subcommand guard in this file (#110, #13, #15)
    rather than raising, since main.py has no outer caller to catch it.

    `channel_shape=True` is for the `frames`/`export`/`detect-patterns`
    subcommands, whose input (map-stage or frames-stage JSON) is a dict
    keyed by the five NES channel names, every one of them optional -- so
    `required_keys` alone can't express "this must be the right stage's
    shape" the way `run_map`'s `['events']` or `run_export`'s
    `['patterns', 'references']` can. Without this, a non-empty JSON object
    that happens to have none of those five keys (most commonly a
    parse-stage file, `{"events": [...], "metadata": {...}}`, or a
    detect-patterns file fed to the wrong subcommand) passed the guard
    silently and produced an empty-but-exit-0 result at every stage
    downstream (#485/PIPE-2026-08-22-1, a regression of #377/PIPE-2026-07-19-1
    whose fix commit was never merged to master). A genuinely empty `{}`
    (a real all-rest song) is still accepted -- only non-empty JSON with no
    recognizable channel key is rejected.
    """
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] {stage_name} input not found: {p}")
        sys.exit(1)
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        print(f"[ERROR] {stage_name} input is not valid JSON: {p} ({e})")
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"[ERROR] {stage_name} input must be a JSON object: {p}")
        sys.exit(1)
    missing = [k for k in required_keys if k not in data]
    if missing:
        print(f"[ERROR] {stage_name} input missing expected key(s) {missing}: {p} "
              f"(is this the right stage's JSON?)")
        sys.exit(1)
    if channel_shape and data and not any(k in data for k in _PIPELINE_CHANNEL_KEYS):
        print(f"[ERROR] {stage_name} input has none of the expected channel keys "
              f"({', '.join(_PIPELINE_CHANNEL_KEYS)}): {p} "
              f"(is this the right stage's JSON? a 'parse' stage file has "
              f"'events'/'metadata' instead, and needs 'map' run on it first)")
        sys.exit(1)
    return data


@dataclass
class DpcmPackResult:
    """Result of `pack_dpcm_into_asm` (#380/TD-28). `index_found=False` means
    there was nothing to pack (no dpcm_index.json) and no other field is
    meaningful; otherwise `warning` is set on failure/no-samples-resolved,
    `loaded_samples`/`bank_count` describe a successful pack."""
    index_found: bool = False
    sample_ids: Dict[str, int] = field(default_factory=dict)
    loaded_samples: int = 0
    skipped_samples: int = 0
    bank_count: int = 0
    warning: Optional[str] = None
    # Populated only on the except path, so a --verbose caller can print it
    # (captured here, not at the call site, since the exception context
    # that traceback.format_exc() needs only exists inside this function).
    traceback_text: Optional[str] = None


def pack_dpcm_into_asm(frames, asm_path, *, verbose=False) -> DpcmPackResult:
    """Pack this song's referenced DPCM samples and append the generated
    lookup tables + binary includes to `asm_path`.

    Extracted from run_export's and run_full_pipeline's identical
    copy-pasted DPCM-packing sequence (#380/TD-28) -- both blocks did the
    same thing in the same order (instantiate DpcmPacker, check
    dpcm_index.json exists, compute sample_ids, load into the packer,
    append packer.generate_assembly()) with the same broad `except
    Exception` warning message, but had already drifted (run_export never
    passed verbose= through; only run_full_pipeline printed packed-count/
    no-samples/no-index status lines) -- a fix to one path could silently
    miss the other. Presentation (step banners, status lines) stays at the
    call sites; only the pack logic and the broad-except handling live here.
    """
    from dpcm_sampler.dpcm_packer import DpcmPacker
    from dpcm_sampler.generate_dpcm_index import (
        load_dpcm_index_into_packer,
        get_dpcm_sample_ids_from_frames,
    )
    dpcm_index_path = Path('dpcm_index.json')
    if not dpcm_index_path.exists():
        return DpcmPackResult(index_found=False)

    packer = DpcmPacker()
    try:
        with open(dpcm_index_path, 'r') as f:
            dpcm_index = json.load(f)
        # Pack only the samples this song triggers, not the whole catalog
        # (#140), in ascending id order so they align with the engine's
        # positional tables. An empty dict means "pack nothing" (no DPCM in
        # this song), not "pack everything" -- pass it through directly.
        # The dense_id -> catalog_id shape also lets the packer key each
        # entry by its (small) dense id instead of a potentially huge
        # catalog id, avoiding the note-byte collision two high catalog ids
        # used to hit (#200/D-14).
        sample_ids = get_dpcm_sample_ids_from_frames(frames)
        skipped_details = []
        loaded_samples, skipped_samples = load_dpcm_index_into_packer(
            packer, dpcm_index, dpcm_index_path, verbose=verbose,
            sample_ids=sample_ids, skipped_details=skipped_details)

        with open(asm_path, 'a') as f:
            f.write("\n\n" + packer.generate_assembly())

        warning = None
        if loaded_samples == 0 and sample_ids:
            warning = (
                f"this song references {len(sample_ids)} DPCM sample(s) but none "
                f"resolved to a file — the exported ASM has NO drums."
            )
        elif skipped_details:
            # Partial miss (#367/DP-DPCM-05): the frames stage already baked
            # dense_id = note-1 for every referenced sample before file
            # resolution ran here, so a skipped id's lookup-table slot is a
            # $00 placeholder the frame still indexes. Name the dropped
            # drums (loud, not just verbose-gated) instead of silently
            # leaving that slot for the runtime $00-length skip to catch.
            # Built from skipped_details (populated in-place by this call),
            # not the skipped count returned above -- robust to a caller
            # that mocks load_dpcm_index_into_packer's return shape.
            names = ", ".join(
                f"{d['filename']} (id {d['pack_id']})" for d in skipped_details)
            warning = (
                f"{len(skipped_details)} of {len(sample_ids)} referenced DPCM "
                f"sample(s) could not be found and were dropped (silenced, not "
                f"substituted): {names}"
            )
        return DpcmPackResult(
            index_found=True, sample_ids=sample_ids,
            loaded_samples=loaded_samples, skipped_samples=skipped_samples,
            bank_count=len(packer.banks),
            warning=warning,
        )
    except Exception as e:
        # Tracks any failure so it can be surfaced prominently rather than
        # buried above the final status line -- a corrupt/partial
        # dpcm_index.json (bad JSON, or an entry missing 'id'/'filename')
        # used to be swallowed by this broad except with only an
        # easy-to-miss warning (#123).
        import traceback
        return DpcmPackResult(
            index_found=True,
            warning=(
                f"DPCM packing failed ({e}) — the exported ASM has NO drums "
                f"even though dpcm_index.json may reference some."
            ),
            traceback_text=traceback.format_exc(),
        )


def run_parse(args):
    # Use fast parser by default for better performance
    from tracker.parser_fast import parse_midi_to_frames as parse_fast
    midi_data = parse_fast(args.input)
    # Compact separators (#116): this is a machine-only intermediate a human
    # rarely opens, and indent=2 typically inflates it 2-3x for no benefit.
    Path(args.output).write_text(json.dumps(midi_data, separators=(',', ':')))
    print(f"[OK] Parsed MIDI -> {args.output}")

def run_map(args):
    # Guard against a missing/corrupt file or wrong-stage JSON (#110, #120).
    midi_data = load_json_stage(args.input, ['events'], 'parse')
    # Honor --dpcm-index instead of silently using the default (#13).
    dpcm_index_path = getattr(args, 'dpcm_index', None) or 'dpcm_index.json'
    # A missing DPCM index made assign_tracks_to_nes_channels raise a bare
    # FileNotFoundError, so the step-by-step `map` subcommand exited with a raw
    # traceback -- unlike the packer path (which checks .exists() and degrades)
    # and every other subcommand guard here (#256/D-18). Surface a clean
    # [ERROR] with the same exit(1) convention as load_json_stage.
    if not Path(dpcm_index_path).exists():
        print(f"[ERROR] DPCM index not found: {dpcm_index_path} "
              f"(pass --dpcm-index <path>, or restore dpcm_index.json)")
        sys.exit(1)
    # Extract just the events from the parsed data
    mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
    Path(args.output).write_text(json.dumps(mapped, separators=(',', ':')))
    print(f"[OK] Mapped tracks -> {args.output}")

def run_frames(args):
    # Guard against a missing/corrupt file (#120); the mapped JSON's channel
    # keys are all optional, so there is no fixed required key to validate
    # -- channel_shape=True instead rejects a non-empty file with none of
    # them at all, e.g. a parse-stage file (#485/PIPE-2026-08-22-1).
    mapped = load_json_stage(args.input, [], 'map', channel_shape=True)
    emulator = NESEmulatorCore()
    frames = emulator.process_all_tracks(mapped)
    Path(args.output).write_text(json.dumps(frames, separators=(',', ':')))
    print(f" Generated frames -> {args.output}")

# Music.asm sizing + the mapper capacity pre-flight live in mappers.capacity so
# NESProjectBuilder.prepare_project (a library entry point) runs the same gate
# the CLI does, not just main.py (#363/MAP-2026-07-19-3). Re-exported here so
# existing `from main import estimate_segment_sizes` / `check_mapper_capacity`
# imports keep resolving.
from mappers.capacity import (  # noqa: E402
    estimate_segment_sizes,
    estimate_music_data_size,
    check_mapper_capacity,
)

# Declares the three re-exported names above as intentionally public, so
# pyflakes' F401 (unused-import) check doesn't flag estimate_segment_sizes --
# the only one of the three with no call site inside main.py itself (the
# other two are also used internally at lines ~272/491/1070). `__all__`
# membership is what pyflakes actually honors for "this import is used
# elsewhere"; a `# noqa: F401` comment is NOT honored by plain pyflakes
# (unlike flake8), so it would silently fail to suppress this (#393/REG-23).
__all__ = [
    "estimate_segment_sizes",
    "estimate_music_data_size",
    "check_mapper_capacity",
]


def _requires_mmc3_bytecode_engine(music_asm_path):
    """True if music.asm was generated by the MMC3 macro-bytecode (pattern-
    compressed) exporter path (CA65Exporter.export_tables_with_patterns with
    non-empty patterns), identified the same way nes/project_builder.py's
    `is_bytecode` does: a marker comment only that path emits.

    That engine's DPCM/sequence-bank switching (`switch_dpcm_bank`,
    `fetch_sequence_byte`) is built directly on MMC3's $8000/$8001 bank
    registers -- NROM has no bank switching at all and MMC1's
    generate_bank_switch_code() doesn't define a `switch_dpcm_bank` label, so
    a non-MMC3 build in this mode fails at link time with an unresolved
    external, not a clean error (discovered while wiring up #217/MAP-6).
    """
    path = Path(music_asm_path)
    return path.exists() and "MMC3 Macro Bytecode" in path.read_text()


def _direct_export_packed_mapper_name(music_asm_path):
    """Return the mapper name a direct-export music.asm was bin-packed for
    (e.g. 'MMC1'), or None.

    When a mapper's direct_export_bank_size() is not None (currently only
    MMC1), CA65Exporter.export_direct_frames bin-packs the frame tables into
    RODATA_BANK_NN segments that ONLY that mapper's linker config defines, and
    stamps a "; Direct export bank-packed for <name>" marker. `prepare`/
    `compile` parse their own --mapper independently, so a mismatched later
    choice (e.g. `export --mapper mmc1` then `prepare` with the mmc3 default)
    would otherwise pass check_mapper_capacity — which recognizes no
    RODATA_BANK_NN branch for the wrong mapper — and defer the failure to a raw
    ld65 "Missing memory area assignment" error (#283/MAP-2026-07-05B-3,
    #285/PL-09). This is the direct-export mirror of the bytecode-path guard
    _requires_mmc3_bytecode_engine.
    """
    path = Path(music_asm_path)
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        marker = "; Direct export bank-packed for "
        if line.startswith(marker):
            return line[len(marker):].strip()
    return None


# Marker CA65Exporter.export_direct_frames stamps when a direct-export song has
# a DPCM channel. Direct-export DPCM is MMC3-only, so the split prepare/compile
# flow keys off this to re-force MMC3 / reject a non-MMC3 --mapper
# (#362/MAP-2026-07-19-2).
DIRECT_EXPORT_DPCM_MARKER = "; Direct export DPCM (MMC3-only)"


def _direct_export_requires_mmc3_dpcm(music_asm_path):
    """True if music.asm is a direct-export song carrying the DPCM marker.

    Direct-export (--no-patterns) DPCM is MMC3-only: play_dpcm writes MMC3's
    $8000/$8001 bank ports and DpcmPacker emits MMC3-only DPCM_NN segments. The
    `export`/`run_full_pipeline` paths enforce this in-memory via
    enforce_direct_export_dpcm_mapper, but the split `prepare`/`compile` flow
    only has the finished music.asm — this marker lets resolve_mapper reproduce
    the enforcement up front instead of failing at a raw ld65 "Missing memory
    area assignment for DPCM_00" (#362/MAP-2026-07-19-2). Mirrors
    _requires_mmc3_bytecode_engine / _direct_export_packed_mapper_name.
    """
    path = Path(music_asm_path)
    return path.exists() and DIRECT_EXPORT_DPCM_MARKER in path.read_text()


def _prepared_mapper_name_from_cfg(nes_cfg_path):
    """Return the mapper name a project was prepared with, read from the
    leading marker NESProjectBuilder stamps into nes.cfg, or None.

    nes.cfg is the authoritative record of what `prepare` built. A NROM (or
    MMC1) direct-export project's music.asm carries no engine/bank marker, so
    without this `compile` cannot tell it apart from an MMC3 project and its
    --mapper default (mmc3) mis-sizes it (#297/MAP-2026-07-06-1). Recovering
    the mapper from nes.cfg makes the split prepare/compile flow round-trip for
    every mapper, and also gives `prepare --mapper auto` a matching compile
    invocation (#269/PL-08).
    """
    path = Path(nes_cfg_path)
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith(NES_CFG_MAPPER_MARKER):
            return line[len(NES_CFG_MAPPER_MARKER):].strip() or None
    return None


def resolve_mapper(mapper_choice, music_asm_path=None):
    """Resolve a --mapper CLI value ('auto', 'nrom', 'mmc1', 'mmc3') to a
    mapper instance (#217/MAP-6).

    MapperFactory.auto_select()'s smallest-fits-first selection previously
    had no caller outside tests/test_mappers.py -- every real build hardcoded
    MMC3Mapper. 'auto' estimates the music data size from music_asm_path and
    picks the smallest mapper that fits it; any other value is looked up
    directly via MapperFactory.get_mapper(). Either way, a music.asm built by
    the MMC3 macro-bytecode engine forces MMC3 -- see
    _requires_mmc3_bytecode_engine.
    """
    from mappers.factory import MapperFactory
    needs_mmc3 = music_asm_path is not None and _requires_mmc3_bytecode_engine(music_asm_path)
    direct_dpcm = music_asm_path is not None and _direct_export_requires_mmc3_dpcm(music_asm_path)
    packed_for = (_direct_export_packed_mapper_name(music_asm_path)
                  if music_asm_path is not None else None)
    if mapper_choice == 'auto':
        # Both the bytecode engine and direct-export DPCM are MMC3-only; force it.
        if needs_mmc3 or direct_dpcm:
            return MapperFactory.get_mapper('mmc3')
        # A direct-export music.asm bin-packed for a specific banked mapper can
        # only link against that mapper's RODATA_BANK_NN regions, so 'auto'
        # must honor it rather than re-estimating a (smaller) mapper by size
        # (#283/#285) -- mirrors forcing MMC3 for the bytecode marker above.
        if packed_for:
            return MapperFactory.get_mapper(packed_for)
        # Reaching here means a non-bytecode, non-bank-packed music.asm -- i.e.
        # a direct (--no-patterns) export -- so rank by each mapper's real direct
        # budget (#361/MAP-2026-07-19-1), not the flat banked capacity.
        data_size = estimate_music_data_size(music_asm_path)
        return MapperFactory.auto_select(data_size, direct=True)
    mapper = MapperFactory.get_mapper(mapper_choice)
    if needs_mmc3 and mapper.mapper_number != 4:
        raise MapperError(
            f"{mapper.name} cannot run the MMC3 macro-bytecode (pattern-compressed) "
            f"engine this music.asm was built with -- rebuild with --no-patterns "
            f"for direct frame export, or pass --mapper mmc3."
        )
    if direct_dpcm and mapper.mapper_number != 4:
        raise MapperError(
            f"--mapper {mapper_choice} does not support DPCM samples in direct-export "
            f"(--no-patterns) mode: this music.asm packs DPCM_NN sample segments and "
            f"triggers them via MMC3-only $8000/$8001 bank writes. Use --mapper mmc3 "
            f"(the default) or --mapper auto, or rebuild without --no-patterns."
        )
    if packed_for and mapper.name != packed_for:
        raise MapperError(
            f"this music.asm's frame tables were bank-packed for {packed_for} at "
            f"export time (RODATA_BANK_NN segments only {packed_for}'s linker config "
            f"defines), but --mapper {mapper_choice} was selected here -- re-export "
            f"with --mapper {mapper_choice} or run prepare/compile with "
            f"--mapper {packed_for.lower()}."
        )
    return mapper


def enforce_direct_export_dpcm_mapper(mapper, mapper_choice, frames):
    """Direct-export (--no-patterns) DPCM is MMC3-only. Return the mapper to
    actually build with, forcing MMC3 for 'auto' and rejecting an explicit
    non-MMC3 request (#281/MAP-2026-07-05B-1, #282/MAP-2026-07-05B-2).

    A song with a non-empty ``dpcm`` channel emits two hardcoded MMC3-only
    pieces in the direct-export path:
      - ``play_dpcm`` triggers a sample by writing MMC3's R6 bank-select port
        (``$8000``/``$8001``); on MMC1 those addresses are a 5-write serial
        shift register, so the two raw writes corrupt MMC1's Control register
        and can un-fix the engine/vector bank mid-song (#281);
      - ``DpcmPacker`` emits ``DPCM_NN`` segments only mmc3's nes.cfg defines,
        so a sample that actually packs fails to link on MMC1/NROM (#282).

    Neither path is mapper-aware yet (the MMC1 Mode-2 streaming design in
    docs/MAPPER_MMC1_REFERENCE.md §4 is unimplemented), so rather than ship a
    ROM that corrupts or won't link, mirror the bytecode path (always MMC3):
    'auto' picks MMC3 (a mapper that works); an explicit mmc1/nrom is a clean
    ValueError. Called only on the direct-export branch — the bytecode/pattern
    path is already forced to MMC3.
    """
    if not frames.get('dpcm'):
        return mapper
    if mapper.mapper_number == 4:  # MMC3
        return mapper
    if mapper_choice == 'auto':
        from mappers.mmc3 import MMC3Mapper
        return MMC3Mapper()
    raise MapperError(
        f"--mapper {mapper_choice} does not support DPCM samples in direct-export "
        f"(--no-patterns) mode: this song maps drums to the DPCM channel, whose "
        f"trigger/sample code is MMC3-only. Use --mapper mmc3 (the default) or "
        f"--mapper auto, or rebuild without --no-patterns."
    )


def get_mapper_choice(args):
    """Read args.mapper defensively, defaulting to 'mmc3' (#217/MAP-6).

    A plain `getattr(args, 'mapper', 'mmc3')` breaks for MagicMock-based args
    fixtures (used throughout tests/test_e2e_pipeline.py): MagicMock
    auto-vivifies any accessed attribute instead of raising AttributeError,
    so the getattr default is never reached and resolve_mapper() gets a
    MagicMock instead of a mapper name. Real CLI usage never hits this --
    argparse's `choices=` and the default pipeline's SimpleArgs both always
    set a valid string -- so falling back to 'mmc3' for anything else is
    safe, not a silent typo swallow.
    """
    value = getattr(args, 'mapper', 'mmc3')
    return value if isinstance(value, str) else 'mmc3'


def _backup_existing_rom(output_rom):
    """Back up a pre-existing ROM at output_rom before it gets overwritten
    (#178/PL-05), shared by the full pipeline and the `compile` subcommand so
    both get the same restore-on-failure contract.

    Returns the backup path, or None if there was nothing at output_rom yet.
    """
    output_rom = Path(output_rom)
    if not output_rom.exists():
        return None
    backup_path = output_rom.with_suffix('.nes.backup')
    print(f"  💾 Creating backup of existing ROM: {backup_path.name}")
    shutil.copy2(output_rom, backup_path)
    return backup_path


def _restore_backup(output_rom, backup_path):
    """Restore a pre-build backup ROM over the (now-invalid) output. If there
    was no pre-existing ROM to restore, move the freshly written unbootable
    ROM aside instead of leaving a broken .nes at the output path (#178/PL-05)."""
    output_rom = Path(output_rom)
    if backup_path and Path(backup_path).exists():
        print(f"  💊 Restoring backup ROM: {Path(backup_path).name} → {output_rom.name}")
        shutil.copy2(backup_path, output_rom)
        print(f"  ✅ Original ROM restored from backup")
    elif output_rom.exists():
        failed_path = Path(str(output_rom) + '.failed')
        print(f"  🗑️  Moving unbootable ROM aside: {output_rom.name} → {failed_path.name}")
        output_rom.replace(failed_path)


def validate_rom(output_rom):
    """Post-build ROM validation shared by the full pipeline and the `compile`
    subcommand (#15) so step-by-step ROMs get the same gate as the default path.

    Returns True if the ROM is bootable. On a boot-fatal defect (invalid
    $FFFA-$FFFF vectors or no APU init) it returns False — the caller owns backup
    restore (#26). Non-fatal health issues are warned but pass. A diagnostics
    engine failure (e.g. a broken `debug` import) is treated as a validation
    failure (#177/PL-04): callers only reach this function when the user did
    NOT pass --skip-validation, so silently accepting the ROM here would defeat
    the one gate that catches unbootable ROMs. The warning always prints, not
    just under --verbose, so a skipped validation is never silent.
    """
    try:
        from debug.rom_diagnostics import ROMDiagnostics
        rom_result = ROMDiagnostics(verbose=False).diagnose_rom(str(output_rom))
    except Exception as e:
        print(f"  ⚠️  Warning: ROM validation could not run: {e} — ROM NOT validated")
        return False

    fatal_defects = []
    if not rom_result.reset_vectors_valid:
        fatal_defects.append("invalid reset/NMI/IRQ vectors ($FFFA-$FFFF)")
    if rom_result.apu_pattern_count == 0:
        fatal_defects.append("no APU initialization code found")
    if fatal_defects:
        print("[ERROR] ROM validation failed - unbootable ROM:")
        for defect in fatal_defects:
            print(f"    - {defect}")
        return False

    if rom_result.overall_health not in ["HEALTHY", "GOOD"]:
        print(f"⚠️  ROM health check: {rom_result.overall_health}")
        print(f"  Issues found: {len(rom_result.issues)}")
        for issue in rom_result.issues[:3]:
            print(f"    - {issue}")
        if rom_result.overall_health == "ERROR":
            print("[ERROR] ROM validation failed - ROM is invalid")
            return False
    else:
        print(f"  ✓ ROM Health: {rom_result.overall_health}")
        print(f"  ✓ APU Patterns: {rom_result.apu_pattern_count}")
        print(f"  ✓ Assembly Score: {rom_result.assembly_code_score}/220")
    return True


def _reject_debug_visualizer_combo(args):
    """--debug and --visualizer both write into the ROM's nametable/CHR-RAM,
    but neither knows about the other: --debug never enables PPUMASK itself
    (nes/debug_overlay.py), and --visualizer's small CHR tile set would leave
    --debug's ASCII-as-tile-index text reading as garbage tiles once
    rendering is turned on. Reject the combination up front with a clear
    message instead of silently building a confusing, half-working ROM.
    """
    if getattr(args, 'debug', False) and getattr(args, 'visualizer', False):
        print("[ERROR] --debug and --visualizer cannot be combined yet -- "
              "both draw into the same on-screen nametable/CHR-RAM region. "
              "Use one or the other.", file=sys.stderr)
        sys.exit(2)


def run_compile(args):
    """Compile a prepared NES project to a ROM and validate it (#15).

    Gives the step-by-step path the same compile + post-build validation the
    full pipeline runs, instead of stopping at `prepare` and building by hand.
    Also gives it the same backup/restore contract as the default pipeline
    (#178/PL-05): a pre-existing output ROM is backed up before compiling and
    restored if compilation or validation fails; a first-time build that fails
    validation has its unbootable ROM moved aside (`<name>.nes.failed`)
    instead of being left at the output path.
    """
    project_path = Path(args.input)
    output_rom = Path(args.output)
    if not project_path.is_dir():
        print(f"[ERROR] Prepared project directory not found: {project_path}")
        sys.exit(1)

    # The exact-size check (#28/M-8) and post-process step need the same mapper
    # the project was actually prepared with (#217/MAP-6). `prepare` stamps that
    # mapper into nes.cfg, so recover it from there authoritatively -- a marker-
    # less NROM/MMC1 music.asm would otherwise fall to the mmc3 default and be
    # rejected with a misleading size mismatch (#297/MAP-2026-07-06-1). This
    # also gives a `prepare --mapper auto` project a working compile (#269).
    # Fall back to --mapper (default mmc3) for older projects with no marker.
    # music.asm is still passed so resolve_mapper can catch a mapper that can't
    # run this project's bytecode engine.
    cfg_mapper = _prepared_mapper_name_from_cfg(project_path / "nes.cfg")
    mapper_choice = cfg_mapper if cfg_mapper else get_mapper_choice(args)
    try:
        mapper = resolve_mapper(mapper_choice, str(project_path / "music.asm"))
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    backup_path = _backup_existing_rom(output_rom)
    build_succeeded = False
    try:
        print(f"Compiling NES ROM from {project_path} ...")
        if not compile_rom(project_path, output_rom, verbose=getattr(args, 'verbose', False), mapper=mapper):
            print("[ERROR] ROM compilation failed")
            sys.exit(1)

        if not getattr(args, 'skip_validation', False):
            print("Validating ROM...")
            if not validate_rom(output_rom):
                sys.exit(1)

        build_succeeded = True
        print(f"[OK] Compiled ROM -> {output_rom}")
    finally:
        if not build_succeeded:
            _restore_backup(output_rom, backup_path)
        elif backup_path:
            backup_path.unlink(missing_ok=True)


def run_prepare(args):
    # --mapper (#217/MAP-6): 'auto' picks the smallest mapper that fits this
    # song's data via MapperFactory.auto_select(), previously reachable only
    # from tests/test_mappers.py. Defaults to mmc3, matching prior behavior
    # for callers who don't pass --mapper.
    try:
        mapper = resolve_mapper(get_mapper_choice(args), args.input)
        data_size = check_mapper_capacity(args.input, mapper)
        print(f"  ✓ Music data {data_size:,} bytes fits the {mapper.name} PRG regions")
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    # Honor --debug/--visualizer on the step-by-step `prepare` path the same
    # way the default pipeline does, instead of silently building a ROM
    # without them (#175).
    builder = NESProjectBuilder(args.output, debug_mode=getattr(args, 'debug', False),
                                 mapper=mapper, visualizer_mode=getattr(args, 'visualizer', False))
    # prepare_project may raise (bad path/permissions) or return falsy; either
    # way surface a clean nonzero exit instead of an uncaught traceback or a
    # silent exit 0 on failure (#15).
    try:
        prepared = builder.prepare_project(args.input)
    except Exception as e:
        print(f"[ERROR] Failed to prepare NES project: {e}")
        sys.exit(1)
    if not prepared:
        print("[ERROR] Failed to prepare NES project")
        sys.exit(1)
    print(f" Prepared NES project -> {args.output}")
    print(" Ready for CC65 compilation!")
    print(" To build:")
    print(f" 1. cd {args.output}")
    print(" 2. ./build.sh  (or build.bat on Windows)")
    print(" Or compile + validate in one step: python main.py compile "
          f"{args.output} <output.nes>")

def run_export(args):
    """Export function supporting multiple formats with pattern compression"""
    # Guard against a missing/corrupt file (#120); the frames JSON's channel
    # keys are all optional, so there is no fixed required key to validate
    # -- channel_shape=True instead rejects a non-empty file with none of
    # them at all, e.g. a wrong-stage file (#485/PIPE-2026-08-22-1).
    frames = load_json_stage(args.input, [], 'frames', channel_shape=True)

    # Check if we have pattern data
    pattern_data = None
    if args.patterns:
        # detect-patterns always writes 'patterns'/'references'; a wrong-stage
        # file here used to raise a raw KeyError below instead of this clear
        # message (#120).
        pattern_data = load_json_stage(args.patterns, ['patterns', 'references'], 'detect-patterns')

    # NOTE: `nsf` was removed from --format until the NSF exporter produces a
    # playable file (#81/EXP-05). The old `if args.format == "nsftxt"` branch
    # dispatched on a string argparse never allowed, so `--format nsf` silently
    # wrote nothing (#79). With `ca65` the only choice, argparse now rejects an
    # nsf request up front instead of no-oping; re-add the branch here when NSF
    # is real.
    if args.format == "ca65":
        # Always use CA65Exporter, with empty patterns if none provided
        if pattern_data:
            patterns = pattern_data['patterns']
            references = pattern_data['references']
        else:
            patterns = {}
            references = {}

        exporter = CA65Exporter()

        # Resolve --mapper BEFORE exporting when this is a direct (no
        # patterns) export -- a bank-switching-aware export (MMC1,
        # #255/MAP-2026-07-05-1) must know the target mapper up front to
        # bin-pack frame tables and emit bank-switches. An empty `patterns`
        # dict falls through to direct export the same way
        # export_tables_with_patterns itself dispatches on it, even if
        # --patterns was passed but yielded no patterns.
        mapper = None
        if not patterns:
            from mappers.factory import MapperFactory
            mapper_choice = get_mapper_choice(args)
            try:
                if mapper_choice == 'auto':
                    estimated_size = exporter.estimate_direct_export_size(frames)
                    mapper = MapperFactory.auto_select(estimated_size, direct=True)
                else:
                    mapper = MapperFactory.get_mapper(mapper_choice)
                # Direct-export DPCM is MMC3-only: force MMC3 for 'auto', reject
                # an explicit non-MMC3 mapper (#281/#282).
                mapper = enforce_direct_export_dpcm_mapper(mapper, mapper_choice, frames)
            except ValueError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)

        exporter.export_tables_with_patterns(
            frames,
            patterns,
            references,
            args.output,
            standalone=False,  # Don't include header and vectors for project builder
            mapper=mapper,
            visualizer=getattr(args, 'visualizer', False)
        )

        # Pack DPCM samples for exported ASM (#380/TD-28: extracted helper
        # shared with run_full_pipeline, so a fix to one path can't
        # silently miss the other).
        pack_result = pack_dpcm_into_asm(
            frames, args.output, verbose=getattr(args, 'verbose', False))
        dpcm_pack_warning = pack_result.warning

        print(f" Exported CA65 ASM -> {args.output}")
        if not pack_result.index_found:
            # A missing dpcm_index.json used to print nothing at all here --
            # `if dpcm_pack_warning:` below is None in this case, so a song
            # with percussion silently lost its drums with zero feedback,
            # unlike run_full_pipeline's explicit index_found branch
            # (#411/SAFE-2026-08-06-1). Same wording as that sibling branch.
            print("   ℹ️ No dpcm_index.json found, skipping DPCM packing.")
        elif dpcm_pack_warning:
            # "NO DRUMS" only actually describes the all-missing case
            # (loaded_samples == 0); a partial miss (#367/DP-DPCM-05) still
            # has *some* drums, so labeling it "NO DRUMS" would misdescribe
            # the very warning meant to make the drop visible.
            label = "NO DRUMS" if pack_result.loaded_samples == 0 else "PARTIAL DPCM MISS"
            print(f"   ⚠️  {label}: {dpcm_pack_warning}")

def run_detect_patterns(args):
    # Guard against a missing/corrupt file (#120); the frames JSON's channel
    # keys are all optional, so there is no fixed required key to validate
    # -- channel_shape=True instead rejects a non-empty file with none of
    # them at all, e.g. a wrong-stage file (#485/PIPE-2026-08-22-1).
    frames = load_json_stage(args.input, [], 'frames', channel_shape=True)

    # Sequential detector's event cap, optionally overridden by --config (#219).
    max_events, _, _ = get_pattern_detection_caps(getattr(args, 'config', None))

    # Create tempo map and pattern detector. tempo_map is a required
    # constructor arg but carries no real tempo-change data here (the events
    # below are already-quantized frame positions, not MIDI ticks), so its
    # per-pattern tempo analysis would only produce a discarded constant
    # result — skip it (analyze_tempo=False) rather than pay for it (#119).
    # #376/PERF-A-06 (won't-fix): this always defaults to ticks_per_beat=480
    # rather than the source file's actual resolution, since parse_midi_to_frames
    # returns an empty `metadata` by design and this stage only has `frames`
    # (no MIDI ticks) to work from. Threading the real value through would
    # require widening the parse-stage JSON contract for a value
    # analyze_tempo=False never reads (EnhancedPatternDetector only touches
    # tempo_map when analyze_tempo is True) -- not worth the contract churn.
    tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM default
    detector = EnhancedPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH,
                                       max_pattern_length=PATTERN_MAX_LENGTH,
                                       max_events=max_events, analyze_tempo=False)

    # Extract events from frames structure (shared extractor skips the
    # dpcm_sample_map side table and returns them frame-sorted — #261).
    events = frames_to_events(frames)
    # This subcommand only emits patterns, never a ROM, so `frames` (the largest
    # structure) is dead once events are extracted. Free it before detection
    # rather than holding it alongside the detector's working copies (#115/PERF-04).
    del frames

    # This subcommand runs the sequential EnhancedPatternDetector, whose internal
    # cap is max_events (DETECTOR_MAX_EVENTS unless overridden). Sample uniformly
    # straight to that limit so the warning reports the count the detector
    # actually retains, instead of a larger figure the detector would silently
    # re-sample away (#100, #21).
    original_count = len(events)
    events, was_sampled = sample_events_for_detection(events, max_events)
    if was_sampled:
        print(f"⚠️  Large file ({original_count} events): sampled to {len(events)} "
              f"({len(events)/original_count*100:.1f}%, lossy) before pattern detection")

    # Detect patterns
    pattern_result = detector.detect_patterns(events)
    
    # Save compressed patterns
    output = {
        'patterns': pattern_result['patterns'],
        'references': pattern_result['references'],
        'stats': pattern_result['stats']
    }
    Path(args.output).write_text(json.dumps(output, separators=(',', ':')))
    print(f" Detected patterns -> {args.output}")
    # compression_ratio is a dedup ratio within the patterned subset only, not
    # a measure of the whole song (#169/PAT-03) -- the coverage line says what
    # fraction of the song that subset actually is.
    print(f" Pattern dedup ratio: {pattern_result['stats']['compression_ratio']:.1f}% "
          f"reduction (patterned subset only)")
    coverage_note = ""
    if was_sampled:
        # Uniform sampling can put retained samples out of phase with the
        # song's period, collapsing coverage_ratio well below what the full
        # song would report (#312/PAT-11) -- label it so the number isn't
        # read as a property of the full song.
        coverage_note = " (lossy — measured over the sampled subset, detection quality reduced)"
    print(f" Pattern coverage: {pattern_result['stats']['coverage_ratio']:.1f}% of "
          f"{pattern_result['stats']['total_events']:,} events matched a detected pattern{coverage_note}")

def run_song_add(args):
    """Add a song to the song bank"""
    bank = SongBank()

    # Load existing bank if specified. Guards a corrupt/malformed --bank file
    # (#220/SAFE-09) -- the same defect class SAFE-01/#120 fixed for the
    # pipeline subcommands, extended here to the song-bank family.
    if args.bank and Path(args.bank).exists():
        try:
            bank.import_bank(args.bank)
        except Exception as e:
            print(f"[ERROR] Failed to load song bank: {e}")
            sys.exit(1)

    # Prepare metadata
    metadata = {
        'composer': args.composer,
        'loop_point': args.loop_point,
        'tags': args.tags.split(',') if args.tags else [],
        'tempo_base': args.tempo
    }
    
    # Add song to bank. A corrupt/missing MIDI (InvalidMIDIError/
    # FileNotFoundError, tracker/parser_fast.py), a duplicate song name, or
    # a full bank (both bare ValueError, nes/song_bank.py's add_song) used
    # to escape as a raw traceback -- every sibling subcommand converts its
    # documented failure modes to a clean [ERROR] + exit 1 (#455/
    # SAFE-2026-08-21-1), matching the --bank load guard three lines above.
    try:
        bank.add_song_from_midi(args.input, args.name, metadata)

        # Save bank
        output_path = args.bank or 'song_bank.json'
        bank.export_bank(output_path)
    except (MIDI2NESError, FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    print(f"Song added to bank: {output_path}")

def run_song_list(args):
    """List songs in the song bank"""
    if not Path(args.bank).exists():
        print(f"Error: Song bank file not found: {args.bank}")
        return

    bank = SongBank()
    try:
        bank.import_bank(args.bank)
    except Exception as e:
        print(f"[ERROR] Failed to load song bank: {e}")
        sys.exit(1)

    print("\nSongs in bank:")
    print("-" * 50)
    for name, song_data in bank.songs.items():
        metadata = song_data['metadata']
        print(f"Title: {name}")
        if metadata.get('composer'):
            print(f"Composer: {metadata['composer']}")
        if metadata.get('tags'):
            print(f"Tags: {', '.join(metadata['tags'])}")
        if metadata.get('loop_point') is not None:
            print(f"Loop point: {metadata['loop_point']}")
        print(f"Bank: {song_data['bank']}")
        print("-" * 50)

def run_song_remove(args):
    """Remove a song from the bank"""
    if not Path(args.bank).exists():
        print(f"Error: Song bank file not found: {args.bank}")
        return

    bank = SongBank()
    try:
        bank.import_bank(args.bank)
    except Exception as e:
        print(f"[ERROR] Failed to load song bank: {e}")
        sys.exit(1)

    if args.name not in bank.songs:
        print(f"Error: Song '{args.name}' not found in bank")
        return
    
    del bank.songs[args.name]
    bank.export_bank(args.bank)
    print(f"Song '{args.name}' removed from bank")


def midi_to_frames_for_song(midi_path, use_arranger, dpcm_index_path='dpcm_index.json', verbose=False):
    """Parse one MIDI file into NES-mapped frames for a `song build` (#30/F-13).

    Mirrors run_full_pipeline's inline parse -> map/arrange steps (its
    steps 1-3), but as a standalone callable a multi-song build can invoke
    once per song. Deliberately NOT extracted from run_full_pipeline itself:
    that function's `del midi_data`/`del mapped` calls are pinned in place by
    a memory-optimization test contract (see the stage-helpers comment block
    above `detect_patterns_or_direct_export`), so this is a separate, small
    function rather than a refactor of that path.

    Raises FileNotFoundError (legacy/non-arranger mode only) if
    `dpcm_index_path` doesn't exist, matching run_full_pipeline's own
    requirement -- assign_tracks_to_nes_channels needs it unconditionally,
    even for a song with no drums.
    """
    from tracker.parser_fast import parse_midi_to_frames as parse_fast
    midi_data = parse_fast(str(midi_path))

    if use_arranger:
        return arrange_for_nes(midi_data["events"], arp_speed=3, verbose=verbose)

    if not Path(dpcm_index_path).exists():
        raise FileNotFoundError(
            f"DPCM index not found: {dpcm_index_path} (pass --dpcm-index <path>, "
            f"or restore dpcm_index.json) -- required for legacy (non-arranger) mapping"
        )
    mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
    emulator = NESEmulatorCore()
    return emulator.process_all_tracks(mapped)


def _song_has_dpcm_events(frames):
    """True if `frames['dpcm']` contains a real (non-silent) drum hit.

    `song build` doesn't support DPCM in v1 (#30/F-13, see docs/ROADMAP.md),
    so callers use this to reject a song with a clear error instead of
    silently producing a ROM with a broken/colliding DPCM bank pool (each
    song's sequence bytecode already claims its own fresh bank range, but
    DPCM sample packing -- excluded here -- would need the same treatment
    and doesn't have it yet).
    """
    dpcm_frames = frames.get('dpcm') or {}
    return any(
        (frame_data or {}).get('note', 0) and (frame_data or {}).get('volume', 0)
        for frame_data in dpcm_frames.values()
    )


def run_song_build(args):
    """Build a multi-song 'jukebox' ROM from a song bank (#30/F-13).

    v1 scope: MMC3 only, no DPCM/drums, no --debug overlay, no pattern
    detection (bytecode compression already comes from macro/instrument
    dedup, not the detector -- see CLAUDE.md). See docs/ROADMAP.md for the
    documented cuts and planned follow-ups.
    """
    bank_path = Path(args.bank)
    if not bank_path.exists():
        print(f"Error: Song bank file not found: {bank_path}")
        sys.exit(1)

    bank = SongBank()
    try:
        bank.import_bank(str(bank_path))
    except Exception as e:
        print(f"[ERROR] Failed to load song bank: {e}")
        sys.exit(1)

    if not bank.songs:
        print("[ERROR] Song bank is empty -- nothing to build")
        sys.exit(1)

    # metadata['order'] was recorded at `song add` time but never consumed
    # by anything until now -- this is what finally gives it a purpose.
    ordered_names = sorted(
        bank.songs, key=lambda name: bank.songs[name]['metadata'].get('order', 0))

    use_arranger = getattr(args, 'arranger', False)
    dpcm_index_path = getattr(args, 'dpcm_index', None) or 'dpcm_index.json'
    verbose = getattr(args, 'verbose', False)

    songs = []
    for name in ordered_names:
        song_data = bank.songs[name]
        midi_path = song_data.get('midi_path')
        if not midi_path:
            print(f"[ERROR] Song '{name}' has no recorded source MIDI -- "
                  f"re-add it with 'song add' to build it.")
            sys.exit(1)
        if not Path(midi_path).exists():
            print(f"[ERROR] Song '{name}' source MIDI not found: {midi_path}")
            sys.exit(1)

        print(f"  Parsing '{name}' ({midi_path})...")
        try:
            frames = midi_to_frames_for_song(
                midi_path, use_arranger, dpcm_index_path=dpcm_index_path, verbose=verbose)
        except FileNotFoundError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)

        if _song_has_dpcm_events(frames):
            print(f"[ERROR] Song '{name}' contains DPCM drum samples -- "
                  f"'song build' does not support DPCM in multi-song ROMs yet "
                  f"(see docs/ROADMAP.md). Remove drums or build this song "
                  f"individually with the normal pipeline.")
            sys.exit(1)

        songs.append({'frames': frames})

    output_rom = Path(args.output)
    skip_validation = getattr(args, 'skip_validation', False)

    # Backup/restore + typed-exception contract (#486/PIPE-2026-08-22-2,
    # #467/TD-32): this build used to re-implement the capacity->prepare->
    # compile->validate sequence with its own per-step sys.exit(1) calls and
    # no backup of a pre-existing ROM -- a re-build that compiled but failed
    # validation left the broken ROM at output_rom with no way back, and any
    # exception out of prepare_project surfaced as a raw traceback instead of
    # a clean [ERROR]. Reusing build_and_validate_rom (the same helper
    # run_full_pipeline calls) gives this path the exact contract the other
    # two ROM-build entry points (run_full_pipeline, run_compile) already
    # have, instead of a third, drifted copy.
    backup_path = _backup_existing_rom(output_rom)
    build_succeeded = False
    try:
        with tempfile.TemporaryDirectory(prefix="midi2nes_") as temp_dir:
            temp_path = Path(temp_dir)
            music_asm = temp_path / "music.asm"

            exporter = CA65Exporter()
            try:
                exporter.export_song_bank_bytecode(songs, str(music_asm))
            except ValueError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)

            from mappers.factory import MapperFactory
            mapper = MapperFactory.get_mapper('mmc3')

            project_path = temp_path / "nes_project"
            print(f"🔨 Compiling {len(songs)}-song jukebox ROM...")
            build_and_validate_rom(
                mapper, music_asm, project_path, output_rom,
                debug_mode=False, skip_validation=skip_validation, args=args,
                song_count=len(songs))

        build_succeeded = True
        print(f"✅ Jukebox ROM built: {output_rom} ({len(songs)} songs)")
    except MIDI2NESError as e:
        print(f"[ERROR] {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected failure building jukebox ROM: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    finally:
        if not build_succeeded:
            _restore_backup(output_rom, backup_path)
        elif backup_path:
            backup_path.unlink(missing_ok=True)


def load_config(config_path: Optional[str] = None) -> DrumMapperConfig:
    """Load drum mapper configuration from file or use defaults"""
    if config_path:
        if not Path(config_path).exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")
        return DrumMapperConfig.from_file(config_path)
    return DrumMapperConfig()


# =============================================================================
# run_full_pipeline stage helpers (#406/TD-11-FOLLOWUP)
# =============================================================================
#
# These three functions extract run_full_pipeline's three most self-contained
# stages -- the ones with real inline logic worth testing in isolation, not
# just a call-through to an already-separate subsystem class. Steps 1-3
# (parse + map/arrange + frame generation) deliberately stay inline in
# run_full_pipeline itself: the `del midi_data` / `del mapped` calls that trim
# peak memory between them (#371/PERF-A-01, pinned by
# TestRunFullPipelineMemoryOverhead's source-inspection tests) only free
# anything if they execute in the same frame that holds the last reference --
# moving that code into a callee would silently break the memory contract
# without changing behavior in an obviously-visible way, so it isn't worth
# the risk for stages that are already short, mostly straight-line branching.
#
# Each helper below raises on failure instead of calling sys.exit itself.
# run_full_pipeline's single existing try/except/finally is the one and only
# place that decides how to report an error and whether to restore a backup
# (#26) -- these helpers don't need to know that policy exists.

def detect_patterns_or_direct_export(frames, use_patterns, args):
    """Step 4: run pattern detection for compression, or build the
    unpatterned direct-export stats stub.

    Returns (pattern_result, pattern_loss_warning, coverage_lossy_note).
    pattern_loss_warning is set when the sequential fallback had to sample
    events down for compression analysis only (#176/PL-03) --  every
    emitted ROM byte still derives from the full `frames` dict regardless.
    coverage_lossy_note is a short banner suffix for the same reason
    (#312/PAT-11).
    """
    pattern_loss_warning = None
    coverage_lossy_note = ""

    if not use_patterns:
        print("[4/7] Skipping pattern detection (direct export mode)...")
        print(f"  📊 Processing direct frame export for complete data preservation")
        # Dummy pattern result for direct export. The stats must use the SAME
        # schema the detectors emit (original_size/compressed_size/
        # compression_ratio/unique_patterns/total_events/patterned_events/
        # coverage_ratio) so any consumer sees one shape regardless of path
        # (#104). Direct export applies no pattern compression, so ratio is
        # 0% reduction (#17) and coverage is 0% -- nothing is patterned
        # (#169/PAT-03).
        # Use the same frames->events extractor the real detectors call so the
        # stub's counts stay value-equivalent to what they'd report for this
        # frames dict (#104) -- a plain frames.values() sweep would double-count
        # the non-channel dpcm_sample_map side table as events (#200/D-14, #261).
        direct_size = len(frames_to_events(frames))
        pattern_result = {
            'patterns': {},
            'references': {},
            'stats': {
                'original_size': direct_size,
                'compressed_size': direct_size,
                'compression_ratio': 0,
                'unique_patterns': 0,
                'total_events': direct_size,
                'patterned_events': 0,
                'coverage_ratio': 0
            },
            # Match the 4-key top-level envelope both detectors emit so a
            # consumer doing pattern_result['variations'] can't KeyError only
            # on the --no-patterns path (#258/PAT-09).
            'variations': {}
        }
        return pattern_result, pattern_loss_warning, coverage_lossy_note

    print("[4/7] Detecting patterns for compression...")
    # Analysis-only tempo map (#98/TEMPO-06): the detector requires a
    # tempo_map constructor arg, but the events below are already
    # frame-indexed (tempo was applied upstream), so this map carries no real
    # tempo changes and the default ticks_per_beat is irrelevant. Mirrors the
    # documented construction in run_detect_patterns (#119).
    # #376/PERF-A-06 (won't-fix, mirrors run_detect_patterns above): the
    # `mapped`/`midi_data` this song's real events came from are already
    # `del`eted by this point (#371/PERF-A-01's deliberate early free), so
    # there is nothing left here to derive a real tempo map or a pre-frame
    # event list from without reversing that memory-freeing on purpose.
    tempo_map = EnhancedTempoMap(initial_tempo=500000)

    # Convert frames to events for pattern detection (shared extractor skips
    # the dpcm_sample_map side table -- #261).
    events = frames_to_events(frames)

    # Sampling caps + advisory large-file threshold, optionally overridden in
    # lockstep by --config (#219, #334/PERF-14).
    max_events, max_pattern_events, large_file_threshold = get_pattern_detection_caps(
        getattr(args, 'config', None))

    # Heads-up only -- does not alter detection (that's what
    # max_pattern_events actually caps).
    if len(events) > large_file_threshold:
        print(f"  ⚠️  Large MIDI file ({len(events):,} events) detected")
        print(f"  🚀 Proceeding with improved pattern detection...")

    # Use parallel pattern detection with position mapping fix
    fallback_sampled = False
    try:
        from tracker.pattern_detector_parallel import ParallelPatternDetector
        detector = ParallelPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH, max_pattern_length=PATTERN_MAX_LENGTH, max_pattern_events=max_pattern_events)
        print(f"  Using parallel pattern detection with {len(events):,} events")
        pattern_result = detector.detect_patterns(events)
    except Exception as e:
        print(f"  Parallel detection failed, using fallback: {e}")
        from tracker.pattern_detector import EnhancedPatternDetector
        # tempo_map here has no real tempo-change data for the same reason as
        # run_detect_patterns's fallback (#119).
        detector = EnhancedPatternDetector(tempo_map, min_pattern_length=PATTERN_MIN_LENGTH, max_pattern_length=PATTERN_MAX_LENGTH, max_events=max_events, analyze_tempo=False)
        # Sequential fallback can only handle the detector's internal cap, so
        # sample uniformly straight to max_events. This keeps song structure
        # (not a head cut) AND makes the warning below report the count
        # actually retained, not a larger sample the detector would silently
        # re-cut (#100).
        fallback_count = len(events)
        events, fallback_sampled = sample_events_for_detection(events, max_events)
        if fallback_sampled:
            pattern_loss_warning = (
                f"pattern detection fell back to the sequential detector and "
                f"sampled {fallback_count:,} events down to {len(events):,} for "
                f"compression analysis only — compression stats are approximate; "
                f"ROM content is unaffected (#176/PL-03)."
            )
            print(f"  ⚠️  NOTE: {pattern_loss_warning}")
        pattern_result = detector.detect_patterns(events)
        # events is already sampled to the detector's cap by the time it
        # reaches detect_patterns, so the detector's own internal re-sample
        # (tracker/pattern_detector.py) is a no-op and detector.was_sampled
        # stays False -- checking only that flag below used to silently drop
        # the "(lossy...)" coverage suffix even though coverage genuinely was
        # computed over this sampled subset (#378/PIPE-2026-07-19-2).

    if detector.was_sampled or fallback_sampled:
        # Uniform sampling can put retained samples out of phase with the
        # song's period, collapsing coverage_ratio well below what the full
        # song would report (#312/PAT-11) -- label it so the number isn't
        # read as a property of the full song.
        coverage_lossy_note = (
            " (lossy — measured over the sampled subset, "
            "detection quality reduced)"
        )

    return pattern_result, pattern_loss_warning, coverage_lossy_note


def export_frames_and_resolve_mapper(frames, pattern_result, music_asm, use_patterns, args):
    """Steps 5-5.5: export frames to CA65 assembly, pack DPCM samples, and
    resolve the target --mapper.

    Mapper resolution timing genuinely differs by path: a direct-export
    (bank-switching-aware) build must know its mapper *before* exporting so
    frame tables can be bin-packed and bank-switches emitted
    (#255/MAP-2026-07-05-1); the patterned/macro-bytecode path is always
    forced to MMC3 regardless of choice, so it's cheaper (and matches the
    prior behavior) to resolve it *after* export, from the written
    music.asm's size. Both orderings converge here so run_full_pipeline's
    orchestration doesn't need to know the difference.

    Raises ValueError on an invalid or oversized mapper choice.

    Returns (mapper, pack_result).
    """
    print("[5/7] Exporting to CA65 assembly...")
    exporter = CA65Exporter()

    mapper = None
    if not use_patterns:
        from mappers.factory import MapperFactory
        mapper_choice = get_mapper_choice(args)
        if mapper_choice == 'auto':
            estimated_size = exporter.estimate_direct_export_size(frames)
            mapper = MapperFactory.auto_select(estimated_size, direct=True)
        else:
            mapper = MapperFactory.get_mapper(mapper_choice)
        # Direct-export DPCM is MMC3-only: force MMC3 for 'auto', reject an
        # explicit non-MMC3 mapper (#281/#282).
        mapper = enforce_direct_export_dpcm_mapper(mapper, mapper_choice, frames)

    # The CA65 exporter emits every byte from `frames`; the detector's
    # pattern `references` are analysis/metrics only and are never read by
    # export_tables_with_patterns (#4). `patterns` truthiness merely selects
    # the macro-bytecode serializer over direct export -- `references` has no
    # effect on emitted bytes either way, but pass the real dict (mirroring
    # run_export, #379/PIPE-2026-07-19-3) rather than a hardcoded `{}` so the
    # two entry points stay forward-compatible if `references` is ever wired
    # up to affect output.
    exporter.export_tables_with_patterns(
        frames,
        pattern_result['patterns'],
        pattern_result['references'],
        str(music_asm),
        standalone=False,  # We'll create our own project structure
        mapper=mapper,
        visualizer=getattr(args, 'visualizer', False)
    )

    # Pack DPCM samples (#380/TD-28: extracted helper shared with run_export,
    # so a fix to one path can't silently miss the other).
    print("[5.5/7] Packing DPCM samples...")
    pack_result = pack_dpcm_into_asm(frames, music_asm, verbose=args.verbose)

    if not pack_result.index_found:
        print("  ℹ️ No dpcm_index.json found, skipping DPCM packing.")
    elif pack_result.warning:
        print(f"  ⚠️ Warning: {pack_result.warning}")
        if args.verbose and pack_result.traceback_text:
            print(pack_result.traceback_text)
    elif pack_result.loaded_samples > 0:
        print(f"  ✓ Packed {pack_result.loaded_samples} DPCM samples "
              f"across {pack_result.bank_count} banks")
    else:
        print("  ℹ️ No DPCM samples referenced by this song.")

    # --mapper (#217/MAP-6): 'auto' picks the smallest mapper that fits this
    # song's data via MapperFactory.auto_select(), previously reachable only
    # from tests/test_mappers.py. Defaults to mmc3, matching prior hardcoded
    # behavior for callers who don't pass --mapper. Already resolved above
    # for a direct-export build (#255/MAP-2026-07-05-1); only the
    # bytecode/pattern path (always forced to MMC3) still resolves here,
    # after export.
    if mapper is None:
        mapper = resolve_mapper(get_mapper_choice(args), str(music_asm))

    return mapper, pack_result


def build_and_validate_rom(mapper, music_asm, project_path, output_rom,
                            debug_mode, skip_validation, args, song_count=None,
                            visualizer_mode=False):
    """Steps 6-8: PRG capacity pre-flight, NES project prep, ROM compile,
    and (unless skipped) ROM validation.

    Raises MapperError (capacity -- also a ValueError, #457/
    SAFE-2026-08-21-3), ExportError (prepare), CompilationError (compile), or
    ValidationError (validate) on failure -- all MIDI2NESError subclasses, so
    a caller's single try/except/finally can decide how to report it and
    whether to restore a backup (#26) via one `except MIDI2NESError` clause
    instead of missing these as "unexpected" (bare RuntimeError used to fall
    through to that branch). Shared by run_full_pipeline and run_song_build
    (#486/PIPE-2026-08-22-2, #467/TD-32) -- both get the same backup/restore
    and typed-exception contract instead of each re-implementing it.

    `song_count` is forwarded to `prepare_project` unchanged (None for a
    single-song build, matching prior behavior; an int for a jukebox build,
    which defines JUKEBOX_BUILD -- nes/project_builder.py).

    Returns the music.asm data size in bytes (post capacity check).
    """
    # Capacity pre-flight (#11): catch an oversized song with a clear message
    # before ld65 reports a raw region overflow.
    data_size = check_mapper_capacity(str(music_asm), mapper)
    print(f"  ✓ Music data {data_size:,} bytes fits the {mapper.name} PRG regions")

    print("[6/7] Preparing NES project...")
    builder = NESProjectBuilder(str(project_path), debug_mode=debug_mode, mapper=mapper,
                                 visualizer_mode=visualizer_mode)
    if not builder.prepare_project(str(music_asm), song_count=song_count):
        # Matches prepare_project's own ExportError type for its other
        # failure mode (missing audio_engine.asm, nes/project_builder.py).
        raise ExportError("Failed to prepare NES project")

    print("[7/7] Compiling NES ROM...")
    if not compile_rom(project_path, output_rom, verbose=args.verbose, mapper=mapper):
        raise CompilationError("ROM compilation failed")

    if not skip_validation:
        print("[8/8] Validating ROM...")
        if not validate_rom(output_rom):
            raise ValidationError("ROM validation failed")

    return data_size


def run_full_pipeline(args):
    """Run the complete MIDI to NES ROM pipeline"""
    input_midi = Path(args.input)
    if not input_midi.exists():
        print(f"[ERROR] Input MIDI file not found: {input_midi}")
        sys.exit(1)
    
    # Determine output ROM path
    if hasattr(args, 'output') and args.output:
        output_rom = Path(args.output)
    else:
        output_rom = input_midi.with_suffix('.nes')
    
    # Create backup if output ROM already exists
    backup_path = _backup_existing_rom(output_rom)
    
    # Check for no-patterns flag
    use_patterns = not (hasattr(args, 'no_patterns') and args.no_patterns)
    
    print(f"🎵 MIDI2NES Pipeline: {input_midi.name} → {output_rom.name}")
    if not use_patterns:
        print("   🔄 Direct export mode (no pattern compression)")
    print("=" * 60)
    
    # Create temporary directory for intermediate files
    build_succeeded = False
    with tempfile.TemporaryDirectory(prefix="midi2nes_") as temp_dir:
        temp_path = Path(temp_dir)

        try:
            # Step 1: Parse MIDI to frames (using fast parser)
            print("[1/7] Parsing MIDI file...")
            from tracker.parser_fast import parse_midi_to_frames as parse_fast
            midi_data = parse_fast(str(input_midi))

            # Check for arranger mode
            use_arranger = hasattr(args, 'arranger') and args.arranger

            if use_arranger:
                # Step 2+3: Use intelligent arranger with arpeggiation
                print("[2/7] Analyzing musical structure...")
                print("[3/7] Arranging for NES with arpeggiation...")
                frames = arrange_for_nes(
                    midi_data["events"],
                    arp_speed=3,  # 20Hz arpeggiation (classic NES)
                    verbose=args.verbose
                )
                # midi_data is not referenced again downstream -- release it
                # instead of holding both it and frames simultaneously
                # (#371/PERF-A-01; run_detect_patterns already dels frames
                # the same way after extracting its own events).
                del midi_data
            else:
                # Step 2: Map tracks to NES channels (legacy mode)
                print("[2/7] Mapping tracks to NES channels...")
                dpcm_index_path = 'dpcm_index.json'
                # Same guard as run_map (#256/D-18): without it, a missing
                # index makes assign_tracks_to_nes_channels raise a bare
                # FileNotFoundError that the outer except below only relays
                # as a generic "[ERROR] Pipeline failed: ..." line, aborting
                # the whole 7-step build for what step 5.5's DPCM packing
                # treats as optional (#381/SAFE-2026-07-19-1). Surface the
                # same actionable message here instead.
                if not Path(dpcm_index_path).exists():
                    print(f"[ERROR] DPCM index not found: {dpcm_index_path} "
                          f"(pass --dpcm-index <path>, or restore dpcm_index.json)")
                    sys.exit(1)
                mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
                # midi_data's data is now fully captured in mapped; step 3
                # below never reads midi_data again (#371/PERF-A-01).
                del midi_data

                # Step 3: Generate frame data
                print("[3/7] Generating NES frame data...")
                emulator = NESEmulatorCore()
                frames = emulator.process_all_tracks(mapped)
                # mapped is not referenced again downstream -- the frames
                # stage's peak used to hold both mapped (its input) and
                # frames (its output) simultaneously (#371/PERF-A-01).
                del mapped
            
            # Steps 4-8 are extracted into stage helpers (#406/TD-11-FOLLOWUP)
            # defined just above this function -- see their docstrings for
            # what each one owns. `frames` is the only large object still
            # alive by this point (mapped/midi_data are already gone above),
            # so there is no further #371-style del-ordering to preserve
            # here; each helper raises on failure straight into this
            # function's single try/except/finally.
            pattern_result, pattern_loss_warning, coverage_lossy_note = (
                detect_patterns_or_direct_export(frames, use_patterns, args)
            )

            music_asm = temp_path / "music.asm"
            mapper, pack_result = export_frames_and_resolve_mapper(
                frames, pattern_result, music_asm, use_patterns, args)
            dpcm_pack_warning = pack_result.warning

            project_path = temp_path / "nes_project"
            debug_mode = hasattr(args, 'debug') and args.debug
            visualizer_mode = hasattr(args, 'visualizer') and args.visualizer
            skip_validation = hasattr(args, 'skip_validation') and args.skip_validation
            build_and_validate_rom(
                mapper, music_asm, project_path, output_rom,
                debug_mode, skip_validation, args, visualizer_mode=visualizer_mode)

            # Success!
            rom_size = output_rom.stat().st_size
            print("\n" + "=" * 60)
            print(f"✅ SUCCESS! ROM created: {output_rom.name}")
            print(f"   ROM size: {rom_size:,} bytes ({rom_size / 1024:.1f} KB)")
            # compression_ratio is a pattern-analysis metric over the patterned
            # subset only, unrelated to the ROM size above (actual size
            # reduction comes from macro/instrument dedup in the bytecode
            # serializer, #4) -- labeled and paired with a coverage line so it
            # isn't misread as describing this ROM (#169/PAT-03).
            print(f"   Pattern dedup ratio: {pattern_result['stats']['compression_ratio']:.1f}% "
                  f"reduction (patterned subset only, pattern-analysis metric)")
            print(f"   Pattern coverage: {pattern_result['stats']['coverage_ratio']:.1f}% of "
                  f"{pattern_result['stats']['total_events']:,} events matched a detected pattern"
                  f"{coverage_lossy_note}")
            print(f"   Total patterns detected: {len(pattern_result['patterns'])}")
            if pattern_loss_warning:
                print(f"\n   ⚠️  {pattern_loss_warning}")
            if dpcm_pack_warning:
                # See run_export's identical labeling: "NO DRUMS" only
                # actually describes the all-missing case (#367/DP-DPCM-05).
                label = "NO DRUMS" if pack_result.loaded_samples == 0 else "PARTIAL DPCM MISS"
                print(f"\n   ⚠️  {label}: {dpcm_pack_warning}")
            print("\n🎮 Your NES ROM is ready to run on emulators or flash carts!")

            # The new ROM is final and validated; mark success so the finally
            # block does not attempt a restore, then drop the now-redundant backup.
            build_succeeded = True
            if backup_path:
                backup_path.unlink(missing_ok=True)

        except MIDI2NESError as e:
            # Every typed failure surface underneath (InvalidMIDIError,
            # ConfigurationError, ToolchainError, CompilationError,
            # ValidationError, ...) derives from this common base -- these
            # are expected user-facing errors whose message is already
            # actionable (#384/SAFE-2026-07-19-2). Narrowed from a single
            # blanket `except Exception` so a caller/test can tell an
            # expected error apart from a genuinely unexpected defect below,
            # mirroring config_manager's precedent (#125/SAFE-08).
            print(f"\n[ERROR] Pipeline failed: {str(e)}")
            if args.verbose:
                import traceback
                print("\nFull traceback:")
                traceback.print_exc()
            sys.exit(1)

        except Exception as e:
            # An unexpected defect (not one of our typed errors) -- flagged
            # distinctly so it isn't mistaken for an expected user error.
            print(f"\n[ERROR] Unexpected pipeline failure: {str(e)}")
            if args.verbose:
                import traceback
                print("\nFull traceback:")
                traceback.print_exc()
            sys.exit(1)

        finally:
            # Single restore point that covers every failure path after backup
            # creation: compile failure, prepare failure, top-level exception (#26).
            if not build_succeeded:
                _restore_backup(output_rom, backup_path)

def main():
    parser = argparse.ArgumentParser(
        description=f"MIDI to NES ROM compiler v{__version__}\n\nDefault usage: midi2nes song.mid [output.nes]",
        epilog="For more information, visit: https://github.com/matiaszanolli/midi2nes",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--version', action='version', version=f'MIDI2NES {__version__}')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug overlay in ROM (shows APU status, frame counter, errors on screen)')
    parser.add_argument('--visualizer', action='store_true', help='Add an on-screen per-channel volume-bar UI to the ROM (background-tile VU meter for Pulse1/Pulse2/Triangle/Noise). Cannot be combined with --debug.')
    parser.add_argument('--arranger', '-a', action='store_true', help='Use intelligent arranger with arpeggiation for polyphonic content (default pipeline only; no subcommand equivalent yet)')
    
    subparsers = parser.add_subparsers(dest='command', help='Advanced commands (optional - default is MIDI to ROM conversion)')

    # Existing subcommands
    p_parse = subparsers.add_parser('parse', help='Parse MIDI to intermediate JSON')
    p_parse.add_argument('input')
    p_parse.add_argument('output')
    p_parse.set_defaults(func=run_parse)

    # Update map command with new configuration options
    p_map = subparsers.add_parser('map', help='Map parsed MIDI to NES channels')
    p_map.add_argument('input')
    p_map.add_argument('output')
    # NOTE: drum-mapper --config is not consumed by assign_tracks_to_nes_channels,
    # so it was dropped here rather than left as a silently-ignored flag (#13).
    p_map.add_argument('--dpcm-index', help='Path to DPCM sample index')
    p_map.set_defaults(func=run_map)

    # Add new configuration management commands
    p_config = subparsers.add_parser('config', help='Configuration management')
    config_subparsers = p_config.add_subparsers(dest='config_command')

    # Generate default config
    p_config_init = config_subparsers.add_parser('init', 
                                                help='Generate default configuration')
    p_config_init.add_argument('output', help='Output configuration file path')
    p_config_init.set_defaults(func=run_config_init)

    # Validate config
    p_config_validate = config_subparsers.add_parser('validate', 
                                                    help='Validate configuration file')
    p_config_validate.add_argument('config', help='Configuration file to validate')
    p_config_validate.set_defaults(func=run_config_validate)

    # Keep existing commands
    p_frames = subparsers.add_parser('frames', help='Generate frame data from mapped tracks')
    p_frames.add_argument('input')
    p_frames.add_argument('output')
    p_frames.set_defaults(func=run_frames)

    p_patterns = subparsers.add_parser('detect-patterns',
                                      help='Detect and compress patterns in frame data')
    p_patterns.add_argument('input')
    p_patterns.add_argument('output')
    # NOTE: --config here only overrides processing.pattern_detection.max_events
    # (the sequential detector's sampling cap, #219) — it still does NOT touch
    # the tempo or PATTERN_MIN/MAX_LENGTH, which stay hardcoded. Same scoped
    # treatment as map --config (#13, #109): only wire what is actually consumed.
    p_patterns.add_argument('--config', help='Path to YAML config overriding pattern-detection sampling caps')
    p_patterns.set_defaults(func=run_detect_patterns)

    p_export = subparsers.add_parser('export', help='Export NES-ready files (ca65/FamiTracker)')
    p_export.add_argument('input')
    p_export.add_argument('output')
    # `nsf` is intentionally absent until the NSF exporter is playable (#79/#81);
    # offering it made `--format nsf` a silent no-op rather than a real export.
    p_export.add_argument('--format', choices=['ca65'], default='ca65')
    p_export.add_argument('--patterns', help='Path to pattern data JSON (optional)')
    p_export.add_argument('--mapper', choices=['auto', 'nrom', 'mmc1', 'mmc3'], default='mmc3',
                           help="NES mapper this export targets (must match the mapper "
                                "later passed to `prepare`); only affects direct (no "
                                "patterns) exports. Default: mmc3")
    p_export.set_defaults(func=run_export)

    # Keep other existing commands...
    p_prepare = subparsers.add_parser('prepare', help='Prepare CA65 project for compilation')
    p_prepare.add_argument('input', help='Input music.asm file')
    p_prepare.add_argument('output', help='Output project directory')
    p_prepare.add_argument('--mapper', choices=['auto', 'nrom', 'mmc1', 'mmc3'], default='mmc3',
                            help="NES mapper to target. 'auto' picks the smallest mapper "
                                 "that fits this song's data (default: mmc3)")
    p_prepare.set_defaults(func=run_prepare)

    # `compile` gives the step-by-step path the same compile + validation gate as
    # the full pipeline, instead of stopping at `prepare` (#15).
    p_compile = subparsers.add_parser('compile', help='Compile a prepared NES project to a ROM and validate it')
    p_compile.add_argument('input', help='Prepared NES project directory')
    p_compile.add_argument('output', help='Output .nes ROM path')
    p_compile.add_argument('--mapper', choices=['nrom', 'mmc1', 'mmc3'], default='mmc3',
                            help='NES mapper the project directory was prepared with '
                                 '(must match `prepare --mapper`; default: mmc3)')
    p_compile.add_argument('--skip-validation', action='store_true', help='Skip post-compile ROM validation')
    p_compile.add_argument('--verbose', '-v', action='store_true', help='Verbose validation output')
    p_compile.set_defaults(func=run_compile)

    # Song bank management commands
    p_song = subparsers.add_parser(
        'song',
        help='Song bank management (add/list/remove manage a JSON bank; build compiles it to a multi-song ROM)'
    )
    song_subparsers = p_song.add_subparsers(dest='song_command')

    p_song_add = song_subparsers.add_parser('add', help='Add song to bank')
    p_song_add.add_argument('input', help='Input MIDI file')
    p_song_add.add_argument('--bank', help='Song bank file (creates new if not exists)')
    p_song_add.add_argument('--name', help='Song name (defaults to filename)')
    p_song_add.add_argument('--composer', help='Song composer')
    p_song_add.add_argument('--loop-point', type=int, help='Loop point in frames')
    p_song_add.add_argument('--tags', help='Comma-separated tags')
    p_song_add.add_argument('--tempo', type=int, default=120, help='Base tempo (default: 120)')
    # NOTE: song-add --config was not consumed by run_song_add, so it was dropped
    # rather than left as a silently-ignored flag — same treatment as map --config
    # (#13, #109).
    p_song_add.set_defaults(func=run_song_add)

    p_song_list = song_subparsers.add_parser('list', help='List songs in bank')
    p_song_list.add_argument('bank', help='Song bank file')
    p_song_list.set_defaults(func=run_song_list)

    p_song_remove = song_subparsers.add_parser('remove', help='Remove song from bank')
    p_song_remove.add_argument('bank', help='Song bank file')
    p_song_remove.add_argument('name', help='Song name to remove')
    p_song_remove.set_defaults(func=run_song_remove)

    p_song_build = song_subparsers.add_parser(
        'build',
        help="Build a multi-song 'jukebox' ROM from a song bank (#30/F-13; MMC3 only, no DPCM/drums yet)"
    )
    p_song_build.add_argument('bank', help='Song bank file')
    p_song_build.add_argument('output', help='Output .nes ROM path')
    p_song_build.add_argument('--arranger', action='store_true',
                               help='Use arranger mode (voice allocation + arpeggiation) for every song in the bank')
    p_song_build.add_argument('--dpcm-index', help='Path to DPCM sample index (legacy/non-arranger mode only)')
    p_song_build.add_argument('--skip-validation', action='store_true', help='Skip post-compile ROM validation')
    p_song_build.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    p_song_build.set_defaults(func=run_song_build)

    # Add benchmark command
    p_benchmark = subparsers.add_parser('benchmark', help='Performance benchmarking')
    benchmark_subparsers = p_benchmark.add_subparsers(dest='benchmark_command')
    
    # Run benchmark
    p_benchmark_run = benchmark_subparsers.add_parser('run', help='Run performance benchmark')
    p_benchmark_run.add_argument('files', nargs='*', help='MIDI files to benchmark (optional)')
    p_benchmark_run.add_argument('--output', default='benchmark_results', help='Output directory')
    p_benchmark_run.add_argument('--memory', action='store_true', help='Enable detailed memory profiling')
    p_benchmark_run.set_defaults(func=run_benchmark)
    
    # Memory usage command
    p_benchmark_memory = benchmark_subparsers.add_parser('memory', help='Show current memory usage')
    p_benchmark_memory.set_defaults(func=run_benchmark_memory)

    # Custom argument parsing to handle default behavior
    import sys
    
    # Check if first argument (if any) is a subcommand
    subcommands = ['parse', 'map', 'config', 'frames', 'detect-patterns', 'export', 'prepare', 'compile', 'song', 'benchmark']
    
    # Handle special cases first
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    if len(sys.argv) == 2 and sys.argv[1] in ['--help', '-h']:
        parser.print_help()
        sys.exit(0)
    
    if len(sys.argv) == 2 and sys.argv[1] in ['--version']:
        parser.parse_args(sys.argv[1:])
        return
    
    # Check if first non-option argument is a subcommand
    first_arg = None
    for arg in sys.argv[1:]:
        if not arg.startswith('-'):
            first_arg = arg
            break
    
    if first_arg in subcommands:
        # --arranger is declared on the top-level parser, so argparse happily
        # accepts it before a subcommand -- but no subcommand reads args.arranger,
        # so it would be silently discarded and the step-by-step chain would
        # produce the legacy (non-arranger) song with zero diagnostics (#174).
        pre_subcommand_args = sys.argv[1:sys.argv.index(first_arg)]
        if '--arranger' in pre_subcommand_args or '-a' in pre_subcommand_args:
            # `song build` has its own --arranger (p_song_build, read at
            # run_song_build's use_arranger), so it isn't true that no
            # step-by-step equivalent exists there -- the fix is to place the
            # flag after `build`, not to drop it (#487/PIPE-2026-08-22-3, a
            # message-accuracy regression from #174/PL-01, filed before
            # `song build --arranger` existed).
            if first_arg == 'song':
                print("Error: --arranger must come after 'song build', not before 'song' "
                      "-- e.g. 'midi2nes song build bank.json out.nes --arranger'.",
                      file=sys.stderr)
            else:
                print("Error: --arranger only applies to the default MIDI-to-ROM pipeline "
                      f"or 'song build'; there is no step-by-step equivalent for '{first_arg}' yet.",
                      file=sys.stderr)
                print(f"Run 'midi2nes --arranger song.mid' instead, or drop --arranger before '{first_arg}'.",
                      file=sys.stderr)
            sys.exit(2)
        # It's a subcommand, parse normally
        args = parser.parse_args()
        _reject_debug_visualizer_combo(args)
        if hasattr(args, 'func'):
            args.func(args)
        else:
            parser.print_help()
    else:
        # It's the default MIDI-to-ROM behavior
        # Parse global options first
        global_args = []
        remaining_args = []
        
        i = 1
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg in ['--verbose', '-v']:
                global_args.extend([arg])
                i += 1
            elif arg in ['--debug', '-d']:
                global_args.extend([arg])
                i += 1
            elif arg == '--visualizer':
                global_args.extend([arg])
                i += 1
            elif arg in ['--arranger', '-a']:
                global_args.extend([arg])
                i += 1
            elif arg == '--version':
                # Match argparse's action='version' behavior: print and exit
                # immediately regardless of any other arguments present, rather
                # than filing this into global_args where nothing consumed it
                # and a full pipeline run happened instead (#179/PL-06).
                print(f"MIDI2NES {__version__}")
                sys.exit(0)
            elif arg == '--no-patterns':
                global_args.extend([arg])
                i += 1
            elif arg == '--skip-validation':
                global_args.extend([arg])
                i += 1
            elif arg == '--config':
                if i + 1 >= len(sys.argv):
                    print("Error: --config requires a path argument", file=sys.stderr)
                    sys.exit(2)
                global_args.extend([arg, sys.argv[i + 1]])
                i += 2
            elif arg == '--mapper':
                if i + 1 >= len(sys.argv) or sys.argv[i + 1] not in ('auto', 'nrom', 'mmc1', 'mmc3'):
                    print("Error: --mapper requires one of: auto, nrom, mmc1, mmc3", file=sys.stderr)
                    sys.exit(2)
                global_args.extend([arg, sys.argv[i + 1]])
                i += 2
            elif arg.startswith('-'):
                # Reject unknown/typo flags instead of silently dropping them —
                # a swallowed --no-patterns/--arranger produces a different ROM (#8).
                print(f"Error: Unknown option: {arg}", file=sys.stderr)
                print("Run 'midi2nes --help' for available options.", file=sys.stderr)
                sys.exit(2)
            else:
                remaining_args.append(arg)
                i += 1

        if not remaining_args:
            print("Error: Please provide an input MIDI file")
            print("\nUsage examples:")
            print("  midi2nes song.mid                  # Creates song.nes")
            print("  midi2nes song.mid output.nes       # Creates output.nes")
            print("  midi2nes --arranger song.mid       # Smart voice allocation + arpeggiation")
            print("  midi2nes --no-patterns song.mid    # Direct export (no compression)")
            print("  midi2nes --debug song.mid          # Debug ROM (shows APU status on screen)")
            print("  midi2nes --visualizer song.mid     # ROM with on-screen per-channel volume bars")
            print("  midi2nes --skip-validation song.mid # Skip ROM validation after compilation")
            print("  midi2nes --config cfg.yaml song.mid # Override pattern-detection sampling caps")
            print("  midi2nes --mapper auto song.mid    # Auto-select the smallest mapper that fits")
            print("  midi2nes --help                    # Show full help")
            sys.exit(1)

        # Create a simple args object for the default pipeline
        class SimpleArgs:
            def __init__(self):
                self.input = remaining_args[0] if remaining_args else None
                self.output = remaining_args[1] if len(remaining_args) > 1 else None
                self.verbose = '--verbose' in global_args or '-v' in global_args
                self.no_patterns = '--no-patterns' in global_args
                self.debug = '--debug' in global_args or '-d' in global_args
                self.visualizer = '--visualizer' in global_args
                self.arranger = '--arranger' in global_args or '-a' in global_args
                self.skip_validation = '--skip-validation' in global_args
                self.config = (global_args[global_args.index('--config') + 1]
                              if '--config' in global_args else None)
                self.mapper = (global_args[global_args.index('--mapper') + 1]
                              if '--mapper' in global_args else 'mmc3')
                self.command = None

        args = SimpleArgs()
        _reject_debug_visualizer_combo(args)
        run_full_pipeline(args)

def run_config_init(args):
    """Generate default configuration file"""
    try:
        config_manager = ConfigManager()
        config_manager.copy_default_config_to(args.output)
        print(f"[OK] Generated default configuration -> {args.output}")
        print(f"     Edit this file to customize MIDI2NES behavior")
    except Exception as e:
        print(f"[ERROR] Failed to generate configuration: {str(e)}")
        sys.exit(1)

def run_config_validate(args):
    """Validate configuration file"""
    try:
        config_manager = ConfigManager(args.config)
        config_manager.validate()
        print(f"[OK] Configuration file is valid: {args.config}")
        
        # Show some key settings
        if hasattr(args, 'verbose') and args.verbose:
            print("\nConfiguration summary:")
            print(f"  Pattern detection min length: {config_manager.get('processing.pattern_detection.min_length')}")
            print(f"  Memory limit: {config_manager.get('performance.max_memory_mb')} MB")
            print(f"  NSF load address: 0x{config_manager.get('export.nsf.load_address'):04X}")
            
    except Exception as e:
        print(f"[ERROR] Configuration validation failed: {str(e)}")
        sys.exit(1)

def run_benchmark(args):
    """Run performance benchmarks"""
    benchmark = PerformanceBenchmark()
    
    # Set up test files
    test_files = []
    if args.files:
        for file_pattern in args.files:
            file_path = Path(file_pattern)
            if file_path.is_file():
                test_files.append(str(file_path))
            elif file_path.is_dir():
                # Find MIDI files in directory
                midi_files = list(file_path.glob('*.mid')) + list(file_path.glob('*.midi'))
                test_files.extend([str(f) for f in midi_files])
            else:
                print(f"Warning: {file_pattern} not found")
    
    if not test_files:
        print("No test files specified. Using built-in test data.")
        # Generate some test data
        test_files = None
    
    try:
        # Create output directory
        output_dir = Path(args.output)
        output_dir.mkdir(exist_ok=True)
        
        # Run the benchmarks
        print(f"Running performance benchmarks...")
        if args.memory:
            print("Memory profiling enabled")
            
        if test_files:
            # Run benchmarks on provided files
            results = {}
            for midi_file in test_files:
                print(f"Running pipeline benchmark on: {midi_file}")
                try:
                    result = benchmark.run_full_pipeline(midi_file)
                    results[Path(midi_file).name] = {
                        'file_path': result.file_path,
                        'file_size_kb': result.file_size_kb,
                        'execution_time': result.total_duration_ms / 1000,  # Convert to seconds
                        'memory_peak': result.total_memory_mb,
                        'stages': [{stage.stage: {'duration_ms': stage.duration_ms, 'success': stage.success}} for stage in result.stages],
                        'midi_info': result.midi_info
                    }
                    if result.midi_info.get('total_events', 0) > 0:
                        results[Path(midi_file).name]['throughput'] = result.midi_info['total_events'] / (result.total_duration_ms / 1000)
                except Exception as e:
                    print(f"  Failed to benchmark {midi_file}: {str(e)}")
                    results[Path(midi_file).name] = {'error': str(e)}
        else:
            print("Running synthetic benchmark tests...")
            # Create simple synthetic test
            results = {
                'synthetic_test': {
                    'execution_time': 0.001,
                    'memory_peak': 10.0,
                    'note': 'Synthetic test - no actual MIDI files provided'
                }
            }
        
        # Save results to JSON
        results_file = output_dir / "benchmark_results.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        # Print summary
        print(f"\n[OK] Benchmark completed -> {results_file}")
        print("\nBenchmark Summary:")
        print("-" * 50)
        
        for test_name, result in results.items():
            if isinstance(result, dict) and 'execution_time' in result:
                print(f"{test_name}: {result['execution_time']:.3f}s")
                if 'memory_peak' in result:
                    print(f"  Peak memory: {result['memory_peak']:.2f} MB")
                if 'throughput' in result:
                    print(f"  Throughput: {result['throughput']:.1f} events/sec")
        
    except Exception as e:
        print(f"[ERROR] Benchmark failed: {str(e)}")
        sys.exit(1)

def run_benchmark_memory(args):
    """Show current memory usage"""
    try:
        memory_info = get_memory_usage()
        log_memory_usage("Current Memory Usage")
        
        print("Memory Usage Report:")
        print("-" * 30)
        for key, value in memory_info.items():
            if isinstance(value, float):
                print(f"{key}: {value:.2f} MB")
            else:
                print(f"{key}: {value}")
                
    except Exception as e:
        print(f"[ERROR] Memory profiling failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
