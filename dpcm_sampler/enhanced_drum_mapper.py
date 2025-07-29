from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import json
import os
from tracker.pattern_detector import DrumPatternDetector
from .dpcm_sample_manager import DPCMSampleManager
from .drum_engine import DEFAULT_MIDI_DRUM_MAPPING, ADVANCED_MIDI_DRUM_MAPPING


@dataclass
class DrumPatternConfig:
    """Configuration for drum pattern detection"""
    min_pattern_length: int = 2
    max_pattern_length: int = 16
    similarity_threshold: float = 0.85
    variation_threshold: float = 0.7
    
    # Pattern detection weights
    timing_weight: float = 0.4
    velocity_weight: float = 0.3
    instrument_weight: float = 0.3
    
    # Pattern scoring parameters
    repetition_weight: float = 0.5
    length_weight: float = 0.3
    consistency_weight: float = 0.2
    
    # Common pattern lengths (in frames)
    preferred_lengths: List[int] = field(default_factory=lambda: [4, 8, 16])
    
    def validate(self):
        """Validate configuration parameters"""
        if not 0 < self.min_pattern_length <= self.max_pattern_length:
            raise ValueError("Invalid pattern length range")
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("Similarity threshold must be between 0 and 1")
        if not 0 <= self.variation_threshold <= 1:
            raise ValueError("Variation threshold must be between 0 and 1")
        
        weights = [self.timing_weight, self.velocity_weight, 
                  self.instrument_weight]
        if not all(0 <= w <= 1 for w in weights) or abs(sum(weights) - 1) > 0.001:
            raise ValueError("Pattern detection weights must sum to 1")
            
        scoring_weights = [self.repetition_weight, self.length_weight, 
                         self.consistency_weight]
        if not all(0 <= w <= 1 for w in scoring_weights) or \
           abs(sum(scoring_weights) - 1) > 0.001:
            raise ValueError("Pattern scoring weights must sum to 1")

@dataclass
class SampleManagerConfig:
    """Configuration for DPCM sample management"""
    max_samples: int = 16
    memory_limit: int = 4096  # in bytes
    
    # Sample allocation parameters
    similarity_threshold: float = 0.85
    cache_size: int = 32
    
    # Sample scoring weights
    usage_weight: float = 0.5
    size_weight: float = 0.3
    similarity_weight: float = 0.2
    
    # Memory optimization
    auto_optimize_threshold: float = 0.9  # Trigger optimization at 90% memory usage
    keep_minimum_samples: int = 4  # Minimum samples to keep during optimization
    
    # Sample similarity comparison
    length_similarity_weight: float = 0.4
    waveform_similarity_weight: float = 0.6
    
    def validate(self):
        """Validate configuration parameters"""
        if self.max_samples < 1 or self.max_samples > 64:
            raise ValueError("max_samples must be between 1 and 64")
        if self.memory_limit < 1024 or self.memory_limit > 16384:
            raise ValueError("memory_limit must be between 1KB and 16KB")
        if not 0 <= self.similarity_threshold <= 1:
            raise ValueError("Similarity threshold must be between 0 and 1")
            
        weights = [self.usage_weight, self.size_weight, self.similarity_weight]
        if not all(0 <= w <= 1 for w in weights) or abs(sum(weights) - 1) > 0.001:
            raise ValueError("Sample scoring weights must sum to 1")
            
        similarity_weights = [self.length_similarity_weight, 
                            self.waveform_similarity_weight]
        if not all(0 <= w <= 1 for w in similarity_weights) or \
           abs(sum(similarity_weights) - 1) > 0.001:
            raise ValueError("Similarity weights must sum to 1")

