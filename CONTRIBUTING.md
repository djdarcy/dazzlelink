# Contributing to Dazzlelink

Thank you for considering contributing to **Dazzlelink**, the symbolic link preservation tool. This document outlines guidelines to help you contribute effectively and respectfully.

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md) to foster a respectful and inclusive environment.

## How You Can Contribute

### 🔧 Reporting Bugs

1. Check the [Issues page](https://github.com/djdarcy/dazzlelink/issues) to see if your bug is already reported.
2. If not, open a new issue using the bug report template.
3. Include as much detail as possible:
   - Steps to reproduce
   - Expected vs. actual behavior
   - Error messages or logs
   - Environment (OS, Python version, etc.)

### ✨ Suggesting Features

1. Browse existing issues and pull requests to avoid duplication.
2. Create a new issue using the feature request template.
3. Clearly describe your feature and its use case.

### 🔀 Submitting Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes and follow coding guidelines
4. Run and verify all tests
5. Commit with a clear message
6. Push your branch (`git push origin feature/your-feature`)
7. Open a pull request against the `main` branch

## Development Setup

### ⚙️ CLI Version

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Make changes to `dazzlelink.py`
4. Run tests or scripts as needed
5. Ensure code works on your target OS

## Coding Guidelines

- Follow Pythonic conventions (PEP8)
- Use `black`, `flake8`, or `pylint` for formatting/linting
- Comment non-obvious logic
- Include docstrings where appropriate
- Add/update tests when adding features or fixing bugs
- Keep commit messages clear and concise

## Versioning

We follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: Incompatible API changes
- **MINOR**: Backward-compatible new features
- **PATCH**: Backward-compatible bug fixes

## Documentation

Please update the following when relevant:
- `README.md` for usage and setup
- `CHANGELOG.md` for user-facing changes
- Inline comments or docstrings for maintainability

## License Agreement

By submitting a contribution, you agree that your code will be licensed under the existing license of the project.

Thank you for helping improve Dazzlelink!
