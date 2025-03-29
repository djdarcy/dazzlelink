#!/usr/bin/env python3

from setuptools import setup, find_packages
import os
import sys

# Read the version from dazzlelink/__init__.py
with open('dazzlelink/__init__.py', 'r') as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.split('=')[1].strip().strip('"\'')
            break
    else:
        version = '0.5.0'

# Read long description from README.md
if os.path.exists('README.md'):
    with open('README.md', 'r', encoding='utf-8') as f:
        long_description = f.read()
else:
    long_description = (
        'Dazzlelink - A cross-platform tool for preserving, managing, '
        'and understanding symbolic links across different systems.'
    )

setup(
    name='dazzlelink',
    version=version,
    description='Cross-platform tool for preserving and managing symbolic links',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Dustin Darcy',
    author_email='dustindarcy@gmail.com',
    url='https://github.com/djdarcy/dazzlelink',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: OS Independent',
        'Topic :: System :: Filesystems',
        'Topic :: Utilities',
    ],
    keywords='symlinks, symbolic links, network paths, UNC paths, file management',
    python_requires='>=3.6',
    install_requires=[
        'pathlib;python_version<"3.4"',
    ],
    extras_require={
        'windows': [
            'pywin32>=223',  # For advanced Windows functionality
        ],
        'dev': [
            'pytest>=6.0.0',
            'pytest-cov>=2.10.0',
            'flake8>=3.8.0',
            'mypy>=0.800',
            'black>=20.8b1',
        ],
        'docs': [
            'sphinx>=3.0.0',
            'sphinx-rtd-theme>=0.5.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'dazzlelink=dazzlelink.cli:main',
        ],
    },
    project_urls={
        'Bug Reports': 'https://github.com/djdarcy/dazzlelink/issues',
        'Source': 'https://github.com/djdarcy/dazzlelink',
        'Documentation': 'https://github.com/djdarcy/dazzlelink#readme',
    },
)
