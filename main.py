import argparse
import sys
import json
from pathlib import Path

from tracker.parser import parse_midi_to_frames
from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore
from nes.project_builder import NESProjectBuilder
from exporter.exporter_nsftxt import generate_nsftxt
from exporter.exporter_ca65 import export_ca65_tables_with_patterns
from exporter.exporter import generate_famitracker_txt_with_patterns
from tracker.pattern_detector import EnhancedPatternDetector  # Add this import
from tracker.tempo_map import EnhancedTempoMap  # Add this import

def run_parse(args):
    midi_data = parse_midi_to_frames(args.input)
    Path(args.output).write_text(json.dumps(midi_data, indent=2))
    print(f"[OK] Parsed MIDI -> {args.output}")

def run_map(args):
    midi_data = json.loads(Path(args.input).read_text())
    dpcm_index_path = 'dpcm_index.json'
    # Extract just the events from the parsed data
    mapped = assign_tracks_to_nes_channels(midi_data["events"], dpcm_index_path)
    Path(args.output).write_text(json.dumps(mapped, indent=2))
    print(f"[OK] Mapped tracks -> {args.output}")

def run_frames(args):
    mapped = json.loads(Path(args.input).read_text())
    emulator = NESEmulatorCore()
    frames = emulator.process_all_tracks(mapped)
    Path(args.output).write_text(json.dumps(frames, indent=2))
    print(f" Generated frames -> {args.output}")

def run_prepare(args):
    builder = NESProjectBuilder(args.output)
    if builder.prepare_project(args.input):
        print(f" Prepared NES project -> {args.output}")
        print(" Ready for CC65 compilation!")
        print(" To build:")
        print(f" 1. cd {args.output}")
        print(" 2. ./build.sh  (or build.bat on Windows)")

def run_export(args):
    """Modified export function to support pattern compression"""
    frames = json.loads(Path(args.input).read_text())
    
    # Check if we have pattern data
    pattern_data = None
    if args.patterns:
        pattern_data = json.loads(Path(args.patterns).read_text())
    
    if args.format == "nsftxt":
        if pattern_data:
            output = generate_famitracker_txt_with_patterns(
                frames,
                pattern_data['patterns'],
                pattern_data['references']
            )
        else:
            output = generate_nsftxt(frames)
        Path(args.output).write_text(output)
        print(f" Exported FamiTracker TXT -> {args.output}")
    
    elif args.format == "ca65":
        # Always use export_ca65_tables_with_patterns, with empty patterns if none provided
        if pattern_data:
            patterns = pattern_data['patterns']
            references = pattern_data['references']
        else:
            patterns = []
            references = {}
            
        export_ca65_tables_with_patterns(
            frames,
            patterns,
            references,
            args.output
        )
        print(f" Exported CA65 ASM -> {args.output}")

def run_detect_patterns(args):
    frames = json.loads(Path(args.input).read_text())
    
    # Create tempo map and pattern detector
    tempo_map = EnhancedTempoMap(initial_tempo=500000)  # 120 BPM default
    detector = EnhancedPatternDetector(tempo_map, min_pattern_length=3)
    
    # Extract events from frames structure
    events = []
    for channel_name, channel_frames in frames.items():
        for frame_num, frame_data in channel_frames.items():
            event = {
                'frame': int(frame_num),
                'note': frame_data.get('note', 0),
                'volume': frame_data.get('volume', 0)
            }
            events.append(event)
    
    # Sort events by frame number
    events.sort(key=lambda x: x['frame'])
    
    # Detect patterns
    pattern_result = detector.detect_patterns(events)
    
    # Save compressed patterns
    output = {
        'patterns': pattern_result['patterns'],
        'references': pattern_result['references'],
        'stats': pattern_result['stats']
    }
    Path(args.output).write_text(json.dumps(output, indent=2))
    print(f" Detected patterns -> {args.output}")
    print(f" Compression ratio: {pattern_result['stats']['compression_ratio']:.2f}")

def main():
    parser = argparse.ArgumentParser(description="MIDI to NES compiler")
    subparsers = parser.add_subparsers(dest='command')

    # Subcommands
    p_parse = subparsers.add_parser('parse', help='Parse MIDI to intermediate JSON')
    p_parse.add_argument('input')
    p_parse.add_argument('output')
    p_parse.set_defaults(func=run_parse)

    p_map = subparsers.add_parser('map', help='Map parsed MIDI to NES channels')
    p_map.add_argument('input')
    p_map.add_argument('output')
    p_map.set_defaults(func=run_map)

    p_frames = subparsers.add_parser('frames', help='Generate frame data from mapped tracks')
    p_frames.add_argument('input')
    p_frames.add_argument('output')
    p_frames.set_defaults(func=run_frames)

    p_patterns = subparsers.add_parser('detect-patterns', 
                                      help='Detect and compress patterns in frame data')
    p_patterns.add_argument('input')
    p_patterns.add_argument('output')
    p_patterns.set_defaults(func=run_detect_patterns)

    p_export = subparsers.add_parser('export', help='Export NES-ready files (ca65/FamiTracker)')
    p_export.add_argument('input')
    p_export.add_argument('output')
    p_export.add_argument('--format', choices=['nsftxt', 'ca65'], default='ca65')
    p_export.add_argument('--patterns', help='Path to pattern data JSON (optional)')
    p_export.set_defaults(func=run_export)

    p_prepare = subparsers.add_parser('prepare', help='Prepare CA65 project for compilation')
    p_prepare.add_argument('input', help='Input music.asm file')
    p_prepare.add_argument('output', help='Output project directory')
    p_prepare.set_defaults(func=run_prepare)

    args = parser.parse_args()

    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
