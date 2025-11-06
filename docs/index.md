![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/peppoller/peppol_per_country/daily.yml)
![GitHub last commit](https://img.shields.io/github/last-commit/peppoller/peppol_per_country)
![GitHub commit activity](https://img.shields.io/github/commit-activity/w/peppoller/peppol_per_country)
![GitHub commit activity](https://img.shields.io/github/commit-activity/m/peppoller/peppol_per_country)


# Peppol Per Country

![](unsplash.national.jpg)

**Peppol Per Country** is a GitHub repository where the Peppol Business Cards export from [directory.peppol.eu](https://directory.peppol.eu/export/businesscards) (a single XML file of more than 2GB), is split into manageable 2MB XML files per country, and this is synced on a daily basis.

It allows for

* version control of the Peppol repository.
* subscribing to one specific country (cf [sparse checkout](sparse.md) )

## Core Technology

- [peppol_sync.py](peppol_sync.md)
- Python 3.x with `lxml` for XML processing
- [GitHub Actions](github.md) for daily automated sync
- [Project Documentation](documentation.md) : MkDocs with Material theme (using [pforret/mkdox](https://github.ciom/pforret/mkdox) )

## Sparse Checkout

You can 'subscribe' to only the .xml files **for 1 specific country** (so not the full 2+GB of extract files) , using [git sparse-checkout](sparse.md).

![GitHub Repo stars](https://img.shields.io/github/stars/peppoller/peppol_per_country)
 [github.com/peppoller/peppol_per_country](https://github.com/peppoller/peppol_per_country)