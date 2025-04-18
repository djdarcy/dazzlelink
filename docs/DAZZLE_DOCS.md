# Dazzlelink Documentation

## Advanced Usage & Configuration

Welcome to Dazzlelink! Here we'll guide you through advanced techniques to maximize your symbolic linking prowess.

### Configuration Mastery

Dazzlelink can be finely tuned at three distinct layers:

- **Global Settings (`~/.dazzlelinkrc.json`)**: Your defaults—set once, relax forever.
- **Directory Settings (`.dazzlelink_config.json`)**: Tailor your config per project.
- **File-level Settings**: Precision control embedded in every `.dazzlelink` file.

Think of these as your Dazzlelink Swiss army knife—ready to adapt at a moment's notice.

#### Example: Global vs. Directory

Imagine your global config (`~/.dazzlelinkrc.json`) says "Always preserve timestamps." Yet, your project requires fresh timestamps upon import—just drop a `.dazzlelink_config.json` in the project's root directory with:

```json
{
  "timestamp_strategy": "current"
}
```

### Advanced Symlink Mirroring

Need to replicate complex directory structures without duplicating actual files? Say hello to `mirror`:

```bash
dazzlelink mirror /source/media-library /destination/library-copy
```

It creates a lean, fully functional replica with symbolic links pointing back to the originals, ideal for managing large media libraries or development environments.

---

## 🌐 Network Paths & Timestamp Strategies

Dazzlelink gracefully manages the complexities of network shares and the tricky art of timestamp management. Here's how to master it:

### UNC Paths & Drive Letters Demystified

Crossing platforms? No worries! Dazzlelink effortlessly translates paths between UNC (`\\server\share\file.txt`) and subst'ed drive letters (`Z:\folder\file.txt`).

```bash
dazzlelink export "Z:\project\important-data"
```

On import, Dazzlelink intelligently adapts to your current OS conventions, ensuring your symbolic links always hit the target.

### Timestamp Wizardry

Dazzlelink's timestamp strategies let you control exactly what time metadata your imported links carry:

- **`current`**: Uses current system time. Fresh start!
- **`symlink`**: Original symbolic link timestamps preserved.
- **`target`**: Borrow timestamps from the original linked file. Trust the source!
- **`preserve-all`**: Everything is exactly as it was (target preferred, falling back to symlink)

#### Example:

Preserve original file timestamps when importing:

```bash
dazzlelink import --timestamp-strategy target file.dazzlelink
```

### 💡 Tips & Best Practices

- **Network Drives**: Use UNC paths when sharing across diverse systems—simplicity wins.
- **Timestamp Consistency**: Stick with one strategy across projects to avoid confusion.
- **Regular Checks**: Run `dazzlelink check` periodically to spot broken links early.

Now, armed with these advanced skills, you're ready to link smarter, faster, and more effectively. Happy linking!

