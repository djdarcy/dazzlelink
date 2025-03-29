"""
Core operations for Dazzlelink.

This module provides the main DazzleLink class with core functionality
for working with symbolic links and dazzlelink files.
"""

import os
import sys
import re
import json
import stat
import shutil
import datetime
import subprocess
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

from ..exceptions import DazzleLinkException
from ..data import DazzleLinkData
from ..config import DazzleLinkConfig
from ..path import UNCAdapter, get_unc_adapter

# Add debugging support
VERBOSE = os.environ.get('DAZZLELINK_VERBOSE', '0') == '1'
logger = logging.getLogger(__name__)

def debug_print(message):
    """Print debug messages if VERBOSE is enabled"""
    if VERBOSE:
        print(f"DEBUG: {message}")
        logger.debug(message)

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
        
        # Initialize UNC adapter for path conversions
        self._initialize_unc_adapter()
    
    def _initialize_unc_adapter(self):
        """Initialize the UNC adapter if on Windows and not already initialized"""
        if os.name == 'nt' and not hasattr(self, '_unc_adapter'):
            try:
                # Use the UNCAdapter from the path module
                self._unc_adapter = get_unc_adapter()
                debug_print("Initialized UNC adapter")
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