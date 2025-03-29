#!/usr/bin/env python3
"""
Command-line interface for Dazzlelink.

This module provides the command-line entry point for the dazzlelink tool.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Optional, Any, Dict, Tuple

from . import (
    __version__,
    DazzleLinkConfig,
    DazzleLink,
    export_link,
    import_link,
    create_link,
    convert,
    mirror,
    execute,
    scan,
    check,
    rebase,
    configure_logging,
    enable_verbose_logging,
    DazzleLinkException
)

def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description='Dazzlelink - Symbolic Link Preservation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    dazzlelink create target.txt link.dazzlelink       Create a new dazzlelink
    dazzlelink export path/to/symlink                  Export a symlink to a dazzlelink
    dazzlelink import path/to/file.dazzlelink          Import a dazzlelink, recreating the symlink
    dazzlelink scan /path -r                           Scan a directory recursively for symlinks
    dazzlelink convert /path                           Convert all symlinks in a directory to dazzlelinks
    dazzlelink mirror /source /dest                    Mirror a directory structure with dazzlelinks
    dazzlelink execute /path/to/file.dazzlelink        Execute/open a dazzlelink
    dazzlelink check /path                             Check symlinks and report broken ones
    dazzlelink rebase /path --relative                 Convert absolute links to relative paths

For more information, see https://github.com/djdarcy/dazzlelink
"""
    )
    
    parser.add_argument('--version', '-V', action='version', version=f'dazzlelink {__version__}')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    
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
    
    return parser

