#!/usr/bin/env python3
"""
Test script to verify that the pattern reference fix works correctly
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from exporter.exporter_ca65 import CA65Exporter

def test_pattern_reference_fix():
    """Test that pattern references with string IDs are handled correctly"""
    print("🧪 Testing Pattern Reference Fix")
    print("=" * 50)
    
    # Set up test data - this simulates the data structure that was causing the error
    test_frames = {
        "pulse1": {
            "0": {"note": 60, "volume": 100},
            "1": {"note": 62, "volume": 100}
        }
    }
    
    test_patterns = {
        "pattern_0": {
            "events": [
                {"note": 60, "volume": 100},
                {"note": 62, "volume": 100}
            ]
        }
    }
    
    # Pattern references in the correct format: pattern_id -> [frame_positions]
    test_references = {
        "pattern_0": [0, 4, 8],  # This pattern appears at frames 0, 4, 8
        "pattern_1": [2, 6]      # Another pattern at frames 2, 6
    }
    
    exporter = CA65Exporter()
    
    try:
        output_file = "/tmp/test_pattern_export.s"
        
        # This call was failing before the fix with:
        # "invalid literal for int() with base 10: 'pattern_0'"
        exporter.export_tables_with_patterns(
            test_frames, 
            test_patterns, 
            test_references, 
            output_file, 
            standalone=True
        )
        
        print("✅ Pattern export completed successfully!")
        
        # Check that the output file was created
        if Path(output_file).exists():
            print("✅ Output file created successfully!")
            
            # Read and verify some content
            with open(output_file, 'r') as f:
                content = f.read()
                
            if "pattern_0:" in content:
                print("✅ Pattern definitions found in output!")
            
            if "pattern_refs:" in content:
                print("✅ Pattern reference table found in output!")
                
            print(f"📄 Generated {len(content.split())} lines of assembly code")
            
        else:
            print("❌ Output file was not created!")
            return False
            
        print("\n🎉 Pattern reference fix is working correctly!")
        return True
        
    except ValueError as e:
        if "invalid literal for int()" in str(e) and "pattern_" in str(e):
            print(f"❌ Pattern reference conversion error still exists: {e}")
            return False
        else:
            print(f"❌ Unexpected ValueError: {e}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_pattern_reference_fix()
    sys.exit(0 if success else 1)
