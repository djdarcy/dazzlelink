#!/usr/bin/env python3
"""
Dazzlelink - Symbolic Link Preservation Tool

A tool for exporting, importing, and managing symbolic links across
different systems, particularly useful for network shares and cross-platform
environments where native symlinks might not be properly supported.

Usage:
    dazzlelink create <target> <link_name>    Create a new dazzlelink
    dazzlelink export <link_path>             Export a symlink to a dazzlelink
    dazzlelink import <dazzlelink_path>       Import and recreate a symlink from a dazzlelink
    dazzlelink scan <directory>               Scan for symlinks and report
    dazzlelink convert <directory>            Convert all symlinks in directory to dazzlelinks
    dazzlelink mirror <src_dir> <dest_dir>    Mirror directory structure with dazzlelinks
    dazzlelink execute <dazzlelink_path>      Execute/open the target of a dazzlelink
    dazzlelink config                         View or set configuration options

Configuration:
    Global configuration: ~/.dazzlelinkrc.json
    Directory configuration: .dazzlelink_config.json in any directory
    Link-specific configuration: Embedded in each dazzlelink file

Author: Dustin Darcy
"""

import os
import sys
import json
import stat
import shutil
import argparse
import datetime
import subprocess
import time
from pathlib import Path

__version__ = "0.5.0"

# Add debugging support
VERBOSE = os.environ.get('DAZZLELINK_VERBOSE', '0') == '1'
def debug_print(message):
    """Print debug messages if VERBOSE is enabled"""
    if VERBOSE:
        print(f"DEBUG: {message}")

class UNCAdapter:
    """
    A simplified UNC path converter that maps UNC paths to drive letters and vice versa.
    This is particularly useful for handling symlinks on network shares.
    """
    
    def __init__(self):
        """Initialize the adapter with an empty mapping cache."""
        self.mapping: Dict[str, str] = {}
        self.refresh_mapping()
    
    def refresh_mapping(self) -> None:
        """
        Refresh the mapping of UNC paths to drive letters by parsing the output of 'net use'.
        This creates a dictionary where keys are UNC paths and values are drive letters.
        """
        self.mapping = {}
        
        # Only applicable on Windows
        if os.name != 'nt':
            return
            
        try:
            # Use 'net use' to get network mappings
            output = subprocess.check_output(["net", "use"], text=True, stderr=subprocess.STDOUT)
            for line in output.splitlines():
                # Look for lines containing drive mappings: OK Z: \\server\share
                m = re.search(r"^(OK|Disconnected)\s+([A-Z]:)\s+(\\\\\S+)", line, re.IGNORECASE)
                if m:
                    drive_letter = m.group(2).upper()
                    # Ensure drive letter has trailing backslash
                    if not drive_letter.endswith("\\"):
                        drive_letter += "\\"
                    # Store the UNC path (lowercase, no trailing backslash) as the key
                    remote_share = m.group(3).rstrip("\\").lower()
                    self.mapping[remote_share] = drive_letter
                    
            # Debug logging if needed
            if self.mapping:
                logging.debug(f"UNC mappings: {self.mapping}")
        except Exception as e:
            logging.warning(f"Failed to get network mappings: {e}")
    
    def unc_to_drive(self, path: Path) -> Path:
        """
        Convert a UNC path to its corresponding mapped drive path.
        If the path is not a UNC path or doesn't match a known mapping, return it unchanged.
        
        Args:
            path (Path): The path to convert, possibly a UNC path
            
        Returns:
            Path: The converted path using drive letter if possible, otherwise unchanged
        """
        path_str = str(path).replace('/', '\\')
        path_lower = path_str.lower()
        
        # If path doesn't start with \\, it's not a UNC path
        if not path_lower.startswith('\\\\'):
            return path
            
        # Try to find a matching UNC mapping, checking most specific (longest) first
        for unc_prefix in sorted(self.mapping.keys(), key=len, reverse=True):
            if path_lower.startswith(unc_prefix):
                # Replace the UNC prefix with the drive letter
                drive_path = self.mapping[unc_prefix] + path_str[len(unc_prefix):]
                return Path(drive_path)
                
        # No matching mapping found
        return path
    
    def drive_to_unc(self, path: Path) -> Path:
        """
        Convert a mapped drive path to its corresponding UNC path.
        If the path doesn't use a mapped drive, return it unchanged.
        
        Args:
            path (Path): The path to convert, possibly using a mapped drive
            
        Returns:
            Path: The converted UNC path if possible, otherwise unchanged
        """
        path_str = str(path).replace('/', '\\')
        
        # If the path doesn't start with a drive letter, return unchanged
        if not re.match(r'^[A-Z]:\\', path_str, re.IGNORECASE):
            return path
            
        # Extract the drive letter (with backslash)
        drive = path_str[:3].upper()
        
        # Look for the drive in our mapping values
        for unc_path, mapped_drive in self.mapping.items():
            if mapped_drive.upper() == drive:
                # Replace the drive with the UNC path
                unc_path_str = unc_path + path_str[2:]  # path_str[2:] to exclude the drive letter and colon
                return Path(unc_path_str)
                
        # No matching mapping found
        return path
    
    def normalize_path(self, path: Path, prefer_unc: bool = False) -> Path:
        """
        Normalize a path by converting between UNC and drive letter formats.
        
        Args:
            path (Path): The path to normalize
            prefer_unc (bool): If True, prefer UNC paths; otherwise prefer drive paths
            
        Returns:
            Path: The normalized path
        """
        if prefer_unc:
            return self.drive_to_unc(path)
        else:
            return self.unc_to_drive(path)
        
    def convert_path(self, path, to_unc=False):
        """
        Convert between UNC and mapped drive paths
        
        Args:
            path (str or Path): The path to convert
            to_unc (bool): If True, convert to UNC path; otherwise, convert to mapped drive
            
        Returns:
            Path: The converted path
        """
        if not hasattr(self, 'unc_converter'):
            # Import UNC converter if not already initialized
            try:
                from unc_converter import UNCConverter
                self.unc_converter = UNCConverter()
            except ImportError:
                # If UNC converter is not available, return path unchanged
                print("Warning: UNCConverter not available, path conversion disabled")
                return Path(path)
        
        path_obj = Path(path)
        
        try:
            if to_unc:
                # Convert from mapped drive to UNC path
                return self.unc_converter.drive_to_unc(path_obj)
            else:
                # Convert from UNC to mapped drive path
                return self.unc_converter.convert(path_obj)
        except Exception as e:
            # If conversion fails, return original path
            print(f"Warning: Path conversion failed: {e}")
            return path_obj
        
    def _initialize_unc_adapter(self):
        """Initialize the UNC adapter if on Windows and not already initialized"""
        if os.name == 'nt' and not hasattr(self, '_unc_adapter'):
            try:
                # First try to use the UNCAdapter class from this module
                if 'UNCAdapter' in globals():
                    self._unc_adapter = UNCAdapter()
                    debug_print("Initialized UNC adapter from module")
                else:
                    # Try to import UNCAdapter from local file
                    try:
                        script_dir = os.path.dirname(os.path.abspath(__file__))
                        unc_adapter_path = os.path.join(script_dir, 'unc_adapter.py')
                        
                        if os.path.exists(unc_adapter_path):
                            # If file exists in the same directory, import it
                            import importlib.util
                            spec = importlib.util.spec_from_file_location("unc_adapter", unc_adapter_path)
                            unc_adapter_module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(unc_adapter_module)
                            self._unc_adapter = unc_adapter_module.UNCAdapter()
                            debug_print(f"Initialized UNC adapter from local file: {unc_adapter_path}")
                        else:
                            # Try as a regular import
                            try:
                                from unc_adapter import UNCAdapter
                                self._unc_adapter = UNCAdapter()
                                debug_print("Initialized UNC adapter from package")
                            except ImportError:
                                debug_print("UNC adapter not available, path conversion disabled")
                                self._unc_adapter = None
                    except Exception as e:
                        debug_print(f"Failed to initialize UNC adapter: {e}")
                        self._unc_adapter = None
            except Exception as e:
                debug_print(f"Failed to initialize UNC adapter: {e}")
                self._unc_adapter = None

    def _get_path_representations(self, path):
        """
        Get all representations of a path (UNC and drive letter)
        
        Args:
            path (str or Path): The path to get representations for
            
        Returns:
            dict: Dictionary containing the original path and normalized versions
        """
        path_obj = Path(path)
        
        # Initialize with the original path
        representations = {
            "original_path": str(path_obj),
        }
        
        # Add normalized versions on Windows
        if os.name == 'nt':
            # Initialize UNC adapter if needed
            if not hasattr(self, '_unc_adapter') or self._unc_adapter is None:
                try:
                    self._initialize_unc_adapter()
                except Exception as e:
                    debug_print(f"Failed to initialize UNC adapter: {e}")
                    return representations
            
            # If UNC adapter is available, add normalized representations
            if hasattr(self, '_unc_adapter') and self._unc_adapter is not None:
                try:
                    # Add UNC path
                    unc_path = self._unc_adapter.drive_to_unc(path_obj)
                    if str(unc_path) != str(path_obj):
                        representations["unc_path"] = str(unc_path)
                    
                    # Add drive path
                    drive_path = self._unc_adapter.unc_to_drive(path_obj)
                    if str(drive_path) != str(path_obj):
                        representations["drive_path"] = str(drive_path)
                except Exception as e:
                    debug_print(f"Failed to get path representations: {e}")
        
        return representations

    def _normalize_path(self, path, to_unc=False):
        """
        Normalize a path between UNC and drive letter formats
        
        Args:
            path (str or Path): The path to normalize
            to_unc (bool): If True, convert to UNC path; if False, convert to drive letter
            
        Returns:
            Path: The normalized path
        """
        # If not on Windows, return the path unchanged
        if os.name != 'nt':
            return Path(path)
            
        # Initialize UNC adapter if needed
        if not hasattr(self, '_unc_adapter') or self._unc_adapter is None:
            try:
                self._initialize_unc_adapter()
            except Exception as e:
                debug_print(f"Failed to initialize UNC adapter: {e}")
                return Path(path)
        
        # If UNC adapter is not available, return the path unchanged
        if not hasattr(self, '_unc_adapter') or self._unc_adapter is None:
            return Path(path)
            
        # Convert the path
        try:
            path_obj = Path(path)
            if to_unc:
                return self._unc_adapter.drive_to_unc(path_obj)
            else:
                return self._unc_adapter.unc_to_drive(path_obj)
        except Exception as e:
            debug_print(f"Path normalization failed: {e}")
            return Path(path)


class DazzleLinkException(Exception):
    """Base exception for DazzleLink errors"""
    pass

class DazzleLinkData:
    """
    Abstract Data Type (ADT) for working with dazzlelink data.
    
    This class provides a consistent interface for accessing dazzlelink data,
    handling different format versions and maintaining backward compatibility.
    """
    
    def __init__(self, data=None):
        """
        Initialize with existing data or create a new dazzlelink data structure.
        
        Args:
            data (dict, optional): Existing dazzlelink data. If None, creates a new structure.
        """
        if data is None:
            # Create new structure
            self.data = {
                "schema_version": 1,
                "created_by": "DazzleLink v1",
                "creation_timestamp": datetime.datetime.now().timestamp(),
                "creation_date": datetime.datetime.now().isoformat(),
                
                # New dazzlelink metadata section
                "dazzlelink_metadata": {
                    "last_updated_timestamp": datetime.datetime.now().timestamp(),
                    "last_updated_date": datetime.datetime.now().isoformat(),
                    "update_history": ["initial_creation"]
                },
                
                "link": {
                    "original_path": "",
                    "path_representations": {},
                    "target_path": "",
                    "target_representations": {},
                    "type": "unknown",
                    "relative_path": False,
                    "timestamps": {
                        "created": None,
                        "modified": None,
                        "accessed": None,
                        "created_iso": None,
                        "modified_iso": None,
                        "accessed_iso": None
                    },
                    "attributes": {
                        "hidden": False,
                        "system": False,
                        "readonly": False
                    }
                },
                
                "target": {
                    "exists": False,
                    "type": "unknown",
                    "size": None,
                    "checksum": None,
                    "extension": None,
                    "timestamps": {
                        "created": None,
                        "modified": None,
                        "accessed": None,
                        "created_iso": None,
                        "modified_iso": None,
                        "accessed_iso": None
                    }
                },
                
                "security": {
                    "permissions": None,
                    "owner": None,
                    "group": None
                },
                
                "config": {
                    "default_mode": "info",
                    "platform": "unknown"
                }
            }
        else:
            # Use existing data
            self.data = data
    
    # Schema information
    def get_schema_version(self):
        """Get the schema version of the dazzlelink data."""
        return self.data.get("schema_version", 1)
    
    def get_creator(self):
        """Get the creator string of the dazzlelink data."""
        return self.data.get("created_by", "Unknown")
    
    # Creation timestamps
    def get_creation_timestamp(self):
        """Get the creation timestamp of the dazzlelink."""
        return self.data.get("creation_timestamp")
    
    def get_creation_date(self):
        """Get the creation date of the dazzlelink as ISO format string."""
        return self.data.get("creation_date")
    
    # Dazzlelink metadata
    def get_last_updated_timestamp(self):
        """Get the last updated timestamp of the dazzlelink."""
        # Try new format first, fall back to creation timestamp
        dazzlelink_metadata = self.data.get("dazzlelink_metadata", {})
        return dazzlelink_metadata.get("last_updated_timestamp", self.get_creation_timestamp())
    
    def get_last_updated_date(self):
        """Get the last updated date of the dazzlelink as ISO format string."""
        # Try new format first, fall back to creation date
        dazzlelink_metadata = self.data.get("dazzlelink_metadata", {})
        return dazzlelink_metadata.get("last_updated_date", self.get_creation_date())
    
    def get_update_history(self):
        """Get the update history of the dazzlelink."""
        dazzlelink_metadata = self.data.get("dazzlelink_metadata", {})
        return dazzlelink_metadata.get("update_history", ["initial_creation"])
    
    def update_metadata(self, reason="manual_update"):
        """
        Update the dazzlelink metadata to reflect changes.
        
        Args:
            reason (str): Reason for the update.
        """
        now = datetime.datetime.now()
        timestamp = now.timestamp()
        date_str = now.isoformat()
        
        # Ensure dazzlelink_metadata exists
        if "dazzlelink_metadata" not in self.data:
            self.data["dazzlelink_metadata"] = {
                "last_updated_timestamp": timestamp,
                "last_updated_date": date_str,
                "update_history": ["initial_creation", reason]
            }
        else:
            self.data["dazzlelink_metadata"]["last_updated_timestamp"] = timestamp
            self.data["dazzlelink_metadata"]["last_updated_date"] = date_str
            if "update_history" not in self.data["dazzlelink_metadata"]:
                self.data["dazzlelink_metadata"]["update_history"] = ["initial_creation", reason]
            else:
                self.data["dazzlelink_metadata"]["update_history"].append(reason)
    
    # Link information
    def get_link_type(self):
        """Get the type of the link (symlink, file, etc.)."""
        link = self.data.get("link", {})
        return link.get("type", "unknown")
    
    def get_original_path(self):
        """Get the original path of the link."""
        link = self.data.get("link", {})
        return link.get("original_path", "")
    
    def set_original_path(self, path):
        """Set the original path of the link."""
        if "link" not in self.data:
            self.data["link"] = {}
        self.data["link"]["original_path"] = str(path)
    
    def get_target_path(self):
        """Get the target path of the link."""
        # Handle both old and new formats
        if "target_path" in self.data:
            # Old format
            return self.data["target_path"]
        else:
            # New format
            link = self.data.get("link", {})
            return link.get("target_path", "")
    
    def set_target_path(self, path):
        """Set the target path of the link."""
        if "link" not in self.data:
            self.data["link"] = {}
        self.data["link"]["target_path"] = str(path)
    
    def get_path_representations(self):
        """Get all path representations for the link."""
        link = self.data.get("link", {})
        return link.get("path_representations", {"original_path": self.get_original_path()})
    
    def get_target_representations(self):
        """Get all path representations for the target."""
        link = self.data.get("link", {})
        return link.get("target_representations", {"original_path": self.get_target_path()})
    
    # Link timestamps
    def get_link_timestamps(self):
        """Get all timestamps for the original link."""
        link = self.data.get("link", {})
        return link.get("timestamps", {
            "created": None,
            "modified": None,
            "accessed": None,
            "created_iso": None,
            "modified_iso": None,
            "accessed_iso": None
        })
    
    def set_link_timestamps(self, created=None, modified=None, accessed=None):
        """
        Set timestamps for the original link.
        
        Args:
            created (float, optional): Creation timestamp.
            modified (float, optional): Modification timestamp.
            accessed (float, optional): Access timestamp.
        """
        if "link" not in self.data:
            self.data["link"] = {}
        
        if "timestamps" not in self.data["link"]:
            self.data["link"]["timestamps"] = {}
        
        timestamps = self.data["link"]["timestamps"]
        
        if created is not None:
            timestamps["created"] = created
            timestamps["created_iso"] = datetime.datetime.fromtimestamp(created).isoformat() if created else None
        
        if modified is not None:
            timestamps["modified"] = modified
            timestamps["modified_iso"] = datetime.datetime.fromtimestamp(modified).isoformat() if modified else None
        
        if accessed is not None:
            timestamps["accessed"] = accessed
            timestamps["accessed_iso"] = datetime.datetime.fromtimestamp(accessed).isoformat() if accessed else None
    
    # Target information
    def get_target_exists(self):
        """Check if the target exists."""
        target = self.data.get("target", {})
        return target.get("exists", False)
    
    def get_target_type(self):
        """Get the type of the target (file, directory, etc.)."""
        target = self.data.get("target", {})
        return target.get("type", "unknown")
    
    def get_target_size(self):
        """Get the size of the target file."""
        target = self.data.get("target", {})
        return target.get("size")
    
    # Target timestamps
    def get_target_timestamps(self):
        """Get all timestamps for the target."""
        target = self.data.get("target", {})
        if "timestamps" in target:
            return target["timestamps"]
        else:
            # For backward compatibility, create empty timestamps
            return {
                "created": None,
                "modified": None,
                "accessed": None,
                "created_iso": None,
                "modified_iso": None,
                "accessed_iso": None
            }
    
    def set_target_timestamps(self, created=None, modified=None, accessed=None):
        """
        Set timestamps for the target.
        
        Args:
            created (float, optional): Creation timestamp.
            modified (float, optional): Modification timestamp.
            accessed (float, optional): Access timestamp.
        """
        if "target" not in self.data:
            self.data["target"] = {}
        
        if "timestamps" not in self.data["target"]:
            self.data["target"]["timestamps"] = {}
        
        timestamps = self.data["target"]["timestamps"]
        
        if created is not None:
            timestamps["created"] = created
            timestamps["created_iso"] = datetime.datetime.fromtimestamp(created).isoformat() if created else None
        
        if modified is not None:
            timestamps["modified"] = modified
            timestamps["modified_iso"] = datetime.datetime.fromtimestamp(modified).isoformat() if modified else None
        
        if accessed is not None:
            timestamps["accessed"] = accessed
            timestamps["accessed_iso"] = datetime.datetime.fromtimestamp(accessed).isoformat() if accessed else None
    
    # Configuration
    def get_default_mode(self):
        """Get the default execution mode."""
        config = self.data.get("config", {})
        return config.get("default_mode", "info")
    
    def set_default_mode(self, mode):
        """Set the default execution mode."""
        if "config" not in self.data:
            self.data["config"] = {}
        self.data["config"]["default_mode"] = mode
    
    def get_platform(self):
        """Get the platform the dazzlelink was created on."""
        config = self.data.get("config", {})
        return config.get("platform", "unknown")
    
    def set_platform(self, platform):
        """Set the platform the dazzlelink was created on."""
        if "config" not in self.data:
            self.data["config"] = {}
        self.data["config"]["platform"] = platform
    
    # I/O operations
    def to_dict(self):
        """
        Convert to a dictionary suitable for serialization.
        
        Returns:
            dict: The dazzlelink data as a dictionary.
        """
        return self.data
    
    @classmethod
    def from_file(cls, file_path):
        """
        Load dazzlelink data from a file.
        
        Args:
            file_path (str): Path to the dazzlelink file.
            
        Returns:
            DazzleLinkData: A new instance with the loaded data.
            
        Raises:
            ValueError: If the file is not a valid dazzlelink file.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    return cls(data)
                except json.JSONDecodeError:
                    # Try to handle script-embedded format
                    content = f.read()
                    json_start = content.find('# DAZZLELINK_DATA_BEGIN')
                    if json_start != -1:
                        json_text = content[json_start + len('# DAZZLELINK_DATA_BEGIN'):].strip()
                        data = json.loads(json_text)
                        return cls(data)
                    raise ValueError(f"Invalid dazzlelink file: {file_path}")
        except Exception as e:
            raise ValueError(f"Error reading dazzlelink file {file_path}: {str(e)}")
    
    def save_to_file(self, file_path, make_executable=False):
        """
        Save dazzlelink data to a file.
        
        Args:
            file_path (str): Path to save the dazzlelink file.
            make_executable (bool): Whether to make the file executable.
            
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)
                
            if make_executable:
                # TODO: Implement executable script generation
                pass
                
            return True
        except Exception as e:
            print(f"Error saving dazzlelink file {file_path}: {str(e)}")
            return False

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

