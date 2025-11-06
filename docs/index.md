# Peppol Git Per Country

PEPPOL Per Country is a Python-based tool that synchronizes PEPPOL business directory exports by country. It downloads the massive XML export from `directory.peppol.eu`, processes it using streaming XML parsing, and splits business cards into country-specific files stored in git.

## Core Script

- Python 3.x with `lxml` for XML processing: [peppol_sync.py](peppol_sync.md)
- GitHub Actions for daily automated sync
- MkDocs with Material theme for documentation
* data processing is done by 

## GitHub Action

**Daily Sync Workflow** (`.github/workflows/daily.yml`)

- Runs at 09:15 UTC daily
- Executes `python3 peppol_sync.py sync -V`
- Commits and pushes changes to `extracts/` automatically
- Creates `extracts/git_diff.txt` with change summary
- takes +- 5 minutes

**Pages Deployment** (`.github/workflows/static.yml`)

- Deploys `site/` directory to GitHub Pages
- Triggered on push to main branch

## sparse-checkout

You can 'subscribe' to only the .xml files **for 1 specific country** (so not the full 2+GB of extract files) , using [git sparse-checkout](sparse.md).

## Version Management

Version is stored in `VERSION.md` and updated via commit messages like `setver: set version to 0.1.12`. There is no automated version bumping script in the repository.

## Documentation Site

Uses MkDocs with Material theme. Configuration in `mkdocs.yml`:

- Main docs in `docs/` directory
- Publish to `site/` directory
- Documentation is deployed to GitHub Pages via the static workflow
- `README.md` is a symlink to `docs/index.md`
