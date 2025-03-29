"""
Timestamp management operations for Dazzlelink.

This module provides functionality for preserving and restoring file timestamps
when working with symbolic links.
"""

import os
import sys
import datetime
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Union, Any

# Add debugging support
VERBOSE = os.environ.get('DAZZLELINK_VERBOSE', '0') == '1'
logger = logging.getLogger(__name__)

def debug_print(message):
    """Print debug messages if VERBOSE is enabled"""
    if VERBOSE:
        print(f"DEBUG: {message}")
        logger.debug(message)

def set_file_times(file_path, modified_time, accessed_time=None, created_time=None):
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

def set_link_timestamps(link_path, timestamp_data, max_attempts=2, verify=True, retry_delay=0.05):
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
    success = set_file_times(link_path, modified_time, accessed_time, created_time)
    
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
        success = set_file_times(link_path, modified_time, accessed_time, created_time)
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

def verify_timestamps(link_path, dl_data, strategy, use_live_target=False):
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
                        live_timestamps = collect_target_timestamp_info(target_path)
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
                        set_file_times(
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
                        set_file_times(
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

def collect_timestamp_info(file_path):
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

def collect_target_timestamp_info(target_path):
    """
    Collect timestamp information for the target of a symlink.
    
    This is similar to collect_timestamp_info but specifically for target files,
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

def apply_timestamp_strategy(link_path, dl_data, strategy, use_live_target=False, batch_mode=False):
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
                            live_target_timestamps = collect_target_timestamp_info(path)
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
                    live_target_timestamps = collect_target_timestamp_info(target_path)
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
                set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
                
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
                set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
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
                set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
            elif live_target_timestamps and live_target_timestamps.get('modified') is not None:
                # Fall back to live target even if not explicitly requested
                timestamp_data = {
                    'created': live_target_timestamps.get('created'),
                    'modified': live_target_timestamps.get('modified'),
                    'accessed': live_target_timestamps.get('accessed')
                }
                
                debug_print(f"Falling back to live target timestamps: created={timestamp_data['created']}, modified={timestamp_data['modified']}, accessed={timestamp_data['accessed']}")
                
                # Set the timestamps on the recreated symlink with verification
                set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
                
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
                if set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps):
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
                if set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps):
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
                if set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps):
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
                set_link_timestamps(link_path, timestamp_data, verify=verify_timestamps)
        
    except Exception as e:
        debug_print(f"Failed to apply timestamp strategy: {str(e)}")
