# peppol_sync.py

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
```

## GitHub action testing
