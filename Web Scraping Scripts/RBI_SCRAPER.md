# RBI Circular Scraper

This script downloads circulars from the RBI circular index at [rbi.org.in](https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx), including the archive tree by year and month.

## What it saves

- `archives.csv`: one row per year/month archive queried
- `items.csv`: one row per circular
- `attachments.csv`: one row per PDF attachment
- `<year-month>/<circular-id>/metadata.json`: parsed metadata and body text
- `<year-month>/<circular-id>/attachments/...`: downloaded PDFs

## Examples

Scrape the full archive:

```bash
python rbi_circulars_scraper.py --output-dir rbi_circular_downloads
```

Quick smoke test:

```bash
python rbi_circulars_scraper.py --max-items 5
```

## Notes

- RBI exposes the archive tree through hidden `hdnYear` and `hdnMonth` fields, so the scraper can request old months directly.
- The detail pages contain the full circular text plus a direct PDF link.
- If you want the `Standalone Circulars` or `Circulars Withdrawn` sections too, I can add those as additional source categories.
