"""
Operations package for Dazzlelink.

This package provides the core functionality for working with symbolic links
and dazzlelink files, including creation, conversion, import/export, and more.
"""

from .core import DazzleLink
from .links import (
    create_windows_symlink,
    restore_file_attributes,
    scan_directory,
    find_dazzlelinks,
    make_dazzlelink_executable
)
from .timestamps import (
    set_file_times,
    set_link_timestamps,
    verify_timestamps,
    apply_timestamp_strategy,
    collect_timestamp_info,
    collect_target_timestamp_info
)
from .batch import (
    batch_import,
    convert_directory,
    mirror_directory,
    batch_copy,
    check_links,
    rebase_links,
    update_config_batch
)
from .recreate import (
    recreate_link,
    execute_dazzlelink
)

__all__ = [
    # Core operations class
    'DazzleLink',
    
    # Link operations
    'create_windows_symlink',
    'restore_file_attributes',
    'scan_directory',
    'find_dazzlelinks',
    'make_dazzlelink_executable',
    
    # Timestamp operations
    'set_file_times',
    'set_link_timestamps',
    'verify_timestamps',
    'apply_timestamp_strategy',
    'collect_timestamp_info',
    'collect_target_timestamp_info',
    
    # Batch operations
    'batch_import',
    'convert_directory',
    'mirror_directory',
    'batch_copy',
    'check_links',
    'rebase_links',
    'update_config_batch',
    
    # Recreation operations
    'recreate_link',
    'execute_dazzlelink'
]
