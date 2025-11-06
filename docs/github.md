# GitHub action

## Daily Sync Workflow

- via `.github/workflows/daily.yml`
- Runs at 09:15 UTC daily
- Executes `python3 peppol_sync.py sync -V`
- Commits and pushes changes to `extracts/` automatically
- Creates `extracts/git_diff.txt` with change summary
- takes +- 5 minutes

## Pages Deployment

- via `.github/workflows/static.yml`
- Deploys `site/` directory to GitHub Pages
- Triggered on push to main branch

## GitHub action testing

```bash
# uses https://github.com/nektos/act
# on MacOS: brew install act

test_gh_action.sh
```
