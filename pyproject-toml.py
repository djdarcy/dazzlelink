[build-system]
requires = ["setuptools>=42", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dazzlelink"
dynamic = ["version"]
description = "Cross-platform tool for preserving and managing symbolic links"
readme = "README.md"
authors = [
    {name = "Dustin Darcy", email = "dustindarcy@gmail.com"}
]
license = {text = "GPL-3.0"}
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Intended Audience :: System Administrators",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.6",
    "Programming Language :: Python :: 3.7",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Operating System :: Microsoft :: Windows",
    "Operating System :: POSIX :: Linux",
    "Operating System :: MacOS :: MacOS X",
    "Operating System :: OS Independent",
    "Topic :: System :: Filesystems",
    "Topic :: Utilities",
]
keywords = ["symlinks", "symbolic links", "network paths", "UNC paths", "file management"]
requires-python = ">=3.6"
dependencies = [
    'pathlib;python_version<"3.4"',
]

[project.optional-dependencies]
windows = [
    "pywin32>=223",
]
dev = [
    "pytest>=6.0.0",
    "pytest-cov>=2.10.0",
    "flake8>=3.8.0",
    "mypy>=0.800",
    "black>=20.8b1",
]
docs = [
    "sphinx>=3.0.0",
    "sphinx-rtd-theme>=0.5.0",
]

[project.urls]
"Bug Reports" = "https://github.com/djdarcy/dazzlelink/issues"
"Source" = "https://github.com/djdarcy/dazzlelink"
"Documentation" = "https://github.com/djdarcy/dazzlelink#readme"

[project.scripts]
dazzlelink = "dazzlelink.cli:main"

[tool.setuptools]
packages = ["dazzlelink"]

[tool.setuptools.dynamic]
version = {attr = "dazzlelink.__version__"}

[tool.black]
line-length = 100
target-version = ['py36', 'py37', 'py38', 'py39']

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.6"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false
disallow_incomplete_defs = false

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
python_functions = "test_*"
python_classes = "Test*"
addopts = "--cov=dazzlelink --cov-report=term-missing"
