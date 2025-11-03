# PEPPOL SYNC

Python-based synchronization tool for PEPPOL business directory exports.

## What it does

1. Downloads the PEPPOL business cards export from https://directory.peppol.eu/export/businesscards
   - Saves to `tmp/directory-export-business-cards.xml`
   - Uses streaming download with progress tracking
   - Reuses existing file unless forced with `-f`

2. Processes the massive XML file in streaming mode
   - Splits business cards by country code
   - Creates sequentially numbered files per country: `extracts/{COUNTRY}/business-cards.{SEQUENCE:06d}.xml`
   - Files are split based on size threshold (default: 1MB per file via `--max-bytes`)
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

- `-T, --tmp-dir`: Temporary directory (default: tmp)
- `-L, --log-dir`: Log directory (default: log)
- `-v, --verbose`: Enable verbose output
- `-f, --force`: Force re-download even if file exists
- `-n, --number`: Number of largest files to show (default: 10)
- `--max-bytes`: Maximum bytes per output file (default: 1000000)

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

