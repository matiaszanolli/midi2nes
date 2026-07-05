"""
NES Voice Allocator for MIDI2NES.

Takes analyzed MIDI data and allocates notes to NES channels frame-by-frame,
implementing arpeggiation for polyphonic content and priority-based voice stealing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
from collections import defaultdict

from .gm_instruments import (
    MusicalRole, NESChannel, PlayStyle, DutyCycle,
    get_instrument_mapping, get_drum_mapping,
)
from .role_analyzer import NoteInfo, TrackAnalysis, ArrangementPlan


@dataclass
class ChannelState:
    """Current state of a NES channel."""
    note: Optional[int] = None
    velocity: int = 0
    duty: DutyCycle = DutyCycle.DUTY_50
    # For arpeggiation
    arp_notes: List[int] = field(default_factory=list)
    arp_index: int = 0
    # Frames elapsed since the current chord started, so the arp phase is
    # measured per-chord (root first) rather than from the global frame counter
    # (#252).
    arp_frame: int = 0
    # Source tracking
    source_track: int = -1


@dataclass
class FrameAllocation:
    """What each channel plays on a specific frame."""
    pulse1: Optional[Tuple[int, int, DutyCycle]] = None  # (note, velocity, duty)
    pulse2: Optional[Tuple[int, int, DutyCycle]] = None
    triangle: Optional[Tuple[int, int]] = None  # (note, velocity) - no duty
    noise: Optional[Tuple[int, int]] = None  # (period, velocity)
    dpcm: Optional[int] = None  # sample index


class ArpStyle(Enum):
    """Arpeggiation patterns."""
    UP = "up"           # Low to high
    DOWN = "down"       # High to low
    UP_DOWN = "updown"  # Low-high-low (no repeat at ends)
    RANDOM = "random"   # Random order (not implemented yet)


class VoiceAllocator:
    """
    Allocates MIDI notes to NES channels frame-by-frame.

    Handles:
    - Priority-based channel assignment
    - Arpeggiation for polyphonic content
    - Voice stealing when channels are full
    - Duty cycle selection based on instrument
    """

    # Arpeggiation speed in frames (at 60fps)
    # 3 frames = 20Hz arpeggiation (classic NES sound)
    # 2 frames = 30Hz (faster, smoother)
    # 4 frames = 15Hz (slower, more distinct notes)
    DEFAULT_ARP_SPEED = 3

    def __init__(
        self,
        arp_speed: int = DEFAULT_ARP_SPEED,
        arp_style: ArpStyle = ArpStyle.UP,
    ):
        self.arp_speed = arp_speed
        self.arp_style = arp_style

        # Channel states
        self.pulse1 = ChannelState()
        self.pulse2 = ChannelState()
        self.triangle = ChannelState()
        self.noise = ChannelState()

        # Frame counter for arpeggiation timing
        self.frame_count = 0

        # Track assignments from arrangement plan. A track may occupy more than
        # one channel: a drum track claims NOISE *and* DPCM at once, and a plain
        # 1:1 dict would let the DPCM entry clobber the NOISE one, silently
        # dropping every noise-routed percussion hit (#251). So each track maps
        # to a list of channels and allocate_frame dispatches per note.
        self.track_assignments: Dict[int, List[NESChannel]] = {}
        self.track_info: Dict[int, TrackAnalysis] = {}

    def set_arrangement(self, plan: ArrangementPlan):
        """Configure allocator from an arrangement plan."""
        # Map tracks to channels (append, don't overwrite — a drum track is in
        # both noise_tracks and dpcm_tracks and must keep both, #251).
        for channel, track_ids in (
            (NESChannel.PULSE1, plan.pulse1_tracks),
            (NESChannel.PULSE2, plan.pulse2_tracks),
            (NESChannel.TRIANGLE, plan.triangle_tracks),
            (NESChannel.NOISE, plan.noise_tracks),
            (NESChannel.DPCM, plan.dpcm_tracks),
        ):
            for track_id in track_ids:
                channels = self.track_assignments.setdefault(track_id, [])
                if channel not in channels:
                    channels.append(channel)

        # Store track info
        for track in plan.tracks:
            self.track_info[track.track_id] = track

    def allocate_frame(
        self,
        active_notes: Dict[int, List[NoteInfo]],  # track_id -> notes active this frame
    ) -> FrameAllocation:
        """
        Allocate notes to channels for a single frame.

        Args:
            active_notes: Dictionary of track_id to list of notes active this frame

        Returns:
            FrameAllocation with what each channel should play
        """
        allocation = FrameAllocation()

        # Collect notes by their assigned channel
        channel_notes: Dict[NESChannel, List[Tuple[int, NoteInfo, TrackAnalysis]]] = defaultdict(list)

        for track_id, notes in active_notes.items():
            channels = self.track_assignments.get(track_id)
            if not channels:
                continue  # Track not assigned (dropped)

            track_info = self.track_info.get(track_id)
            if track_info is None:
                continue

            for note in notes:
                channel = self._route_note(note, channels)
                if channel is None:
                    continue
                channel_notes[channel].append((track_id, note, track_info))

        # Allocate each channel
        allocation.pulse1 = self._allocate_pulse(
            channel_notes.get(NESChannel.PULSE1, []),
            self.pulse1
        )

        allocation.pulse2 = self._allocate_pulse(
            channel_notes.get(NESChannel.PULSE2, []),
            self.pulse2
        )

        allocation.triangle = self._allocate_triangle(
            channel_notes.get(NESChannel.TRIANGLE, [])
        )

        allocation.noise = self._allocate_noise(
            channel_notes.get(NESChannel.NOISE, [])
        )

        allocation.dpcm = self._allocate_dpcm(
            channel_notes.get(NESChannel.DPCM, [])
        )

        # Advance frame counter
        self.frame_count += 1

        return allocation

    def _route_note(
        self,
        note: NoteInfo,
        channels: List[NESChannel],
    ) -> Optional[NESChannel]:
        """Pick which assigned channel a note plays on.

        Single-channel tracks route every note to that channel. A drum track
        claims both NOISE and DPCM, so its notes are dispatched per pitch: the
        kick/snare that GM_DRUM_MAP flags for sampling go to DPCM, and every
        other percussion hit (hi-hats, cymbals, toms, ...) goes to NOISE as the
        catch-all — instead of one channel silently clobbering the other (#251).
        """
        if len(channels) == 1:
            return channels[0]

        mapping = get_drum_mapping(note.pitch)
        if (NESChannel.DPCM in channels
                and mapping.use_sample
                and mapping.channel == NESChannel.DPCM):
            return NESChannel.DPCM
        if NESChannel.NOISE in channels:
            return NESChannel.NOISE
        # No noise slot for a multi-channel track: honor the mapped channel if
        # it's one we own, else fall back to the first assigned channel.
        if mapping.channel in channels:
            return mapping.channel
        return channels[0]

    def _allocate_pulse(
        self,
        notes_data: List[Tuple[int, NoteInfo, TrackAnalysis]],
        state: ChannelState,
    ) -> Optional[Tuple[int, int, DutyCycle]]:
        """Allocate notes to a pulse channel, with arpeggiation if needed."""
        if not notes_data:
            # No notes - silence
            state.note = None
            state.arp_notes = []
            return None

        # Get all unique pitches and their info
        pitches = []
        max_velocity = 0
        duty = DutyCycle.DUTY_50

        for track_id, note, track_info in notes_data:
            pitches.append(note.pitch)
            max_velocity = max(max_velocity, note.velocity)
            if track_info.duty_cycle:
                duty = track_info.duty_cycle

        # Remove duplicates and sort
        unique_pitches = sorted(set(pitches))

        if len(unique_pitches) == 1:
            # Single note - no arpeggiation needed
            state.note = unique_pitches[0]
            state.arp_notes = []
            return (unique_pitches[0], max_velocity, duty)

        # Multiple notes - arpeggiate!
        arp_notes = self._order_arp_notes(unique_pitches)

        # Restart the arpeggio on its root (index 0) whenever the chord changes,
        # including the first frame it appears, then hold each note for arp_speed
        # frames. The phase is measured with a per-chord frame counter rather
        # than the global frame_count: the old code advanced the index *before*
        # the first read and keyed off frame_count, so a chord starting where
        # `frame_count % arp_speed == 0` skipped its root on the attack (#252).
        if arp_notes != state.arp_notes:
            state.arp_notes = arp_notes
            state.arp_index = 0
            state.arp_frame = 0
        else:
            state.arp_frame += 1
            if state.arp_frame % self.arp_speed == 0:
                state.arp_index = (state.arp_index + 1) % len(state.arp_notes)

        current_note = state.arp_notes[state.arp_index]
        state.note = current_note

        return (current_note, max_velocity, duty)

    def _order_arp_notes(self, pitches: List[int]) -> List[int]:
        """Order notes according to arpeggio style."""
        if self.arp_style == ArpStyle.UP:
            return pitches  # Already sorted low-to-high
        elif self.arp_style == ArpStyle.DOWN:
            return list(reversed(pitches))
        elif self.arp_style == ArpStyle.UP_DOWN:
            if len(pitches) <= 2:
                return pitches
            # Up then down, but don't repeat top and bottom
            return pitches + list(reversed(pitches[1:-1]))
        else:
            return pitches

    def _allocate_triangle(
        self,
        notes_data: List[Tuple[int, NoteInfo, TrackAnalysis]],
    ) -> Optional[Tuple[int, int]]:
        """Allocate notes to triangle channel (typically bass)."""
        if not notes_data:
            self.triangle.note = None
            return None

        # Triangle is monophonic, pick the lowest note (bass)
        lowest_pitch = min(note.pitch for _, note, _ in notes_data)
        max_velocity = max(note.velocity for _, note, _ in notes_data)

        self.triangle.note = lowest_pitch
        return (lowest_pitch, max_velocity)

    # The only two DPCM-eligible drum categories GM_DRUM_MAP currently flags
    # `use_sample=True` for are kick (notes 35/36) and snare (note 38); slots
    # are keyed by GM_DRUM_MAP's own name so a note it does NOT route to DPCM
    # (e.g. note 40, Electric Snare -> NOISE) can never be misrouted here (#87).
    DPCM_SAMPLE_SLOTS = {
        "Acoustic Bass Drum": 0,
        "Bass Drum 1": 0,
        "Acoustic Snare": 1,
    }

    def _allocate_noise(
        self,
        notes_data: List[Tuple[int, NoteInfo, TrackAnalysis]],
    ) -> Optional[Tuple[int, int]]:
        """Allocate to noise channel for drums/percussion."""
        if not notes_data:
            self.noise.note = None
            return None

        # Pick highest priority/velocity drum hit
        best_note = max(notes_data, key=lambda x: x[1].velocity)
        _, note, _ = best_note

        # Use GM_DRUM_MAP's curated noise_period instead of recomputing a
        # linear pitch-based formula, so e.g. a closed hi-hat (period 0) and a
        # cowbell (period 8) sound distinct as intended (#87). Fall back to 5
        # (matching get_drum_mapping's own "Unknown Drum" default) when the
        # mapped drum has no curated period (e.g. it's normally routed to a
        # different channel, like the toms -> TRIANGLE).
        # NB: a curated period of 0 (closed hi-hat) is returned as-is here but
        # floored to 1 at the noise-bytecode boundary, because period 0 is the
        # rest sentinel — so period-0 drums render one step lower in frequency
        # (#253, see arranger/pipeline_integration.py).
        noise_period = get_drum_mapping(note.pitch).noise_period
        if noise_period is None:
            noise_period = 5
        noise_period = max(0, min(15, noise_period))

        self.noise.note = note.pitch
        return (noise_period, note.velocity)

    def _allocate_dpcm(
        self,
        notes_data: List[Tuple[int, NoteInfo, TrackAnalysis]],
    ) -> Optional[int]:
        """Allocate DPCM samples for kicks/snares.

        Routing and slot selection are driven by GM_DRUM_MAP (get_drum_mapping)
        instead of a hardcoded note list, so a note GM_DRUM_MAP does not flag
        `use_sample=True` for (e.g. note 40, Electric Snare -> NOISE) is never
        treated as a DPCM hit (#87).
        """
        if not notes_data:
            return None

        dpcm_candidates = [
            (note, get_drum_mapping(note.pitch)) for _, note, _ in notes_data
        ]
        dpcm_candidates = [
            (note, mapping) for note, mapping in dpcm_candidates
            if mapping.use_sample and mapping.channel == NESChannel.DPCM
        ]
        if not dpcm_candidates:
            return None

        # Highest GM priority wins (kick outranks snare in GM_DRUM_MAP).
        _, mapping = max(dpcm_candidates, key=lambda nm: nm[1].priority)
        return self.DPCM_SAMPLE_SLOTS.get(mapping.name, 2)


class FrameByFrameAllocator:
    """
    Processes entire songs frame-by-frame, producing complete NES frame data.
    """

    def __init__(self, total_frames: int, fps: int = 60):
        self.total_frames = total_frames
        self.fps = fps
        self.allocator = VoiceAllocator()

    def process_song(
        self,
        notes_by_track: Dict[int, List[NoteInfo]],
        plan: ArrangementPlan,
    ) -> Dict[str, Dict[int, dict]]:
        """
        Process all notes and produce frame data for each channel.

        Returns:
            Dictionary with channel names as keys, each containing
            frame_number -> frame_data mappings
        """
        self.allocator.set_arrangement(plan)

        # Output frame data
        frames = {
            "pulse1": {},
            "pulse2": {},
            "triangle": {},
            "noise": {},
            "dpcm": {},
        }

        # Build frame-indexed note lookup
        # frame -> track_id -> list of active notes
        frame_notes: Dict[int, Dict[int, List[NoteInfo]]] = defaultdict(lambda: defaultdict(list))

        for track_id, notes in notes_by_track.items():
            for note in notes:
                for frame in range(note.start_frame, note.end_frame):
                    if 0 <= frame < self.total_frames:
                        frame_notes[frame][track_id].append(note)

        # Process each frame
        for frame in range(self.total_frames):
            active_notes = frame_notes.get(frame, {})
            allocation = self.allocator.allocate_frame(active_notes)

            # Store allocations
            if allocation.pulse1:
                note, vel, duty = allocation.pulse1
                frames["pulse1"][frame] = {
                    "note": note,
                    "volume": vel // 8,  # Scale to 0-15
                    "duty": duty.value,
                }

            if allocation.pulse2:
                note, vel, duty = allocation.pulse2
                frames["pulse2"][frame] = {
                    "note": note,
                    "volume": vel // 8,
                    "duty": duty.value,
                }

            if allocation.triangle:
                note, vel = allocation.triangle
                frames["triangle"][frame] = {
                    "note": note,
                    "volume": 15 if vel > 0 else 0,  # Triangle has no volume control
                }

            if allocation.noise:
                period, vel = allocation.noise
                frames["noise"][frame] = {
                    "period": period,
                    "volume": vel // 8,
                }

            if allocation.dpcm is not None:
                frames["dpcm"][frame] = {
                    "sample": allocation.dpcm,
                }

        return frames


def allocate_with_arpeggiation(
    notes_by_track: Dict[int, List[NoteInfo]],
    plan: ArrangementPlan,
    total_frames: int,
    arp_speed: int = 3,
) -> Dict[str, Dict[int, dict]]:
    """
    Convenience function to process a song with arpeggiation.

    Args:
        notes_by_track: Dict of track_id to list of NoteInfo
        plan: ArrangementPlan from VoiceRoleAnalyzer
        total_frames: Total frames in the song
        arp_speed: Frames between arpeggio note changes (default 3 = 20Hz)

    Returns:
        Frame data dictionary ready for NES export
    """
    processor = FrameByFrameAllocator(total_frames)
    processor.allocator.arp_speed = arp_speed
    return processor.process_song(notes_by_track, plan)
