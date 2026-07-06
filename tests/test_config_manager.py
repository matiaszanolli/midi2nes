"""Tests for the configuration management system."""

import unittest
import tempfile
import os
from pathlib import Path
import yaml

from config.config_manager import ConfigManager, ProcessingConfig, ExportConfig, PerformanceConfig
from core.exceptions import ConfigurationError


class TestConfigManager(unittest.TestCase):
    """Test configuration management functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "test_config.yaml"
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_default_config_loading(self):
        """Test loading default configuration."""
        config = ConfigManager()
        
        # Check that basic configuration values are loaded
        self.assertEqual(config.get("processing.pattern_detection.min_length"), 3)
        self.assertEqual(config.get("performance.max_memory_mb"), 512)
        self.assertTrue(config.get("export.ca65.standalone_mode"))
    
    def test_config_file_creation_and_loading(self):
        """Test creating and loading configuration files."""
        # Create default config
        config = ConfigManager()
        config.copy_default_config_to(self.config_path)
        
        # Verify file was created
        self.assertTrue(self.config_path.exists())
        
        # Load the created config
        loaded_config = ConfigManager(self.config_path)
        self.assertEqual(loaded_config.get("processing.pattern_detection.min_length"), 3)
    
    def test_config_get_set(self):
        """Test getting and setting configuration values."""
        config = ConfigManager()
        
        # Test getting existing value
        self.assertEqual(config.get("processing.pattern_detection.min_length"), 3)
        
        # Test getting non-existent value with default
        self.assertEqual(config.get("nonexistent.key", "default"), "default")
        
        # Test setting value
        config.set("processing.pattern_detection.min_length", 5)
        self.assertEqual(config.get("processing.pattern_detection.min_length"), 5)
        
        # Test setting nested value
        config.set("new.nested.key", "value")
        self.assertEqual(config.get("new.nested.key"), "value")
    
    def test_config_validation(self):
        """Test configuration validation."""
        config = ConfigManager()
        
        # Valid configuration should pass
        self.assertTrue(config.validate())
        
        # Invalid min_length should fail
        config.set("processing.pattern_detection.min_length", -1)
        with self.assertRaises(ValueError):
            config.validate()
        
        # Invalid similarity threshold should fail
        config = ConfigManager()
        config.set("processing.pattern_detection.similarity_threshold", 1.5)
        with self.assertRaises(ValueError):
            config.validate()
        
        # Invalid memory limit should fail
        config = ConfigManager()
        config.set("performance.max_memory_mb", 10)  # Too low
        with self.assertRaises(ValueError):
            config.validate()

    def test_pattern_detection_sampling_caps_default(self):
        """Regression (#219): sampling caps ship as config keys with the same
        values as the hardcoded tracker/pattern_detector.py defaults."""
        config = ConfigManager()
        self.assertEqual(config.get("processing.pattern_detection.max_events"), 1000)
        self.assertEqual(config.get("processing.pattern_detection.max_pattern_events"), 15000)

    def test_pattern_detection_sampling_caps_validation(self):
        """Regression (#219): non-positive/non-int sampling caps must fail
        validation, same treatment as the existing min_length/similarity_threshold checks."""
        config = ConfigManager()
        config.set("processing.pattern_detection.max_events", 0)
        with self.assertRaises(ValueError):
            config.validate()

        config = ConfigManager()
        config.set("processing.pattern_detection.max_pattern_events", -5)
        with self.assertRaises(ValueError):
            config.validate()

        config = ConfigManager()
        config.set("processing.pattern_detection.max_events", 2500)
        self.assertTrue(config.validate())

    def test_config_save_load_roundtrip(self):
        """Test saving and loading configuration preserves values."""
        config = ConfigManager()
        
        # Modify some values
        config.set("processing.pattern_detection.min_length", 7)
        config.set("performance.max_memory_mb", 1024)
        config.set("export.nsf.load_address", 0x9000)
        
        # Save to file
        config.save(self.config_path)
        
        # Load from file
        loaded_config = ConfigManager(self.config_path)
        
        # Verify values were preserved
        self.assertEqual(loaded_config.get("processing.pattern_detection.min_length"), 7)
        self.assertEqual(loaded_config.get("performance.max_memory_mb"), 1024)
        self.assertEqual(loaded_config.get("export.nsf.load_address"), 0x9000)
    
    def test_dataclass_configs(self):
        """Test getting configuration as dataclass objects."""
        config = ConfigManager()
        
        # Test processing config
        proc_config = config.get_processing_config()
        self.assertIsInstance(proc_config, ProcessingConfig)
        self.assertEqual(proc_config.pattern_detection["min_length"], 3)
        
        # Test export config
        export_config = config.get_export_config()
        self.assertIsInstance(export_config, ExportConfig)
        self.assertTrue(export_config.ca65["standalone_mode"])
        
        # Test performance config
        perf_config = config.get_performance_config()
        self.assertIsInstance(perf_config, PerformanceConfig)
        self.assertEqual(perf_config.max_memory_mb, 512)
    
    def test_yaml_structure(self):
        """Test that generated YAML has correct structure."""
        config = ConfigManager()
        config.copy_default_config_to(self.config_path)
        
        # Load and verify YAML structure
        with open(self.config_path, 'r') as f:
            yaml_data = yaml.safe_load(f)
        
        # Check main sections exist
        expected_sections = ["processing", "export", "performance", "quality", "validation", "development"]
        for section in expected_sections:
            self.assertIn(section, yaml_data)
        
        # Check nested structure
        self.assertIn("pattern_detection", yaml_data["processing"])
        self.assertIn("ca65", yaml_data["export"])
        self.assertIn("nsf", yaml_data["export"])
    
    def test_missing_config_file(self):
        """Regression (#267/PL-07): a --config path that is given but does
        not exist must raise ConfigurationError, not silently fall back to
        defaults -- silent fallback let `config validate <typo'd path>`
        report a nonexistent file as valid."""
        non_existent_path = Path(self.temp_dir) / "missing.yaml"

        with self.assertRaises(ConfigurationError):
            ConfigManager(non_existent_path)

    def test_no_config_path_falls_back_to_defaults(self):
        """No path given at all (the normal no-config-file case) must still
        load defaults without error -- only a given-but-missing path (above)
        is an error."""
        config = ConfigManager()
        self.assertEqual(config.get("processing.pattern_detection.min_length"), 3)
    
    def test_invalid_yaml_file(self):
        """Regression (#125/SAFE-08): malformed YAML must raise the dedicated
        ConfigurationError (already defined for this, previously unused),
        not a bare ValueError that can't be distinguished from other bugs."""
        # Create invalid YAML file
        invalid_yaml = "invalid: yaml: content: ["
        with open(self.config_path, 'w') as f:
            f.write(invalid_yaml)

        with self.assertRaises(ConfigurationError):
            ConfigManager(self.config_path)

    def test_unreadable_config_file_raises_configuration_error(self):
        """A file-system error (not malformed YAML) reaching _load_from_file
        must also raise ConfigurationError, not propagate the raw OSError."""
        # A directory 'exists()'s but open() raises IsADirectoryError (OSError).
        with self.assertRaises(ConfigurationError):
            ConfigManager(Path(self.temp_dir))


if __name__ == '__main__':
    unittest.main()