@dataclass
class DrumMapperConfig:
    """Main configuration for the drum mapping system"""
    pattern_config: DrumPatternConfig = field(default_factory=DrumPatternConfig)
    sample_config: SampleManagerConfig = field(default_factory=SampleManagerConfig)
    
    # Global settings
    frame_rate: int = 60  # From constants.FRAME_RATE_HZ
    use_advanced_mapping: bool = True
    enable_pattern_detection: bool = True
    enable_sample_optimization: bool = True
    
    # Layering options
    max_layers: int = 3
    layer_velocity_scaling: bool = True
    
    def validate(self):
        """Validate the entire configuration"""
        self.pattern_config.validate()
        self.sample_config.validate()
        
        if self.frame_rate <= 0:
            raise ValueError("frame_rate must be positive")
        if self.max_layers < 1:
            raise ValueError("max_layers must be at least 1")
    
    def to_file(self, config_path: str) -> None:
        """Save configuration to JSON file"""
        config_data = {
            'pattern_detection': {
                'min_pattern_length': self.pattern_config.min_pattern_length,
                'max_pattern_length': self.pattern_config.max_pattern_length,
                'similarity_threshold': self.pattern_config.similarity_threshold,
                'variation_threshold': self.pattern_config.variation_threshold,
                'timing_weight': self.pattern_config.timing_weight,
                'velocity_weight': self.pattern_config.velocity_weight,
                'instrument_weight': self.pattern_config.instrument_weight,
                'repetition_weight': self.pattern_config.repetition_weight,
                'length_weight': self.pattern_config.length_weight,
                'consistency_weight': self.pattern_config.consistency_weight,
                'preferred_lengths': self.pattern_config.preferred_lengths
            },
            'sample_management': {
                'max_samples': self.sample_config.max_samples,
                'memory_limit': self.sample_config.memory_limit,
                'similarity_threshold': self.sample_config.similarity_threshold,
                'cache_size': self.sample_config.cache_size,
                'usage_weight': self.sample_config.usage_weight,
                'size_weight': self.sample_config.size_weight,
                'similarity_weight': self.sample_config.similarity_weight,
                'auto_optimize_threshold': self.sample_config.auto_optimize_threshold,
                'keep_minimum_samples': self.sample_config.keep_minimum_samples,
                'length_similarity_weight': self.sample_config.length_similarity_weight,
                'waveform_similarity_weight': self.sample_config.waveform_similarity_weight
            },
            'global_settings': {
                'frame_rate': self.frame_rate,
                'use_advanced_mapping': self.use_advanced_mapping,
                'enable_pattern_detection': self.enable_pattern_detection,
                'enable_sample_optimization': self.enable_sample_optimization,
                'max_layers': self.max_layers,
                'layer_velocity_scaling': self.layer_velocity_scaling
            }
        }
        
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
    
    @classmethod
    def from_file(cls, config_path: str) -> 'DrumMapperConfig':
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
                
            pattern_config = DrumPatternConfig(
                **config_data.get('pattern_detection', {})
            )
            sample_config = SampleManagerConfig(
                **config_data.get('sample_management', {})
            )
            
            global_config = config_data.get('global_settings', {})
            
            return cls(
                pattern_config=pattern_config,
                sample_config=sample_config,
                frame_rate=global_config.get('frame_rate', 60),
                use_advanced_mapping=global_config.get('use_advanced_mapping', True),
                enable_pattern_detection=global_config.get('enable_pattern_detection', True),
                enable_sample_optimization=global_config.get('enable_sample_optimization', True),
                max_layers=global_config.get('max_layers', 3),
                layer_velocity_scaling=global_config.get('layer_velocity_scaling', True)
            )
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")

