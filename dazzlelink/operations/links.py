"""
Symbolic link operations for Dazzlelink.

This module provides functionality for creating, manipulating, and working
with symbolic links across different operating systems.
"""

import os
import sys
import re
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Tuple

# Add debugging support
VERBOSE = os.environ.get('DAZZLELINK_VERBOSE', '0') == '1'
logger = logging.getLogger(__name__)

def debug_print(message):
    """Print debug messages if VERBOSE is enabled"""
    if VERBOSE:
        print(f"DEBUG: {message}")
        logger.debug(message)

def create_windows_symlink(target_path, link_path, is_directory):
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
    raise Exception(f"Failed to create symlink: {link_path} -> {target_path}")

def restore_file_attributes(link_path, link_data):
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

def find_dazzlelinks(path_patterns, recursive=False, pattern=None, dazzlelink_ext='.dazzlelink'):
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
        pattern = f"*{dazzlelink_ext}"
        
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
                if path_obj.suffix == dazzlelink_ext and (pattern == f"*{dazzlelink_ext}" or fnmatch.fnmatch(path_obj.name, pattern)):
                    found_dazzlelinks.append(path_obj)
            
            # Case 2: Directory path
            elif path_obj.is_dir():
                if recursive:
                    # Recursive search
                    for root, _, files in os.walk(path_obj):
                        root_path = Path(root)
                        for file in files:
                            if file.endswith(dazzlelink_ext) and fnmatch.fnmatch(file, pattern):
                                found_dazzlelinks.append(root_path / file)
                else:
                    # Non-recursive, just search the directory
                    for file in path_obj.glob(pattern):
                        if file.is_file() and file.suffix == dazzlelink_ext:
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
                            if file.is_file() and file.suffix == dazzlelink_ext and fnmatch.fnmatch(file.name, pattern):
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

def scan_directory(directory, recursive=True):
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
        raise Exception(f"{directory} is not a directory")
    
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
        raise Exception(f"Failed to scan directory {directory}: {str(e)}")

def make_dazzlelink_executable(dazzlelink_path, link_data=None):
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
        raise Exception(f"Invalid dazzlelink format in {dazzlelink_path}")
    
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
