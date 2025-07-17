"""
Enhanced TempoMap implementation for midi2nes
Provides advanced tempo tracking, validation, and optimization features
"""

import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
from enum import Enum
from constants import FRAME_MS, FRAME_RATE_HZ


@dataclass
class TempoValidationConfig:
    """Configuration for tempo change validation"""
    min_tempo_bpm: float = 20.0
    max_tempo_bpm: float = 300.0
    min_duration_frames: int = 1
    max_duration_frames: int = FRAME_RATE_HZ * 60  # 1 minute
    max_tempo_change_ratio: float = 2.0  # Maximum allowed tempo change ratio


class TempoChangeType(Enum):
    """Types of tempo changes supported"""
    IMMEDIATE = "immediate"
    LINEAR = "linear"
    CURVE = "curve"
    PATTERN_SYNC = "pattern_sync"


class TempoOptimizationStrategy(Enum):
    """Optimization strategies for tempo changes"""
    MINIMIZE_CHANGES = "minimize_changes"
    SMOOTH_TRANSITIONS = "smooth_transitions"
    PATTERN_ALIGNED = "pattern_aligned"
    FRAME_ALIGNED = "frame_aligned"


class TempoValidationError(Exception):
    """Exception raised when tempo validation fails"""
    pass


class TempoChange:
    """Represents a single tempo change event"""
    def __init__(self, tick: int, tempo: int, 
                 change_type: TempoChangeType = TempoChangeType.IMMEDIATE,
                 duration_ticks: int = 0, curve_factor: float = 1.0,
                 pattern_id: Optional[str] = None):
        self.tick = tick
        self.tempo = tempo
        self.change_type = change_type
        self.duration_ticks = duration_ticks
        self.curve_factor = curve_factor
        self.pattern_id = pattern_id
        self.end_tick = tick + duration_ticks if duration_ticks > 0 else tick


class PatternTempoInfo:
    """Tempo information specific to a pattern"""
    def __init__(self, pattern_id: str, base_tempo: int, 
                 variations: List[TempoChange] = None):
        self.pattern_id = pattern_id
        self.base_tempo = base_tempo
        self.variations = variations or []


class TempoMap:
    """Base TempoMap class - maintains compatibility with existing code"""
    def __init__(self, initial_tempo=500000, ticks_per_beat=480):
        """
        Initialize TempoMap with default tempo (120 BPM = 500000 microseconds per beat)
        
        Args:
            initial_tempo: Microseconds per quarter note (500000 = 120 BPM)
            ticks_per_beat: MIDI ticks per quarter note
        """
        self.tempo_changes = [(0, initial_tempo)]
        self.ticks_per_beat = ticks_per_beat
        self._time_cache = {}
        
    def add_tempo_change(self, tick: int, tempo: int):
        """Add a tempo change at the specified tick"""
        self.tempo_changes.append((tick, tempo))
        self.tempo_changes.sort()
        self._time_cache = {}
        
    def get_tempo_at_tick(self, tick: int) -> int:
        """Get the active tempo at a specific tick"""
        active_tempo = self.tempo_changes[0][1]
        for change_tick, tempo in self.tempo_changes:
            if change_tick <= tick:
                active_tempo = tempo
            else:
                break
        return active_tempo
        
    def calculate_time_ms(self, start_tick: int, end_tick: int) -> float:
        """Calculate time in milliseconds between two ticks"""
        if start_tick == end_tick:
            return 0.0
            
        cache_key = (start_tick, end_tick)
        if cache_key in self._time_cache:
            return self._time_cache[cache_key]
            
        total_time_ms = 0.0
        current_tick = start_tick
        current_tempo = self.get_tempo_at_tick(start_tick)
        
        for next_tick, next_tempo in self.tempo_changes:
            if next_tick <= start_tick:
                current_tempo = next_tempo
                continue
                
            if next_tick >= end_tick:
                break
                
            # Calculate time until this tempo change
            segment_ticks = next_tick - current_tick
            segment_time = self._ticks_to_ms(segment_ticks, current_tempo)
            total_time_ms += segment_time
            
            current_tick = next_tick
            current_tempo = next_tempo
            
        # Calculate remaining time
        if current_tick < end_tick:
            remaining_ticks = end_tick - current_tick
            remaining_time = self._ticks_to_ms(remaining_ticks, current_tempo)
            total_time_ms += remaining_time
            
        self._time_cache[cache_key] = total_time_ms
        return total_time_ms
        
    def _ticks_to_ms(self, ticks: int, tempo_microseconds: int) -> float:
        """Convert ticks to milliseconds for a given tempo"""
        microseconds_per_tick = tempo_microseconds / self.ticks_per_beat
        return (ticks * microseconds_per_tick) / 1000.0
        
    def get_frame_for_tick(self, tick: int) -> int:
        """Get the frame number for a specific tick"""
        time_ms = self.calculate_time_ms(0, tick)
        return int(time_ms / FRAME_MS)
        
    def get_tempo_bpm_at_tick(self, tick: int) -> float:
        """Get tempo in BPM at a specific tick"""
        tempo_microseconds = self.get_tempo_at_tick(tick)
        return 60_000_000 / tempo_microseconds
        
    def get_debug_info(self) -> Dict:
        """Get debug information about tempo changes"""
        info = {
            "ticks_per_beat": self.ticks_per_beat,
            "tempo_changes": []
        }
        
        for tick, tempo in self.tempo_changes:
            bpm = 60_000_000 / tempo
            info["tempo_changes"].append({
                "tick": tick,
                "tempo_microseconds": tempo,
                "bpm": round(bpm, 2),
                "time_ms": self.calculate_time_ms(0, tick),
                "frame": self.get_frame_for_tick(tick)
            })
            
        return info


