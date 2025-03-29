"""
Path handling utilities for UNC paths, network drives, and substituted drives.
"""

import os
import re
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional, Union

from .exceptions import DazzleLinkException

# Set up module-level logger
logger = logging.getLogger(__name__)

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
                logger.debug(f"UNC mappings: {self.mapping}")
        except Exception as e:
            logger.warning(f"Failed to get network mappings: {e}")
    
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


# Helper functions that create and use a global UNCAdapter instance
_global_adapter = None

def get_unc_adapter():
    """Get or create the global UNCAdapter instance."""
    global _global_adapter
    if _global_adapter is None:
        _global_adapter = UNCAdapter()
    return _global_adapter

def convert_to_drive(path: Union[str, Path]) -> Path:
    """
    Convert a UNC path to a drive path if possible.
    
    Args:
        path: The path to convert
    
    Returns:
        The converted path or the original if no conversion is possible
    """
    adapter = get_unc_adapter()
    return adapter.unc_to_drive(Path(path))

def convert_to_unc(path: Union[str, Path]) -> Path:
    """
    Convert a drive path to a UNC path if possible.
    
    Args:
        path: The path to convert
    
    Returns:
        The converted path or the original if no conversion is possible
    """
    adapter = get_unc_adapter()
    return adapter.drive_to_unc(Path(path))

def normalize_path(path: Union[str, Path], prefer_unc: bool = False) -> Path:
    """
    Normalize a path by converting between UNC and drive path formats.
    
    Args:
        path: The path to normalize
        prefer_unc: Whether to prefer UNC paths over drive paths
    
    Returns:
        The normalized path
    """
    adapter = get_unc_adapter()
    return adapter.normalize_path(Path(path), prefer_unc)

def refresh_mappings() -> None:
    """Refresh the network drive mappings."""
    adapter = get_unc_adapter()
    adapter.refresh_mapping()