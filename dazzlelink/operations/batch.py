"""
Batch operations for Dazzlelink.

This module provides functionality for performing operations on multiple links
or files at once, such as batch import, batch conversion, and batch checking.
"""

import os
import sys
import re
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

from ..exceptions import DazzleLinkException
from ..data import DazzleLinkData
from ..config import DazzleLinkConfig
from . import links, timestamps

# Add debugging support
VERBOSE = os.environ.get('DAZZLELINK_VERBOSE', '0') == '1'
logger = logging.getLogger(__name__)

def debug_print(message):
    """Print debug messages if VERBOSE is enabled"""
    if VERBOSE:
        print(f"DEBUG: {message}")
        logger.debug(message)

def batch_import(path_patterns, target_location=None, recursive=False, 
                flatten=False, pattern=None, dry_run=False, remove_dazzlelinks=False,
                config_level='file', timestamp_strategy='current', update_dazzlelink=False,
                use_live_target=False, batch_optimization=True, dazzlelink_ext='.dazzlelink'):
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
        dazzlelink_ext (str): The file extension for dazzlelink files
        
    Returns:
        dict: Report of imported files with details on success, errors, etc.
    """
    # Find all matching dazzlelink files
    dazzlelinks = links.find_dazzlelinks(path_patterns, recursive, pattern, dazzlelink_ext)
    
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
    
    # Initialize config
    config = DazzleLinkConfig()
    
    for dir_path, dir_dazzlelinks in dazzlelinks_by_dir.items():
        print(f"\nProcessing directory: {dir_path}")
        
        # Load directory-specific config if using directory level
        if config_level == 'directory':
            config.load_directory_config(dir_path)
        
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
                        links.create_windows_symlink(target_path, new_link_path, is_dir)
                    else:
                        os.symlink(target_path, new_link_path)
                    
                    # Apply timestamp strategy with batch optimization
                    timestamps.apply_timestamp_strategy(
                        new_link_path,
                        dl_data,
                        timestamp_strategy,
                        use_live_target,
                        batch_mode=batch_optimization
                    )
                    
                    # Restore file attributes
                    links.restore_file_attributes(new_link_path, dl_data.to_dict())
                    
                    # Update dazzlelink metadata if requested
                    if update_dazzlelink:
                        dl_data.update_metadata(reason="symlink_recreation")
                        
                        # If we used live target, update target timestamps too
                        if use_live_target and timestamp_strategy in ['target', 'preserve-all']:
                            if os.path.exists(target_path):
                                target_timestamps = timestamps.collect_target_timestamp_info(target_path)
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

def convert_directory(directory, recursive=None, keep_originals=None, make_executable=None, mode=None, config=None):
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
        config (DazzleLinkConfig, optional): Configuration object to use.
            If None, creates a new one.
            
    Returns:
        list: List of created dazzlelink paths
    """
    # Get or create config
    if config is None:
        config = DazzleLinkConfig()
    
    # Load directory-specific config
    config.load_directory_config(directory)
    
    # Use config defaults if parameters not specified
    if recursive is None:
        recursive = config.get("recursive_scan")
    if keep_originals is None:
        keep_originals = config.get("keep_originals")
    if make_executable is None:
        make_executable = config.get("make_executable")
    if mode is None:
        mode = config.get("default_mode")
        
    # Scan for links
    found_links = links.scan_directory(directory, recursive)
    dazzlelinks = []
    
    # Process each link
    from .core import DazzleLink
    dazzle = DazzleLink(config)
    
    for link in found_links:
        try:
            dazzlelink = dazzle.serialize_link(
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

def mirror_directory(src_dir, dest_dir, recursive=None, make_executable=None, mode=None, config=None):
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
        config (DazzleLinkConfig, optional): Configuration object to use.
            If None, creates a new one.
            
    Returns:
        list: List of created dazzlelink paths
    """
    # Get or create config
    if config is None:
        config = DazzleLinkConfig()
    
    # Load source directory-specific config
    config.load_directory_config(src_dir)
    
    # Use config defaults if parameters not specified
    if recursive is None:
        recursive = config.get("recursive_scan")
    if make_executable is None:
        make_executable = config.get("make_executable")
    if mode is None:
        mode = config.get("default_mode")
        
    # Find all symlinks in the source directory
    found_links = links.scan_directory(src_dir, recursive)
    src_dir = Path(src_dir).resolve()
    dest_dir = Path(dest_dir).resolve()
    dazzlelinks = []
    
    # Create destination directory if it doesn't exist
    os.makedirs(dest_dir, exist_ok=True)
    
    # Process each link
    from .core import DazzleLink
    dazzle = DazzleLink(config)
    
    for link in found_links:
        try:
            # Calculate relative path
            rel_path = os.path.relpath(link, src_dir)
            dest_path = os.path.join(dest_dir, rel_path)
            
            # Create parent directories
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # Create dazzlelink at the destination
            dazzlelink = dazzle.serialize_link(
                link, 
                output_path=f"{dest_path}{dazzle.DAZZLELINK_EXT}", 
                make_executable=make_executable,
                mode=mode
            )
            dazzlelinks.append(dazzlelink)
            
        except Exception as e:
            print(f"WARNING: Failed to mirror {link}: {str(e)}")
                
    return dazzlelinks

def batch_copy(src_paths, dst_dir, preserve_structure=False, base_dir=None, 
          relative_links=None, verify=True):
    """
    Copy symbolic links to a destination directory.
    
    Args:
        src_paths (list or str): List of symlink paths or single symlink path
        dst_dir (str): Destination directory
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
    if isinstance(src_paths, str):
        src_paths = [src_paths]
    
    # Ensure all are symlinks
    for link in src_paths:
        if not os.path.islink(link):
            raise DazzleLinkException(f"{link} is not a symbolic link")
    
    # Resolve destination
    dst_dir = Path(dst_dir).resolve()
    os.makedirs(dst_dir, exist_ok=True)
    
    # Determine base directory for structure preservation
    if preserve_structure and not base_dir:
        # Find common parent directory
        paths = [Path(link).parent for link in src_paths]
        base_dir = os.path.commonpath([str(p) for p in paths])
    
    created_links = []
    
    for link in src_paths:
        try:
            link_path = Path(link).resolve()
            target_path = os.readlink(link)
            is_absolute = os.path.isabs(target_path)
            
            # Determine destination link path
            if preserve_structure:
                rel_path = os.path.relpath(link, base_dir)
                dest_link = os.path.join(dst_dir, rel_path)
                # Ensure parent directories exist
                os.makedirs(os.path.dirname(dest_link), exist_ok=True)
            else:
                dest_link = os.path.join(dst_dir, os.path.basename(link))
            
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
                links.create_windows_symlink(target_path, dest_link, is_dir)
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

def check_links(directory, recursive=True, report_only=True, fix_relative=False):
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
    found_links = links.scan_directory(directory, recursive)
    
    result = {
        'ok': [],
        'broken': [],
        'fixed': []
    }
    
    if not found_links:
        print(f"No symlinks found in {directory}")
        return result
    
    print(f"Checking {len(found_links)} symlinks...")
    
    for link in found_links:
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

def rebase_links(directory, recursive=True, make_relative=None, 
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
    found_links = links.scan_directory(directory, recursive)
    
    result = {
        'changed': [],
        'unchanged': [],
        'errors': []
    }
    
    if not found_links:
        print(f"No symlinks found in {directory}")
        return result
    
    print(f"Rebasing {len(found_links)} symlinks...")
    
    for link in found_links:
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

def update_config_batch(path, mode=None, pattern="*.dazzlelink", recursive=False, 
                        dry_run=False, config_level='file', make_executable=None):
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
    
    # Initialize config
    config = DazzleLinkConfig()
    
    # Handle config level
    if config_level == 'global':
        # Save to global config
        if mode is not None:
            config.set('default_mode', mode)
        if make_executable is not None:
            config.set('make_executable', make_executable)
            
        if not dry_run:
            # Save global config
            if config.save_global_config():
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
        config.load_directory_config(directory)
        
        # Update config
        if mode is not None:
            config.set('default_mode', mode)
        if make_executable is not None:
            config.set('make_executable', make_executable)
            
        if not dry_run:
            # Save directory config
            if config.save_directory_config(directory):
                print(f"Updated directory configuration for {directory}")
            else:
                print(f"Failed to update directory configuration for {directory}")
    
    # Continue only if we're updating file-level configs or we're in dry-run mode
    if config_level == 'file' or dry_run:
        # Find all matching dazzlelinks
        dazzlelinks_to_update = []
        path_obj = Path(path)
        
        if path_obj.is_file():
            # Single file
            if path_obj.suffix == '.dazzlelink':
                dazzlelinks_to_update.append(path_obj)
        elif path_obj.is_dir():
            # Directory search
            if recursive:
                # Recursive search
                for root, _, files in os.walk(path_obj):
                    for file in files:
                        if fnmatch.fnmatch(file, pattern):
                            dazzlelinks_to_update.append(Path(root) / file)
            else:
                # Non-recursive search
                for file in path_obj.glob(pattern):
                    if file.is_file():
                        dazzlelinks_to_update.append(file)
        
        # Process each matching file
        for dazzlelink_path in dazzlelinks_to_update:
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
                            "platform": 'windows' if os.name == 'nt' else 'linux'
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
                        links.make_dazzlelink_executable(dazzlelink_path, link_data)
                    # Note: There's no direct way to make a file "non-executable" in the current code
                
                results['updated'].append(str(dazzlelink_path))
                
            except Exception as e:
                results['errors'].append({
                    'path': str(dazzlelink_path),
                    'error': str(e)
                })
    
    return results