# Dazzlelink Module

This is the modular version of Dazzlelink. It's been restructured to make the code more maintainable and to support better integration with UNC-lib and other libraries.

## Package Structure

```
dazzlelink/
├── __init__.py              # Package initialization and high-level API
├── cli.py                   # Command-line interface
├── config.py                # Configuration handling
├── data.py                  # Dazzlelink data structures
├── exceptions.py            # Custom exceptions
├── path.py                  # Path handling (will be replaced by UNC-lib)
├── operations/              # Core operations
│   ├── __init__.py          # Operations package initialization
│   ├── core.py              # Core DazzleLink class
│   ├── links.py             # Symlink operations
│   ├── timestamps.py        # Timestamp handling
│   ├── batch.py             # Batch operations
│   └── recreate.py          # Link recreation functionality
```

## Installation for Development

To install the module in development mode:

```bash
# Clone the repository
git clone https://github.com/djdarcy/dazzlelink.git
cd dazzlelink

# Install in development mode
pip install -e .

# Optional: Install with Windows-specific dependencies
pip install -e ".[windows]"

# Optional: Install development dependencies
pip install -e ".[dev]"
```

## Usage as a Module

```python
import dazzlelink

# Create a dazzlelink
dazzlelink.create_link("target.txt", "link.dazzlelink")

# Export a symlink to a dazzlelink
dazzlelink.export_link("path/to/symlink")

# Import a dazzlelink, recreating the original symlink
dazzlelink.import_link("path/to/dazzlelink")

# Convert all symlinks in a directory to dazzlelinks
dazzlelinks = dazzlelink.convert("/path/to/directory")

# Check for broken symlinks
results = dazzlelink.check("/path/to/directory")
```

## Command-Line Usage

The command-line interface is unchanged from the monolithic version:

```bash
# Create a dazzlelink
dazzlelink create target.txt link.dazzlelink

# Export a symlink to a dazzlelink
dazzlelink export path/to/symlink

# Import a dazzlelink
dazzlelink import path/to/dazzlelink

# Convert all symlinks in a directory to dazzlelinks
dazzlelink convert /path/to/directory

# Check for broken symlinks
dazzlelink check /path/to/directory
```

## Future Integration with UNC-lib

This modular structure is designed to facilitate future integration with UNC-lib. The current path handling in `path.py` will be replaced with UNC-lib functionality, while maintaining the same API to ensure backward compatibility.

## Compatibility with Monolithic Version

The monolithic version of Dazzlelink (`dazzlelink.py`) will continue to be maintained alongside this modular version for an extended period to ensure backward compatibility for users who prefer to use it directly without installation.