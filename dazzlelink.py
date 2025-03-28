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
            
            # Collect target information - use separate function to avoid following symlinks
            target_info = self._collect_target_info(target_path)
                
            # Collect security information
            security_info = self._collect_security_info(link_path)
            
            # Get file stats if available
            creation_time, modified_time, access_time = self._collect_timestamp_info(link_path)
                
            # Validate mode
            if mode not in DazzleLinkConfig.VALID_MODES:
                print(f"WARNING: Invalid mode '{mode}', using default")
                mode = self.config.get("default_mode")
                
            link_data = {
                "schema_version": self.VERSION,
                "created_by": f"DazzleLink v{self.VERSION}",
                "creation_timestamp": datetime.datetime.now().timestamp(),
                "creation_date": datetime.datetime.now().isoformat(),
                
                "link": {
                    "original_path": str(link_path),
                    "path_representations": path_representations,
                    "target_path": target_path,
                    "target_representations": target_representations,
                    "type": "symlink" if is_symlink else "file",
                    "relative_path": os.path.isabs(target_path) == False,
                    "timestamps": {
                        "created": creation_time,
                        "modified": modified_time,
                        "accessed": access_time,
                        "created_iso": datetime.datetime.fromtimestamp(creation_time).isoformat() if creation_time else None,
                        "modified_iso": datetime.datetime.fromtimestamp(modified_time).isoformat() if modified_time else None,
                        "accessed_iso": datetime.datetime.fromtimestamp(access_time).isoformat() if access_time else None
                    },
                    "attributes": self._collect_file_attributes(link_path)
                },
                
                "target": target_info,
                "security": security_info,
                
                "config": {
                    "default_mode": mode,
                    "platform": self.platform
                }
            }
            
            if output_path is None:
                output_path = f"{link_path}{self.DAZZLELINK_EXT}"
            else:
                output_path = Path(output_path)
                # Ensure parent directory exists
                os.makedirs(output_path.parent, exist_ok=True)
            
            # Create the dazzlelink file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(link_data, f, indent=2)
            
            if make_executable:
                self._make_dazzlelink_executable(output_path, link_data)
            
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
        
    def _collect_timestamp_info(self, file_path):
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

    def recreate_link(self, dazzlelink_path, target_location=None):
        """
        Recreate a symbolic link from a .dazzlelink file
        
        Args:
            dazzlelink_path (str): Path to the dazzlelink file
            target_location (str, optional): Override location for the recreated symlink
            
        Returns:
            str: Path to the created symbolic link
        """
        try:
            with open(dazzlelink_path, 'r', encoding='utf-8') as f:
                link_data = json.load(f)
            
            # Handle both old and new schema formats
            if "target_path" in link_data:
                # Old format
                target_path = link_data["target_path"]
                original_path = link_data["original_path"]
                is_dir = link_data.get("is_directory", False)
            elif "link" in link_data and "target_path" in link_data["link"]:
                # New format
                target_path = link_data["link"]["target_path"]
                original_path = link_data["link"]["original_path"]
                is_dir = link_data["target"].get("type") == "directory" if "target" in link_data else False
            else:
                raise DazzleLinkException(f"Invalid dazzlelink format in {dazzlelink_path}")
            
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
            
            # Attempt to restore file attributes if available
            self._restore_file_attributes(link_path, link_data)
            
            return link_path
            
        except Exception as e:
            raise DazzleLinkException(f"Failed to recreate link from {dazzlelink_path}: {str(e)}")
    
    def _restore_file_attributes(self, link_path, link_data):
        """
        Attempt to restore file attributes from the link data
        
        Args:
            link_path (str): Path to the recreated symlink
            link_data (dict): The dazzlelink data containing attributes
        """
        # Only attempt on Windows for now as Unix is more complex with permissions
        if os.name != 'nt':
            return
            
        try:
            # Extract attributes from either schema format
            if "attributes" in link_data:
                # Old format
                attributes = link_data["attributes"]
                hidden = attributes.get("hidden", False)
                system = attributes.get("system", False)
                readonly = attributes.get("readonly", False)
            elif "link" in link_data and "attributes" in link_data["link"]:
                # New format
                attributes = link_data["link"]["attributes"]
                hidden = attributes.get("hidden", False)
                system = attributes.get("system", False)
                readonly = attributes.get("readonly", False)
            else:
                return
                
            if os.name == 'nt':
                import ctypes
                
                # Get current attributes
                current_attrs = ctypes.windll.kernel32.GetFileAttributesW(link_path)
                
                if current_attrs == -1:
                    return
                    
                # Modify attributes as needed
                new_attrs = current_attrs
                
                if hidden:
                    new_attrs |= 0x2  # FILE_ATTRIBUTE_HIDDEN
                else:
                    new_attrs &= ~0x2
                    
                if system:
                    new_attrs |= 0x4  # FILE_ATTRIBUTE_SYSTEM
                else:
                    new_attrs &= ~0x4
                    
                if readonly:
                    new_attrs |= 0x1  # FILE_ATTRIBUTE_READONLY
                else:
                    new_attrs &= ~0x1
                    
                # Apply new attributes if different
                if new_attrs != current_attrs:
                    ctypes.windll.kernel32.SetFileAttributesW(link_path, new_attrs)
        except:
            # Don't fail the whole operation just because we couldn't restore attributes
            pass

    def _create_windows_symlink(self, target_path, link_path, is_directory):
        """
        Create a symbolic link on Windows, handling privilege elevation if needed
        
        Args:
            target_path (str): Target of the symlink
            link_path (str): Location of the symlink to create
            is_directory (bool): Whether the target is a directory
        """
        try:
            # Try direct creation first
            if is_directory:
                os.symlink(target_path, link_path, target_is_directory=True)
            else:
                os.symlink(target_path, link_path)
        except OSError as e:
            if getattr(e, 'winerror', 0) == 1314:  # Privilege not held
                # Fall back to using mklink command with elevation
                dir_flag = '/D ' if is_directory else ''
                cmd = f'mklink {dir_flag}"{link_path}" "{target_path}"'
                
                try:
                    # Inform the user
                    print(f"Attempting to create symlink with elevated privileges...")
                    
                    # Use PowerShell to run elevated command
                    ps_cmd = f'Start-Process cmd.exe -Verb RunAs -ArgumentList "/c {cmd}"'
                    subprocess.run(['powershell', '-Command', ps_cmd], check=True)
                    
                    # Check if link was created (there might be a delay)
                    attempts = 0
                    while attempts < 5 and not os.path.exists(link_path):
                        time.sleep(1)
                        attempts += 1
                    
                    if not os.path.exists(link_path):
                        print(f"WARNING: Link creation requested but could not verify it was created.")
                        print(f"You may need to manually run: {cmd}")
                except subprocess.SubprocessError as se:
                    raise DazzleLinkException(f"Failed to create elevated symlink: {str(se)}")
            else:
                raise DazzleLinkException(f"Failed to create symlink: {str(e)}")

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
    

    def execute_dazzlelink(self, dazzlelink_path, mode=None):
        """
        Execute or open a dazzlelink file
        
        Args:
            dazzlelink_path (str): Path to the dazzlelink file
            mode (str, optional): Override execution mode for this execution
                If None, uses the mode stored in the dazzlelink
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
            
            # Use specified mode or default mode from the dazzlelink
            execute_mode = mode or default_mode
            
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
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export a symlink to a dazzlelink')
    export_parser.add_argument('link_path', help='Path to the symlink')
    export_parser.add_argument('--output', '-o', help='Output path for the dazzlelink')
    export_parser.add_argument('--executable', '-e', action='store_true', 
                              help='Make the dazzlelink executable')
    export_parser.add_argument('--mode', '-m', choices=['info', 'open', 'auto'],
                              help='Default execution mode for this dazzlelink')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import and recreate a symlink from a dazzlelink')
    import_parser.add_argument('dazzlelink_path', help='Path to the dazzlelink')
    import_parser.add_argument('--target-location', '-t', help='Override location for the recreated symlink')
    
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
    
    # Execute command
    execute_parser = subparsers.add_parser('execute', help='Execute/open the target of a dazzlelink')
    execute_parser.add_argument('dazzlelink_path', help='Path to the dazzlelink')
    execute_parser.add_argument('--mode', '-m', choices=['info', 'open', 'auto'],
                              help='Override execution mode for this execution')
    
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
            dazzlelink_path = dazzlelink.serialize_link(
                args.link_path, 
                output_path=args.output,
                make_executable=args.executable,
                mode=args.mode
            )
            print(f"Exported symlink to dazzlelink: {dazzlelink_path}")
            
        elif args.command == 'import':
            link_path = dazzlelink.recreate_link(
                args.dazzlelink_path,
                target_location=args.target_location
            )
            print(f"Recreated symlink: {link_path}")
            
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
            dazzlelink.execute_dazzlelink(
                args.dazzlelink_path,
                mode=args.mode if hasattr(args, 'mode') else None
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
        # Then add these in the command handling part of main()
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