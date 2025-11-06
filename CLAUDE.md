# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PEPPOL Per Country is a Python-based tool that synchronizes PEPPOL business directory exports by country. It downloads the massive XML export from `directory.peppol.eu`, processes it using streaming XML parsing, and splits business cards into country-specific files stored in git.

**Core Technologies:**
- Python 3.x with `lxml` for XML processing
- GitHub Actions for daily automated sync
- MkDocs with Material theme for documentation

## Development Commands

### Running the sync tool

```bash
# Full sync: download + process XML (recommended for first run)
python3 peppol_sync.py sync

# Force re-download even if file exists
python3 peppol_sync.py sync -F

# Keep temporary files for debugging
python3 peppol_sync.py sync -K

# Don't delete existing extracts before processing
python3 peppol_sync.py sync -C

# Verbose output
python3 peppol_sync.py sync -V
```

### Utility commands

```bash
# Download XML only (no processing)
python3 peppol_sync.py download

# Check configuration
python3 peppol_sync.py check

# Show largest output files
python3 peppol_sync.py huge -n 20

# Custom max file size (default: 2MB)
python3 peppol_sync.py sync -M 1000000
```

### Documentation

```bash
# Build and serve docs locally
mkdocs serve

# Build static site (output to site/)
mkdocs build
```

### Dependencies

```bash
# Install required Python package
pip install lxml
```

## Architecture

### Main Script: peppol_sync.py

The `PeppolSync` class handles the entire workflow:

1. **Download Phase** (`download_xml()` at line 70)
   - Streams XML from `https://directory.peppol.eu/export/businesscards`
   - Saves to `tmp/directory-export-business-cards.xml`
   - Shows progress every 100MB
   - Skips download if file exists (override with `-F`)

2. **Processing Phase** (`process_xml()` at line 153)
   - Uses text-based chunking (1MB chunks) for memory efficiency
   - Parses business cards with `lxml.etree` for fast XML handling
   - Extracts country code from `<entity countrycode="XX">`
   - Extracts registration date from `<regdate>` for statistics
   - Writes pretty-printed XML to country directories

3. **File Splitting Logic** (lines 228-250)
   - Splits files when they exceed `max_bytes` (default: 2MB)
   - Sequential naming: `business-cards.000001.xml`, `business-cards.000002.xml`, etc.
   - Each country has its own directory: `extracts/BE/`, `extracts/NO/`, etc.
   - Automatically creates header and footer tags for valid XML

4. **Report Generation** (`generate_report()` at line 269)
   - Creates `extracts/report.md` with country statistics
   - Shows file count, card count, and size per country

### Output Structure

```
extracts/
├── AT/
│   ├── business-cards.000001.xml
│   └── business-cards.000002.xml
├── BE/
│   ├── business-cards.000001.xml
│   └── ...
├── report.md
└── peppol_sync.log
```

### GitHub Actions

**Daily Sync Workflow** (`.github/workflows/daily.yml`)
- Runs at 09:15 UTC daily
- Executes `python3 peppol_sync.py sync -V`
- Commits and pushes changes to `extracts/` automatically
- Creates `extracts/git_diff.txt` with change summary

**Pages Deployment** (`.github/workflows/static.yml`)
- Deploys `site/` directory to GitHub Pages
- Triggered on push to main branch

## Key Implementation Details

### Memory-Efficient XML Processing

The script processes multi-GB XML files without loading everything into memory:
- Reads in 1MB text chunks
- Splits on `</businesscard>` delimiter
- Parses individual cards with lxml
- Uses streaming writes to output files

### Country Code Extraction

Located in `extract_country_from_etree()` (line 130):
```python
entity = element.find(".//entity")
if entity is not None:
    return entity.get("countrycode")
```

### File Rotation

When a country file exceeds `max_bytes`:
1. Writes `</root>` footer to close current file
2. Increments sequence number in `self.file_stats[country]['sequence']`
3. Opens new file with updated sequence
4. Writes XML header to new file

### Cleanup Behavior

- **Temporary files** (`tmp/`): Deleted after processing by default (keep with `-K`)
- **Extract files** (`extracts/**/*.xml`): Deleted before each sync by default (preserve with `-C`)
- **Log file** (`extracts/peppol_sync.log`): Overwritten on each run

## Version Management

Version is stored in `VERSION.md` and updated via commit messages like `setver: set version to 0.1.12`. There is no automated version bumping script in the repository.

## Documentation Site

Uses MkDocs with Material theme. Configuration in `mkdocs.yml`:
- Main docs in `docs/` directory
- Documentation is deployed to GitHub Pages via the static workflow
- `README.md` is a symlink to `docs/index.md`
