import argparse
import sys
import json
from pathlib import Path

from tracker.parser import parse_midi_to_frames
from tracker.track_mapper import assign_tracks_to_nes_channels
from nes.emulator_core import NESEmulatorCore
from exporter_nsftxt import generate_nsftxt
from exporter_ca65 import export_ca65_tables

def run_parse(args):
    midi_data = parse_midi_to_frames(args.input)
    Path(args.output).write_text(json.dumps(midi_data, indent=2))
    print(f"✅ Parsed MIDI -> {args.output}")

def run_map(args):
    midi_data = json.loads(Path(args.input).read_text())
    dpcm_index_path = 'dpcm_index.json'
    mapped = assign_tracks_to_nes_channels(midi_data, dpcm_index_path)
    Path(args.output).write_text(json.dumps(mapped, indent=2))
    print(f"✅ Mapped tracks -> {args.output}")

def run_frames(args):
    mapped = json.loads(Path(args.input).read_text())
    emulator = NESEmulatorCore()
    frames = emulator.process_all_tracks(mapped)
    Path(args.output).write_text(json.dumps(frames, indent=2))
    print(f" Generated frames -> {args.output}")

def run_export(args):
    frames = json.loads(Path(args.input).read_text())
    if args.format == "nsftxt":
        output = generate_nsftxt(frames)
        Path(args.output).write_text(output)
        print(f"✅ Exported FamiTracker TXT -> {args.output}")
    elif args.format == "ca65":
        export_ca65_tables(frames, args.output)
        print(f"✅ Exported CA65 ASM -> {args.output}")

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

    p_export = subparsers.add_parser('export', help='Export NES-ready files (ca65/FamiTracker)')
    p_export.add_argument('input')
    p_export.add_argument('output')
    p_export.add_argument('--format', choices=['nsftxt', 'ca65'], default='ca65')
    p_export.set_defaults(func=run_export)

    args = parser.parse_args()

    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()