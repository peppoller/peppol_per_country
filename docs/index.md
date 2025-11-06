# Peppol Git Per Country

PEPPOL Per Country is a Python-based tool that synchronizes PEPPOL business directory exports by country. It downloads the massive XML export from `directory.peppol.eu`, processes it using streaming XML parsing, and splits business cards into country-specific files stored in git.

## Core Script

- [peppol_sync.py](peppol_sync.md)
- Python 3.x with `lxml` for XML processing
- [GitHub Actions](github.md) for daily automated sync
- [Documentation](documentation.md) : MkDocs with Material theme (using [pforret/mkdox](https://github.ciom/pforret/mkdox) )

## Sparse Checkout

You can 'subscribe' to only the .xml files **for 1 specific country** (so not the full 2+GB of extract files) , using [git sparse-checkout](sparse.md).