class DazzleLink:
    """
    Core DazzleLink functionality for handling symbolic links
    across different platforms and environments.
    """
    DAZZLELINK_EXT = '.dazzlelink'
    VERSION = 1

    def __init__(self, config=None):
        self.platform = 'windows' if os.name == 'nt' else 'linux'
        self.config = config or DazzleLinkConfig()
        
            
    def _initialize_unc_adapter(self):
        """Initialize the UNC adapter if on Windows and not already initialized"""
        if os.name == 'nt' and not hasattr(self, '_unc_adapter'):
            try:
                # Try to use the internal UNCAdapter class first
                self._unc_adapter = UNCAdapter()
                debug_print("Initialized internal UNC adapter")
            except Exception as e:
                debug_print(f"Failed to initialize UNC adapter: {e}")
                self._unc_adapter = None

    def _get_path_representations(self, path):
        """
        Get all representations of a path (UNC and drive letter)
        
        Args:
            path (str or Path): The path to get representations for
            
        Returns:
            dict: Dictionary containing the original path and normalized versions
        """
        path_obj = Path(path)
        
        # Initialize with the original path
        representations = {
            "original_path": str(path_obj),
        }
        
        # Add normalized versions on Windows
        if os.name == 'nt':
            # Initialize UNC adapter if needed
            if not hasattr(self, '_unc_adapter') or self._unc_adapter is None:
                try:
                    self._initialize_unc_adapter()
                except Exception as e:
                    debug_print(f"Failed to initialize UNC adapter: {e}")
                    return representations
            
            # If UNC adapter is available, add normalized representations
            if hasattr(self, '_unc_adapter') and self._unc_adapter is not None:
                try:
                    # Add UNC path
                    unc_path = self._unc_adapter.drive_to_unc(path_obj)
                    if str(unc_path) != str(path_obj):
                        representations["unc_path"] = str(unc_path)
                    
                    # Add drive path
                    drive_path = self._unc_adapter.unc_to_drive(path_obj)
                    if str(drive_path) != str(path_obj):
                        representations["drive_path"] = str(drive_path)
                except Exception as e:
                    debug_print(f"Failed to get path representations: {e}")
        
        return representations

    def _normalize_path(self, path, to_unc=False):
        """
        Normalize a path between UNC and drive letter formats
        
        Args:
            path (str or Path): The path to normalize
            to_unc (bool): If True, convert to UNC path; if False, convert to drive letter
            
        Returns:
            Path: The normalized path
        """
        # If not on Windows, return the path unchanged
        if os.name != 'nt':
            return Path(path)
            
        # Initialize UNC adapter if needed
        if not hasattr(self, '_unc_adapter') or self._unc_adapter is None:
            try:
                self._initialize_unc_adapter()
            except Exception as e:
                debug_print(f"Failed to initialize UNC adapter: {e}")
                return Path(path)
        
        # If UNC adapter is not available, return the path unchanged
        if not hasattr(self, '_unc_adapter') or self._unc_adapter is None:
            return Path(path)
            
        # Convert the path
        try:
            path_obj = Path(path)
            if to_unc:
                return self._unc_adapter.drive_to_unc(path_obj)
            else:
                return self._unc_adapter.unc_to_drive(path_obj)
        except Exception as e:
            debug_print(f"Path normalization failed: {e}")
            return Path(path)
    
    """
    Fix for the serialize_link method in DazzleLink class

    The issue is that the create command is failing because it's checking if the source file
    is a symlink, but the source file is not a symlink in the test case. We need to modify
    the serialize_link method to either create a symlink if needed or to skip the symlink check
    when in create mode.

    This fix adds a flag to the serialize_link method to indicate if it should require the source
    to be a symlink. It also adds UNC path support via the UNCConverter.
    """
    def serialize_link(self, link_path, output_path=None, make_executable=None, mode=None, require_symlink=True):
        """
        Serialize a symbolic link to a .dazzlelink file
        
        Args:
            link_path (str): Path to the symbolic link or file/directory to link to
            output_path (str, optional): Output path for the dazzlelink file.
                If None, will use link_path + .dazzlelink
            make_executable (bool, optional): Whether to make the dazzlelink executable.
                If None, uses configuration default.
            mode (str, optional): Default execution mode for this dazzlelink.
                If None, uses configuration default.
            require_symlink (bool, optional): Whether to require link_path to be a symlink.
                If False, will create a dazzlelink directly without checking if link_path is a symlink.
            
        Returns:
            str: Path to the created dazzlelink file
        """
        debug_print(f"serialize_link called with link_path={link_path}, output_path={output_path}, require_symlink={require_symlink}")
        link_path = Path(link_path)
        
        # Important: Do NOT use resolve() here as it follows symlinks
        # Instead, use absolute() to get the absolute path without following symlinks
        link_path = link_path.absolute()
        debug_print(f"Absolute link_path: {link_path}")
        
        # Load directory-specific config
        self.config.load_directory_config(os.path.dirname(str(link_path)))
        
        # Use config defaults if parameters not specified
        if make_executable is None:
            make_executable = self.config.get("make_executable")
        if mode is None:
            mode = self.config.get("default_mode")
        
        # Check if it's a symlink when required
        is_symlink = os.path.islink(link_path)
        debug_print(f"Is {link_path} a symlink? {is_symlink}")
        
        if require_symlink and not is_symlink:
            raise DazzleLinkException(f"{link_path} is not a symbolic link")
        
        try:
            # Initialize UNC methods if needed
            if not hasattr(self, '_initialize_unc_adapter'):
                self._initialize_unc_adapter = lambda: None
                self._get_path_representations = lambda path: {"original_path": str(path)}
            else:
                # If methods exist but need initialization, initialize them
                self._initialize_unc_adapter()
            
            # Get path representations for UNC path handling
            if hasattr(self, '_get_path_representations'):
                path_representations = self._get_path_representations(link_path)
                debug_print(f"Path representations: {path_representations}")
            else:
                path_representations = {"original_path": str(link_path)}
            
            # If it's a symlink, get the target
            if is_symlink:
                target_path = os.readlink(link_path)
                debug_print(f"Symlink target: {target_path}")
                
                # Convert to absolute path if relative
                if not os.path.isabs(target_path):
                    base_dir = os.path.dirname(str(link_path))
                    target_path = os.path.normpath(os.path.join(base_dir, target_path))
                    debug_print(f"Converted relative target to absolute: {target_path}")
            else:
                # If not a symlink, use the link_path itself as the target path
                # IMPORTANT: Do NOT use resolve() here as it would follow symlinks
                target_path = str(link_path)
                debug_print(f"Not a symlink, using path as target: {target_path}")
            
            # Get target path representations for UNC path handling
            if hasattr(self, '_get_path_representations'):
                target_representations = self._get_path_representations(target_path)
                debug_print(f"Target representations: {target_representations}")
            else:
                target_representations = {"original_path": str(target_path)}
            
            # Create a new DazzleLinkData instance
            link_data = DazzleLinkData()
            
            # Set basic link info
            link_data.set_original_path(str(link_path))
            link_data.set_target_path(target_path)
            link_data.set_platform(self.platform)
            link_data.set_default_mode(mode)
            
            # Get timestamps for link and target
            link_timestamps = self._collect_timestamp_info(link_path)
            link_data.set_link_timestamps(
                created=link_timestamps[0],
                modified=link_timestamps[1],
                accessed=link_timestamps[2]
            )
            
            # Collect target timestamps
            target_timestamps = self._collect_target_timestamp_info(target_path)
            link_data.set_target_timestamps(
                created=target_timestamps.get("created"),
                modified=target_timestamps.get("modified"),
                accessed=target_timestamps.get("accessed")
            )
            
            # Update the raw data structure with additional information
            data_dict = link_data.to_dict()
            
            # Add path representations
            if "link" not in data_dict:
                data_dict["link"] = {}
            data_dict["link"]["path_representations"] = path_representations
            data_dict["link"]["target_representations"] = target_representations
            data_dict["link"]["type"] = "symlink" if is_symlink else "file"
            data_dict["link"]["relative_path"] = not os.path.isabs(target_path)
            data_dict["link"]["attributes"] = self._collect_file_attributes(link_path)
            
            # Add target info
            if "target" not in data_dict:
                data_dict["target"] = {}
            target_info = self._collect_target_info(target_path)
            for key, value in target_info.items():
                if key != "timestamps":  # Don't overwrite timestamps
                    data_dict["target"][key] = value
            
            # Add security info
            data_dict["security"] = self._collect_security_info(link_path)
            
            # Validate mode
            if mode not in DazzleLinkConfig.VALID_MODES:
                print(f"WARNING: Invalid mode '{mode}', using default")
                mode = self.config.get("default_mode")
                data_dict["config"]["default_mode"] = mode
            
            if output_path is None:
                output_path = f"{link_path}{self.DAZZLELINK_EXT}"
            else:
                output_path = Path(output_path)
                # Ensure parent directory exists
                os.makedirs(output_path.parent, exist_ok=True)
            
            # Create the dazzlelink file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data_dict, f, indent=2)
            
            if make_executable:
                self._make_dazzlelink_executable(output_path, data_dict)
            
            return output_path
            
        except Exception as e:
            raise DazzleLinkException(f"Failed to serialize link {link_path}: {str(e)}")
        
    def _collect_file_attributes(self, file_path):
        """Collect file attributes in a platform-independent way"""
        attributes = {
            "hidden": False,
            "system": False,
            "readonly": False
        }
        
        try:
            if os.name == 'nt':
                # Windows specific attributes
                stats = os.lstat(file_path)
                if hasattr(stats, 'st_file_attributes'):
                    attributes["hidden"] = bool(stats.st_file_attributes & 0x2)
                    attributes["system"] = bool(stats.st_file_attributes & 0x4)
                    attributes["readonly"] = bool(stats.st_file_attributes & 0x1)
            else:
                # Unix-like attributes
                path = Path(file_path)
                # Hidden files in Unix start with a dot
                attributes["hidden"] = path.name.startswith('.')
                # Check if file is readonly
                attributes["readonly"] = not os.access(file_path, os.W_OK)
        except:
            pass
            
        return attributes
        
    def _collect_target_info(self, target_path):
        """Collect information about the target of a symlink"""
        target_info = {
            "exists": os.path.exists(target_path),
            "type": "unknown",
            "size": None,
            "checksum": None,
            "extension": os.path.splitext(target_path)[1].lower() if os.path.splitext(target_path)[1] else None
        }
        
        try:
            if os.path.exists(target_path):
                if os.path.isdir(target_path):
                    target_info["type"] = "directory"
                    # Count items in directory
                    try:
                        target_info["item_count"] = len(os.listdir(target_path))
                    except:
                        target_info["item_count"] = None
                elif os.path.isfile(target_path):
                    target_info["type"] = "file"
                    target_info["size"] = os.path.getsize(target_path)
                    
                    # Calculate checksum for small files only (avoid performance issues)
                    if os.path.isfile(target_path) and os.path.getsize(target_path) < 1024 * 1024:  # 1MB limit
                        try:
                            import hashlib
                            with open(target_path, 'rb') as f:
                                file_hash = hashlib.md5()
                                chunk = f.read(8192)
                                while chunk:
                                    file_hash.update(chunk)
                                    chunk = f.read(8192)
                                target_info["checksum"] = file_hash.hexdigest()
                        except:
                            pass
        except:
            pass
            
        return target_info
        
    def _collect_security_info(self, file_path):
        """Collect security and permission information"""
        security_info = {
            "permissions": None,
            "owner": None,
            "group": None
        }
        
        try:
            stats = os.lstat(file_path)
            
            if os.name != 'nt':
                # Unix permissions
                security_info["permissions"] = stats.st_mode & 0o777
                security_info["permissions_octal"] = f"{security_info['permissions']:o}"
                
                # Try to get owner and group names
                try:
                    import pwd
                    import grp
                    security_info["owner"] = pwd.getpwuid(stats.st_uid).pw_name
                    security_info["group"] = grp.getgrgid(stats.st_gid).gr_name
                except ImportError:
                    # Fallback to numeric IDs if pwd/grp not available
                    security_info["owner_id"] = stats.st_uid
                    security_info["group_id"] = stats.st_gid
            else:
                # Windows security is complex, just store basic info
                security_info["owner_id"] = stats.st_uid
                
                # Try to get Windows ACL info if available
                try:
                    import win32security
                    security_info["windows_security"] = "Available but not implemented"
                except ImportError:
                    security_info["windows_security"] = "Not available"
        except:
            pass
            
        return security_info
    
    def _set_link_timestamps(self, link_path, timestamp_data, max_attempts=2, verify=True, retry_delay=0.05):
        """
        Set timestamps on a symlink with verification and retry logic.
        
        This is a wrapper around _set_file_times that adds verification and retries
        specifically for symlinks where timestamp setting can be more complex.
        
        Args:
            link_path (str): Path to the symlink
            timestamp_data (dict): Dictionary with 'created', 'modified', and 'accessed' timestamps
            max_attempts (int): Maximum number of retry attempts
            verify (bool): Whether to verify timestamps after setting (can be disabled for batch processing)
            retry_delay (float): Delay in seconds between retry attempts
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not os.name == 'nt':
            debug_print("Advanced symlink timestamp setting only available on Windows")
            return False
            
        if not os.path.exists(link_path):
            debug_print(f"Link does not exist: {link_path}")
            return False
            
        # Extract timestamps
        created_time = timestamp_data.get('created')
        modified_time = timestamp_data.get('modified')
        accessed_time = timestamp_data.get('accessed')
        
        # Ensure we have at least the modified time
        if modified_time is None:
            debug_print("No modification time provided, cannot set timestamps")
            return False
            
        debug_print(f"Setting symlink timestamps: {link_path}")
        debug_print(f"  Created:  {created_time} ({datetime.datetime.fromtimestamp(created_time).isoformat() if created_time else 'None'})")
        debug_print(f"  Modified: {modified_time} ({datetime.datetime.fromtimestamp(modified_time).isoformat() if modified_time else 'None'})")
        debug_print(f"  Accessed: {accessed_time} ({datetime.datetime.fromtimestamp(accessed_time).isoformat() if accessed_time else 'None'})")
        
        # First attempt - just set the timestamps without verification if verification is disabled
        success = self._set_file_times(link_path, modified_time, accessed_time, created_time)
        
        if not success:
            debug_print("Initial timestamp setting failed")
            return False
            
        # If verification is disabled, exit early
        if not verify:
            return True
        
        # Verification needed - start with attempt 1 since we already did initial set
        for attempt in range(1, max_attempts):
            # Verify the timestamps were correctly set
            try:
                import win32file
                
                # Open a handle to the file
                handle = win32file.CreateFile(
                    link_path,
                    win32file.GENERIC_READ,
                    win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
                    None,
                    win32file.OPEN_EXISTING,
                    win32file.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_BACKUP_SEMANTICS | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
                    None
                )
                
                try:
                    # Get the current timestamps
                    actual_created, actual_accessed, actual_modified = win32file.GetFileTime(handle)
                    
                    # Convert to Unix timestamps for easier comparison
                    actual_created_ts = int(actual_created) / 10000000 - 11644473600 if actual_created else None
                    actual_accessed_ts = int(actual_accessed) / 10000000 - 11644473600 if actual_accessed else None
                    actual_modified_ts = int(actual_modified) / 10000000 - 11644473600 if actual_modified else None
                    
                    # Allow a larger tolerance (5 seconds) for timestamp comparisons
                    tolerance = 5.0
                    verified = True
                    
                    # Only check creation and modification times - access time can change frequently
                    # Check creation time (most important)
                    if created_time is not None and actual_created_ts is not None:
                        diff = abs(created_time - actual_created_ts)
                        if diff > tolerance:
                            debug_print(f"  Creation time mismatch: expected={created_time}, actual={actual_created_ts}, diff={diff}")
                            verified = False
                    
                    # Check modification time
                    if modified_time is not None and actual_modified_ts is not None:
                        diff = abs(modified_time - actual_modified_ts)
                        if diff > tolerance:
                            debug_print(f"  Modification time mismatch: expected={modified_time}, actual={actual_modified_ts}, diff={diff}")
                            verified = False
                    
                    if verified:
                        debug_print("Timestamp verification successful")
                        return True
                    
                finally:
                    handle.Close()
                    
            except ImportError:
                debug_print("win32file module not available, cannot verify timestamps")
                # Since we can't verify, assume it worked if _set_file_times reported success
                return success
            except Exception as e:
                debug_print(f"Error verifying timestamps: {str(e)}")
            
            # If we reach here, verification failed - set timestamps again
            debug_print(f"Verification failed, retry attempt {attempt}")
            success = self._set_file_times(link_path, modified_time, accessed_time, created_time)
            if not success:
                debug_print("Timestamp setting failed on retry")
                return False
                
            # Short delay before next verification
            if attempt < max_attempts - 1:
                time.sleep(retry_delay)
        
        # If we reach here, we've used all our attempts
        debug_print(f"Failed to verify timestamps after {max_attempts} attempts")
        # Return true anyway since we did set the timestamps, even if verification failed
        return True
    
    def _collect_timestamp_info(self, file_path):
        """
        Collect timestamp information for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Tuple of (creation_time, modified_time, access_time)
        """
        creation_time = None
        modified_time = None
        access_time = None
        
        try:
            stats = os.lstat(file_path)
            
            # Get the available timestamps
            if hasattr(stats, 'st_ctime'):
                creation_time = stats.st_ctime
                debug_print(f"Collected creation time for {file_path}: {creation_time} ({datetime.datetime.fromtimestamp(creation_time).isoformat()})")
            if hasattr(stats, 'st_mtime'):
                modified_time = stats.st_mtime
                debug_print(f"Collected modified time for {file_path}: {modified_time} ({datetime.datetime.fromtimestamp(modified_time).isoformat()})")
            if hasattr(stats, 'st_atime'):
                access_time = stats.st_atime
                debug_print(f"Collected access time for {file_path}: {access_time} ({datetime.datetime.fromtimestamp(access_time).isoformat()})")
                
        except Exception as e:
            # Default to current time if stats fail
            debug_print(f"Failed to collect timestamps for {file_path}: {str(e)}")
            current_time = datetime.datetime.now().timestamp()
            creation_time = current_time
            modified_time = current_time
            access_time = current_time
            
        return creation_time, modified_time, access_time

    def _collect_target_timestamp_info(self, target_path):
        """
        Collect timestamp information for the target of a symlink.
        
        This is similar to _collect_timestamp_info but specifically for target files,
        and it handles cases where the target might not exist or might be inaccessible.
        
        Args:
            target_path (str): Path to the target file or directory.
            
        Returns:
            dict: Dictionary with timestamp information.
        """
        timestamps = {
            "created": None,
            "modified": None,
            "accessed": None,
            "created_iso": None,
            "modified_iso": None,
            "accessed_iso": None
        }
        
        # Check if target exists
        if not os.path.exists(target_path):
            debug_print(f"Target does not exist, cannot collect timestamps: {target_path}")
            return timestamps
            
        try:
            # Get target stats (without following symlinks if the target itself is a symlink)
            stats = os.stat(target_path)
            
            # Get the available timestamps
            if hasattr(stats, 'st_ctime'):
                timestamps["created"] = stats.st_ctime
                timestamps["created_iso"] = datetime.datetime.fromtimestamp(stats.st_ctime).isoformat()
                debug_print(f"Collected creation time for target {target_path}: {stats.st_ctime} ({timestamps['created_iso']})")
                
            if hasattr(stats, 'st_mtime'):
                timestamps["modified"] = stats.st_mtime
                timestamps["modified_iso"] = datetime.datetime.fromtimestamp(stats.st_mtime).isoformat()
                debug_print(f"Collected modified time for target {target_path}: {stats.st_mtime} ({timestamps['modified_iso']})")
                
            if hasattr(stats, 'st_atime'):
                timestamps["accessed"] = stats.st_atime
                timestamps["accessed_iso"] = datetime.datetime.fromtimestamp(stats.st_atime).isoformat()
                debug_print(f"Collected access time for target {target_path}: {stats.st_atime} ({timestamps['accessed_iso']})")
                
        except Exception as e:
            debug_print(f"Error collecting timestamps for {target_path}: {str(e)}")
            
        return timestamps
        """Collect timestamp information for a file"""
        creation_time = None
        modified_time = None
        access_time = None
        
        try:
            stats = os.lstat(file_path)
            
            # Get the available timestamps
            if hasattr(stats, 'st_ctime'):
                creation_time = stats.st_ctime
            if hasattr(stats, 'st_mtime'):
                modified_time = stats.st_mtime
            if hasattr(stats, 'st_atime'):
                access_time = stats.st_atime
                
        except:
            # Default to current time if stats fail
            current_time = datetime.datetime.now().timestamp()
            creation_time = current_time
            modified_time = current_time
            access_time = current_time
            
        return creation_time, modified_time, access_time

    def recreate_link(self, dazzlelink_path, target_location=None, timestamp_strategy='current', 
                        update_dazzlelink=False, use_live_target=False, batch_mode=False):
        """
        Recreate a symbolic link from a .dazzlelink file
        
        Args:
            dazzlelink_path (str): Path to the dazzlelink file
            target_location (str, optional): Override location for the recreated symlink
            timestamp_strategy (str): Strategy for setting timestamps ('current', 'symlink', 'target', 'preserve-all')
            update_dazzlelink (bool): Whether to update the dazzlelink metadata during recreation
            use_live_target (bool): Whether to check the live target file for timestamps
            batch_mode (bool): If True, optimizes for batch processing (less verification)
            
        Returns:
            str: Path to the created symbolic link
        """
        try:
            # Load the dazzlelink data
            dl_data = DazzleLinkData.from_file(dazzlelink_path)
            
            # Get the target and original paths
            target_path = dl_data.get_target_path()
            original_path = dl_data.get_original_path()
            
            # Determine if target is a directory
            is_dir = dl_data.get_target_type() == "directory"
            
            # Determine where to create the symlink
            if target_location:
                # Use the provided location but keep the original filename
                original_name = os.path.basename(original_path)
                link_path = os.path.join(target_location, original_name)
            else:
                link_path = original_path
            
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(link_path), exist_ok=True)
            
            # Remove existing link/file if it exists
            if os.path.exists(link_path):
                if os.path.isdir(link_path) and not os.path.islink(link_path):
                    shutil.rmtree(link_path)
                else:
                    os.unlink(link_path)
            
            # Create symlink with appropriate method based on OS
            if os.name == 'nt':
                self._create_windows_symlink(target_path, link_path, is_dir)
            else:
                os.symlink(target_path, link_path)
            
            # Verify symlink was created
            if not os.path.exists(link_path):
                raise DazzleLinkException(f"Failed to create symlink at {link_path}")
            
            # Very small delay to ensure symlink creation is complete (helps avoid race conditions)
            # Reduced from 0.1 to 0.01 seconds
            if not batch_mode:
                time.sleep(0.01)
            
            # Apply timestamps based on the selected strategy
            self._apply_timestamp_strategy(link_path, dl_data, timestamp_strategy, use_live_target, batch_mode=batch_mode)
            
            # Verify timestamps were correctly applied (if not current and not in batch mode)
            if timestamp_strategy != 'current' and os.name == 'nt' and not batch_mode:
                self._verify_timestamps(link_path, dl_data, timestamp_strategy, use_live_target)
            
            # Attempt to restore file attributes if available
            self._restore_file_attributes(link_path, dl_data.to_dict())
            
            # Update dazzlelink metadata if requested
            if update_dazzlelink:
                try:
                    # Update dazzlelink metadata
                    dl_data.update_metadata(reason="symlink_recreation")
                    
                    # If we used live target and it was successful, update target timestamps too
                    if use_live_target and timestamp_strategy in ['target', 'preserve-all']:
                        target_path = dl_data.get_target_path()
                        if os.path.exists(target_path):
                            # Get current target timestamps
                            target_timestamps = self._collect_target_timestamp_info(target_path)
                            
                            # Update in the dazzlelink data
                            dl_data.set_target_timestamps(
                                created=target_timestamps.get('created'),
                                modified=target_timestamps.get('modified'),
                                accessed=target_timestamps.get('accessed')
                            )
                    
                    # Save the updated dazzlelink
                    dl_data.save_to_file(dazzlelink_path)
                    
                    debug_print(f"Updated dazzlelink metadata for {dazzlelink_path}")
                except Exception as e:
                    debug_print(f"Failed to update dazzlelink metadata: {str(e)}")
            
            return link_path
            
        except Exception as e:
            raise DazzleLinkException(f"Failed to recreate link from {dazzlelink_path}: {str(e)}")
            
    def _verify_timestamps(self, link_path, dl_data, strategy, use_live_target=False):
        """
        Verify that timestamps were correctly applied to a file.
        
        Args:
            link_path (str): Path to the file to verify
            dl_data (DazzleLinkData): The dazzlelink data
            strategy (str): Timestamp strategy that was used
            use_live_target (bool): Whether to check the live target file for timestamps
        """
        if os.name != 'nt':
            return
            
        try:
            import win32file
            import pywintypes
            
            # Open a handle to the file
            handle = win32file.CreateFile(
                link_path,
                win32file.GENERIC_READ,
                win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
                None,
                win32file.OPEN_EXISTING,
                win32file.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_BACKUP_SEMANTICS | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
                None
            )
            
            try:
                # Get the current timestamps
                created, accessed, modified = win32file.GetFileTime(handle)
                
                # Convert to Unix timestamps for easier comparison
                actual_created = int(created) / 10000000 - 11644473600 if created else None
                actual_accessed = int(accessed) / 10000000 - 11644473600 if accessed else None
                actual_modified = int(modified) / 10000000 - 11644473600 if modified else None
                
                debug_print("Timestamp verification results:")
                debug_print(f"  Created:  {actual_created} ({datetime.datetime.fromtimestamp(actual_created).isoformat() if actual_created else 'None'})")
                debug_print(f"  Modified: {actual_modified} ({datetime.datetime.fromtimestamp(actual_modified).isoformat() if actual_modified else 'None'})")
                debug_print(f"  Accessed: {actual_accessed} ({datetime.datetime.fromtimestamp(actual_accessed).isoformat() if actual_accessed else 'None'})")
                
                # Determine expected timestamps based on strategy
                expected_timestamps = None
                if strategy == 'symlink':
                    link_timestamps = dl_data.get_link_timestamps()
                    expected_timestamps = {
                        'created': link_timestamps.get('created'),
                        'modified': link_timestamps.get('modified'),
                        'accessed': link_timestamps.get('accessed')
                    }
                    debug_print("Expected symlink timestamps from original link")
                elif strategy == 'target':
                    # For target strategy, prefer live target timestamps if available
                    if use_live_target:
                        target_path = dl_data.get_target_path()
                        if os.path.exists(target_path):
                            live_timestamps = self._collect_target_timestamp_info(target_path)
                            expected_timestamps = {
                                'created': live_timestamps.get('created'),
                                'modified': live_timestamps.get('modified'),
                                'accessed': live_timestamps.get('accessed')
                            }
                            debug_print("Expected timestamps from live target")
                    
                    # Fall back to stored target timestamps if live ones aren't available
                    if expected_timestamps is None:
                        target_timestamps = dl_data.get_target_timestamps()
                        expected_timestamps = {
                            'created': target_timestamps.get('created'),
                            'modified': target_timestamps.get('modified'),
                            'accessed': target_timestamps.get('accessed')
                        }
                        debug_print("Expected timestamps from stored target info")
                elif strategy == 'preserve-all':
                    # preserve-all has a complex priority order - implement what's appropriate
                    debug_print("preserve-all strategy - not checking specific timestamps")
                    return
                
                # Compare timestamps if we have expected values
                if expected_timestamps:
                    # Allow a small tolerance (5 seconds) for timestamp comparisons
                    tolerance = 5.0
                    
                    # Check creation time
                    if expected_timestamps['created'] is not None and actual_created is not None:
                        diff = abs(expected_timestamps['created'] - actual_created)
                        if diff > tolerance:
                            debug_print(f"  WARNING: Creation time mismatch: expected={expected_timestamps['created']}, actual={actual_created}, diff={diff}")
                            # If timestamps don't match, try setting them again
                            debug_print("  Attempting to reapply timestamps...")
                            self._set_file_times(
                                link_path, 
                                expected_timestamps['modified'], 
                                expected_timestamps['accessed'], 
                                expected_timestamps['created']
                            )
                            return
                    
                    # Check modification time
                    if expected_timestamps['modified'] is not None and actual_modified is not None:
                        diff = abs(expected_timestamps['modified'] - actual_modified)
                        if diff > tolerance:
                            debug_print(f"  WARNING: Modification time mismatch: expected={expected_timestamps['modified']}, actual={actual_modified}, diff={diff}")
                            # If timestamps don't match, try setting them again
                            debug_print("  Attempting to reapply timestamps...")
                            self._set_file_times(
                                link_path, 
                                expected_timestamps['modified'], 
                                expected_timestamps['accessed'], 
                                expected_timestamps['created']
                            )
                            return
                    
                    debug_print("  Timestamp verification: OK")
                
            finally:
                handle.Close()
                
        except ImportError:
            debug_print("win32file module not available, cannot verify timestamps")
        except Exception as e:
            debug_print(f"Error verifying timestamps: {str(e)}")
			
    def _apply_timestamp_strategy(self, link_path, dl_data, strategy, use_live_target=False, batch_mode=False):
        """
        Apply the selected timestamp strategy to a recreated symlink.
        
        Args:
            link_path (str): Path to the recreated symlink
            dl_data (DazzleLinkData): The dazzlelink data
            strategy (str): Timestamp strategy ('current', 'symlink', 'target', 'preserve-all')
            use_live_target (bool): Whether to check the live target file for timestamps
            batch_mode (bool): If True, optimizes for batch processing (less verification)
        """
        # Skip if not on Windows - timestamp setting is more reliable on Windows
        if os.name != 'nt':
            debug_print("Timestamp setting is only reliable on Windows, skipping")
            return
            
        # For batch processing, we'll skip verification to improve performance
        verify_timestamps = not batch_mode
        
        try:
            # Get target path for possible live target check
            target_path = dl_data.get_target_path()
            live_target_timestamps = None
            
            # Check live target if requested or if we might need it
            if use_live_target or strategy in ['target', 'preserve-all']:
                try:
                    debug_print(f"Attempting to get live target timestamps from: {target_path}")
                    
                    # Try different path representations if available
                    target_representations = dl_data.get_target_representations()
                    
                    # Try each representation until we find one that works
                    for repr_type, path in target_representations.items():
                        try:
                            # Check if path exists
                            if os.path.exists(path):
                                live_target_timestamps = self._collect_target_timestamp_info(path)
                                if any(v is not None for v in [
                                    live_target_timestamps.get('created'),
                                    live_target_timestamps.get('modified'),
                                    live_target_timestamps.get('accessed')
                                ]):
                                    debug_print(f"Found live target using representation: {repr_type}")
                                    break
                        except Exception as e:
                            debug_print(f"Failed with representation {repr_type}: {str(e)}")
                            continue
                    
                    # If no representation worked, try the original path
                    if (not live_target_timestamps or 
                        not any(v is not None for v in [
                            live_target_timestamps.get('created'),
                            live_target_timestamps.get('modified'),
                            live_target_timestamps.get('accessed')
                        ])) and os.path.exists(target_path):
                        live_target_timestamps = self._collect_target_timestamp_info(target_path)
                        debug_print(f"Found live target using original path")
                except Exception as e:
                    debug_print(f"Failed to get live target timestamps: {str(e)}")
            
            # Get timestamps based on strategy
            if strategy == 'current':
                # Use current time - nothing to do
                debug_print("Using current time for timestamps")
                return
                
            elif strategy == 'symlink':
                # Use original symlink timestamps
                link_timestamps = dl_data.get_link_timestamps()
                
                # Only set if we have timestamps
                if link_timestamps.get('modified') is not None:
                    timestamp_data = {
                        'created': link_timestamps.get('created'),
                        'modified': link_timestamps.get('modified'),
                        'accessed': link_timestamps.get('accessed')
                    }
                    
                    debug_print(f"Using symlink timestamps: created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                    
                    # Set the timestamps on the recreated symlink with verification
                    self._set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
                    
            elif strategy == 'target':
                # Try live target timestamps first if available and requested
                if use_live_target and live_target_timestamps and live_target_timestamps.get('modified') is not None:
                    timestamp_data = {
                        'created': live_target_timestamps.get('created'),
                        'modified': live_target_timestamps.get('modified'),
                        'accessed': live_target_timestamps.get('accessed')
                    }
                    
                    debug_print(f"Using live target timestamps: created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                    
                    # Set the timestamps on the recreated symlink with verification
                    self._set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
                    return
                
                # Fall back to stored target timestamps
                target_timestamps = dl_data.get_target_timestamps()
                
                # Only set if we have timestamps
                if target_timestamps.get('modified') is not None:
                    timestamp_data = {
                        'created': target_timestamps.get('created'),
                        'modified': target_timestamps.get('modified'),
                        'accessed': target_timestamps.get('accessed')
                    }
                    
                    debug_print(f"Using stored target timestamps: created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                    
                    # Set the timestamps on the recreated symlink with verification
                    self._set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
                elif live_target_timestamps and live_target_timestamps.get('modified') is not None:
                    # Fall back to live target even if not explicitly requested
                    timestamp_data = {
                        'created': live_target_timestamps.get('created'),
                        'modified': live_target_timestamps.get('modified'),
                        'accessed': live_target_timestamps.get('accessed')
                    }
                    
                    debug_print(f"Falling back to live target timestamps: created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                    
                    # Set the timestamps on the recreated symlink with verification
                    self._set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
                    
            elif strategy == 'preserve-all':
                # Try target timestamps first, in order of:
                # 1. Live target (if use_live_target is True)
                # 2. Stored target timestamps
                # 3. Symlink timestamps
                
                # 1. Try live target first if requested
                if use_live_target and live_target_timestamps and live_target_timestamps.get('modified') is not None:
                    timestamp_data = {
                        'created': live_target_timestamps.get('created'),
                        'modified': live_target_timestamps.get('modified'),
                        'accessed': live_target_timestamps.get('accessed')
                    }
                    
                    debug_print(f"Using live target timestamps (preserve-all): created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                    
                    # Set the timestamps on the recreated symlink with verification
                    if self._set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps):
                        return
                
                # 2. Try stored target timestamps
                target_timestamps = dl_data.get_target_timestamps()
                if target_timestamps.get('modified') is not None:
                    timestamp_data = {
                        'created': target_timestamps.get('created'),
                        'modified': target_timestamps.get('modified'),
                        'accessed': target_timestamps.get('accessed')
                    }
                    
                    debug_print(f"Using stored target timestamps (preserve-all): created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                    
                    # Set the timestamps on the recreated symlink with verification
                    if self._set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps):
                        return
                
                # 3. Try to fall back to live target even if not explicitly requested
                if live_target_timestamps and live_target_timestamps.get('modified') is not None:
                    timestamp_data = {
                        'created': live_target_timestamps.get('created'),
                        'modified': live_target_timestamps.get('modified'),
                        'accessed': live_target_timestamps.get('accessed')
                    }
                    
                    debug_print(f"Falling back to live target timestamps (preserve-all): created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                    
                    # Set the timestamps on the recreated symlink with verification
                    if self._set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps):
                        return
                
                # 4. Finally, fall back to symlink timestamps
                link_timestamps = dl_data.get_link_timestamps()
                if link_timestamps.get('modified') is not None:
                    timestamp_data = {
                        'created': link_timestamps.get('created'),
                        'modified': link_timestamps.get('modified'),
                        'accessed': link_timestamps.get('accessed')
                    }
                    
                    debug_print(f"Falling back to symlink timestamps (preserve-all): created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                    
                    # Set the timestamps on the recreated symlink with verification
                    self._set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
            
        except Exception as e:
            debug_print(f"Failed to apply timestamp strategy: {str(e)}")

    def _set_file_times(self, file_path, modified_time, accessed_time=None, created_time=None):
        """
        Set modification, access, and creation times for a file or symlink.
        
        Args:
            file_path (str): Path to the file or symlink
            modified_time (float): Modification timestamp
            accessed_time (float, optional): Access timestamp. If None, uses modified_time
            created_time (float, optional): Creation timestamp. If None, doesn't change creation time
        
        Returns:
            bool: True if successful, False otherwise
        """
        if accessed_time is None:
            accessed_time = modified_time
        
        debug_print(f"Setting timestamps for {file_path}")
        debug_print(f"  Modified: {modified_time} ({datetime.datetime.fromtimestamp(modified_time).isoformat() if modified_time else 'None'})")
        debug_print(f"  Accessed: {accessed_time} ({datetime.datetime.fromtimestamp(accessed_time).isoformat() if accessed_time else 'None'})")
        debug_print(f"  Created: {created_time} ({datetime.datetime.fromtimestamp(created_time).isoformat() if created_time else 'None'})")
        
        # On Windows, use Win32 API to set all timestamps including creation time
        if os.name == 'nt': # and created_time is not None:
            try:
                import win32file
                import win32con
                import pywintypes
                
                # Convert Unix timestamps to Windows FILETIME
                win_created = pywintypes.Time(int(created_time)) if created_time is not None else None
                win_accessed = pywintypes.Time(int(accessed_time)) if accessed_time is not None else None
                win_modified = pywintypes.Time(int(modified_time)) if modified_time is not None else None
                
                debug_print("Using Win32 API to set file times")
                
                # Important: Use FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT
                # to work properly with symlinks on Windows
				# Open file handle with proper sharing mode to avoid "file in use" errors
                handle = win32file.CreateFile(
                    file_path,
                    win32file.GENERIC_WRITE,
                    win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
                    None,
                    win32file.OPEN_EXISTING,
                    win32file.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_BACKUP_SEMANTICS | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
                    None
                )
                
                try:
                    # Set times - pass all three timestamps to SetFileTime
                    win32file.SetFileTime(handle, win_created, win_accessed, win_modified)
                    debug_print("Successfully set all timestamps using Win32 API")
                    
                    # Verify the timestamps were correctly set
                    try:
                        # Close handle first to ensure changes are flushed
                        handle.Close()
                        handle = None
                        
                        # Reopen to check
                        verify_handle = win32file.CreateFile(
                            file_path,
                            win32file.GENERIC_READ,
                            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
                            None,
                            win32file.OPEN_EXISTING,
                            win32file.FILE_ATTRIBUTE_NORMAL | win32file.FILE_FLAG_BACKUP_SEMANTICS | win32file.FILE_FLAG_OPEN_REPARSE_POINT,
                            None
                        )
                        
                        try:
                            actual_created, actual_accessed, actual_modified = win32file.GetFileTime(verify_handle)
                            
                            debug_print("Timestamp verification:")
                            if win_created:
                                debug_print(f"  Created: Expected={win_created}, Actual={actual_created}")
                            if win_accessed:
                                debug_print(f"  Accessed: Expected={win_accessed}, Actual={actual_accessed}")
                            if win_modified:
                                debug_print(f"  Modified: Expected={win_modified}, Actual={actual_modified}")
                        finally:
                            verify_handle.Close()
                    except Exception as ve:
                        debug_print(f"Timestamp verification failed: {str(ve)}")
                    
                    return True
                finally:
                    # Close handle if still open
                    if handle:
                        handle.Close()
                    
            except ImportError:
                debug_print("win32file module not available, cannot set creation time on Windows")
            except Exception as win_error:
                debug_print(f"Failed to set timestamps using Win32 API: {str(win_error)}")
        
        # Fall back to os.utime for modification and access times only
        try:
            # Use standard os.utime function (note: this won't set creation time)
            os.utime(file_path, (accessed_time, modified_time))
            debug_print(f"Set modification and access times using os.utime")
            
            # Return True if creation time wasn't needed, False if it was needed but not set
            return created_time is None
        except Exception as e:
            debug_print(f"Failed to set timestamps using os.utime: {str(e)}")
            return False

    def batch_import(self, path_patterns, target_location=None, recursive=False, 
                    flatten=False, pattern=None, dry_run=False, remove_dazzlelinks=False,
                    config_level='file', timestamp_strategy='current', update_dazzlelink=False,
                    use_live_target=False, batch_optimization=True):
        """
        Batch import multiple dazzlelink files, recreating the original symlinks.
        
        Args:
            path_patterns (list or str): Path pattern(s) to search for dazzlelinks
            target_location (str, optional): Override location for recreated symlinks
            recursive (bool): Whether to search subdirectories recursively
            flatten (bool): If True, flatten directory structure when recreating symlinks
            pattern (str, optional): Glob pattern to filter dazzlelink filenames
            dry_run (bool): If True, only show what would be done without making changes
            remove_dazzlelinks (bool): If True, remove dazzlelink files after successful import
            config_level (str): Configuration level to use ('global', 'directory', 'file')
            timestamp_strategy (str): Strategy for setting timestamps ('current', 'symlink', 'target', 'preserve-all')
            update_dazzlelink (bool): Whether to update dazzlelink metadata during import
            use_live_target (bool): Whether to check the live target file for timestamps
            batch_optimization (bool): Whether to use optimizations for batch processing
            
        Returns:
            dict: Report of imported files with details on success, errors, etc.
        """
        # Find all matching dazzlelink files
        dazzlelinks = self._find_dazzlelinks(path_patterns, recursive, pattern)
        
        if not dazzlelinks:
            print(f"No dazzlelink files found matching the specified criteria")
            return {"success": [], "error": [], "skipped": []}
        
        # Setup result tracking
        results = {
            "success": [],
            "error": [],
            "skipped": []
        }
        
        # Group dazzlelinks by directory for better reporting
        dazzlelinks_by_dir = {}
        for dl_path in dazzlelinks:
            dir_path = str(dl_path.parent)
            if dir_path not in dazzlelinks_by_dir:
                dazzlelinks_by_dir[dir_path] = []
            dazzlelinks_by_dir[dir_path].append(dl_path)
        
        # Process each dazzlelink
        total_count = len(dazzlelinks)
        processed_count = 0
        
        print(f"Found {total_count} dazzlelink files in {len(dazzlelinks_by_dir)} directories")
        if dry_run:
            print("DRY RUN - no changes will be made")
        
        print(f"Using timestamp strategy: {timestamp_strategy}")
        if use_live_target:
            print("Will check live target files for timestamps")
        
        for dir_path, dir_dazzlelinks in dazzlelinks_by_dir.items():
            print(f"\nProcessing directory: {dir_path}")
            
            # Load directory-specific config if using directory level
            if config_level == 'directory':
                self.config.load_directory_config(dir_path)
            
            for dl_path in dir_dazzlelinks:
                processed_count += 1
                print(f"  [{processed_count}/{total_count}] Processing: {dl_path.name}")
                
                try:
                    # Load the dazzlelink data for validation
                    try:
                        dl_data = DazzleLinkData.from_file(str(dl_path))
                    except ValueError as e:
                        results["error"].append({
                            "path": str(dl_path),
                            "error": str(e)
                        })
                        print(f"    ERROR: {str(e)}")
                        continue
                    
                    # Get target path for informational purposes
                    target_path = dl_data.get_target_path()
                    original_path = dl_data.get_original_path()
                    
                    # Determine where to create the symlink
                    if target_location:
                        if flatten:
                            # Use just the filename in the target location
                            link_name = os.path.basename(original_path)
                            new_link_path = os.path.join(target_location, link_name)
                        else:
                            # Preserve relative path structure
                            try:
                                # If original_path is absolute, convert to relative to common base
                                if os.path.isabs(original_path):
                                    # Find common base path if possible
                                    dl_dir = os.path.dirname(str(dl_path))
                                    common_base = os.path.commonpath([original_path, dl_dir])
                                    if common_base:
                                        rel_path = os.path.relpath(original_path, common_base)
                                        new_link_path = os.path.join(target_location, rel_path)
                                    else:
                                        # No common base, just use basename
                                        link_name = os.path.basename(original_path)
                                        new_link_path = os.path.join(target_location, link_name)
                                else:
                                    # If already relative, just join with target location
                                    new_link_path = os.path.join(target_location, original_path)
                            except Exception as e:
                                # Fallback to flatten if path processing fails
                                link_name = os.path.basename(original_path)
                                new_link_path = os.path.join(target_location, link_name)
                    else:
                        # Use the original path as specified in the dazzlelink
                        new_link_path = original_path
                    
                    # Check if link already exists
                    if os.path.exists(new_link_path) and not dry_run:
                        print(f"    WARNING: Path already exists: {new_link_path}")
                    
                    # Log what would be done in dry run mode
                    if dry_run:
                        results["success"].append({
                            "dazzlelink": str(dl_path),
                            "new_link": new_link_path,
                            "target": target_path,
                            "removed": remove_dazzlelinks,
                            "timestamp_strategy": timestamp_strategy,
                            "updated_metadata": update_dazzlelink,
                            "use_live_target": use_live_target
                        })
                        print(f"    WOULD CREATE: {new_link_path} -> {target_path}")
                        print(f"    TIMESTAMP STRATEGY: {timestamp_strategy}")
                        if use_live_target:
                            print(f"    WOULD CHECK LIVE TARGET: {target_path}")
                        if remove_dazzlelinks:
                            print(f"    WOULD REMOVE: {dl_path}")
                        if update_dazzlelink:
                            print(f"    WOULD UPDATE METADATA: {dl_path}")
                        continue
                    
                    # Create the link - pass batch_optimization flag to indicate we're in batch mode
                    # This affects timestamp verification strategy
                    try:
                        # Ensure parent directory exists
                        os.makedirs(os.path.dirname(new_link_path), exist_ok=True)
                        
                        # Remove existing link/file if it exists
                        if os.path.exists(new_link_path):
                            if os.path.isdir(new_link_path) and not os.path.islink(new_link_path):
                                shutil.rmtree(new_link_path)
                            else:
                                os.unlink(new_link_path)
                        
                        # Get target information
                        target_path = dl_data.get_target_path()
                        is_dir = dl_data.get_target_type() == "directory"
                        
                        # Create symlink
                        if os.name == 'nt':
                            self._create_windows_symlink(target_path, new_link_path, is_dir)
                        else:
                            os.symlink(target_path, new_link_path)
                        
                        # Apply timestamp strategy with batch optimization
                        self._apply_timestamp_strategy(
                            new_link_path,
                            dl_data,
                            timestamp_strategy,
                            use_live_target,
                            batch_mode=batch_optimization
                        )
                        
                        # Restore file attributes
                        self._restore_file_attributes(new_link_path, dl_data.to_dict())
                        
                        # Update dazzlelink metadata if requested
                        if update_dazzlelink:
                            dl_data.update_metadata(reason="symlink_recreation")
                            
                            # If we used live target, update target timestamps too
                            if use_live_target and timestamp_strategy in ['target', 'preserve-all']:
                                if os.path.exists(target_path):
                                    target_timestamps = self._collect_target_timestamp_info(target_path)
                                    dl_data.set_target_timestamps(
                                        created=target_timestamps.get('created'),
                                        modified=target_timestamps.get('modified'),
                                        accessed=target_timestamps.get('accessed')
                                    )
                                    
                            # Save the updated dazzlelink
                            dl_data.save_to_file(str(dl_path))
                        
                        # Track success
                        results["success"].append({
                            "dazzlelink": str(dl_path),
                            "new_link": new_link_path,
                            "target": target_path,
                            "removed": False,
                            "timestamp_strategy": timestamp_strategy,
                            "updated_metadata": update_dazzlelink,
                            "use_live_target": use_live_target
                        })
                        print(f"    SUCCESS: Created symlink at {new_link_path} -> {target_path}")
                        if use_live_target:
                            print(f"    CHECKED LIVE TARGET: {target_path}")
                        
                        # Remove dazzlelink if requested
                        if remove_dazzlelinks:
                            try:
                                os.unlink(dl_path)
                                results["success"][-1]["removed"] = True
                                print(f"    REMOVED: {dl_path}")
                            except Exception as e:
                                print(f"    WARNING: Failed to remove dazzlelink {dl_path}: {str(e)}")
                                results["success"][-1]["removal_error"] = str(e)
                    except Exception as e:
                        results["error"].append({
                            "path": str(dl_path),
                            "error": str(e)
                        })
                        print(f"    ERROR: Failed to recreate link: {str(e)}")
                        
                except Exception as e:
                    results["error"].append({
                        "path": str(dl_path),
                        "error": str(e)
                    })
                    print(f"    ERROR: Failed to process {dl_path}: {str(e)}")
        
        # Print summary
        print("\nImport Summary:")
        print(f"  {len(results['success'])} links successfully created")
        print(f"  {len(results['error'])} errors occurred")
        print(f"  {len(results['skipped'])} items skipped")
        
        if remove_dazzlelinks and not dry_run:
            # Count how many were successfully removed
            removed_count = sum(1 for item in results['success'] if item.get('removed', False))
            print(f"  {removed_count} dazzlelink files removed")
        
        return results
    
    def _restore_file_attributes(self, link_path, link_data):
        """
        Restore file attributes from the link data to the recreated symlink.
        
        Args:
            link_path (str): Path to the recreated symlink
            link_data (dict): The dazzlelink data containing attributes
        """
        # Only attempt on Windows for now as Unix is more complex with permissions
        if os.name != 'nt':
            debug_print("File attribute restoration is primarily for Windows")
            return
            
        try:
            # Extract attributes from either schema format
            attributes = None
            if "attributes" in link_data:
                # Old format
                attributes = link_data["attributes"]
            elif "link" in link_data and "attributes" in link_data["link"]:
                # New format
                attributes = link_data["link"]["attributes"]
            
            if not attributes:
                debug_print("No attribute data found in dazzlelink")
                return
                
            # Get attribute values with defaults
            hidden = attributes.get("hidden", False)
            system = attributes.get("system", False)
            readonly = attributes.get("readonly", False)
            
            debug_print(f"Restoring file attributes for {link_path}")
            debug_print(f"  Hidden: {hidden}")
            debug_print(f"  System: {system}")
            debug_print(f"  Read-only: {readonly}")
            
            if os.name == 'nt':
                # First try using ctypes directly
                try:
                    import ctypes
                    
                    # Get current attributes
                    current_attrs = ctypes.windll.kernel32.GetFileAttributesW(link_path)
                    
                    if current_attrs == -1:
                        debug_print("Failed to get current file attributes")
                        return
                        
                    # Modify attributes as needed
                    new_attrs = current_attrs
                    
                    # FILE_ATTRIBUTE constants
                    FILE_ATTRIBUTE_HIDDEN = 0x2
                    FILE_ATTRIBUTE_SYSTEM = 0x4
                    FILE_ATTRIBUTE_READONLY = 0x1
                    
                    if hidden:
                        new_attrs |= FILE_ATTRIBUTE_HIDDEN
                    else:
                        new_attrs &= ~FILE_ATTRIBUTE_HIDDEN
                        
                    if system:
                        new_attrs |= FILE_ATTRIBUTE_SYSTEM
                    else:
                        new_attrs &= ~FILE_ATTRIBUTE_SYSTEM
                        
                    if readonly:
                        new_attrs |= FILE_ATTRIBUTE_READONLY
                    else:
                        new_attrs &= ~FILE_ATTRIBUTE_READONLY
                        
                    # Apply new attributes if different
                    if new_attrs != current_attrs:
                        result = ctypes.windll.kernel32.SetFileAttributesW(link_path, new_attrs)
                        if result:
                            debug_print("Successfully restored file attributes")
                        else:
                            debug_print(f"Failed to set file attributes, error code: {ctypes.GetLastError()}")
                    else:
                        debug_print("No attribute changes needed")
                        
                except Exception as ctypes_error:
                    debug_print(f"Error using ctypes for attributes: {str(ctypes_error)}")
                    
                    # Fall back to win32api if available
                    try:
                        import win32api
                        import win32con
                        
                        # Get current attributes
                        current_attrs = win32api.GetFileAttributes(link_path)
                        
                        # Modify attributes as needed
                        new_attrs = current_attrs
                        
                        if hidden:
                            new_attrs |= win32con.FILE_ATTRIBUTE_HIDDEN
                        else:
                            new_attrs &= ~win32con.FILE_ATTRIBUTE_HIDDEN
                            
                        if system:
                            new_attrs |= win32con.FILE_ATTRIBUTE_SYSTEM
                        else:
                            new_attrs &= ~win32con.FILE_ATTRIBUTE_SYSTEM
                            
                        if readonly:
                            new_attrs |= win32con.FILE_ATTRIBUTE_READONLY
                        else:
                            new_attrs &= ~win32con.FILE_ATTRIBUTE_READONLY
                            
                        # Apply new attributes if different
                        if new_attrs != current_attrs:
                            win32api.SetFileAttributes(link_path, new_attrs)
                            debug_print("Successfully restored file attributes using win32api")
                        else:
                            debug_print("No attribute changes needed")
                            
                    except ImportError:
                        debug_print("win32api module not available for attribute restoration")
                    except Exception as win32_error:
                        debug_print(f"Error using win32api for attributes: {str(win32_error)}")
            else:
                # On Unix-like systems, attempt to set permissions
                try:
                    # Get security information if available
                    if "security" in link_data and "permissions" in link_data["security"]:
                        permission = link_data["security"]["permissions"]
                        if permission:
                            debug_print(f"Setting Unix permissions: {permission}")
                            # Convert from octal string if needed
                            if isinstance(permission, str) and permission.startswith("0o"):
                                permission = int(permission, 8)
                            os.chmod(link_path, permission)
                except Exception as unix_error:
                    debug_print(f"Error setting Unix permissions: {str(unix_error)}")
        except Exception as e:
            # Don't fail the whole operation just because we couldn't restore attributes
            debug_print(f"Error in attribute restoration: {str(e)}")

    def _create_windows_symlink(self, target_path, link_path, is_directory):
        """
        Create a symbolic link on Windows, handling privilege elevation if needed.
        
        Args:
            target_path (str): Target of the symlink
            link_path (str): Location of the symlink to create
            is_directory (bool): Whether the target is a directory
            
        Returns:
            bool: True if successful, False if an error occurs
        """
        if not os.name == 'nt':
            debug_print("Not running on Windows, using standard os.symlink")
            os.symlink(target_path, link_path)
            return True
            
        debug_print(f"Creating Windows symlink: {link_path} -> {target_path} (is_directory={is_directory})")
        
        # Try using the os.symlink method first
        try:
            os.symlink(target_path, link_path, target_is_directory=is_directory)
            debug_print("Symlink created successfully using os.symlink")
            return True
        except OSError as e:
            # Handle "privilege not held" error
            if getattr(e, 'winerror', 0) == 1314:
                debug_print("Permission denied (admin privileges required), trying alternative methods")
            else:
                debug_print(f"Error creating symlink with os.symlink: {str(e)}")
        except Exception as e:
            debug_print(f"Unexpected error in os.symlink: {str(e)}")
            
        # Try using win32file API if available
        try:
            import win32file
            
            flags = 0
            if is_directory:
                flags = win32file.SYMBOLIC_LINK_FLAG_DIRECTORY
            
            # Add SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE for Windows 10 v1703+
            try:
                flags |= 0x2  # SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE
            except:
                pass
                
            debug_print(f"Creating symlink with win32file.CreateSymbolicLink, flags={flags}")
            
            # Create the symlink
            result = win32file.CreateSymbolicLink(link_path, target_path, flags)
            
            if result:
                debug_print("Symlink created successfully using win32file API")
                return True
            else:
                debug_print("Failed to create symlink with win32file API")
        except ImportError:
            debug_print("win32file module not available, cannot use its API")
        except Exception as e:
            debug_print(f"Error creating symlink with win32file: {str(e)}")
        
        # Fall back to using mklink command with elevation if needed
        try:
            # Prepare the mklink command
            dir_flag = '/D ' if is_directory else ''
            cmd = f'mklink {dir_flag}"{link_path}" "{target_path}"'
            
            debug_print(f"Attempting to create symlink with mklink: {cmd}")
            
            # Try running directly first
            try:
                result = subprocess.run(
                    ['cmd', '/c', cmd], 
                    text=True, 
                    capture_output=True, 
                    check=False
                )
                
                if result.returncode == 0:
                    debug_print("Symlink created successfully using mklink")
                    return True
                else:
                    debug_print(f"mklink failed: {result.stderr}")
            except Exception as cmd_error:
                debug_print(f"Error running mklink command: {str(cmd_error)}")
            
            # If direct call failed, try with elevation
            debug_print("Attempting to create symlink with elevated privileges")
            
            # Use PowerShell to run elevated command
            ps_cmd = f'Start-Process cmd.exe -Verb RunAs -ArgumentList "/c {cmd}"'
            
            try:
                subprocess.run(['powershell', '-Command', ps_cmd], check=True)
                
                # Check if link was created (there might be a delay)
                attempts = 0
                while attempts < 5 and not os.path.exists(link_path):
                    time.sleep(1)
                    attempts += 1
                    
                if os.path.exists(link_path):
                    debug_print("Symlink created successfully using elevated mklink")
                    return True
                else:
                    debug_print("Link creation requested but could not verify it was created")
                    debug_print(f"Manual command needed: {cmd}")
                    return False
            except subprocess.SubprocessError as se:
                debug_print(f"Failed to create elevated symlink: {str(se)}")
        except Exception as e:
            debug_print(f"Unexpected error in mklink fallback: {str(e)}")
        
        # If all methods failed, raise an exception
        raise DazzleLinkException(f"Failed to create symlink: {link_path} -> {target_path}")
		
    def _find_dazzlelinks(self, path_patterns, recursive=False, pattern=None):
        """
        Find dazzlelink files based on path patterns, recursion, and filtering.
        
        Args:
            path_patterns (list or str): Path pattern(s) to search for dazzlelinks
            recursive (bool): Whether to search subdirectories recursively
            pattern (str, optional): Glob pattern to filter dazzlelink filenames (e.g., "*.dazzlelink")
                If None, defaults to "*.dazzlelink"
        
        Returns:
            list: List of dazzlelink file paths (as Path objects)
        """
        import glob
        import fnmatch
        from pathlib import Path
        
        # Normalize input to list
        if isinstance(path_patterns, str):
            path_patterns = [path_patterns]
            
        # Default pattern if not specified
        if pattern is None:
            pattern = f"*{self.DAZZLELINK_EXT}"
            
        found_dazzlelinks = []
        
        for path_pattern in path_patterns:
            # Expand any glob patterns in the input paths
            expanded_paths = glob.glob(path_pattern, recursive=False)
            
            # If glob didn't match anything, use the path as-is
            if not expanded_paths:
                expanded_paths = [path_pattern]
                
            for path in expanded_paths:
                path_obj = Path(path)
                
                # Case 1: Direct file path
                if path_obj.is_file():
                    if path_obj.suffix == self.DAZZLELINK_EXT and (pattern == f"*{self.DAZZLELINK_EXT}" or fnmatch.fnmatch(path_obj.name, pattern)):
                        found_dazzlelinks.append(path_obj)
                
                # Case 2: Directory path
                elif path_obj.is_dir():
                    if recursive:
                        # Recursive search
                        for root, _, files in os.walk(path_obj):
                            root_path = Path(root)
                            for file in files:
                                if file.endswith(self.DAZZLELINK_EXT) and fnmatch.fnmatch(file, pattern):
                                    found_dazzlelinks.append(root_path / file)
                    else:
                        # Non-recursive, just search the directory
                        for file in path_obj.glob(pattern):
                            if file.is_file() and file.suffix == self.DAZZLELINK_EXT:
                                found_dazzlelinks.append(file)
                
                # Case 3: Non-existent path with wildcards (could be a pattern)
                elif '*' in str(path_obj) or '?' in str(path_obj):
                    # This might be a pattern that didn't get expanded by glob
                    try:
                        # Try using Path.glob on the parent directory
                        parent = path_obj.parent
                        if parent.exists():
                            file_pattern = path_obj.name
                            for file in parent.glob(file_pattern):
                                if file.is_file() and file.suffix == self.DAZZLELINK_EXT and fnmatch.fnmatch(file.name, pattern):
                                    found_dazzlelinks.append(file)
                    except Exception as e:
                        debug_print(f"Error while processing pattern {path_obj}: {e}")
        
        # Remove duplicates while preserving order
        unique_dazzlelinks = []
        seen = set()
        for link in found_dazzlelinks:
            link_str = str(link)
            if link_str not in seen:
                seen.add(link_str)
                unique_dazzlelinks.append(link)
        
        return unique_dazzlelinks

    def scan_directory(self, directory, recursive=True):
        """
        Scan a directory for symbolic links
        
        Args:
            directory (str): Directory to scan
            recursive (bool): Whether to scan recursively
            
        Returns:
            list: List of symbolic link paths found
        """
        links = []
        directory = Path(directory).resolve()
        
        if not directory.is_dir():
            raise DazzleLinkException(f"{directory} is not a directory")
        
        try:
            if recursive:
                for root, dirs, files in os.walk(directory):
                    for name in dirs + files:
                        path = os.path.join(root, name)
                        if os.path.islink(path):
                            links.append(path)
            else:
                for item in os.listdir(directory):
                    path = os.path.join(directory, item)
                    if os.path.islink(path):
                        links.append(path)
                        
            return links
        except Exception as e:
            raise DazzleLinkException(f"Failed to scan directory {directory}: {str(e)}")

    def convert_directory(self, directory, recursive=None, keep_originals=None, make_executable=None, mode=None):
        """
        Convert all symlinks in a directory to dazzlelinks
        
        Args:
            directory (str): Directory to scan
            recursive (bool, optional): Whether to scan recursively.
                If None, uses configuration default.
            keep_originals (bool, optional): Whether to keep the original symlinks.
                If None, uses configuration default.
            make_executable (bool, optional): Whether to make the dazzlelinks executable.
                If None, uses configuration default.
            mode (str, optional): Default execution mode for dazzlelinks.
                If None, uses configuration default.
            
        Returns:
            list: List of created dazzlelink paths
        """
        # Load directory-specific config
        self.config.load_directory_config(directory)
        
        # Use config defaults if parameters not specified
        if recursive is None:
            recursive = self.config.get("recursive_scan")
        if keep_originals is None:
            keep_originals = self.config.get("keep_originals")
        if make_executable is None:
            make_executable = self.config.get("make_executable")
        if mode is None:
            mode = self.config.get("default_mode")
            
        links = self.scan_directory(directory, recursive)
        dazzlelinks = []
        
        for link in links:
            try:
                dazzlelink = self.serialize_link(
                    link, 
                    make_executable=make_executable,
                    mode=mode
                )
                dazzlelinks.append(dazzlelink)
                
                if not keep_originals:
                    os.unlink(link)
                    
            except Exception as e:
                print(f"WARNING: Failed to convert {link}: {str(e)}")
                
        return dazzlelinks

    def mirror_directory(self, src_dir, dest_dir, recursive=None, make_executable=None, mode=None):
        """
        Mirror a directory structure, converting all symlinks to dazzlelinks
        
        Args:
            src_dir (str): Source directory
            dest_dir (str): Destination directory
            recursive (bool, optional): Whether to scan recursively.
                If None, uses configuration default.
            make_executable (bool, optional): Whether to make the dazzlelinks executable.
                If None, uses configuration default.
            mode (str, optional): Default execution mode for dazzlelinks.
                If None, uses configuration default.
            
        Returns:
            list: List of created dazzlelink paths
        """
        # Load source directory-specific config
        self.config.load_directory_config(src_dir)
        
        # Use config defaults if parameters not specified
        if recursive is None:
            recursive = self.config.get("recursive_scan")
        if make_executable is None:
            make_executable = self.config.get("make_executable")
        if mode is None:
            mode = self.config.get("default_mode")
            
        links = self.scan_directory(src_dir, recursive)
        dazzlelinks = []
        src_dir = Path(src_dir).resolve()
        dest_dir = Path(dest_dir).resolve()
        
        # Create destination directory if it doesn't exist
        os.makedirs(dest_dir, exist_ok=True)
        
        for link in links:
            try:
                # Calculate relative path
                rel_path = os.path.relpath(link, src_dir)
                dest_path = os.path.join(dest_dir, rel_path)
                
                # Create parent directories
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                
                # Create dazzlelink at the destination
                dazzlelink = self.serialize_link(
                    link, 
                    output_path=f"{dest_path}{self.DAZZLELINK_EXT}", 
                    make_executable=make_executable,
                    mode=mode
                )
                dazzlelinks.append(dazzlelink)
                
            except Exception as e:
                print(f"WARNING: Failed to mirror {link}: {str(e)}")
                
        return dazzlelinks
    
    def _make_dazzlelink_executable(self, dazzlelink_path, link_data=None):
        """
        Make a dazzlelink file executable, adding the necessary script code
        
        Args:
            dazzlelink_path (str): Path to the dazzlelink file
            link_data (dict, optional): Link data if already loaded
        """
        if link_data is None:
            try:
                with open(dazzlelink_path, 'r', encoding='utf-8') as f:
                    link_data = json.load(f)
            except json.JSONDecodeError as e:
                # File is already executable or corrupted
                print(f"Warning: Could not parse {dazzlelink_path} as JSON: {e}")
                return
        # Handle both old and new schema formats
        if "target_path" in link_data:
            # Old format
            target_path = link_data["target_path"]
            default_mode = link_data.get("config", {}).get("default_mode", "info")
        elif "link" in link_data and "target_path" in link_data["link"]:
            # New format
            target_path = link_data["link"]["target_path"]
            default_mode = link_data.get("config", {}).get("default_mode", "info")
        else:
            raise DazzleLinkException(f"Invalid dazzlelink format in {dazzlelink_path}")
        
        # Create a temporary file with both script and JSON content
        temp_path = f"{dazzlelink_path}.tmp"
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            # Write script header (works as both shell script and batch file)
            f.write('#!/bin/sh\n')
            f.write('""":"\n')
            f.write(':: Windows Batch Script\n')
            f.write('@echo off\n')
            
            # Handle default mode in batch section
            if default_mode == "open" or default_mode == "auto":
                f.write('if "%~1"=="" goto open_target\n')
            else:
                f.write('if "%~1"=="" goto show_info\n')
                
            f.write('if "%1"=="--open" goto open_target\n')
            f.write('if "%1"=="--auto" goto open_target\n')
            f.write('if "%1"=="--info" goto show_info\n')
            f.write('python "%~dpnx0" %*\n')
            f.write('exit /b\n')
            f.write('\n')
            f.write(':open_target\n')
            f.write(f'start "" "{target_path}"\n')
            f.write('exit /b\n')
            f.write('\n')
            f.write(':show_info\n')
            f.write('echo DazzleLink Information:\n')
            f.write(f'echo Target: {target_path}\n')
            f.write('echo.\n')
            f.write('echo Use --open to open the target directly\n')
            f.write('exit /b\n')
            f.write('"""\n')
            f.write('\n')
            f.write('# Python Script\n')
            f.write('import os\n')
            f.write('import sys\n')
            f.write('import json\n')
            f.write('import subprocess\n')
            f.write('\n')
            f.write('def main():\n')
            f.write('    """Process dazzlelink commands"""\n')
            f.write('    # Extract the link data from this file\n')
            f.write('    with open(__file__, "r", encoding="utf-8") as f:\n')
            f.write('        # Skip the script header\n')
            f.write('        in_header = True\n')
            f.write('        json_text = ""\n')
            f.write('        for line in f:\n')
            f.write('            if line.strip() == "# DAZZLELINK_DATA_BEGIN":\n')
            f.write('                in_header = False\n')
            f.write('                continue\n')
            f.write('            if not in_header:\n')
            f.write('                json_text += line\n')
            f.write('\n')
            f.write('    link_data = json.loads(json_text)\n')
            f.write('\n')
            f.write('    # Handle both old and new schema formats\n')
            f.write('    if "target_path" in link_data:\n')
            f.write('        # Old format\n')
            f.write('        target_path = link_data["target_path"]\n')
            f.write('        default_mode = link_data.get("config", {}).get("default_mode", "info")\n')
            f.write('        original_path = link_data.get("original_path", "Unknown")\n')
            f.write('        creation_date = link_data.get("creation_date", "Unknown")\n')
            f.write('    elif "link" in link_data and "target_path" in link_data["link"]:\n')
            f.write('        # New format\n')
            f.write('        target_path = link_data["link"]["target_path"]\n')
            f.write('        default_mode = link_data.get("config", {}).get("default_mode", "info")\n')
            f.write('        original_path = link_data["link"].get("original_path", "Unknown")\n')
            f.write('        creation_date = link_data.get("creation_date", "Unknown")\n')
            f.write('    else:\n')
            f.write('        print("ERROR: Invalid dazzlelink format")\n')
            f.write('        sys.exit(1)\n')
            f.write('\n')
            
            # Set default mode behavior
            f.write('    # Process command arguments\n')
            f.write('    if len(sys.argv) > 1:\n')
            f.write('        if sys.argv[1] == "--open" or sys.argv[1] == "--auto":\n')
            f.write('            # Open the target file/directory\n')
            f.write('            open_target(target_path)\n')
            f.write('        elif sys.argv[1] == "--info":\n')
            f.write('            # Show info explicitly\n')
            f.write('            show_info(link_data, target_path, original_path, creation_date)\n')
            f.write('        else:\n')
            f.write('            # Show help\n')
            f.write('            show_help(target_path, default_mode)\n')
            f.write('    else:\n')
            f.write('        # No arguments - use default mode\n')
            f.write('        if default_mode == "open" or default_mode == "auto":\n')
            f.write('            open_target(target_path)\n')
            f.write('        else:  # Default to info mode\n')
            f.write('            show_info(link_data, target_path, original_path, creation_date)\n')
            f.write('\n')
            
            f.write('def open_target(target_path):\n')
            f.write('    """Open the target file or directory"""\n')
            f.write('    try:\n')
            f.write('        if os.name == "nt":\n')
            f.write('            os.startfile(target_path)\n')
            f.write('        else:\n')
            f.write('            subprocess.run(["xdg-open", target_path])\n')
            f.write('    except Exception as e:\n')
            f.write('        print(f"Error opening target: {str(e)}")\n')
            f.write('        print(f"Target path: {target_path}")\n')
            f.write('        if not os.path.exists(target_path):\n')
            f.write('            print("Target does not exist!")\n')
            f.write('\n')
            
            f.write('def show_info(link_data, target_path, original_path, creation_date):\n')
            f.write('    """Display information about the link"""\n')
            f.write('    print("DazzleLink Information:")\n')
            f.write('    print(f"Target: {target_path}")\n')
            f.write('    print(f"Original Path: {original_path}")\n')
            f.write('    print(f"Creation Date: {creation_date}")\n')
            f.write('\n')
            f.write('    # Display target information if available (new schema)\n')
            f.write('    if "target" in link_data:\n')
            f.write('        target_info = link_data["target"]\n')
            f.write('        print("\\nTarget Details:")\n')
            f.write('        print(f"  Type: {target_info.get(\'type\', \'Unknown\')}")\n')
            f.write('        print(f"  Exists: {\'Yes\' if target_info.get(\'exists\', False) else \'No\'}")\n')
            f.write('        if target_info.get(\'size\') is not None:\n')
            f.write('            size = target_info[\'size\']\n')
            f.write('            if size < 1024:\n')
            f.write('                size_str = f"{size} bytes"\n')
            f.write('            elif size < 1024 * 1024:\n')
            f.write('                size_str = f"{size/1024:.1f} KB"\n')
            f.write('            else:\n')
            f.write('                size_str = f"{size/(1024*1024):.1f} MB"\n')
            f.write('            print(f"  Size: {size_str}")\n')
            f.write('\n')
            
            f.write('    # Display config information\n')
            f.write('    print("\\nConfiguration:")\n')
            f.write('    if "config" in link_data:\n')
            f.write('        for key, value in link_data["config"].items():\n')
            f.write('            print(f"  {key}: {value}")\n')
            f.write('    else:\n')
            f.write('        print("  No configuration available")\n')
            f.write('\n')
            
            f.write('    print("\\nUsage:")\n')
            f.write('    print("  (no args)   Use default mode (currently: " + \n')
            f.write('          link_data.get("config", {}).get("default_mode", "info") + ")")\n')
            f.write('    print("  --open      Open the target file/directory")\n')
            f.write('    print("  --info      Show this information")\n')
            f.write('    print("  --help      Show help message")\n')
            f.write('\n')
            
            f.write('def show_help(target_path, default_mode):\n')
            f.write('    """Show detailed help"""\n')
            f.write('    print("DazzleLink - Symbolic Link Preservation Tool")\n')
            f.write('    print(f"Target: {target_path}")\n')
            f.write('    print(f"Default Mode: {default_mode}")\n')
            f.write('    print("\\nAvailable Commands:")\n')
            f.write('    print("  --open      Open the target file/directory")\n')
            f.write('    print("  --auto      Same as --open")\n')
            f.write('    print("  --info      Show link information")\n')
            f.write('    print("  --help      Show this help message")\n')
            f.write('\n')
            
            f.write('if __name__ == "__main__":\n')
            f.write('    main()\n')
            f.write('\n')
            f.write('# DAZZLELINK_DATA_BEGIN\n')
            
            # Write the original JSON data
            json.dump(link_data, f, indent=2)
            
        # Replace the original file
        os.replace(temp_path, dazzlelink_path)
        
        # Make it executable on Unix
        if os.name != 'nt':
            os.chmod(dazzlelink_path, os.stat(dazzlelink_path).st_mode | stat.S_IEXEC)
            
    def copy_links(self, links, dest_dir, preserve_structure=False, base_dir=None, 
              relative_links=None, verify=True):
        """
        Copy symbolic links to a destination directory.
        
        Args:
            links (list or str): List of symlink paths or single symlink path
            dest_dir (str): Destination directory
            preserve_structure (bool): Whether to preserve directory structure
            base_dir (str, optional): Base directory for preserving structure.
                If None, use common parent directory.
            relative_links (bool, optional): Convert to relative links in destination.
                If None, preserve original (relative or absolute).
            verify (bool): Verify links after copying
                
        Returns:
            list: List of created symlink paths
        """
        # Handle single link case
        if isinstance(links, str):
            links = [links]
        
        # Ensure all are symlinks
        for link in links:
            if not os.path.islink(link):
                raise DazzleLinkException(f"{link} is not a symbolic link")
        
        # Resolve destination
        dest_dir = Path(dest_dir).resolve()
        os.makedirs(dest_dir, exist_ok=True)
        
        # Determine base directory for structure preservation
        if preserve_structure and not base_dir:
            # Find common parent directory
            paths = [Path(link).parent for link in links]
            base_dir = os.path.commonpath([str(p) for p in paths])
        
        created_links = []
        
        for link in links:
            try:
                link_path = Path(link).resolve()
                target_path = os.readlink(link)
                is_absolute = os.path.isabs(target_path)
                
                # Determine destination link path
                if preserve_structure:
                    rel_path = os.path.relpath(link, base_dir)
                    dest_link = os.path.join(dest_dir, rel_path)
                    # Ensure parent directories exist
                    os.makedirs(os.path.dirname(dest_link), exist_ok=True)
                else:
                    dest_link = os.path.join(dest_dir, os.path.basename(link))
                
                # Determine target path in destination
                if relative_links is not None:
                    # Force to relative or absolute based on parameter
                    if relative_links and is_absolute:
                        # Convert absolute to relative
                        if os.path.exists(target_path):
                            # If target exists, make relative to the new link location
                            dest_link_dir = os.path.dirname(dest_link)
                            target_path = os.path.relpath(target_path, dest_link_dir)
                    elif not relative_links and not is_absolute:
                        # Convert relative to absolute
                        orig_link_dir = os.path.dirname(link)
                        abs_target = os.path.normpath(os.path.join(orig_link_dir, target_path))
                        target_path = abs_target
                
                # Create the link
                if os.path.exists(dest_link):
                    if os.path.isdir(dest_link) and not os.path.islink(dest_link):
                        shutil.rmtree(dest_link)
                    else:
                        os.unlink(dest_link)
                        
                # Create symlink
                if os.name == 'nt':
                    is_dir = os.path.isdir(os.path.join(os.path.dirname(link), target_path))
                    self._create_windows_symlink(target_path, dest_link, is_dir)
                else:
                    os.symlink(target_path, dest_link)
                
                # Copy attributes if possible
                try:
                    shutil.copystat(link, dest_link, follow_symlinks=False)
                except:
                    pass
                    
                created_links.append(dest_link)
                
            except Exception as e:
                print(f"WARNING: Failed to copy {link}: {str(e)}")
        
        # Verify all links if requested
        if verify:
            broken_links = []
            for new_link in created_links:
                try:
                    target = os.readlink(new_link)
                    if not os.path.exists(os.path.join(os.path.dirname(new_link), target)):
                        broken_links.append(new_link)
                except:
                    broken_links.append(new_link)
                    
            if broken_links:
                print(f"WARNING: {len(broken_links)} links may be broken after copying:")
                for link in broken_links[:5]:  # Show first 5
                    print(f"  {link}")
                if len(broken_links) > 5:
                    print(f"  ...and {len(broken_links) - 5} more")
        
        return created_links     

    def check_links(self, directory, recursive=True, report_only=True, fix_relative=False):
        """
        Check symlinks in a directory and report broken ones.
        Optionally attempt to fix broken relative links.
        
        Args:
            directory (str): Directory to scan
            recursive (bool): Whether to scan recursively
            report_only (bool): Only report issues, don't try to fix
            fix_relative (bool): Try to fix broken relative links by searching for targets
                
        Returns:
            dict: Report of link status with lists of 'ok', 'broken', and 'fixed' links
        """
        links = self.scan_directory(directory, recursive)
        
        result = {
            'ok': [],
            'broken': [],
            'fixed': []
        }
        
        if not links:
            print(f"No symlinks found in {directory}")
            return result
        
        print(f"Checking {len(links)} symlinks...")
        
        for link in links:
            try:
                target_path = os.readlink(link)
                absolute_target = target_path
                
                # If target is relative, convert to absolute for checking
                if not os.path.isabs(target_path):
                    base_dir = os.path.dirname(link)
                    absolute_target = os.path.normpath(os.path.join(base_dir, target_path))
                
                # Check if the target exists using os.path.exists()
                target_exists = os.path.exists(absolute_target)
                
                if target_exists:
                    result['ok'].append({
                        'link': link,
                        'target': target_path,
                        'absolute_target': absolute_target
                    })
                else:
                    # Link is broken
                    broken_info = {
                        'link': link,
                        'target': target_path,
                        'attempted_path': absolute_target
                    }
                    
                    # Try to fix if it's a relative link and fixing is enabled
                    if not report_only and not os.path.isabs(target_path) and fix_relative:
                        fixed = False
                        
                        # Try to find the target by searching up the directory tree
                        base_dir = os.path.dirname(link)
                        target_name = os.path.basename(target_path)
                        
                        # Search in parent directories for the target
                        current_dir = base_dir
                        max_depth = 5  # Limit search depth
                        depth = 0
                        
                        while depth < max_depth and current_dir and current_dir != os.path.dirname(current_dir):
                            # Check if target exists in this directory or subdirectories
                            for root, dirs, files in os.walk(current_dir):
                                for name in dirs + files:
                                    if name == target_name:
                                        candidate = os.path.join(root, name)
                                        rel_path = os.path.relpath(candidate, os.path.dirname(link))
                                        
                                        # Update the symlink
                                        os.unlink(link)
                                        os.symlink(rel_path, link)
                                        
                                        broken_info['fixed_target'] = rel_path
                                        result['fixed'].append(broken_info)
                                        fixed = True
                                        break
                                if fixed:
                                    break
                            if fixed:
                                break
                                
                            # Move up to parent directory
                            current_dir = os.path.dirname(current_dir)
                            depth += 1
                        
                        if not fixed:
                            result['broken'].append(broken_info)
                    else:
                        result['broken'].append(broken_info)
                        
            except Exception as e:
                result['broken'].append({
                    'link': link,
                    'error': str(e)
                })
        
        # Print summary
        print(f"Results: {len(result['ok'])} OK, {len(result['broken'])} broken, {len(result['fixed'])} fixed")
        
        # Print broken links
        if result['broken']:
            print("\nBroken links:")
            for info in result['broken']:
                if 'target' in info:
                    print(f"  {info['link']} -> {info['target']}")
                else:
                    print(f"  {info['link']} -> ERROR: {info['error']}")
        
        # Print fixed links
        if result['fixed']:
            print("\nFixed links:")
            for info in result['fixed']:
                print(f"  {info['link']}: {info['target']} -> {info['fixed_target']}")
        
        return result

    def rebase_links(self, directory, recursive=True, make_relative=None, 
                target_base=None, only_broken=False):
        """
        Rebase links in a directory, converting between relative and absolute paths
        or changing the base path of absolute links.
        
        Args:
            directory (str): Directory to scan
            recursive (bool): Whether to scan recursively
            make_relative (bool, optional): If True, convert absolute links to relative.
                If False, convert relative links to absolute.
                If None, don't convert.
            target_base (str, optional): For absolute links, replace base part of path.
                Format: "old_prefix:new_prefix" or just "new_prefix" to replace
                the entire path.
            only_broken (bool): Only rebase broken links
                
        Returns:
            dict: Report of links modified
        """
        links = self.scan_directory(directory, recursive)
        
        result = {
            'changed': [],
            'unchanged': [],
            'errors': []
        }
        
        if not links:
            print(f"No symlinks found in {directory}")
            return result
        
        print(f"Rebasing {len(links)} symlinks...")
        
        for link in links:
            try:
                original_target = os.readlink(link)
                is_absolute = os.path.isabs(original_target)
                link_dir = os.path.dirname(link)
                
                # Check if link is broken (if only_broken is True)
                if only_broken:
                    if is_absolute:
                        target_exists = os.path.exists(original_target)
                    else:
                        abs_path = os.path.normpath(os.path.join(link_dir, original_target))
                        target_exists = os.path.exists(abs_path)
                        
                    if target_exists:
                        result['unchanged'].append({
                            'link': link,
                            'target': original_target,
                            'reason': 'Target exists and only_broken=True'
                        })
                        continue
                
                # Determine new target
                new_target = original_target
                change_reason = None
                
                # Handle relative/absolute conversion
                if make_relative is not None:
                    if make_relative and is_absolute:
                        # Convert absolute to relative
                        new_target = os.path.relpath(original_target, link_dir)
                        change_reason = 'Converted absolute to relative'
                    elif not make_relative and not is_absolute:
                        # Convert relative to absolute
                        new_target = os.path.abspath(os.path.join(link_dir, original_target))
                        change_reason = 'Converted relative to absolute'
                
                # Handle target base replacement for absolute paths
                if target_base and is_absolute:
                    if ':' in target_base:
                        old_prefix, new_prefix = target_base.split(':', 1)
                        if original_target.startswith(old_prefix):
                            new_target = original_target.replace(old_prefix, new_prefix, 1)
                            change_reason = f'Replaced base {old_prefix} with {new_prefix}'
                    else:
                        # Replace the entire path base but keep the last part
                        path_tail = os.path.basename(original_target)
                        new_target = os.path.join(target_base, path_tail)
                        change_reason = f'Replaced with {target_base}'
                
                # Update link if target changed
                if new_target != original_target:
                    # Backup existing link first
                    backup_target = original_target
                    backup_link = f"{link}.backup"
                    if os.path.exists(backup_link):
                        os.unlink(backup_link)
                    os.symlink(backup_target, backup_link)
                    
                    # Update the link
                    os.unlink(link)
                    os.symlink(new_target, link)
                    
                    result['changed'].append({
                        'link': link,
                        'old_target': original_target,
                        'new_target': new_target,
                        'reason': change_reason,
                        'backup': backup_link
                    })
                else:
                    result['unchanged'].append({
                        'link': link,
                        'target': original_target,
                        'reason': 'No changes needed'
                    })
                    
            except Exception as e:
                result['errors'].append({
                    'link': link,
                    'error': str(e)
                })
        
        # Print summary
        print(f"Results: {len(result['changed'])} changed, {len(result['unchanged'])} unchanged, {len(result['errors'])} errors")
        
        # Print changed links
        if result['changed']:
            print("\nChanged links:")
            for info in result['changed']:
                print(f"  {info['link']}: {info['old_target']} -> {info['new_target']}")
                print(f"    Reason: {info['reason']}")
                print(f"    Backup: {info['backup']}")
        
        # Print errors
        if result['errors']:
            print("\nErrors:")
            for info in result['errors']:
                print(f"  {info['link']}: {info['error']}")
        
        return result
    

    def execute_dazzlelink(self, dazzlelink_path, mode=None, config_override=None):
        """
        Execute or open a dazzlelink file
        
        Args:
            dazzlelink_path (str): Path to the dazzlelink file
            mode (str, optional): Override execution mode for this execution
                If None, uses the mode from config_override or the dazzlelink file
            config_override (DazzleLinkConfig, optional): Configuration object to use
                If provided, its settings take precedence over the file's embedded configuration
        """
        try:
            # First try to detect if it's a script or JSON format
            with open(dazzlelink_path, 'r', encoding='utf-8') as f:
                # Read the first few lines to detect format
                first_lines = ''.join([f.readline() for _ in range(3)])
                
                # Reset file pointer to beginning
                f.seek(0)
                
                # Check if it's a script format (has shell/batch header)
                if '#!/bin/sh' in first_lines or '@echo off' in first_lines:
                    # Handle script-embedded dazzlelink
                    if os.name == 'nt':
                        # On Windows, execute as a batch file
                        cmd = [dazzlelink_path]
                        if mode:
                            cmd.append(f"--{mode}")
                        subprocess.run(cmd, shell=True)
                    else:
                        # On Unix, ensure it's executable and run it
                        if not os.access(dazzlelink_path, os.X_OK):
                            os.chmod(dazzlelink_path, os.stat(dazzlelink_path).st_mode | stat.S_IEXEC)
                        cmd = [dazzlelink_path]
                        if mode:
                            cmd.append(f"--{mode}")
                        subprocess.run(cmd)
                    return
                
                # Otherwise, try to parse as JSON
                try:
                    # Reset file pointer again just to be safe
                    f.seek(0)
                    link_data = json.load(f)
                except json.JSONDecodeError:
                    # If it's not a clean JSON but might have embedded JSON
                    # Try to extract JSON section from script format
                    f.seek(0)
                    content = f.read()
                    json_start = content.find('# DAZZLELINK_DATA_BEGIN')
                    
                    if json_start != -1:
                        json_text = content[json_start + len('# DAZZLELINK_DATA_BEGIN'):].strip()
                        try:
                            link_data = json.loads(json_text)
                        except json.JSONDecodeError:
                            raise DazzleLinkException(f"Cannot parse embedded JSON in {dazzlelink_path}")
                    else:
                        raise DazzleLinkException(f"Invalid dazzlelink format in {dazzlelink_path}")
            
            # Handle both old and new schema formats
            if "target_path" in link_data:
                # Old format
                target_path = link_data["target_path"]
                default_mode = link_data.get("default_mode", "info")
            elif "link" in link_data and "target_path" in link_data["link"]:
                # New format
                target_path = link_data["link"]["target_path"]
                default_mode = link_data.get("config", {}).get("default_mode", "info")
            else:
                raise DazzleLinkException(f"Invalid dazzlelink format in {dazzlelink_path}")
            
			
			# Use mode precedence:
            # 1. Command line mode override
            # 2. Config override (if provided)
            # 3. Dazzlelink file's embedded config
            execute_mode = mode
            if execute_mode is None and config_override is not None:
                execute_mode = config_override.get("default_mode")
            if execute_mode is None:
                execute_mode = default_mode
            
            # Execute based on mode
            if execute_mode == "info":
                # Show information about the dazzlelink
                print("DazzleLink Information:")
                print(f"Target: {target_path}")
                
                # Show original path if available
                if "original_path" in link_data:
                    print(f"Original Path: {link_data['original_path']}")
                elif "link" in link_data and "original_path" in link_data["link"]:
                    print(f"Original Path: {link_data['link']['original_path']}")
                
                # Show creation date if available
                if "creation_date" in link_data:
                    print(f"Creation Date: {link_data['creation_date']}")
                
                # Show target information if available
                if "target" in link_data:
                    target_info = link_data["target"]
                    print("\nTarget Details:")
                    print(f"  Type: {target_info.get('type', 'Unknown')}")
                    print(f"  Exists: {'Yes' if target_info.get('exists', False) else 'No'}")
                    if target_info.get('size') is not None:
                        size = target_info['size']
                        if size < 1024:
                            size_str = f"{size} bytes"
                        elif size < 1024 * 1024:
                            size_str = f"{size/1024:.1f} KB"
                        else:
                            size_str = f"{size/(1024*1024):.1f} MB"
                        print(f"  Size: {size_str}")
            
            elif execute_mode == "open" or execute_mode == "auto":
                # Try to open the target
                if os.name == 'nt':
                    os.startfile(target_path)
                else:
                    subprocess.run(['xdg-open', target_path])
            
            else:
                raise DazzleLinkException(f"Unknown execution mode: {execute_mode}")
                
        except Exception as e:
            raise DazzleLinkException(f"Failed to execute dazzlelink {dazzlelink_path}: {str(e)}")
        
    def update_config_batch(self, path, mode=None, pattern="*.dazzlelink", recursive=False):
        """
        Update configuration for multiple dazzlelink files.
        
        Args:
            path: Directory or file path to update
            mode: New default execution mode (info, open, auto)
            pattern: File pattern to match (default: *.dazzlelink)
            recursive: Whether to search subdirectories
            dry_run: If True, show what would be changed without making changes
            config_level: Configuration level to save changes to ('global', 'directory', 'file')
            make_executable: Whether to make updated dazzlelinks executable
            
        Returns:
            dict: Report of updated files and any errors
        """
        import fnmatch
        
        results = {
            'updated': [],
            'errors': [],
            'skipped': []
        }
        
        # Handle config level
        if config_level == 'global':
            # Save to global config
            if mode is not None:
                self.config.set('default_mode', mode)
            if make_executable is not None:
                self.config.set('make_executable', make_executable)
                
            if not dry_run:
                # Save global config
                if self.config.save_global_config():
                    print(f"Updated global configuration")
                else:
                    print(f"Failed to update global configuration")
            
        elif config_level == 'directory':
            # Determine directory based on path
            if os.path.isfile(path):
                directory = os.path.dirname(path)
            else:
                directory = path
                
            # Load existing directory config
            self.config.load_directory_config(directory)
            
            # Update config
            if mode is not None:
                self.config.set('default_mode', mode)
            if make_executable is not None:
                self.config.set('make_executable', make_executable)
                
            if not dry_run:
                # Save directory config
                if self.config.save_directory_config(directory):
                    print(f"Updated directory configuration for {directory}")
                else:
                    print(f"Failed to update directory configuration for {directory}")
        
        # Continue only if we're updating file-level configs or we're in dry-run mode
        if config_level == 'file' or dry_run:
            # Find all matching dazzlelinks
            paths_to_check = []
            path_obj = Path(path)
            
            if path_obj.is_file():
                # Single file
                if path_obj.suffix == self.DAZZLELINK_EXT:
                    paths_to_check.append(path_obj)
            elif path_obj.is_dir():
                # Directory search
                if recursive:
                    # Recursive search
                    for root, _, files in os.walk(path_obj):
                        for file in files:
                            if fnmatch.fnmatch(file, pattern):
                                paths_to_check.append(Path(root) / file)
                else:
                    # Non-recursive search
                    for file in path_obj.glob(pattern):
                        if file.is_file():
                            paths_to_check.append(file)
            
            # Process each matching file
            for dazzlelink_path in paths_to_check:
                try:
                    if config_level != 'file' and not dry_run:
                        # If we're only updating global or directory config, just track files that would be affected
                        results['updated'].append(str(dazzlelink_path))
                        continue
                        
                    # Load the dazzlelink
                    with open(dazzlelink_path, 'r', encoding='utf-8') as f:
                        # Try to detect if it's a script or JSON format
                        content = f.read()
                        
                        # Check if it's a script-embedded dazzlelink
                        json_start = content.find('# DAZZLELINK_DATA_BEGIN')
                        if json_start != -1:
                            # Extract JSON part
                            json_text = content[json_start + len('# DAZZLELINK_DATA_BEGIN'):].strip()
                            try:
                                link_data = json.loads(json_text)
                                is_script = True
                            except json.JSONDecodeError:
                                results['errors'].append({
                                    'path': str(dazzlelink_path),
                                    'error': 'Failed to parse embedded JSON'
                                })
                                continue
                        else:
                            # Try parsing as plain JSON
                            try:
                                link_data = json.loads(content)
                                is_script = False
                            except json.JSONDecodeError:
                                results['errors'].append({
                                    'path': str(dazzlelink_path),
                                    'error': 'Not a valid dazzlelink file'
                                })
                                continue
                    
                    # Check if any changes needed
                    changes_made = False
                    
                    # Update config based on provided parameters
                    if mode is not None:
                        # Validate mode
                        if mode not in DazzleLinkConfig.VALID_MODES:
                            results['errors'].append({
                                'path': str(dazzlelink_path),
                                'error': f"Invalid mode '{mode}'"
                            })
                            continue
                        
                        # Handle both old and new schema formats
                        if "config" in link_data:
                            if "default_mode" not in link_data["config"] or link_data["config"]["default_mode"] != mode:
                                link_data["config"]["default_mode"] = mode
                                changes_made = True
                        else:
                            # Create config if it doesn't exist
                            link_data["config"] = {
                                "default_mode": mode,
                                "platform": self.platform
                            }
                            changes_made = True
                    
                    # Check if we need to update the executable flag
                    if make_executable is not None:
                        # We'll handle this outside the file content
                        changes_made = True
                    
                    # If no changes needed, skip
                    if not changes_made:
                        results['skipped'].append(str(dazzlelink_path))
                        continue
                    
                    # If dry run, report but don't make changes
                    if dry_run:
                        results['updated'].append(str(dazzlelink_path))
                        continue
                    
                    # Make the changes
                    if is_script:
                        # For script-embedded dazzlelinks, preserve the script part
                        script_part = content[:json_start + len('# DAZZLELINK_DATA_BEGIN')]
                        
                        with open(dazzlelink_path, 'w', encoding='utf-8') as f:
                            f.write(script_part + '\n')
                            json.dump(link_data, f, indent=2)
                    else:
                        # For plain JSON dazzlelinks
                        with open(dazzlelink_path, 'w', encoding='utf-8') as f:
                            json.dump(link_data, f, indent=2)
                    
                    # Handle executable flag if specified
                    if make_executable is not None:
                        if make_executable:
                            self._make_dazzlelink_executable(dazzlelink_path, link_data)
                        # Note: There's no direct way to make a file "non-executable" in the current code
                    
                    results['updated'].append(str(dazzlelink_path))
                    
                except Exception as e:
                    results['errors'].append({
                        'path': str(dazzlelink_path),
                        'error': str(e)
                    })
        
        return results

