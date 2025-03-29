"""
Symlink recreation functionality for Dazzlelink.

This module provides functions for recreating symbolic links from dazzlelink files.
"""

import os
import sys
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

from ..exceptions import DazzleLinkException
from ..data import DazzleLinkData
from . import links, timestamps

# Add debugging support
VERBOSE = os.environ.get('DAZZLELINK_VERBOSE', '0') == '1'
logger = logging.getLogger(__name__)

def debug_print(message):
    """Print debug messages if VERBOSE is enabled"""
    if VERBOSE:
        print(f"DEBUG: {message}")
        logger.debug(message)

def recreate_link(dazzlelink_path, target_location=None, timestamp_strategy='current', 
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
            links.create_windows_symlink(target_path, link_path, is_dir)
        else:
            os.symlink(target_path, link_path)
        
        # Verify symlink was created
        if not os.path.exists(link_path):
            raise DazzleLinkException(f"Failed to create symlink at {link_path}")
        
        # Very small delay to ensure symlink creation is complete (helps avoid race conditions)
        # Reduced from 0.1 to 0.01 seconds
        if not batch_mode:
            import time
            time.sleep(0.01)
        
        # Apply timestamps based on the selected strategy
        timestamps.apply_timestamp_strategy(link_path, dl_data, timestamp_strategy, use_live_target, batch_mode=batch_mode)
        
        # Verify timestamps were correctly applied (if not current and not in batch mode)
        if timestamp_strategy != 'current' and os.name == 'nt' and not batch_mode:
            timestamps.verify_timestamps(link_path, dl_data, timestamp_strategy, use_live_target)
        
        # Attempt to restore file attributes if available
        links.restore_file_attributes(link_path, dl_data.to_dict())
        
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
                        target_timestamps = timestamps.collect_target_timestamp_info(target_path)
                        
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

def execute_dazzlelink(dazzlelink_path, mode=None, config_override=None):
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
                    import subprocess
                    subprocess.run(cmd, shell=True)
                else:
                    # On Unix, ensure it's executable and run it
                    if not os.access(dazzlelink_path, os.X_OK):
                        import stat
                        os.chmod(dazzlelink_path, os.stat(dazzlelink_path).st_mode | stat.S_IEXEC)
                    cmd = [dazzlelink_path]
                    if mode:
                        cmd.append(f"--{mode}")
                    import subprocess
                    subprocess.run(cmd)
                return
            
            # Otherwise, try to parse as JSON
            try:
                # Reset file pointer again just to be safe
                f.seek(0)
                import json
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
                import subprocess
                subprocess.run(['xdg-open', target_path])
        
        else:
            raise DazzleLinkException(f"Unknown execution mode: {execute_mode}")
            
    except Exception as e:
        raise DazzleLinkException(f"Failed to execute dazzlelink {dazzlelink_path}: {str(e)}")
