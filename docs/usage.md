# PEPPOL Sync Usage

This document explains how to use the `peppol_sync.py` script to download and process PEPPOL business card data.

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
