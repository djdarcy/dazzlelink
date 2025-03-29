"""
Dazzlelink - Symbolic Link Preservation Tool

A tool for exporting, importing, and managing symbolic links across
different systems, particularly useful for network shares and cross-platform
environments where native symlinks might not be properly supported.
"""

import os
import sys
import logging
from pathlib import Path

__version__ = "0.6.0"

# Set up package-level logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler if not already present
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(console_handler)

# Import core functionality
from .exceptions import DazzleLinkException
from .data import DazzleLinkData
from .config import DazzleLinkConfig
from .path import (
    UNCAdapter,
    get_unc_adapter,
    convert_to_drive,
    convert_to_unc,
    normalize_path,
    refresh_mappings
)
from .operations import (
    DazzleLink,
    create_windows_symlink,
    restore_file_attributes, 
    scan_directory,
    find_dazzlelinks,
    batch_import,
    convert_directory,
    mirror_directory,
    batch_copy,
    check_links,
    rebase_links,
    recreate_link,
    execute_dazzlelink
)

# Create a global instance for convenience
_dazzlelink_instance = None

def get_dazzlelink_instance():
    """Get or create the global DazzleLink instance."""
    global _dazzlelink_instance
    if _dazzlelink_instance is None:
        _dazzlelink_instance = DazzleLink()
    return _dazzlelink_instance

# Convenience functions that use the global instance
def export_link(link_path, output_path=None, make_executable=None, mode=None):
    """
    Export a symlink to a .dazzlelink file
    
    Args:
        link_path: Path to the symlink
        output_path: Output path for the dazzlelink file
        make_executable: Whether to make the dazzlelink executable
        mode: Default execution mode for this dazzlelink
    
    Returns:
        Path to the created dazzlelink file
    """
    dl = get_dazzlelink_instance()
    return dl.serialize_link(link_path, output_path, make_executable, mode)

def import_link(dazzlelink_path, target_location=None, timestamp_strategy='current', 
                update_dazzlelink=False, use_live_target=False):
    """
    Import (recreate) a symlink from a .dazzlelink file
    
    Args:
        dazzlelink_path: Path to the dazzlelink file
        target_location: Override location for the recreated symlink
        timestamp_strategy: Strategy for setting timestamps
        update_dazzlelink: Whether to update dazzlelink metadata
        use_live_target: Whether to check live target for timestamps
    
    Returns:
        Path to the created symlink
    """
    return recreate_link(
        dazzlelink_path, 
        target_location, 
        timestamp_strategy, 
        update_dazzlelink, 
        use_live_target
    )

def create_link(target, link_name, make_executable=None, mode=None):
    """
    Create a new dazzlelink pointing to a target
    
    Args:
        target: The file or directory to link to
        link_name: The path for the new dazzlelink
        make_executable: Whether to make the dazzlelink executable
        mode: Default execution mode for this dazzlelink
    
    Returns:
        Path to the created dazzlelink file
    """
    dl = get_dazzlelink_instance()
    return dl.serialize_link(
        target, 
        output_path=link_name, 
        make_executable=make_executable, 
        mode=mode,
        require_symlink=False
    )

def convert(directory, recursive=True, keep_originals=True):
    """
    Convert symlinks in a directory to dazzlelinks
    
    Args:
        directory: Directory to scan
        recursive: Whether to scan recursively
        keep_originals: Whether to keep original symlinks
    
    Returns:
        List of created dazzlelink paths
    """
    return convert_directory(
        directory, 
        recursive=recursive, 
        keep_originals=keep_originals
    )

def mirror(src_dir, dest_dir, recursive=True):
    """
    Mirror a directory structure with dazzlelinks
    
    Args:
        src_dir: Source directory
        dest_dir: Destination directory
        recursive: Whether to scan recursively
    
    Returns:
        List of created dazzlelink paths
    """
    return mirror_directory(src_dir, dest_dir, recursive=recursive)

def execute(dazzlelink_path, mode=None):
    """
    Execute/open a dazzlelink
    
    Args:
        dazzlelink_path: Path to the dazzlelink
        mode: Override execution mode
    """
    return execute_dazzlelink(dazzlelink_path, mode)

def scan(directory, recursive=True):
    """
    Scan a directory for symlinks
    
    Args:
        directory: Directory to scan
        recursive: Whether to scan recursively
    
    Returns:
        List of symlink paths
    """
    return scan_directory(directory, recursive)

def check(directory, recursive=True, fix=False):
    """
    Check symlinks in a directory and report broken ones
    
    Args:
        directory: Directory to scan
        recursive: Whether to scan recursively
        fix: Try to fix broken links when possible
    
    Returns:
        Dictionary with status of links
    """
    return check_links(directory, recursive, not fix, fix)

def rebase(directory, recursive=True, make_relative=None, target_base=None, only_broken=False):
    """
    Rebase links in a directory
    
    Args:
        directory: Directory containing links to rebase
        recursive: Whether to scan recursively
        make_relative: Convert to relative paths if True, absolute if False
        target_base: Replace base part of absolute paths
        only_broken: Only rebase broken links
    
    Returns:
        Dictionary with status of links
    """
    return rebase_links(directory, recursive, make_relative, target_base, only_broken)

def configure_logging(level=logging.INFO, log_file=None):
    """
    Configure logging for dazzlelink
    
    Args:
        level: Logging level (default: INFO)
        log_file: Path to log file (if None, only console logging is used)
    """
    logger.setLevel(level)
    
    # Clear existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(console_handler)
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )
        logger.addHandler(file_handler)

def enable_verbose_logging():
    """
    Enable verbose (debug) logging
    """
    configure_logging(logging.DEBUG)
    # Also set environment variable for modules that check it directly
    os.environ['DAZZLELINK_VERBOSE'] = '1'

# Export public API
__all__ = [
    # Classes
    'DazzleLinkException',
    'DazzleLinkData',
    'DazzleLinkConfig',
    'DazzleLink',
    'UNCAdapter',
    
    # Path functions
    'get_unc_adapter',
    'convert_to_drive',
    'convert_to_unc',
    'normalize_path',
    'refresh_mappings',
    
    # High-level functions
    'export_link',
    'import_link',
    'create_link',
    'convert',
    'mirror',
    'execute',
    'scan',
    'check',
    'rebase',
    
    # Utility functions
    'get_dazzlelink_instance',
    'configure_logging',
    'enable_verbose_logging',
    
    # Version
    '__version__'
]
