"""
Configuration management for Dazzlelink.
"""

import os
import json
from typing import Any, Dict, Optional

class DazzleLinkConfig:
    """
    Configuration manager for DazzleLink settings.
    Handles loading and merging preferences from multiple sources.
    """
    # Default configuration
    DEFAULT_CONFIG = {
        "default_mode": "info",  # Options: info, open, auto
        "make_executable": True,
        "keep_originals": True,
        "recursive_scan": True
    }
    
    # Modes available
    VALID_MODES = ["info", "open", "auto"]
    
    def __init__(self):
        self.config = self.DEFAULT_CONFIG.copy()
        self._load_global_config()
    
    def _load_global_config(self):
        """Load the global configuration file if it exists"""
        global_config_path = os.path.expanduser("~/.dazzlelinkrc.json")
        self._load_config_file(global_config_path, "global")
    
    def load_directory_config(self, directory=None):
        """
        Load directory-specific configuration if available
        
        Args:
            directory (str, optional): Directory to check for config.
                If None, uses current directory.
        """
        if directory is None:
            directory = os.getcwd()
        
        dir_config_path = os.path.join(directory, ".dazzlelink_config.json")
        self._load_config_file(dir_config_path, "directory")
    
    def _load_config_file(self, config_path, config_type):
        """
        Load configuration from a file and merge with current config
        
        Args:
            config_path (str): Path to the configuration file
            config_type (str): Type of configuration (for error messages)
        """
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                
                # Validate and merge configuration
                for key, value in file_config.items():
                    if key in self.config:
                        if key == "default_mode" and value not in self.VALID_MODES:
                            print(f"WARNING: Invalid mode '{value}' in {config_type} config, using default")
                        else:
                            self.config[key] = value
                    # Silently ignore unknown keys for forward compatibility
            
            except json.JSONDecodeError:
                print(f"WARNING: Invalid JSON in {config_type} configuration file: {config_path}")
            except Exception as e:
                print(f"WARNING: Error reading {config_type} configuration: {str(e)}")
    
    def load_link_config(self, link_data):
        """
        Load configuration from a dazzlelink's embedded data
        
        Args:
            link_data (dict): Link data containing configuration
        """
        if "config" in link_data:
            for key, value in link_data["config"].items():
                if key in self.config:
                    self.config[key] = value
    
    def apply_args(self, args):
        """
        Apply command-line arguments, overriding other settings
        
        Args:
            args (Namespace): Parsed command-line arguments
        """
        # Map argument names to config keys
        arg_map = {
            "mode": "default_mode",
            "executable": "make_executable",
            "keep_originals": "keep_originals",
            "no_recursive": "recursive_scan"
        }
        
        # Override with command-line arguments if provided
        for arg_name, config_key in arg_map.items():
            if hasattr(args, arg_name) and getattr(args, arg_name) is not None:
                value = getattr(args, arg_name)
                
                # Handle inverted boolean flags
                if arg_name == "no_recursive":
                    self.config["recursive_scan"] = not value
                else:
                    self.config[config_key] = value
    
    def get(self, key, default=None):
        """Get a configuration value"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """Set a configuration value"""
        if key in self.config:
            self.config[key] = value
    
    def save_global_config(self):
        """Save the current configuration as global config"""
        config_path = os.path.expanduser("~/.dazzlelinkrc.json")
        return self._save_config_file(config_path)
    
    def save_directory_config(self, directory=None):
        """Save the current configuration as directory config"""
        if directory is None:
            directory = os.getcwd()
        
        config_path = os.path.join(directory, ".dazzlelink_config.json")
        return self._save_config_file(config_path)
    
    def _save_config_file(self, config_path):
        """Save configuration to a file"""
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"ERROR: Failed to save configuration: {str(e)}")
            return False