def main():
    """Main entry point for the dazzlelink tool"""
    parser = argparse.ArgumentParser(
        description='Dazzlelink - Symbolic Link Preservation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument( "--version", "-v", action="version", version=f"%(prog)s {__version__}")
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new dazzlelink')
    create_parser.add_argument('target', help='Target file/directory')
    create_parser.add_argument('link_name', help='Name of the link to create')
    create_parser.add_argument('--executable', '-e', action='store_true', 
                              help='Make the dazzlelink executable')
    create_parser.add_argument('--mode', '-m', choices=['info', 'open', 'auto'],
                              help='Default execution mode for this dazzlelink')
    create_parser.add_argument('--config-level', choices=['global', 'directory', 'file'],
                             default='file', help='Configuration level to use')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export a symlink to a dazzlelink')
    export_parser.add_argument('link_path', help='Path to the symlink')
    export_parser.add_argument('--output', '-o', help='Output path for the dazzlelink')
    export_parser.add_argument('--executable', '-e', action='store_true', 
                              help='Make the dazzlelink executable')
    export_parser.add_argument('--mode', '-m', choices=['info', 'open', 'auto'],
                              help='Default execution mode for this dazzlelink')
    export_parser.add_argument('--config-level', choices=['global', 'directory', 'file'],
                             default='file', help='Configuration level to use')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import and recreate symlinks from dazzlelinks')
    import_parser.add_argument('paths', nargs='+', help='Paths to dazzlelink files or directories')
    import_parser.add_argument('--target-location', '-t', help='Override location for the recreated symlinks')
    import_parser.add_argument('--recursive', '-r', action='store_true',
                              help='Search directories recursively for dazzlelinks')
    import_parser.add_argument('--pattern', '-p', default='*.dazzlelink',
                              help='Glob pattern to filter dazzlelink filenames (default: *.dazzlelink)')
    import_parser.add_argument('--flatten', '-f', action='store_true',
                              help='Flatten directory structure when recreating symlinks')
    import_parser.add_argument('--dry-run', '-d', action='store_true',
                              help='Show what would be done without making changes')
    import_parser.add_argument('--remove-dazzlelinks', action='store_true',
                              help='Remove dazzlelink files after successful import')
    import_parser.add_argument('--config-level', choices=['global', 'directory', 'file'],
                             default='file', help='Configuration level to use')
    import_parser.add_argument('--timestamp-strategy', choices=['current', 'symlink', 'target', 'preserve-all'], default='current',
                              help='Strategy for setting timestamps (default: current)')
    import_parser.add_argument('--update-dazzlelink', '-u', action='store_true',
                              help='Update dazzlelink metadata during import')
    import_parser.add_argument('--use-live-target', '-l', action='store_true',
                              help='Check live target files for timestamps')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan for symlinks and report')
    scan_parser.add_argument('directory', help='Directory to scan')
    scan_parser.add_argument('--no-recursive', '-n', action='store_true', 
                            help='Do not scan recursively')
    scan_parser.add_argument('--json', '-j', action='store_true',
                            help='Output in JSON format')
    
    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert all symlinks in directory to dazzlelinks')
    convert_parser.add_argument('directory', help='Directory to scan')
    convert_parser.add_argument('--no-recursive', '-n', action='store_true', 
                              help='Do not scan recursively')
    convert_parser.add_argument('--remove-originals', '-r', action='store_true',
                              help='Remove original symlinks after conversion')
    convert_parser.add_argument('--executable', '-e', action='store_true', 
                              help='Make the dazzlelinks executable')
    convert_parser.add_argument('--mode', '-m', choices=['info', 'open', 'auto'],
                              help='Default execution mode for dazzlelinks')
    convert_parser.add_argument('--config-level', choices=['global', 'directory', 'file'],
                             default='file', help='Configuration level to use')
    
    # Mirror command
    mirror_parser = subparsers.add_parser('mirror', 
                                         help='Mirror directory structure with dazzlelinks')
    mirror_parser.add_argument('src_dir', help='Source directory')
    mirror_parser.add_argument('dest_dir', help='Destination directory')
    mirror_parser.add_argument('--no-recursive', '-n', action='store_true', 
                             help='Do not scan recursively')
    mirror_parser.add_argument('--executable', '-e', action='store_true', 
                             help='Make the dazzlelinks executable')
    mirror_parser.add_argument('--mode', '-m', choices=['info', 'open', 'auto'],
                             help='Default execution mode for dazzlelinks')
    mirror_parser.add_argument('--config-level', choices=['global', 'directory', 'file'],
                             default='file', help='Configuration level to use')
    
    # Execute command
    execute_parser = subparsers.add_parser('execute', help='Execute/open the target of a dazzlelink')
    execute_parser.add_argument('dazzlelink_path', help='Path to the dazzlelink')
    execute_parser.add_argument('--mode', '-m', choices=['info', 'open', 'auto'],
                              help='Override execution mode for this execution')
    execute_parser.add_argument('--config-level', choices=['global', 'directory', 'file'],
                             default='file', help='Configuration level to use')
    
    # Config command
    config_parser = subparsers.add_parser('config', help='View or set configuration options')
    config_action = config_parser.add_mutually_exclusive_group(required=True)
    config_action.add_argument('--view', action='store_true', help='View current configuration')
    config_action.add_argument('--set', metavar='KEY=VALUE', help='Set a configuration value')
    config_action.add_argument('--reset', action='store_true', help='Reset to default configuration')
    config_scope = config_parser.add_mutually_exclusive_group()
    config_scope.add_argument('--global', dest='global_scope', action='store_true', 
                             help='Apply to global configuration')
    config_scope.add_argument('--directory', '-d', help='Apply to specific directory')

    # Copy command
    copy_parser = subparsers.add_parser('copy', help='Copy symlinks to another location')
    copy_parser.add_argument('links', nargs='+', help='Links to copy (files or directories)')
    copy_parser.add_argument('destination', help='Destination directory')
    copy_parser.add_argument('--preserve-structure', '-p', action='store_true',
                            help='Preserve directory structure')
    copy_parser.add_argument('--base-dir', '-b', help='Base directory for structure preservation')
    copy_parser.add_argument('--relative', '-r', action='store_true',
                            help='Convert to relative links in destination')
    copy_parser.add_argument('--absolute', '-a', action='store_true',
                            help='Convert to absolute links in destination')
    copy_parser.add_argument('--no-verify', '-n', action='store_true',
                            help='Skip verification of links after copying')
    copy_parser.add_argument('--config-level', choices=['global', 'directory', 'file'],
                           default='file', help='Configuration level to use')

    # Check command
    check_parser = subparsers.add_parser('check', help='Check symlinks and report broken ones')
    check_parser.add_argument('directory', help='Directory to scan')
    check_parser.add_argument('--no-recursive', '-n', action='store_true',
                            help='Do not scan recursively')
    check_parser.add_argument('--fix', '-f', action='store_true',
                            help='Try to fix broken links')
    check_parser.add_argument('--fix-relative', '-r', action='store_true',
                            help='Try to fix broken relative links by searching')

    # Rebase command
    rebase_parser = subparsers.add_parser('rebase', help='Change link paths (relative/absolute conversion)')
    rebase_parser.add_argument('directory', help='Directory to scan')
    rebase_parser.add_argument('--no-recursive', '-n', action='store_true',
                            help='Do not scan recursively')
    rebase_parser.add_argument('--relative', '-r', action='store_true',
                            help='Convert absolute links to relative')
    rebase_parser.add_argument('--absolute', '-a', action='store_true',
                            help='Convert relative links to absolute')
    rebase_parser.add_argument('--target-base', '-t', 
                            help='Replace base path (format: old_prefix:new_prefix)')
    rebase_parser.add_argument('--only-broken', '-b', action='store_true',
                            help='Only rebase broken links')

    # Add update-config command
    update_config_parser = subparsers.add_parser('update-config', 
                                               help='Update configuration for multiple dazzlelinks')
    update_config_parser.add_argument('path', help='Path to file or directory to update')
    update_config_parser.add_argument('--mode', '-m', choices=['info', 'open', 'auto'],
                                    help='New default execution mode')
    update_config_parser.add_argument('--pattern', '-p', default='*.dazzlelink',
                                    help='File pattern to match (default: *.dazzlelink)')
    update_config_parser.add_argument('--recursive', '-r', action='store_true',
                                    help='Search subdirectories recursively')
    update_config_parser.add_argument('--dry-run', '-d', action='store_true',
                                    help='Show what would be changed without making changes')
    update_config_parser.add_argument('--config-level', choices=['global', 'directory', 'file'],
                                    default='file', 
                                    help='Configuration level to save changes to (default: file)')
    update_config_parser.add_argument('--make-executable', action='store_true',
                                    help='Make updated dazzlelinks executable')

    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Create configuration
    config = DazzleLinkConfig()
    
    # Create dazzlelink instance with config
    dazzlelink = DazzleLink(config)
    
    try:
        # Fix for the create command in main()
        if args.command == 'create':
            # Apply configuration level
            if hasattr(args, 'config_level'):
                if args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif args.config_level == 'directory':
                    # Apply directory configuration
                    target_dir = os.path.dirname(os.path.abspath(args.link_name))
                    config.load_directory_config(target_dir)
                # 'file' level uses defaults or command-line overrides
            
            # Set specific command options in config
            if hasattr(args, 'executable') and args.executable is not None:
                config.set('make_executable', args.executable)
            if hasattr(args, 'mode') and args.mode is not None:
                config.set('default_mode', args.mode)
                
            link_path = os.path.abspath(args.link_name)
            target_path = os.path.abspath(args.target)
            
            # Create parent directory if needed
            os.makedirs(os.path.dirname(link_path), exist_ok=True)
            
            # Directly create the dazzlelink
            dazzlelink_path = dazzlelink.serialize_link(
                target_path,
                output_path=link_path,  # Use link_path DIRECTLY
                make_executable=args.executable,
                mode=args.mode,
                require_symlink=False
            )
            
            print(f"Created dazzlelink: {dazzlelink_path}")

        elif args.command == 'export':
            # Apply configuration level
            if hasattr(args, 'config_level'):
                if args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif args.config_level == 'directory':
                    # Apply directory configuration
                    link_dir = os.path.dirname(os.path.abspath(args.link_path))
                    config.load_directory_config(link_dir)
                # 'file' level uses defaults or command-line overrides
            
            dazzlelink_path = dazzlelink.serialize_link(
                args.link_path, 
                output_path=args.output,
                make_executable=args.executable,
                mode=args.mode
            )
            print(f"Exported symlink to dazzlelink: {dazzlelink_path}")
           
        elif args.command == 'import':
            # Apply configuration level
            if hasattr(args, 'config_level'):
                if args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif args.config_level == 'directory':
                    # For batch import, directory config will be loaded for each directory
                    pass
                # 'file' level uses defaults or command-line overrides
            
            # Modified condition to handle directory paths without recursion
            # Check if multiple paths, recursive option specified, or if any path is a directory
            if (len(args.paths) > 1 or args.recursive or 
                '*' in ''.join(args.paths) or '?' in ''.join(args.paths) or
                any(os.path.isdir(p) for p in args.paths)):
                
                # Use batch import
                result = dazzlelink.batch_import(
                    args.paths,
                    target_location=args.target_location,
                    recursive=args.recursive,
                    flatten=args.flatten,
                    pattern=args.pattern,
                    dry_run=args.dry_run,
                    remove_dazzlelinks=args.remove_dazzlelinks,
                    config_level=args.config_level if hasattr(args, 'config_level') else 'file',
                    timestamp_strategy=args.timestamp_strategy if hasattr(args, 'timestamp_strategy') else 'current',
                    update_dazzlelink=args.update_dazzlelink if hasattr(args, 'update_dazzlelink') else False,
                    use_live_target=args.use_live_target if hasattr(args, 'use_live_target') else False
                )
                
                if result["error"] and not result["success"]:
                    # If all operations failed, return error code
                    return 1
                    
            else:
                # Single file mode, use original behavior for backward compatibility
                link_path = dazzlelink.recreate_link(
                    args.paths[0],
                    target_location=args.target_location
                )
                print(f"Recreated symlink: {link_path}")
                
                # Handle remove_dazzlelinks option for consistency with batch mode
                if args.remove_dazzlelinks:
                    try:
                        os.unlink(args.paths[0])
                        print(f"Removed dazzlelink: {args.paths[0]}")
                    except Exception as e:
                        print(f"WARNING: Failed to remove dazzlelink {args.paths[0]}: {str(e)}")
            
        elif args.command == 'scan':
            # Configure recursive option
            recursive = not args.no_recursive if hasattr(args, 'no_recursive') else config.get('recursive_scan')
            
            links = dazzlelink.scan_directory(
                args.directory,
                recursive=recursive
            )
            
            if args.json:
                result = []
                for link in links:
                    try:
                        target = os.readlink(link)
                        is_dir = os.path.isdir(os.path.join(os.path.dirname(link), target))
                        result.append({
                            'link_path': link,
                            'target_path': target,
                            'is_directory': is_dir
                        })
                    except:
                        result.append({
                            'link_path': link,
                            'target_path': "ERROR: Could not read link target",
                            'is_directory': False
                        })
                        
                print(json.dumps(result, indent=2))
            else:
                print(f"Found {len(links)} symbolic links in {args.directory}:")
                for link in links:
                    try:
                        target = os.readlink(link)
                        print(f"  {link} -> {target}")
                    except:
                        print(f"  {link} -> ERROR: Could not read link target")
            
        elif args.command == 'convert':
            # Apply configuration level
            if hasattr(args, 'config_level'):
                if args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif args.config_level == 'directory':
                    # Apply directory configuration
                    config.load_directory_config(args.directory)
                # 'file' level uses defaults or command-line overrides
            
            # Apply command-line arguments to config
            config.apply_args(args)
            
            keep_originals = not args.remove_originals if hasattr(args, 'remove_originals') else config.get('keep_originals')
            
            dazzlelinks = dazzlelink.convert_directory(
                args.directory,
                recursive=not args.no_recursive if hasattr(args, 'no_recursive') else None,
                keep_originals=keep_originals,
                make_executable=args.executable if hasattr(args, 'executable') else None,
                mode=args.mode if hasattr(args, 'mode') else None
            )
            
            action = "Converted" if keep_originals else "Replaced"
            print(f"{action} {len(dazzlelinks)} symlinks to dazzlelinks in {args.directory}")
            
        elif args.command == 'mirror':
            # Apply configuration level
            if hasattr(args, 'config_level'):
                if args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif args.config_level == 'directory':
                    # Apply directory configuration from source directory
                    config.load_directory_config(args.src_dir)
                # 'file' level uses defaults or command-line overrides
            
            # Apply command-line arguments to config
            config.apply_args(args)
            
            dazzlelinks = dazzlelink.mirror_directory(
                args.src_dir,
                args.dest_dir,
                recursive=not args.no_recursive if hasattr(args, 'no_recursive') else None,
                make_executable=args.executable if hasattr(args, 'executable') else None,
                mode=args.mode if hasattr(args, 'mode') else None
            )
            
            print(f"Mirrored {len(dazzlelinks)} symlinks as dazzlelinks from {args.src_dir} to {args.dest_dir}")
            
        elif args.command == 'execute':
            # Apply configuration level
            if hasattr(args, 'config_level'):
                if args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif args.config_level == 'directory':
                    # Apply directory configuration
                    dlink_dir = os.path.dirname(os.path.abspath(args.dazzlelink_path))
                    config.load_directory_config(dlink_dir)
                # 'file' level uses the dazzlelink's embedded configuration
            
            dazzlelink.execute_dazzlelink(
                args.dazzlelink_path,
                mode=args.mode if hasattr(args, 'mode') else None,
                config_override=config if hasattr(args, 'config_level') else None
            )
            
        elif args.command == 'config':
            # Determine configuration scope
            if hasattr(args, 'global_scope') and args.global_scope:
                scope = "global"
            elif hasattr(args, 'directory') and args.directory:
                scope = "directory"
                config.load_directory_config(args.directory)
            else:
                # Default to current directory
                scope = "directory"
                config.load_directory_config()
            
            if args.view:
                # View configuration
                print(f"Current {scope} configuration:")
                for key, value in config.config.items():
                    print(f"  {key}: {value}")
                    
            elif args.set:
                # Set configuration value
                try:
                    key, value = args.set.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Convert string values to appropriate types
                    if value.lower() == 'true':
                        value = True
                    elif value.lower() == 'false':
                        value = False
                    elif value.isdigit():
                        value = int(value)
                    
                    if key not in config.config:
                        print(f"WARNING: Unknown configuration key: {key}")
                    elif key == 'default_mode' and value not in DazzleLinkConfig.VALID_MODES:
                        print(f"ERROR: Invalid mode '{value}'. Valid modes are: {', '.join(DazzleLinkConfig.VALID_MODES)}")
                    else:
                        config.set(key, value)
                        
                        # Save configuration
                        if scope == "global":
                            if config.save_global_config():
                                print(f"Updated global configuration: {key}={value}")
                        else:
                            dir_path = args.directory if hasattr(args, 'directory') and args.directory else os.getcwd()
                            if config.save_directory_config(dir_path):
                                print(f"Updated directory configuration for {dir_path}: {key}={value}")
                except ValueError:
                    print("ERROR: Invalid format. Use KEY=VALUE")
                    
            elif args.reset:
                # Reset configuration to defaults
                config.config = config.DEFAULT_CONFIG.copy()
                
                if scope == "global":
                    if config.save_global_config():
                        print("Reset global configuration to defaults")
                else:
                    dir_path = args.directory if hasattr(args, 'directory') and args.directory else os.getcwd()
                    if config.save_directory_config(dir_path):
                        print(f"Reset directory configuration for {dir_path} to defaults")

        elif args.command == 'update-config':
            # Apply configuration level for saving changes
            config_level = args.config_level if hasattr(args, 'config_level') else 'file'
            
            # Execute batch update
            result = dazzlelink.update_config_batch(
                args.path,
                mode=args.mode,
                pattern=args.pattern,
                recursive=args.recursive,
                dry_run=args.dry_run,
                config_level=config_level,
                make_executable=args.make_executable
            )
            
            # Report results
            if args.dry_run:
                print("Dry run - no changes were made")
                
            print(f"Results:")
            print(f"  {len(result['updated'])} files would be updated" if args.dry_run else f"  {len(result['updated'])} files updated")
            print(f"  {len(result['skipped'])} files skipped (no changes needed)")
            print(f"  {len(result['errors'])} errors encountered")
            
            if result['errors']:
                print("\nErrors:")
                for error in result['errors']:
                    print(f"  {error['path']}: {error['error']}")
        
        elif args.command == 'copy':
            # Determine relative/absolute preference
            relative_links = None
            if args.relative and args.absolute:
                print("ERROR: Cannot specify both --relative and --absolute")
                return 1
            elif args.relative:
                relative_links = True
            elif args.absolute:
                relative_links = False
            
            # Expand directories to get all links
            all_links = []
            for link_path in args.links:
                if os.path.isdir(link_path):
                    # Scan directory for links
                    dir_links = dazzlelink.scan_directory(link_path, recursive=True)
                    all_links.extend(dir_links)
                elif os.path.islink(link_path):
                    all_links.append(link_path)
                else:
                    print(f"WARNING: {link_path} is not a symlink or directory, skipping")
            
            if not all_links:
                print("ERROR: No symlinks found to copy")
                return 1
            
            # Copy the links
            copied_links = dazzlelink.copy_links(
                all_links,
                args.destination,
                preserve_structure=args.preserve_structure,
                base_dir=args.base_dir,
                relative_links=relative_links,
                verify=not args.no_verify
            )
            
            print(f"Copied {len(copied_links)} symlinks to {args.destination}")

        elif args.command == 'check':
            recursive = not args.no_recursive if hasattr(args, 'no_recursive') else config.get('recursive_scan')
            report_only = not (args.fix or args.fix_relative)
            
            result = dazzlelink.check_links(
                args.directory,
                recursive=recursive,
                report_only=report_only,
                fix_relative=args.fix_relative
            )
            
            # Result is already printed in the function
            # Return non-zero if broken links found
            if result['broken']:
                return 1

        elif args.command == 'rebase':
            recursive = not args.no_recursive if hasattr(args, 'no_recursive') else config.get('recursive_scan')
            
            # Determine relative/absolute preference
            make_relative = None
            if args.relative and args.absolute:
                print("ERROR: Cannot specify both --relative and --absolute")
                return 1
            elif args.relative:
                make_relative = True
            elif args.absolute:
                make_relative = False
            
            result = dazzlelink.rebase_links(
                args.directory,
                recursive=recursive,
                make_relative=make_relative,
                target_base=args.target_base,
                only_broken=args.only_broken
            )
            
            # Return non-zero if errors found
            if result['errors']:
                return 1
            
        return 0
        
    except DazzleLinkException as e:
        print(f"ERROR: {str(e)}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {str(e)}", file=sys.stderr)
        return 1
        

if __name__ == "__main__":
    sys.exit(main())