# 🔧 Dazzlelink Command Reference

Welcome to the complete command reference guide for Dazzlelink. Each command and parameter is documented in the built-in help through `dazzlelink.py {command} -h` and will always be more accurate than this documentation which may be out of date. But this is an attempt to make the tool easier to use for people who dislike the CLI.

---

## 📌 Global Options

| Option | Description |
|--------|-------------|
| `-h`, `--help` | Display help information about any command |
| `-v`, `--version` | Display the current version of Dazzlelink |

---

## 🚀 Commands

### 🔄 export

**Description:** Export existing symbolic links into portable `.dazzlelink` files.

#### Arguments
- `link_path`: Path to the symlink

#### Options
- `-o`, `--output OUTPUT`: Specify the output path for the `.dazzlelink` file
- `-e`, `--executable`: Make the `.dazzlelink` executable
- `-m`, `--mode {info,open,auto}`: Set default execution mode

---

### 📥 import

**Description:** Import and recreate symbolic links from `.dazzlelink` files.

#### Arguments
- `dazzlelink_path`: Path to the `.dazzlelink` file

#### Options
- `-t`, `--target-location TARGET_LOCATION`: Override location for recreated symlink

---

### 🔍 scan

**Description:** Scan directories to identify symbolic links and provide detailed reporting.

#### Arguments
- `directory`: Directory to scan

#### Options
- `-n`, `--no-recursive`: Do not scan recursively
- `-j`, `--json`: Output scan results in JSON format

---

### 🔀 convert

**Description:** Convert existing symbolic links into `.dazzlelink` files.

#### Arguments
- `directory`: Directory containing symlinks to convert

#### Options
- `-n`, `--no-recursive`: Do not scan recursively
- `-r`, `--remove-originals`: Remove original symlinks after conversion
- `-e`, `--executable`: Make `.dazzlelink` files executable
- `-m`, `--mode {info,open,auto}`: Set default execution mode

---

### 📂 mirror

**Description:** Mirror directory structures using `.dazzlelink` symbolic links.

#### Arguments
- `src_dir`: Source directory
- `dest_dir`: Destination directory

#### Options
- `-n`, `--no-recursive`: Do not scan recursively
- `-e`, `--executable`: Make `.dazzlelink` files executable
- `-m`, `--mode {info,open,auto}`: Set default execution mode

---

### 🚦 check

**Description:** Check symbolic links and report broken or problematic links.

#### Arguments
- `directory`: Directory to scan

#### Options
- `-n`, `--no-recursive`: Do not scan recursively
- `-f`, `--fix`: Attempt to fix broken links
- `-r`, `--fix-relative`: Fix broken relative links by searching

---

### 🎯 rebase

**Description:** Change symbolic link paths between relative and absolute.

#### Arguments
- `directory`: Directory to scan

#### Options
- `-n`, `--no-recursive`: Do not scan recursively
- `-r`, `--relative`: Convert absolute links to relative
- `-a`, `--absolute`: Convert relative links to absolute
- `-t`, `--target-base TARGET_BASE`: Replace base path (`old_prefix:new_prefix`)
- `-b`, `--only-broken`: Rebase only broken links

---

### 📌 create

**Description:** Create a new symbolic link pointing to a target.

#### Arguments
- `target`: Target file/directory
- `link_name`: Name for the new link

#### Options
- `-e`, `--executable`: Make the link executable
- `-m`, `--mode {info,open,auto}`: Set default execution mode

---

### 🚪 execute

**Description:** Execute or open the target of a symbolic link.

#### Arguments
- `dazzlelink_path`: Path of the symbolic link

#### Options
- `-m`, `--mode {info,open,auto}`: Override execution mode

---

### ⚙️ config

**Description:** View or set Dazzlelink configuration options.

#### Options
- `--view`: View current configuration
- `--set KEY=VALUE`: Set a configuration value
- `--reset`: Reset to default configuration
- `--global`: Apply changes globally
- `-d`, `--directory DIRECTORY`: Apply changes to specific directory

---

### 📑 copy

**Description:** Copy symbolic links to another location.

#### Arguments
- `links`: Links to copy (files or directories)
- `destination`: Destination directory

#### Options
- `-p`, `--preserve-structure`: Preserve original directory structure
- `-b`, `--base-dir BASE_DIR`: Base directory for structure preservation
- `-r`, `--relative`: Convert copied links to relative paths
- `-a`, `--absolute`: Convert copied links to absolute paths
- `-n`, `--no-verify`: Skip verification of copied links

---

Each command is designed to hopefully be intuitive to help with managing symbolic links efficiently across multiple environments. Happy linking!

