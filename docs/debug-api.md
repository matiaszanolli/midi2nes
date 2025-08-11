# Debug Tools API Reference

Complete Python API reference for the MIDI2NES debug tools.

## Table of Contents

- [Overview](#overview)
- [Classes](#classes)
- [Data Structures](#data-structures)
- [Functions](#functions)
- [Usage Examples](#usage-examples)
- [Error Handling](#error-handling)

## Overview

The debug tools provide a Python API for programmatic ROM analysis and validation. This is useful for:

- **Automated Testing**: Integrate ROM validation into test suites
- **Build Systems**: Validate ROMs in custom build pipelines  
- **Batch Processing**: Analyze multiple ROMs programmatically
- **Custom Tools**: Build specialized diagnostic tools

## Classes

### `ROMDiagnostics`

Main class for performing ROM diagnostics and analysis.

#### Constructor

```python
ROMDiagnostics(verbose: bool = False)
```

**Parameters:**
- `verbose` (bool): Enable verbose output for detailed pattern analysis

**Example:**
```python
from debug.rom_diagnostics import ROMDiagnostics

# Basic diagnostics
diagnostics = ROMDiagnostics()

# Verbose diagnostics with detailed pattern output
diagnostics = ROMDiagnostics(verbose=True)
```

#### Methods

##### `diagnose_rom(rom_path: str) -> ROMDiagnosticResult`

Performs comprehensive ROM diagnostics and returns detailed results.

**Parameters:**
- `rom_path` (str): Absolute or relative path to the ROM file

**Returns:**
- `ROMDiagnosticResult`: Complete diagnostic results

**Raises:**
- No exceptions - errors are captured in the result object

**Example:**
```python
result = diagnostics.diagnose_rom("game.nes")
print(f"Health: {result.overall_health}")
print(f"Issues: {len(result.issues)}")
```

##### `print_report(result: ROMDiagnosticResult, format: str = "human")`

Prints a formatted diagnostic report.

**Parameters:**
- `result` (ROMDiagnosticResult): Results from `diagnose_rom()`
- `format` (str): Output format - "human" or "json"

**Example:**
```python
result = diagnostics.diagnose_rom("game.nes")
diagnostics.print_report(result)  # Human-readable
diagnostics.print_report(result, "json")  # JSON format
```

## Data Structures

### `ROMDiagnosticResult`

Comprehensive results from ROM analysis. All fields are read-only.

#### Basic Properties

```python
@dataclass
class ROMDiagnosticResult:
    file_path: str              # Path to analyzed ROM file
    file_size: int              # Actual file size in bytes
    is_valid_nes: bool          # True if valid iNES format
    overall_health: str         # Health status: HEALTHY/GOOD/FAIR/POOR/ERROR
```

#### ROM Structure

```python
    prg_banks: int              # Number of PRG banks in header
    chr_banks: int              # Number of CHR banks in header  
    expected_size: int          # Expected file size based on header
    size_mismatch: int          # Difference: actual - expected size
```

#### Content Analysis

```python
    zero_byte_percent: float           # Percentage of zero bytes
    repeated_chunks_percent: float     # Percentage of repeated content
    pattern_data_density: float        # Density of pattern-like data
    assembly_code_score: int           # Assembly pattern score (0-220)
    apu_pattern_count: int             # Number of APU-related patterns found
```

#### Reset Vectors

```python
    reset_vectors: Dict[str, int]      # Vector addresses: {'NMI': addr, 'RESET': addr, 'IRQ': addr}
    reset_vectors_valid: bool          # True if all vectors point to ROM space
```

#### Issue Tracking

```python
    issues: List[str]                  # List of detected issues
    recommendations: List[str]         # Suggested fixes and improvements
```

#### Example Usage

```python
result = diagnostics.diagnose_rom("game.nes")

# Basic health check
if result.overall_health in ['HEALTHY', 'GOOD']:
    print("ROM is ready for distribution")

# Detailed analysis
print(f"File: {result.file_path}")
print(f"Size: {result.file_size} bytes ({result.prg_banks} PRG banks)")
print(f"Zero bytes: {result.zero_byte_percent:.1f}%")
print(f"APU patterns: {result.apu_pattern_count}")

# Check for specific issues
if not result.reset_vectors_valid:
    print("Invalid reset vectors detected!")
    print(f"  NMI: ${result.reset_vectors['NMI']:04X}")
    print(f"  RESET: ${result.reset_vectors['RESET']:04X}")
    print(f"  IRQ: ${result.reset_vectors['IRQ']:04X}")

# Review issues and recommendations
for issue in result.issues:
    print(f"Issue: {issue}")

for rec in result.recommendations:
    print(f"Recommendation: {rec}")
```

## Functions

### `quick_check_rom(rom_path: str, verbose: bool = False) -> bool`

Convenience function for quick ROM health validation.

**Parameters:**
- `rom_path` (str): Path to ROM file
- `verbose` (bool): Enable verbose output

**Returns:**
- `bool`: True if ROM health is HEALTHY or GOOD, False otherwise

**Example:**
```python
from debug import quick_check_rom

if quick_check_rom("game.nes"):
    print("ROM passed health check")
else:
    print("ROM has issues")
```

## Usage Examples

### Basic Health Checking

```python
from debug.rom_diagnostics import ROMDiagnostics

def check_rom_health(rom_path):
    diagnostics = ROMDiagnostics()
    result = diagnostics.diagnose_rom(rom_path)
    
    return {
        'healthy': result.overall_health in ['HEALTHY', 'GOOD'],
        'status': result.overall_health,
        'issues': len(result.issues),
        'size': result.file_size
    }

# Usage
health = check_rom_health("game.nes")
print(f"ROM is {'healthy' if health['healthy'] else 'problematic'}")
```

### Batch ROM Analysis

```python
import os
from debug.rom_diagnostics import ROMDiagnostics

def analyze_rom_directory(directory):
    diagnostics = ROMDiagnostics()
    results = []
    
    for filename in os.listdir(directory):
        if filename.endswith('.nes'):
            rom_path = os.path.join(directory, filename)
            result = diagnostics.diagnose_rom(rom_path)
            results.append({
                'file': filename,
                'health': result.overall_health,
                'size': result.file_size,
                'issues': len(result.issues)
            })
    
    return results

# Analyze all ROMs in a directory
roms = analyze_rom_directory("./roms")
healthy_roms = [r for r in roms if r['health'] in ['HEALTHY', 'GOOD']]
print(f"Found {len(healthy_roms)}/{len(roms)} healthy ROMs")
```

### Custom Validation Rules

```python
from debug.rom_diagnostics import ROMDiagnostics

class CustomROMValidator:
    def __init__(self):
        self.diagnostics = ROMDiagnostics()
        
    def validate_for_distribution(self, rom_path):
        """Strict validation for ROMs ready for distribution"""
        result = self.diagnostics.diagnose_rom(rom_path)
        
        # Distribution requirements
        checks = {
            'valid_format': result.is_valid_nes,
            'size_correct': abs(result.size_mismatch) <= 1,
            'vectors_valid': result.reset_vectors_valid,
            'has_audio': result.apu_pattern_count > 0,
            'low_corruption': result.zero_byte_percent < 50,
            'reasonable_patterns': result.pattern_data_density > 5
        }
        
        passed = all(checks.values())
        
        return {
            'ready_for_distribution': passed,
            'checks': checks,
            'overall_health': result.overall_health,
            'critical_issues': [
                issue for issue in result.issues
                if any(keyword in issue.lower() 
                      for keyword in ['invalid', 'corrupted', 'missing'])
            ]
        }
    
    def validate_for_development(self, rom_path):
        """Relaxed validation for development ROMs"""
        result = self.diagnostics.diagnose_rom(rom_path)
        
        # Development requirements (more lenient)
        return {
            'bootable': result.is_valid_nes and result.reset_vectors_valid,
            'has_content': result.pattern_data_density > 1,
            'health': result.overall_health,
            'warnings': result.issues
        }

# Usage
validator = CustomROMValidator()

# Check if ROM is ready for distribution
dist_check = validator.validate_for_distribution("release.nes")
if dist_check['ready_for_distribution']:
    print("ROM ready for distribution!")
else:
    print("ROM needs fixes before distribution")
    for issue in dist_check['critical_issues']:
        print(f"  - {issue}")

# Check development ROM
dev_check = validator.validate_for_development("dev.nes")
if dev_check['bootable']:
    print("ROM should boot for testing")
```

### Integration with Testing Framework

```python
import unittest
from debug.rom_diagnostics import ROMDiagnostics

class ROMQualityTests(unittest.TestCase):
    def setUp(self):
        self.diagnostics = ROMDiagnostics()
        
    def test_rom_health(self):
        """Test that ROM meets basic health requirements"""
        result = self.diagnostics.diagnose_rom("test.nes")
        
        # Basic health checks
        self.assertTrue(result.is_valid_nes, "ROM must have valid iNES header")
        self.assertIn(result.overall_health, ['HEALTHY', 'GOOD', 'FAIR'], 
                     f"ROM health is {result.overall_health}")
        
    def test_rom_structure(self):
        """Test ROM structure and format"""
        result = self.diagnostics.diagnose_rom("test.nes")
        
        # Structure validation
        self.assertGreater(result.file_size, 0, "ROM must not be empty")
        self.assertGreater(result.prg_banks, 0, "ROM must have PRG banks")
        self.assertTrue(result.reset_vectors_valid, "Reset vectors must be valid")
        
    def test_audio_capability(self):
        """Test that ROM has audio capabilities"""
        result = self.diagnostics.diagnose_rom("test.nes")
        
        # Audio checks
        self.assertGreater(result.apu_pattern_count, 0, 
                          "ROM must contain APU initialization code")
        self.assertGreater(result.pattern_data_density, 1,
                          "ROM must contain reasonable pattern data")
        
    def test_corruption_levels(self):
        """Test that ROM doesn't show signs of corruption"""
        result = self.diagnostics.diagnose_rom("test.nes")
        
        # Corruption checks
        self.assertLess(result.zero_byte_percent, 70,
                       "ROM has too many zero bytes")
        self.assertLess(result.repeated_chunks_percent, 90,
                       "ROM has excessive repetition")

if __name__ == '__main__':
    unittest.main()
```

### Monitoring and Reporting

```python
import json
import time
from debug.rom_diagnostics import ROMDiagnostics

class ROMHealthMonitor:
    def __init__(self):
        self.diagnostics = ROMDiagnostics()
        self.history = []
        
    def monitor_rom(self, rom_path, save_history=True):
        """Monitor ROM health over time"""
        result = self.diagnostics.diagnose_rom(rom_path)
        
        snapshot = {
            'timestamp': int(time.time()),
            'file_path': rom_path,
            'file_size': result.file_size,
            'health': result.overall_health,
            'zero_percent': result.zero_byte_percent,
            'apu_patterns': result.apu_pattern_count,
            'issues_count': len(result.issues),
            'issues': result.issues
        }
        
        if save_history:
            self.history.append(snapshot)
            
        return snapshot
        
    def generate_report(self, rom_paths):
        """Generate comprehensive report for multiple ROMs"""
        report = {
            'generated_at': int(time.time()),
            'total_roms': len(rom_paths),
            'roms': []
        }
        
        health_counts = {'HEALTHY': 0, 'GOOD': 0, 'FAIR': 0, 'POOR': 0, 'ERROR': 0}
        
        for rom_path in rom_paths:
            snapshot = self.monitor_rom(rom_path, save_history=False)
            report['roms'].append(snapshot)
            health_counts[snapshot['health']] += 1
            
        report['health_summary'] = health_counts
        report['healthy_percentage'] = (
            (health_counts['HEALTHY'] + health_counts['GOOD']) / 
            len(rom_paths) * 100
        )
        
        return report
        
    def save_report(self, report, filename):
        """Save report to JSON file"""
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)

# Usage
monitor = ROMHealthMonitor()

# Monitor single ROM over time
for i in range(5):  # Simulate multiple builds
    snapshot = monitor.monitor_rom(f"build_{i}.nes")
    print(f"Build {i}: {snapshot['health']} ({snapshot['issues_count']} issues)")

# Generate batch report
rom_list = ["rom1.nes", "rom2.nes", "rom3.nes"]
report = monitor.generate_report(rom_list)
monitor.save_report(report, "rom_health_report.json")

print(f"Report: {report['healthy_percentage']:.1f}% ROMs are healthy")
```

## Error Handling

The diagnostic tools are designed to be robust and handle errors gracefully:

### File Access Errors

```python
result = diagnostics.diagnose_rom("nonexistent.nes")

if result.overall_health == 'ERROR':
    print(f"Error: {result.issues[0]}")
    # Likely: "ROM file nonexistent.nes not found!"
```

### Invalid ROM Format

```python
result = diagnostics.diagnose_rom("invalid_file.txt")

if not result.is_valid_nes:
    print("Not a valid NES ROM file")
    print(f"Issues: {result.issues}")
    # Likely: "Invalid iNES header!"
```

### Exception Safety

The API never raises exceptions for ROM analysis errors. All errors are captured in the result object:

```python
# This will never raise an exception
try:
    result = diagnostics.diagnose_rom(rom_path)
    # Result always returned, check overall_health for success
    if result.overall_health != 'ERROR':
        print("Analysis completed successfully")
    else:
        print(f"Analysis failed: {result.issues}")
except Exception as e:
    # This should never happen for ROM analysis errors
    print(f"Unexpected error: {e}")
```

### Best Practices

```python
def safe_rom_analysis(rom_path):
    """Example of safe ROM analysis with proper error handling"""
    try:
        diagnostics = ROMDiagnostics()
        result = diagnostics.diagnose_rom(rom_path)
        
        # Check if analysis was successful
        if result.overall_health == 'ERROR':
            return {
                'success': False,
                'error': result.issues[0] if result.issues else 'Unknown error',
                'result': None
            }
            
        # Analysis completed successfully
        return {
            'success': True,
            'error': None,
            'result': result
        }
        
    except Exception as e:
        # Handle unexpected errors
        return {
            'success': False,
            'error': f"Unexpected error: {str(e)}",
            'result': None
        }

# Usage
analysis = safe_rom_analysis("game.nes")
if analysis['success']:
    result = analysis['result']
    print(f"ROM health: {result.overall_health}")
else:
    print(f"Analysis failed: {analysis['error']}")
```

---

For more information, see:
- [User Guide](debug-tools.md)
- [Architecture Overview](debug-architecture.md)
- [Test Suite Documentation](debug-tests.md)
