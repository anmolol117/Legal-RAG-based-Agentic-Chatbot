from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.rbi.org.in"
INDEX_URL = f"{BASE_URL}/Scripts/BS_CircularIndexDisplay.aspx"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class Archive:
    year: int
    month: int

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"

    @property
    def slug(self) -> str:
        return f"{self.year}-{self.month:02d}"


MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def slugify(value: str, max_length: int = 120) -> str:
    value = re.sub(r"\s+", " ", value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return (value or "item")[:max_length].rstrip("-")


def absolute_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    joined = urljoin(INDEX_URL, url)
    parsed = urlparse(joined)
    if not parsed.scheme or not parsed.netloc:
        return joined
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


class RBICircularScraper:
    def __init__(
        self,
        output_dir: Path,
        delay_seconds: float = 0.75,
        timeout_seconds: int = 30,
        retries: int = 3,
        overwrite: bool = False,
        max_items: int | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.overwrite = overwrite
        self.max_items = max_items
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.last_request_at = 0.0
        self.item_rows: list[dict[str, str]] = []
        self.attachment_rows: list[dict[str, str]] = []
        self.archive_rows: list[dict[str, str]] = []

    def run(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        base_html = self.get_text(INDEX_URL)
        base_soup = BeautifulSoup(base_html, "html.parser")
        base_form = self.extract_form_data(base_soup)
        archives = self.discover_archives(base_soup)

        (self.output_dir / "run_config.json").write_text(
            json.dumps(
                {
                    "started_at_epoch": int(time.time()),
                    "delay_seconds": self.delay_seconds,
                    "timeout_seconds": self.timeout_seconds,
                    "retries": self.retries,
                    "overwrite": self.overwrite,
                    "max_items": self.max_items,
                    "archive_count": len(archives),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        total = 0
        for archive in archives:
            if self.max_items is not None and total >= self.max_items:
                break
            print(f"[archive] {archive.label}", flush=True)
            total += self.scrape_archive(archive, base_form, total)

        self.write_indexes()

    def discover_archives(self, soup: BeautifulSoup) -> list[Archive]:
        pairs = []
        for year_str, month_str in re.findall(r'GetYearMonth\("(\d{4})","(\d+)"\)', soup.decode(), re.I):
            month = int(month_str)
            if month == 0:
                continue
            pairs.append(Archive(year=int(year_str), month=month))

        unique = {(a.year, a.month): a for a in pairs}
        return [unique[key] for key in sorted(unique, key=lambda k: (k[0], k[1]), reverse=True)]

    def scrape_archive(self, archive: Archive, base_form: dict[str, str], total_so_far: int) -> int:
        archive_dir = self.output_dir / archive.slug
        archive_dir.mkdir(parents=True, exist_ok=True)

        page_html = self.fetch_archive_page(archive, base_form)
        soup = BeautifulSoup(page_html, "html.parser")
        rows = self.parse_listing_rows(soup)
        if not rows:
            return 0

        self.archive_rows.append(
            {
                "year": str(archive.year),
                "month": str(archive.month),
                "month_name": MONTH_NAMES.get(archive.month, ""),
                "item_count": str(len(rows)),
            }
        )

        count = 0
        for row in rows:
            if self.max_items is not None and total_so_far + count >= self.max_items:
                break
            self.scrape_item(archive, archive_dir, row)
            count += 1

        return count

    def fetch_archive_page(self, archive: Archive, base_form: dict[str, str]) -> str:
        data = dict(base_form)
        data["hdnYear"] = str(archive.year)
        data["hdnMonth"] = str(archive.month)
        data["__EVENTTARGET"] = ""
        data["__EVENTARGUMENT"] = ""
        return self.post(INDEX_URL, data=data, referer=INDEX_URL).text

    def extract_form_data(self, soup: BeautifulSoup) -> dict[str, str]:
        form = soup.find("form")
        if form is None:
            raise RuntimeError("Could not find RBI circular form")
        data: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                data[name] = inp.get("value", "")
        return data

    def parse_listing_rows(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for tr in soup.find_all("tr"):
            anchor = tr.find("a", href=re.compile(r"BS_CircularIndexDisplay\.aspx\?Id=\d+", re.I))
            if not anchor:
                continue
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 5:
                continue
            circular_text = " ".join(anchor.get_text(" ", strip=True).split())
            href = absolute_url(anchor.get("href", ""))
            rows.append(
                {
                    "circular_text": circular_text,
                    "detail_url": href,
                    "date": cell_text(tds, 1),
                    "department": cell_text(tds, 2),
                    "subject": cell_text(tds, 3),
                    "meant_for": cell_text(tds, 4),
                    "circular_number": circular_text.split("\n")[0] if "\n" in circular_text else circular_text.split(" ", 1)[0],
                }
            )
        return rows

    def scrape_item(self, archive: Archive, archive_dir: Path, row: dict[str, str]) -> None:
        circular_id = row["detail_url"].split("Id=")[-1].split("&")[0]
        item_dir = archive_dir / circular_id
        metadata_path = item_dir / "metadata.json"

        if metadata_path.exists() and not self.overwrite:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.append_rows(archive, existing)
            return

        print(f"[item] {archive.label} Id={circular_id} {row['subject'][:80]}", flush=True)
        item_dir.mkdir(parents=True, exist_ok=True)
        detail_html = self.get_text(row["detail_url"])
        detail_soup = BeautifulSoup(detail_html, "html.parser")
        metadata = self.parse_detail_page(archive, row, circular_id, detail_soup)

        attachments_dir = item_dir / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)
        for attachment in metadata["attachments"]:
            self.download_attachment(attachment, attachments_dir)

        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        self.append_rows(archive, metadata)

    def parse_detail_page(self, archive: Archive, row: dict[str, str], circular_id: str, soup: BeautifulSoup) -> dict:
        title = first_non_empty(row.get("subject"), soup.title.get_text(" ", strip=True) if soup.title else "")
        pdf_url = extract_pdf_url(soup)
        body_text = extract_body_text(soup)
        meta = read_meta_tags(soup)
        return {
            "archive_year": archive.year,
            "archive_month": archive.month,
            "archive_label": archive.label,
            "circular_id": circular_id,
            "title": title,
            "detail_url": row.get("detail_url", ""),
            "listing_circular_text": row.get("circular_text", ""),
            "date": row.get("date", ""),
            "department": row.get("department", ""),
            "subject": row.get("subject", ""),
            "meant_for": row.get("meant_for", ""),
            "pdf_url": pdf_url,
            "body_text": body_text,
            "meta": meta,
            "attachments": [
                {
                    "url": pdf_url,
                    "label": title,
                    "filename": pdf_filename_from_url(pdf_url, title),
                }
            ]
            if pdf_url
            else [],
        }

    def download_attachment(self, attachment: dict[str, str], attachments_dir: Path) -> None:
        url = attachment.get("url", "")
        if not url:
            return
        filename = safe_filename(attachment.get("filename") or Path(urlparse(url).path).name)
        destination = attachments_dir / filename
        attachment["relative_path"] = str(destination.relative_to(attachments_dir.parent))
        if destination.exists() and not self.overwrite:
            return
        try:
            response = self.get_response(url, stream=True)
            with destination.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        fh.write(chunk)
        except requests.RequestException as exc:
            attachment["download_error"] = str(exc)
            print(f"[download-error] {url} error={exc}", flush=True)

    def append_rows(self, archive: Archive, metadata: dict) -> None:
        self.item_rows.append(
            {
                "archive_year": str(archive.year),
                "archive_month": str(archive.month),
                "archive_label": archive.label,
                "circular_id": str(metadata.get("circular_id", "")),
                "title": metadata.get("title", ""),
                "date": metadata.get("date", ""),
                "department": metadata.get("department", ""),
                "subject": metadata.get("subject", ""),
                "meant_for": metadata.get("meant_for", ""),
                "detail_url": metadata.get("detail_url", ""),
                "pdf_url": metadata.get("pdf_url", ""),
                "attachment_count": str(len(metadata.get("attachments", []))),
            }
        )
        for attachment in metadata.get("attachments", []):
            self.attachment_rows.append(
                {
                    "archive_year": str(archive.year),
                    "archive_month": str(archive.month),
                    "archive_label": archive.label,
                    "circular_id": str(metadata.get("circular_id", "")),
                    "title": metadata.get("title", ""),
                    "date": metadata.get("date", ""),
                    "department": metadata.get("department", ""),
                    "subject": metadata.get("subject", ""),
                    "meant_for": metadata.get("meant_for", ""),
                    "detail_url": metadata.get("detail_url", ""),
                    "attachment_label": attachment.get("label", ""),
                    "attachment_url": attachment.get("url", ""),
                    "relative_path": attachment.get("relative_path", ""),
                    "download_error": attachment.get("download_error", ""),
                }
            )

    def write_indexes(self) -> None:
        self.write_csv(
            self.output_dir / "archives.csv",
            ["year", "month", "month_name", "item_count"],
            dedupe_rows(self.archive_rows, ("year", "month")),
        )
        self.write_csv(
            self.output_dir / "items.csv",
            [
                "archive_year",
                "archive_month",
                "archive_label",
                "circular_id",
                "title",
                "date",
                "department",
                "subject",
                "meant_for",
                "detail_url",
                "pdf_url",
                "attachment_count",
            ],
            dedupe_rows(self.item_rows, ("circular_id", "detail_url")),
        )
        self.write_csv(
            self.output_dir / "attachments.csv",
            [
                "archive_year",
                "archive_month",
                "archive_label",
                "circular_id",
                "title",
                "date",
                "department",
                "subject",
                "meant_for",
                "detail_url",
                "attachment_label",
                "attachment_url",
                "relative_path",
                "download_error",
            ],
            dedupe_rows(self.attachment_rows, ("attachment_url", "relative_path")),
        )

    def write_csv(self, path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def get_text(self, url: str) -> str:
        response = self.get_response(url, stream=False)
        response.encoding = response.encoding or "utf-8"
        return response.text

    def get_response(self, url: str, stream: bool) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self.respect_rate_limit()
            try:
                response = self.session.get(url, timeout=self.timeout_seconds, stream=stream)
                response.raise_for_status()
                self.last_request_at = time.time()
                return response
            except requests.RequestException as exc:
                last_error = exc
                wait_for = min(8, attempt * 2)
                print(f"[retry] {url} attempt={attempt} wait={wait_for}s error={exc}", flush=True)
                time.sleep(wait_for)
        assert last_error is not None
        raise last_error

    def post(self, url: str, data: dict[str, str], referer: str | None = None) -> requests.Response:
        headers = {}
        if referer:
            headers["Referer"] = referer
        return self._request("POST", url, data=data, headers=headers, stream=False)

    def _request(
        self,
        method: str,
        url: str,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        stream: bool = False,
    ) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            self.respect_rate_limit()
            try:
                response = self.session.request(
                    method,
                    url,
                    data=data,
                    headers=headers,
                    timeout=self.timeout_seconds,
                    stream=stream,
                )
                response.raise_for_status()
                self.last_request_at = time.time()
                return response
            except requests.RequestException as exc:
                last_error = exc
                wait_for = min(8, attempt * 2)
                print(f"[retry] {method} {url} attempt={attempt} wait={wait_for}s error={exc}", flush=True)
                time.sleep(wait_for)
        assert last_error is not None
        raise last_error

    def respect_rate_limit(self) -> None:
        elapsed = time.time() - self.last_request_at
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)


def extract_pdf_url(soup: BeautifulSoup) -> str:
    for a in soup.select("a[href]"):
        href = absolute_url(a.get("href", ""))
        if "rbidocs.rbi.org.in" in href.lower() and href.lower().endswith(".pdf"):
            return href
    return ""


def extract_body_text(soup: BeautifulSoup) -> str:
    table = soup.find("table", class_="tablebg")
    if not table:
        return ""
    inner = table.find_all("td")
    if len(inner) < 3:
        return " ".join(soup.get_text(" ", strip=True).split())
    body = inner[-1]
    return " ".join(body.get_text(" ", strip=True).split())


def pdf_filename_from_url(pdf_url: str, title: str) -> str:
    if pdf_url:
        name = Path(urlparse(pdf_url).path).name
        if name:
            return name
    return f"{slugify(title, 80)}.pdf"


def safe_filename(value: str, default_ext: str = ".pdf") -> str:
    value = value.strip()
    if not value:
        return f"attachment{default_ext}"
    value = value.replace("+", " ")
    suffix = Path(value).suffix or default_ext
    stem = Path(value).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-")
    if not stem:
        stem = "attachment"
    return f"{stem}{suffix.lower()}"


def read_meta_tags(soup: BeautifulSoup) -> dict[str, str]:
    meta: dict[str, str] = {}
    for tag in soup.select("meta[name]"):
        name = tag.get("name", "").strip().lower()
        content = tag.get("content", "").strip()
        if name and content and name not in meta:
            meta[name] = content
    return meta


def first_non_empty(*values: object) -> str:
    for value in values:
        if isinstance(value, list):
            for item in value:
                if item:
                    return str(item)
        elif value:
            return str(value)
    return ""


def cell_text(cells: list[Tag], index: int) -> str:
    if index >= len(cells):
        return ""
    return " ".join(cells[index].get_text(" ", strip=True).split())


def dedupe_rows(rows: Iterable[dict[str, str]], keys: tuple[str, ...]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        fingerprint = tuple(row.get(key, "") for key in keys)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(row)
    return deduped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape RBI circular archives and download PDF attachments.")
    parser.add_argument("--output-dir", default="rbi_circular_downloads", help="Output directory.")
    parser.add_argument("--delay-seconds", type=float, default=0.75, help="Delay between requests.")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="Per-request timeout.")
    parser.add_argument("--retries", type=int, default=3, help="Retries per request.")
    parser.add_argument("--overwrite", action="store_true", help="Re-download files and overwrite metadata.")
    parser.add_argument("--max-items", type=int, default=None, help="Stop after this many circulars.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scraper = RBICircularScraper(
        output_dir=Path(args.output_dir).resolve(),
        delay_seconds=args.delay_seconds,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
        overwrite=args.overwrite,
        max_items=args.max_items,
    )
    scraper.run()


if __name__ == "__main__":
    main()