class EnhancedTempoMap(TempoMap):
    def __init__(self, initial_tempo=500000, ticks_per_beat=480,
                 validation_config: Optional[TempoValidationConfig] = None,
                 optimization_strategy: TempoOptimizationStrategy = TempoOptimizationStrategy.FRAME_ALIGNED):
        self.validation_config = validation_config or TempoValidationConfig()
        
        # Validate initial tempo before calling parent
        initial_bpm = 60_000_000 / initial_tempo
        if not (self.validation_config.min_tempo_bpm <= initial_bpm <= 
                self.validation_config.max_tempo_bpm):
            raise TempoValidationError(
                f"Initial tempo {initial_bpm:.1f} BPM outside valid range "
                f"[{self.validation_config.min_tempo_bpm}, "
                f"{self.validation_config.max_tempo_bpm}]"
            )
            
        super().__init__(initial_tempo, ticks_per_beat)
        self.optimization_strategy = optimization_strategy
        
        # Enhanced features
        self.enhanced_changes = [TempoChange(0, initial_tempo)]
        self.pattern_tempos = {}
        self.loop_points = {}
        self._frame_cache = {}
        self.optimization_stats = defaultdict(int)
        
    def add_tempo_change(self, tick: int, tempo: int, 
                        change_type: TempoChangeType = TempoChangeType.IMMEDIATE,
                        duration_ticks: int = 0, curve_factor: float = 1.0,
                        pattern_id: Optional[str] = None):
        """Add a tempo change with enhanced features"""
        # Don't allow changes at tick 0 (reserved for initial tempo)
        if tick == 0:
            raise TempoValidationError("Cannot add tempo change at tick 0")
            
        change = TempoChange(tick, tempo, change_type, duration_ticks, 
                           curve_factor, pattern_id)
        
        # Validate the change
        self._validate_tempo_change(change)
        
        # Add to enhanced changes
        self.enhanced_changes.append(change)
        self.enhanced_changes.sort(key=lambda x: x.tick)
        
        # Convert to base class format for compatibility
        if change_type == TempoChangeType.IMMEDIATE:
            # Update base class tempo changes
            super().add_tempo_change(tick, tempo)
        else:
            # Create intermediate steps for gradual changes
            self._create_gradual_change_steps(change)
            
        # Clear caches
        self._time_cache = {}
        self._frame_cache = {}
        
    def get_tempo_at_tick(self, tick: int) -> int:
        """Override to ensure correct tempo retrieval"""
        # Use parent class implementation for accurate tempo lookup
        return super().get_tempo_at_tick(tick)
        
    def _validate_tempo_change(self, change: TempoChange):
        """Validate a tempo change against configuration rules"""
        # First check BPM range
        bpm = 60_000_000 / change.tempo
        if not (self.validation_config.min_tempo_bpm <= bpm <= 
                self.validation_config.max_tempo_bpm):
            raise TempoValidationError(
                f"Tempo {bpm:.1f} BPM outside valid range "
                f"[{self.validation_config.min_tempo_bpm}, "
                f"{self.validation_config.max_tempo_bpm}]"
            )
            
        # Then check duration if applicable
        if change.duration_ticks > 0:
            frames = self.get_frame_for_tick(change.duration_ticks)
            if not (self.validation_config.min_duration_frames <= frames <= 
                    self.validation_config.max_duration_frames):
                raise TempoValidationError(
                    f"Change duration {frames} frames outside valid range "
                    f"[{self.validation_config.min_duration_frames}, "
                    f"{self.validation_config.max_duration_frames}]"
                )
                
        # Finally check tempo change ratio for non-initial changes
        if change.tick > 0:  # Skip ratio check for initial tempo
            prev_tempo = self.get_tempo_at_tick(change.tick - 1)
            if prev_tempo > 0:  # Only check ratio if we have a valid previous tempo
                ratio = max(change.tempo / prev_tempo, prev_tempo / change.tempo)
                if ratio > self.validation_config.max_tempo_change_ratio:
                    raise TempoValidationError(
                        f"Tempo change ratio {ratio:.2f} exceeds maximum "
                        f"{self.validation_config.max_tempo_change_ratio}"
                    )
                    
    def _create_gradual_change_steps(self, change: TempoChange):
        """Create intermediate steps for gradual tempo changes"""
        if change.duration_ticks <= 0:
            return
            
        start_tempo = self.get_tempo_at_tick(change.tick)
        steps = max(1, change.duration_ticks // (self.ticks_per_beat // 4))
        
        for i in range(steps + 1):
            current_tick = change.tick + (i * change.duration_ticks // steps)
            progress = i / steps
            
            if change.change_type == TempoChangeType.LINEAR:
                current_tempo = self._calculate_linear_tempo(
                    start_tempo, change.tempo, progress
                )
            elif change.change_type == TempoChangeType.CURVE:
                current_tempo = self._calculate_curved_tempo(
                    start_tempo, change.tempo, progress, change.curve_factor
                )
            else:
                current_tempo = change.tempo
                
            # Update base TempoMap's tempo changes
            if i > 0:  # Skip first step as it's already at the start tempo
                super().add_tempo_change(current_tick, current_tempo)
            
    def _calculate_linear_tempo(self, start_tempo: int, end_tempo: int, 
                              progress: float) -> int:
        """Calculate intermediate tempo for linear changes"""
        return int(start_tempo + (end_tempo - start_tempo) * progress)
        
    def _calculate_curved_tempo(self, start_tempo: int, end_tempo: int, 
                              progress: float, curve_factor: float) -> int:
        """Calculate intermediate tempo for curved changes"""
        curved_progress = pow(progress, curve_factor)
        return int(start_tempo + (end_tempo - start_tempo) * curved_progress)
        
    def _calculate_pattern_sync_tempo(self, start_tempo: int, end_tempo: int, 
                                    progress: float) -> int:
        """Calculate tempo for pattern-synchronized changes using smoothstep"""
        smooth_progress = progress * progress * (3 - 2 * progress)
        return int(start_tempo + (end_tempo - start_tempo) * smooth_progress)
        
    def add_pattern_tempo(self, pattern_id: str, base_tempo: int, 
                         variations: List[TempoChange] = None):
        """Add pattern-specific tempo information"""
        self.pattern_tempos[pattern_id] = PatternTempoInfo(
            pattern_id, base_tempo, variations or []
        )
        
    def register_loop_point(self, loop_id: str, start_tick: int, end_tick: int):
        """Register tempo state for loop points"""
        start_tempo = self.get_tempo_at_tick(start_tick)
        end_tempo = self.get_tempo_at_tick(end_tick)
        
        self.loop_points[loop_id] = {
            'start': {'tick': start_tick, 'tempo': start_tempo},
            'end': {'tick': end_tick, 'tempo': end_tempo}
        }
        
    def get_enhanced_tempo_at_tick(self, tick: int, 
                                  pattern_context: Optional[str] = None) -> int:
        """Get tempo at tick, considering pattern context if provided"""
        base_tempo = self.get_tempo_at_tick(tick)
        
        if pattern_context and pattern_context in self.pattern_tempos:
            pattern_info = self.pattern_tempos[pattern_context]
            # Apply pattern-specific variations
            for variation in pattern_info.variations:
                if variation.tick <= tick <= variation.end_tick:
                    progress = (tick - variation.tick) / variation.duration_ticks
                    return self._calculate_pattern_sync_tempo(
                        base_tempo, variation.tempo, progress
                    )
        
        return base_tempo
        
    def optimize_tempo_changes(self):
        """Optimize tempo changes based on selected strategy"""
        if self.optimization_strategy == TempoOptimizationStrategy.MINIMIZE_CHANGES:
            self._minimize_tempo_changes()
        elif self.optimization_strategy == TempoOptimizationStrategy.SMOOTH_TRANSITIONS:
            self._smooth_tempo_transitions()
        elif self.optimization_strategy == TempoOptimizationStrategy.FRAME_ALIGNED:
            self._align_to_frames()
            
        # Clear caches after optimization
        self._time_cache = {}
        self._frame_cache = {}
        
    def _minimize_tempo_changes(self):
        """Reduce number of tempo changes by combining similar changes"""
        i = 0
        while i < len(self.tempo_changes) - 1:
            current_tempo = self.tempo_changes[i][1]
            next_tempo = self.tempo_changes[i + 1][1]
            
            if abs(current_tempo - next_tempo) / current_tempo < 0.05:
                # Combine changes if difference is less than 5%
                self.tempo_changes.pop(i + 1)
                self.optimization_stats['changes_combined'] += 1
            else:
                i += 1
                
    def _smooth_tempo_transitions(self):
        """Add intermediate steps for large tempo changes"""
        new_changes = []
        
        for i in range(len(self.tempo_changes) - 1):
            current_tick, current_tempo = self.tempo_changes[i]
            next_tick, next_tempo = self.tempo_changes[i + 1]
            new_changes.append((current_tick, current_tempo))
            
            ratio = max(current_tempo / next_tempo, next_tempo / current_tempo)
            
            if ratio > 1.5:  # Add intermediate steps for large changes
                steps = int(ratio * 2)
                step_ticks = (next_tick - current_tick) / steps
                
                for step in range(1, steps):
                    progress = step / steps
                    intermediate_tempo = self._calculate_linear_tempo(
                        current_tempo, next_tempo, progress
                    )
                    intermediate_tick = current_tick + int(step * step_ticks)
                    new_changes.append((intermediate_tick, intermediate_tempo))
                    self.optimization_stats['smoothing_steps_added'] += 1
                    
        new_changes.append(self.tempo_changes[-1])
        self.tempo_changes = new_changes
        
    def _align_to_frames(self):
        """Align tempo changes with frame boundaries"""
        aligned_changes = []
        
        for tick, tempo in self.tempo_changes:
            original_tick = tick
            frame_time = self.calculate_time_ms(0, tick)
            frame_number = frame_time / FRAME_MS
            aligned_frame = round(frame_number)
            aligned_time = aligned_frame * FRAME_MS
            
            # Find tick closest to aligned frame time
            aligned_tick = self._find_tick_at_time(aligned_time)
            
            if aligned_tick != original_tick:
                self.optimization_stats['frame_alignments'] += 1
                
            aligned_changes.append((aligned_tick, tempo))
            
        self.tempo_changes = aligned_changes
        
    def _find_tick_at_time(self, target_time_ms: float) -> int:
        """Binary search to find tick at given time"""
        if not self.tempo_changes:
            return 0
            
        left, right = 0, max(tick for tick, _ in self.tempo_changes)
        
        while left <= right:
            mid = (left + right) // 2
            time = self.calculate_time_ms(0, mid)
            
            if abs(time - target_time_ms) < 0.1:  # Within 0.1ms
                return mid
            elif time < target_time_ms:
                left = mid + 1
            else:
                right = mid - 1
                
        return left
        
    def get_optimization_Stats(self) -> Dict:
        """Get statistics about optimization operations"""
        return dict(self.optimization_stats)
        
    def analyze_pattern_tempo_characteristics(self, pattern_id: str) -> Dict:
        """Analyze detailed tempo characteristics of a pattern"""
        if pattern_id not in self.pattern_tempos:
            return {}
            
        pattern_info = self.pattern_tempos[pattern_id]
        analysis = {
            'base_tempo_bpm': 60_000_000 / pattern_info.base_tempo,
            'variation_count': len(pattern_info.variations),
            'tempo_range': {
                'min': float('inf'),
                'max': float('-inf'),
                'avg': 0
            },
            'timing_stability': 0.0,
            'complexity_score': 0
        }
        
        tempos = []
        for var in pattern_info.variations:
            tempo_bpm = 60_000_000 / var.tempo
            tempos.append(tempo_bpm)
            analysis['tempo_range']['min'] = min(
                analysis['tempo_range']['min'], tempo_bpm
            )
            analysis['tempo_range']['max'] = max(
                analysis['tempo_range']['max'], tempo_bpm
            )
            
        if tempos:
            analysis['tempo_range']['avg'] = sum(tempos) / len(tempos)
            
            # Calculate timing stability (lower variance = more stable)
            variance = sum((t - analysis['tempo_range']['avg']) ** 2 
                         for t in tempos) / len(tempos)
            analysis['timing_stability'] = 1.0 / (1.0 + variance)
            
            # Calculate complexity score
            analysis['complexity_score'] = len(pattern_info.variations) + sum(
                2 if var.change_type in 
                [TempoChangeType.CURVE, TempoChangeType.PATTERN_SYNC] else 1
                for var in pattern_info.variations
            )
            
        return analysis
        
    def get_debug_info(self) -> Dict:
        """Enhanced debug information including frame timing and validation"""
        info = super().get_debug_info()
        
        # Add enhanced information
        info["validation_config"] = {
            "min_tempo_bpm": self.validation_config.min_tempo_bpm,
            "max_tempo_bpm": self.validation_config.max_tempo_bpm,
            "min_duration_frames": self.validation_config.min_duration_frames,
            "max_duration_frames": self.validation_config.max_duration_frames,
            "max_tempo_change_ratio": self.validation_config.max_tempo_change_ratio
        }
        
        info["optimization_strategy"] = self.optimization_strategy.value
        info["optimization_stats"] = dict(self.optimization_stats)
        info["pattern_count"] = len(self.pattern_tempos)
        info["loop_points_count"] = len(self.loop_points)
        
        # Enhance tempo change information
        for change_info in info["tempo_changes"]:
            change_info["frame"] = self.get_frame_for_tick(change_info["tick"])
            
        return info


# Backwards compatibility - export the classes that might be imported
__all__ = ['TempoMap', 'EnhancedTempoMap', 'TempoValidationConfig', 
           'TempoChangeType', 'TempoOptimizationStrategy', 'TempoValidationError']