class EnhancedDrumMapper:
    def __init__(self, dpcm_index_path: str, config: Optional[DrumMapperConfig] = None):
        self.config = config or DrumMapperConfig()
        self.config.validate()
        
        self.pattern_detector = DrumPatternDetector(
            min_pattern_length=self.config.pattern_config.min_pattern_length,
            max_pattern_length=self.config.pattern_config.max_pattern_length
        )
        
        self.sample_manager = DPCMSampleManager(
            max_samples=self.config.sample_config.max_samples,
            memory_limit=self.config.sample_config.memory_limit
        )
        
        self.dpcm_index_path = dpcm_index_path
        self.sample_index = self._load_sample_index()
        
    def _load_sample_index(self) -> Dict:
        """Load and validate the DPCM sample index"""
        try:
            with open(self.dpcm_index_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"DPCM index file not found: {self.dpcm_index_path}"
            )
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Invalid JSON in DPCM index: {self.dpcm_index_path}", 
                e.doc, e.pos
            )
            
    def map_drums(self, midi_events: Dict, 
                 use_advanced: bool = True) -> Tuple[List[Dict], List[Dict]]:
        """
        Enhanced drum mapping with pattern detection and smart sample allocation
        
        Args:
            midi_events: Dictionary of MIDI drum events
            use_advanced: Whether to use advanced mapping features
            
        Returns:
            Tuple of (dpcm_events, noise_events)
        """
        # Detect patterns first
        patterns = {}
        for channel, events in midi_events.items():
            if events:  # Only analyze non-empty channels
                patterns[channel] = self.pattern_detector.detect_drum_patterns(events)
                
        dpcm_events = []
        noise_events = []
        
        mapping = (ADVANCED_MIDI_DRUM_MAPPING if use_advanced 
                  else DEFAULT_MIDI_DRUM_MAPPING)
        
        # Track pattern instances for optimization
        pattern_instances = defaultdict(list)
        
        for ch, events in midi_events.items():
            channel_patterns = patterns.get(ch, {})
            
            for e in events:
                if e.get('velocity', 0) == 0:
                    continue
                    
                midi_note = e['note']
                velocity = e['velocity']
                frame = e['frame']
                
                # Check if this event is part of a pattern
                pattern_info = self._find_pattern_for_event(
                    frame, channel_patterns
                )
                
                if pattern_info:
                    # Handle pattern-based sample allocation
                    events_list = self._handle_pattern_event(
                        pattern_info, midi_note, velocity, frame
                    )
                    dpcm_events.extend(events_list)
                    continue
                
                # Regular event handling
                sample_name = None
                if use_advanced and midi_note in mapping:
                    sample_name = self._get_advanced_sample(
                        mapping[midi_note], velocity
                    )
                else:
                    sample_name = mapping.get(midi_note)
                    
                if sample_name and sample_name in self.sample_index:
                    sample_data = self.sample_index[sample_name]
                    
                    # Use sample manager for allocation
                    allocated_sample = self.sample_manager.allocate_sample(
                        sample_name, sample_data
                    )
                    
                    dpcm_events.append({
                        "frame": frame,
                        "sample_id": allocated_sample['id'],
                        "velocity": velocity
                    })
                    
                    # Handle layered samples if any
                    if use_advanced and "layers" in mapping.get(midi_note, {}):
                        self._handle_layered_samples(
                            mapping[midi_note]["layers"],
                            frame,
                            velocity,
                            dpcm_events
                        )
                else:
                    noise_events.append({
                        "frame": frame,
                        "velocity": velocity
                    })
                    
        return dpcm_events, noise_events
        
    def _find_pattern_for_event(self, frame: int, 
                               channel_patterns: Dict) -> Optional[Dict]:
        """Find if an event at given frame belongs to a pattern"""
        for pattern_id, pattern_info in channel_patterns.items():
            for match in pattern_info['matches']:
                pattern_length = len(pattern_info['template'])
                if match <= frame < match + pattern_length:
                    return {
                        'id': pattern_id,
                        'info': pattern_info,
                        'position': frame - match
                    }
        return None
        
    def _handle_pattern_event(self, pattern_info: Dict, 
                            midi_note: int, 
                            velocity: int, 
                            frame: int) -> List[Dict]:
        """Handle sample allocation for pattern-based events"""
        events = []
        pattern_id = pattern_info['id']
        template = pattern_info['info']['template']
        position = pattern_info['position']
        
        # Get template note and velocity
        template_note, template_vel = template[position]
        
        # Use template velocity as a reference
        velocity_ratio = velocity / template_vel
        
        # Try to reuse previously allocated samples for this pattern
        sample_name = self._get_advanced_sample(
            ADVANCED_MIDI_DRUM_MAPPING.get(template_note, {}),
            velocity
        )
        
        if sample_name and sample_name in self.sample_index:
            sample_data = self.sample_index[sample_name]
            allocated_sample = self.sample_manager.allocate_sample(
                sample_name, sample_data
            )
            
            events.append({
                "frame": frame,
                "sample_id": allocated_sample['id'],
                "velocity": int(velocity),
                "pattern_id": pattern_id
            })
            
        return events
        
    def _get_advanced_sample(self, drum_config: Dict, 
                           velocity: int) -> Optional[str]:
        """Get appropriate sample name based on velocity and config"""
        if not drum_config:
            return None
            
        sample_name = drum_config.get("primary")
        
        # Check velocity ranges
        for (v_min, v_max), v_sample in drum_config.get("velocity_ranges", {}).items():
            if v_min <= velocity <= v_max:
                sample_name = v_sample
                break
                
        return sample_name
        
    def _handle_layered_samples(self, layers: List[str], 
                              frame: int, 
                              velocity: int,
                              events: List[Dict]) -> None:
        """Handle layered samples allocation"""
        for layer in layers:
            if layer in self.sample_index:
                sample_data = self.sample_index[layer]
                allocated_sample = self.sample_manager.allocate_sample(
                    layer, sample_data
                )
                
                events.append({
                    "frame": frame,
                    "sample_id": allocated_sample['id'],
                    "velocity": velocity
                })

# Update the existing map_drums_to_dpcm function to use the new system
def map_drums_to_dpcm(midi_events: Dict, 
                     dpcm_index_path: str, 
                     use_advanced: bool = True) -> Tuple[List[Dict], List[Dict]]:
    """
    Enhanced version of the original map_drums_to_dpcm function
    using the new pattern detection and sample management system
    """
    mapper = EnhancedDrumMapper(dpcm_index_path)
    return mapper.map_drums(midi_events, use_advanced)
