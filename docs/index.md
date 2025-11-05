# PEPPOL SYNC

Python-based synchronization tool for PEPPOL business directory exports.

## What it does

1. Downloads the PEPPOL business cards export from https://directory.peppol.eu/export/businesscards
   - Saves to `tmp/directory-export-business-cards.xml`
   - Uses streaming download with progress tracking
   - Reuses existing file unless forced with `-F`

2. Processes the massive XML file in streaming mode
   - Splits business cards by country code
   - Creates sequentially numbered files per country: `extracts/{COUNTRY}/business-cards.{SEQUENCE:06d}.xml`
   - Files are split based on size threshold (default: 1MB per file via `--max`)
   - Example output: `extracts/NO/business-cards.000001.xml`, `extracts/BE/business-cards.000001.xml`

3. Git operations (manual or via GitHub Actions)
   - `git add`, `git commit`, `git push`
   - Daily GitHub job: `peppol_sync.sh sync`

## Usage

```bash
# Full sync: download + process XML
python3 peppol_sync.py sync

# Just download the XML file
python3 peppol_sync.py download

# Check configuration
python3 peppol_sync.py check

# Show N largest output files
python3 peppol_sync.py huge -n 20
```

## Options

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
## Output Structure

```
extracts/
├── AT/
│   ├── business-cards.000001.xml
│   └── business-cards.000002.xml
├── BE/
│   └── business-cards.000001.xml
├── NO/
│   ├── business-cards.000001.xml
│   ├── business-cards.000002.xml
│   └── business-cards.000003.xml
└── ...
```

## Cleanup

By default, the script automatically deletes all files in the `tmp/` directory after successful processing to save disk space. 
The large XML export file can be several gigabytes.

To keep temporary files for debugging or inspection:
```bash
python3 peppol_sync.py sync -K
```