def main(args=None) -> int:
    """Main entry point for the dazzlelink command-line tool."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    # Enable verbose logging if requested
    if parsed_args.verbose:
        enable_verbose_logging()
    
    # If no command is specified, show help
    if not parsed_args.command:
        parser.print_help()
        return 1
    
    try:
        # Create configuration
        config = DazzleLinkConfig()
        
        # Create dazzlelink instance with config
        dazzle = DazzleLink(config)
        
        # Handle commands
        if parsed_args.command == 'create':
            # Apply configuration level
            if hasattr(parsed_args, 'config_level'):
                if parsed_args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif parsed_args.config_level == 'directory':
                    # Apply directory configuration
                    target_dir = os.path.dirname(os.path.abspath(parsed_args.link_name))
                    config.load_directory_config(target_dir)
                # 'file' level uses defaults or command-line overrides
            
            # Set specific command options in config
            if hasattr(parsed_args, 'executable') and parsed_args.executable is not None:
                config.set('make_executable', parsed_args.executable)
            if hasattr(parsed_args, 'mode') and parsed_args.mode is not None:
                config.set('default_mode', parsed_args.mode)
                
            link_path = os.path.abspath(parsed_args.link_name)
            target_path = os.path.abspath(parsed_args.target)
            
            # Create parent directory if needed
            os.makedirs(os.path.dirname(link_path), exist_ok=True)
            
            # Create the dazzlelink
            dazzlelink_path = create_link(
                target_path,
                link_path,
                make_executable=parsed_args.executable if hasattr(parsed_args, 'executable') else None,
                mode=parsed_args.mode if hasattr(parsed_args, 'mode') else None
            )
            
            print(f"Created dazzlelink: {dazzlelink_path}")

        elif parsed_args.command == 'export':
            # Apply configuration level
            if hasattr(parsed_args, 'config_level'):
                if parsed_args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif parsed_args.config_level == 'directory':
                    # Apply directory configuration
                    link_dir = os.path.dirname(os.path.abspath(parsed_args.link_path))
                    config.load_directory_config(link_dir)
                # 'file' level uses defaults or command-line overrides
            
            dazzlelink_path = export_link(
                parsed_args.link_path, 
                output_path=parsed_args.output,
                make_executable=parsed_args.executable if hasattr(parsed_args, 'executable') else None,
                mode=parsed_args.mode if hasattr(parsed_args, 'mode') else None
            )
            print(f"Exported symlink to dazzlelink: {dazzlelink_path}")
           
        elif parsed_args.command == 'import':
            # Apply configuration level
            if hasattr(parsed_args, 'config_level'):
                if parsed_args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif parsed_args.config_level == 'directory':
                    # For batch import, directory config will be loaded for each directory
                    pass
                # 'file' level uses defaults or command-line overrides
            
            # Modified condition to handle directory paths without recursion
            # Check if multiple paths, recursive option specified, or if any path is a directory
            if (len(parsed_args.paths) > 1 or parsed_args.recursive or 
                '*' in ''.join(parsed_args.paths) or '?' in ''.join(parsed_args.paths) or
                any(os.path.isdir(p) for p in parsed_args.paths)):
                
                # Use batch import
                from .operations import batch_import as batch_import_op
                result = batch_import_op(
                    parsed_args.paths,
                    target_location=parsed_args.target_location,
                    recursive=parsed_args.recursive,
                    flatten=parsed_args.flatten,
                    pattern=parsed_args.pattern,
                    dry_run=parsed_args.dry_run,
                    remove_dazzlelinks=parsed_args.remove_dazzlelinks,
                    config_level=parsed_args.config_level if hasattr(parsed_args, 'config_level') else 'file',
                    timestamp_strategy=parsed_args.timestamp_strategy if hasattr(parsed_args, 'timestamp_strategy') else 'current',
                    update_dazzlelink=parsed_args.update_dazzlelink if hasattr(parsed_args, 'update_dazzlelink') else False,
                    use_live_target=parsed_args.use_live_target if hasattr(parsed_args, 'use_live_target') else False
                )
                
                if result["error"] and not result["success"]:
                    # If all operations failed, return error code
                    return 1
                    
            else:
                # Single file mode, use original behavior for backward compatibility
                link_path = import_link(
                    parsed_args.paths[0],
                    target_location=parsed_args.target_location
                )
                print(f"Recreated symlink: {link_path}")
                
                # Handle remove_dazzlelinks option for consistency with batch mode
                if parsed_args.remove_dazzlelinks:
                    try:
                        os.unlink(parsed_args.paths[0])
                        print(f"Removed dazzlelink: {parsed_args.paths[0]}")
                    except Exception as e:
                        print(f"WARNING: Failed to remove dazzlelink {parsed_args.paths[0]}: {str(e)}")
            
        elif parsed_args.command == 'scan':
            # Configure recursive option
            recursive = not parsed_args.no_recursive if hasattr(parsed_args, 'no_recursive') else True
            
            links = scan(
                parsed_args.directory,
                recursive=recursive
            )
            
            if parsed_args.json:
                import json
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
                print(f"Found {len(links)} symbolic links in {parsed_args.directory}:")
                for link in links:
                    try:
                        target = os.readlink(link)
                        print(f"  {link} -> {target}")
                    except:
                        print(f"  {link} -> ERROR: Could not read link target")
            
        elif parsed_args.command == 'convert':
            # Apply configuration level
            if hasattr(parsed_args, 'config_level'):
                if parsed_args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif parsed_args.config_level == 'directory':
                    # Apply directory configuration
                    config.load_directory_config(parsed_args.directory)
                # 'file' level uses defaults or command-line overrides
            
            # Apply command-line arguments to config
            config.apply_args(parsed_args)
            
            keep_originals = not parsed_args.remove_originals if hasattr(parsed_args, 'remove_originals') else True
            recursive = not parsed_args.no_recursive if hasattr(parsed_args, 'no_recursive') else True
            
            dazzlelinks = convert(
                parsed_args.directory,
                recursive=recursive,
                keep_originals=keep_originals
            )
            
            action = "Converted" if keep_originals else "Replaced"
            print(f"{action} {len(dazzlelinks)} symlinks to dazzlelinks in {parsed_args.directory}")
            
        elif parsed_args.command == 'mirror':
            # Apply configuration level
            if hasattr(parsed_args, 'config_level'):
                if parsed_args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif parsed_args.config_level == 'directory':
                    # Apply directory configuration from source directory
                    config.load_directory_config(parsed_args.src_dir)
                # 'file' level uses defaults or command-line overrides
            
            # Apply command-line arguments to config
            config.apply_args(parsed_args)
            
            recursive = not parsed_args.no_recursive if hasattr(parsed_args, 'no_recursive') else True
            
            dazzlelinks = mirror(
                parsed_args.src_dir,
                parsed_args.dest_dir,
                recursive=recursive
            )
            
            print(f"Mirrored {len(dazzlelinks)} symlinks as dazzlelinks from {parsed_args.src_dir} to {parsed_args.dest_dir}")
            
        elif parsed_args.command == 'execute':
            # Apply configuration level
            if hasattr(parsed_args, 'config_level'):
                if parsed_args.config_level == 'global':
                    # Apply global configuration
                    config._load_global_config()
                elif parsed_args.config_level == 'directory':
                    # Apply directory configuration
                    dlink_dir = os.path.dirname(os.path.abspath(parsed_args.dazzlelink_path))
                    config.load_directory_config(dlink_dir)
                # 'file' level uses the dazzlelink's embedded configuration
            
            execute(
                parsed_args.dazzlelink_path,
                mode=parsed_args.mode if hasattr(parsed_args, 'mode') else None
            )
            
        elif parsed_args.command == 'config':
            # Determine configuration scope
            if hasattr(parsed_args, 'global_scope') and parsed_args.global_scope:
                scope = "global"
            elif hasattr(parsed_args, 'directory') and parsed_args.directory:
                scope = "directory"
                config.load_directory_config(parsed_args.directory)
            else:
                # Default to current directory
                scope = "directory"
                config.load_directory_config()
            
            if parsed_args.view:
                # View configuration
                print(f"Current {scope} configuration:")
                for key, value in config.config.items():
                    print(f"  {key}: {value}")
                    
            elif parsed_args.set:
                # Set configuration value
                try:
                    key, value = parsed_args.set.split('=', 1)
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
                            dir_path = parsed_args.directory if hasattr(parsed_args, 'directory') and parsed_args.directory else os.getcwd()
                            if config.save_directory_config(dir_path):
                                print(f"Updated directory configuration for {dir_path}: {key}={value}")
                except ValueError:
                    print("ERROR: Invalid format. Use KEY=VALUE")
                    
            elif parsed_args.reset:
                # Reset configuration to defaults
                config.config = config.DEFAULT_CONFIG.copy()
                
                if scope == "global":
                    if config.save_global_config():
                        print("Reset global configuration to defaults")
                else:
                    dir_path = parsed_args.directory if hasattr(parsed_args, 'directory') and parsed_args.directory else os.getcwd()
                    if config.save_directory_config(dir_path):
                        print(f"Reset directory configuration for {dir_path} to defaults")

        elif parsed_args.command == 'check':
            recursive = not parsed_args.no_recursive if hasattr(parsed_args, 'no_recursive') else True
            fix_links = parsed_args.fix if hasattr(parsed_args, 'fix') else False
            fix_relative = parsed_args.fix_relative if hasattr(parsed_args, 'fix_relative') else False
            
            result = check(
                parsed_args.directory,
                recursive=recursive,
                fix=fix_links or fix_relative
            )
            
            # Return non-zero if broken links found
            if result['broken']:
                return 1

        elif parsed_args.command == 'rebase':
            recursive = not parsed_args.no_recursive if hasattr(parsed_args, 'no_recursive') else True
            
            # Determine relative/absolute preference
            make_relative = None
            if parsed_args.relative and parsed_args.absolute:
                print("ERROR: Cannot specify both --relative and --absolute")
                return 1
            elif parsed_args.relative:
                make_relative = True
            elif parsed_args.absolute:
                make_relative = False
            
            result = rebase(
                parsed_args.directory,
                recursive=recursive,
                make_relative=make_relative,
                target_base=parsed_args.target_base if hasattr(parsed_args, 'target_base') else None,
                only_broken=parsed_args.only_broken if hasattr(parsed_args, 'only_broken') else False
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