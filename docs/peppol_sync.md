# peppol_sync.py

## Overview

The `peppol_sync.py` script is a command-line tool designed to synchronize business card data from the PEPPOL directory. It downloads a large XML file, splits it into smaller, more manageable XML files organized by country, and stores them in the `extracts/` directory.

## Command-line Usage

```
usage: peppol_sync.py [-h] [-V] [-F] [-C] [-K] [-T TMP] [-M MAX] {sync,check,download,huge}

Synchronize PEPPOL export into git-managed files

positional arguments:
  {sync,check,download,huge}
                        Action to perform

options:
  -h, --help            show this help message and exit
  -V, --verbose         Enable verbose output
  -F, --force           Force re-download of XML file even if it exists
  -C, --nocleanup       Do not delete existing XML files in extracts/ before starting (default: delete)
  -K, --keep-tmp        Keep temporary files after processing (default: delete)
  -T, --tmp TMP         Temporary directory (default: tmp)
  -M, --max MAX         Maximum number of bytes per output file (default: 1000000)
```

## Actions

The first argument to the script must be one of the following actions:

*   `sync`: This is the main action. It performs the entire synchronization process, which includes downloading the XML file (if necessary) and splitting it into country-specific files.
*   `check`: This action checks the configuration and prints the temporary and extracts directories.
*   `download`: This action only downloads the PEPPOL business card XML file and saves it to the temporary directory.
*   `huge`: This action lists the largest XML files found in the `extracts/` directory.

## Options

*   `-h`, `--help`: Shows the help message and exits.
*   `-V`, `--verbose`: Enables verbose output, providing more detailed information about the script's execution.
*   `-F`, `--force`: Forces the script to re-download the main XML file, even if a local copy already exists.
*   `-C`, `--nocleanup`: By default, the script deletes all existing XML files in the `extracts/` directory before starting a new sync. This flag prevents the cleanup, preserving the existing files.
*   `-K`, `--keep-tmp`: Prevents the script from deleting temporary files (like the downloaded XML) after processing is complete.
*   `-T`, `--tmp TMP`: Specifies the temporary directory to use for downloading files. Defaults to `tmp`.
*   `-M`, `--max MAX`: Sets the maximum size in bytes for each output XML file. When a file exceeds this size, a new one is created. Defaults to 2000000 (2MB).

## Functionality

The `PeppolSync` class handles the entire workflow:

1. **Download Phase** (`download_xml()`)

    - Streams XML from `https://directory.peppol.eu/export/businesscards`
    - Saves to `tmp/directory-export-business-cards.xml`
    - Shows progress every 100MB
    - Skips download if file exists (override with `-F`)

2. **Processing Phase** (`process_xml()`)

    - Uses text-based chunking (1MB chunks) for memory efficiency, scanning the buffer by index
    - Parses and pretty-prints cards in a worker pool (`-j`, default: CPU count - 1); the main process keeps input order and does all writing
    - Parses business cards with `lxml.etree` for fast XML handling
    - Extracts country code from `<entity countrycode="XX">`
    - Extracts registration date from `<regdate>` for statistics
    - Writes pretty-printed XML to country/month directories

3. **File Splitting Logic** (in `process_xml()`)

    - Groups cards per country and registration month (`<regdate>`): `extracts/BE/2026-08/`; cards without a registration date go to `extracts/BE/0000-00/`
    - Within a month directory, splits files when they exceed `max_bytes` (default: 2MB)
    - Sequential naming: `business-cards.000001.xml`, `business-cards.000002.xml`, etc.
    - Bucketing by month keeps past months stable: a new registration only touches its own month, so daily commits stay small
    - Keeps one output file open per country/month bucket, with an LRU cache bounded by the process file-descriptor limit
    - Automatically creates header and footer tags for valid XML

4. **Report Generation** (`generate_report()`)
    - Creates `docs/report.md` with country statistics
    - Shows month count, file count, card count, and size per country

## Running the sync tool

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

## Utility commands

```bash
# Download XML only (no processing)
python3 peppol_sync.py download

# Check configuration
python3 peppol_sync.py check

# Show largest output files
python3 peppol_sync.py huge -n 20

# Custom max file size (default: 2MB)
python3 peppol_sync.py sync -M 1000000

# Single process, no worker pool (default: CPU count - 1 workers)
python3 peppol_sync.py sync -j 1
```


## Dependencies

```bash
# Install required Python package
pip install lxml
```

## Key Implementation Details

### Memory-Efficient XML Processing

The script processes multi-GB XML files without loading everything into memory:

- Reads in 1MB text chunks
- Splits on `</businesscard>` delimiter
- Parses individual cards with lxml
- Uses streaming writes to output files

### Card Conversion

`convert_card()` is a module-level function (so worker processes can run it). It parses one
card with lxml, extracts the country code from `<entity countrycode="XX">`, the registration
date from `<regdate>`, the entity name, and returns the pretty-printed card as UTF-8 bytes.
Output files are written in binary mode with a per-bucket byte counter; `tell()` on a
text-mode file was a measurable per-card cost.

### File Rotation

When a country file exceeds `max_bytes`:

1. Writes `</root>` footer to close current file
2. Increments sequence number in `self.file_stats[country]['sequence']`
3. Opens new file with updated sequence
4. Writes XML header to new file

### Cleanup Behavior

- **Temporary files** (`tmp/`): Deleted after processing by default (keep with `-K`)
- **Extract files** (`extracts/**/*.xml`): Deleted before each sync by default (preserve with `-C`)
- **Log file** (`log/peppol_sync.log`): Overwritten on each run
