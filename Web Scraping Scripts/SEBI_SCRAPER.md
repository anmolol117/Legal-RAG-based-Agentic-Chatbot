# SEBI Legal Scraper

This script downloads SEBI legal listings from [sebi.gov.in/legal.html](https://www.sebi.gov.in/legal.html) and saves each item page plus any attached PDF document.

## What it saves

- `categories.csv`: the legal categories processed
- `items.csv`: one row per legal listing item
- `attachments.csv`: one row per attachment discovered
- `<category>/<item-id>/metadata.json`: item metadata and attachment list
- `<category>/<item-id>/attachments/...`: downloaded PDFs

## Examples

Scrape all legal categories:

```bash
python sebi_legal_scraper.py --output-dir sebi_legal_downloads
```

Scrape only circulars:

```bash
python sebi_legal_scraper.py --category Circulars --output-dir sebi_circulars
```

Quick smoke test:

```bash
python sebi_legal_scraper.py --category Circulars --max-items 5
```

## Notes

- The scraper walks the live listing pages and then opens each detail page to collect PDF attachments.
- SEBI uses a JavaScript-driven AJAX pager. The script handles that directly.
- If you want archive coverage too, I can extend the scraper to include archived legal listings where SEBI exposes them separately.
