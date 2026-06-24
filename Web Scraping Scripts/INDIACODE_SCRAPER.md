# India Code Scraper

This script downloads Acts and linked subordinate legislation from [indiacode.nic.in](https://www.indiacode.nic.in/) by walking the public browse pages instead of the disallowed search endpoint.

## What it saves

- `collections.csv`: the collections that were targeted
- `acts.csv`: one row per Act page
- `documents.csv`: one row per downloaded or discovered document
- `<collection>/<handle>/metadata.json`: full Act metadata plus linked documents
- `<collection>/<handle>/downloads/...`: PDFs grouped by section

## Examples

Scrape a small central-only sample:

```bash
python indiacode_scraper.py --scope central --max-acts 5 --max-documents-per-act 3
```

Scrape central Acts only:

```bash
python indiacode_scraper.py --scope central --output-dir indiacode_central
```

Scrape central plus all states and union territories:

```bash
python indiacode_scraper.py --scope all --output-dir indiacode_all --delay-seconds 1.5
```

Scrape selected states:

```bash
python indiacode_scraper.py --scope selected-states --state Delhi --state Haryana
```

## Notes

- The full site is large. Expect a long-running job and substantial disk usage.
- The scraper rate-limits requests by default. Please keep it polite.
- Re-running the script skips Acts that already have a `metadata.json` file unless `--overwrite` is used.
- `--max-documents-per-act` is handy for a quick smoke test before you launch a full crawl.
