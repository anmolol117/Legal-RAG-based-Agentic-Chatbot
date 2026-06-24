from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag


BASE_URL = "https://www.sebi.gov.in"
LISTING_ENDPOINT = f"{BASE_URL}/sebiweb/ajax/home/getnewslistinfo.jsp"
LEGAL_LISTING_URL = f"{BASE_URL}/legal.html"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class Category:
    name: str
    ssid: str

    @property
    def slug(self) -> str:
        return slugify(self.name)


DEFAULT_CATEGORIES = [
    Category("Acts", "1"),
    Category("Rules", "2"),
    Category("Regulations", "3"),
    Category("General Orders", "4"),
    Category("Guidelines", "5"),
    Category("Master Circulars", "6"),
    Category("Circulars", "7"),
]


def slugify(value: str, max_length: int = 120) -> str:
    value = re.sub(r"\s+", " ", value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return (value or "item")[:max_length].rstrip("-")


def absolute_url(url: str) -> str:
    url = url.strip()
    if not url:
        return url
    if url.startswith("//"):
        return f"https:{url}"
    joined = urljoin(BASE_URL, url)
    parsed = urlparse(joined)
    if not parsed.scheme or not parsed.netloc:
        return joined
    return urlunparse(("https", urlparse(BASE_URL).netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


class SEBILegalScraper:
    def __init__(
        self,
        output_dir: Path,
        delay_seconds: float = 0.75,
        timeout_seconds: int = 30,
        retries: int = 3,
        overwrite: bool = False,
        max_items: int | None = None,
        categories: list[Category] | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.overwrite = overwrite
        self.max_items = max_items
        self.categories = categories or DEFAULT_CATEGORIES
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.last_request_at = 0.0
        self.category_rows: list[dict[str, str]] = []
        self.item_rows: list[dict[str, str]] = []
        self.attachment_rows: list[dict[str, str]] = []

    def run(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "run_config.json").write_text(
            json.dumps(
                {
                    "started_at_epoch": int(time.time()),
                    "delay_seconds": self.delay_seconds,
                    "timeout_seconds": self.timeout_seconds,
                    "retries": self.retries,
                    "overwrite": self.overwrite,
                    "max_items": self.max_items,
                    "categories": [c.name for c in self.categories],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        total_items = 0
        for category in self.categories:
            if self.max_items is not None and total_items >= self.max_items:
                break
            print(f"[category] {category.name}", flush=True)
            total_items += self.scrape_category(category, total_items)

        self.write_indexes()

    def scrape_category(self, category: Category, total_items_so_far: int) -> int:
        category_dir = self.output_dir / category.slug
        category_dir.mkdir(parents=True, exist_ok=True)

        listing_url = self.listing_url(category)
        listing = self.get_text(listing_url)
        soup = BeautifulSoup(listing, "html.parser")
        total_pages = self.parse_total_pages(soup)
        form_data = self.base_listing_form_data(soup, category)
        items_in_category = 0

        for page_num in range(1, total_pages + 1):
            if self.max_items is not None and total_items_so_far + items_in_category >= self.max_items:
                break
            if page_num == 1:
                page_html = listing
            else:
                print(f"[page] {category.name} {page_num}/{total_pages}", flush=True)
                page_html = self.fetch_listing_page(category, page_num, form_data)

            page_soup = BeautifulSoup(page_html, "html.parser")
            rows = self.parse_listing_rows(page_soup)
            if not rows:
                continue

            for row in rows:
                if self.max_items is not None and total_items_so_far + items_in_category >= self.max_items:
                    break
                self.scrape_detail(category, category_dir, row)
                items_in_category += 1

        return items_in_category

    def listing_url(self, category: Category) -> str:
        params = {"doListing": "yes", "sid": 1, "smid": 0, "ssid": category.ssid}
        return f"{BASE_URL}/sebiweb/home/HomeAction.do?{urlencode(params)}"

    def fetch_listing_page(self, category: Category, page_num: int, form_data: dict[str, str]) -> str:
        page_num = max(1, page_num)
        data = dict(form_data)
        data.update(
            {
                "nextValue": str(max(1, page_num - 1)),
                "next": "n" if page_num > 1 else "n",
                "doDirect": str(max(1, page_num - 1)),
            }
        )
        response = self.post(LISTING_ENDPOINT, data=data, referer=self.listing_url(category))
        return response.text

    def base_listing_form_data(self, soup: BeautifulSoup, category: Category) -> dict[str, str]:
        form = soup.find("form")
        if form is None:
            raise RuntimeError(f"Could not locate listing form for {category.name}")

        data: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                data[name] = inp.get("value", "")
        for sel in form.find_all("select"):
            name = sel.get("name")
            if name:
                selected = sel.find("option", selected=True)
                data[name] = selected.get("value", "") if selected else ""

        data["sid"] = "1"
        data["smidhidden"] = "0"
        data["ssidhidden"] = category.ssid
        data["sectName"] = "Legal"
        data["ssid"] = category.ssid
        data["nextValue"] = data.get("nextValue", "1")
        data["search"] = data.get("search", "")
        data["fromDate"] = data.get("fromDate", "")
        data["toDate"] = data.get("toDate", "")
        data["deptId"] = data.get("deptId", "")
        data["intmid"] = data.get("intmid", "")
        data["ckvalue"] = data.get("ckvalue", "1")
        return data

    def parse_total_pages(self, soup: BeautifulSoup) -> int:
        match = soup.find("input", attrs={"name": "nextValue"})
        if match and match.get("value", "").isdigit():
            # Hidden value on the first page is the next page number.
            hidden_next = int(match.get("value", "1"))
        else:
            hidden_next = 2
        total_pages = max(1, hidden_next)
        nav_links = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            m = re.search(r"searchFormNewsList\\('n','(\\d+)'\\)", href)
            if m:
                nav_links.append(int(m.group(1)) + 1)
        if nav_links:
            total_pages = max(total_pages, max(nav_links))

        range_match = re.search(r"of\\s+(\\d+)\\s+records", soup.get_text(" ", strip=True))
        if range_match and "Last" in soup.get_text(" ", strip=True):
            last = max(nav_links) if nav_links else total_pages
            total_pages = max(total_pages, last)
        return total_pages

    def parse_listing_rows(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for tr in soup.select("table#sample_1 tr"):
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue
            date = cell_text(cells, 0)
            anchor = cells[1].find("a", href=True)
            if not anchor:
                continue
            title = " ".join(anchor.get_text(" ", strip=True).split())
            href = absolute_url(anchor["href"])
            rows.append({"date": date, "title": title, "detail_url": href})
        return rows

    def scrape_detail(self, category: Category, category_dir: Path, row: dict[str, str]) -> None:
        detail_url = row["detail_url"]
        detail_id = slugify(detail_url.rsplit("_", 1)[-1].replace(".html", ""))
        item_dir = category_dir / detail_id
        metadata_path = item_dir / "metadata.json"

        if metadata_path.exists() and not self.overwrite:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.append_rows(category, existing)
            return

        print(f"[item] {category.name} {row['date']} {row['title'][:80]}", flush=True)
        item_dir.mkdir(parents=True, exist_ok=True)
        html = self.get_text(detail_url)
        soup = BeautifulSoup(html, "html.parser")
        metadata = self.parse_detail_page(category, row, detail_url, soup)
        attachments_dir = item_dir / "attachments"
        attachments_dir.mkdir(parents=True, exist_ok=True)
        for attachment in metadata["attachments"]:
            self.download_attachment(attachment, attachments_dir)

        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        self.append_rows(category, metadata)

    def parse_detail_page(self, category: Category, row: dict[str, str], detail_url: str, soup: BeautifulSoup) -> dict:
        meta = read_meta_tags(soup)
        title = first_non_empty(meta.get("title"), row.get("title"), soup.title.get_text(" ", strip=True) if soup.title else "")
        attachments = self.extract_attachments(soup)
        return {
            "category": category.name,
            "category_ssid": category.ssid,
            "title": title,
            "detail_url": detail_url,
            "date": row.get("date", ""),
            "meta": meta,
            "attachments": attachments,
        }

    def extract_attachments(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        seen: set[str] = set()
        attachments: list[dict[str, str]] = []

        def add_attachment(url: str, label: str = "") -> None:
            url = normalize_attachment_url(url)
            if not url or url in seen:
                return
            seen.add(url)
            attachments.append(
                {
                    "url": url,
                    "label": label.strip() or Path(urlparse(url).path).name,
                    "filename": Path(urlparse(url).path).name or slugify(label or "attachment"),
                }
            )

        for tag in soup.find_all(["a", "iframe", "embed", "object"]):
            href = tag.get("href") or tag.get("src") or tag.get("data") or ""
            if not href:
                continue
            if "sebi_data/attachdocs" in href.lower() or "file=" in href.lower():
                add_attachment(href, tag.get_text(" ", strip=True))

        for match in re.finditer(r"https://www\\.sebi\\.gov\\.in/sebi_data/attachdocs/[^\"'\\s>]+", soup.decode(), re.I):
            add_attachment(match.group(0))

        return attachments

    def download_attachment(self, attachment: dict[str, str], attachments_dir: Path) -> None:
        filename = safe_filename(attachment["filename"])
        destination = attachments_dir / filename
        attachment["relative_path"] = str(destination.relative_to(attachments_dir.parent))
        if destination.exists() and not self.overwrite:
            return
        try:
            response = self.get_response(attachment["url"], stream=True)
            with destination.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        fh.write(chunk)
        except requests.RequestException as exc:
            attachment["download_error"] = str(exc)
            print(f"[download-error] {attachment['url']} error={exc}", flush=True)

    def append_rows(self, category: Category, metadata: dict) -> None:
        self.item_rows.append(
            {
                "category": category.name,
                "category_ssid": category.ssid,
                "title": metadata.get("title", ""),
                "date": metadata.get("date", ""),
                "detail_url": metadata.get("detail_url", ""),
                "attachment_count": str(len(metadata.get("attachments", []))),
            }
        )
        for attachment in metadata.get("attachments", []):
            self.attachment_rows.append(
                {
                    "category": category.name,
                    "category_ssid": category.ssid,
                    "title": metadata.get("title", ""),
                    "date": metadata.get("date", ""),
                    "detail_url": metadata.get("detail_url", ""),
                    "attachment_label": attachment.get("label", ""),
                    "attachment_url": attachment.get("url", ""),
                    "relative_path": attachment.get("relative_path", ""),
                    "download_error": attachment.get("download_error", ""),
                }
            )

    def write_indexes(self) -> None:
        self.write_csv(
            self.output_dir / "categories.csv",
            ["name", "ssid", "slug"],
            [{"name": c.name, "ssid": c.ssid, "slug": c.slug} for c in self.categories],
        )
        self.write_csv(
            self.output_dir / "items.csv",
            ["category", "category_ssid", "title", "date", "detail_url", "attachment_count"],
            dedupe_rows(self.item_rows, ("category_ssid", "detail_url")),
        )
        self.write_csv(
            self.output_dir / "attachments.csv",
            [
                "category",
                "category_ssid",
                "title",
                "date",
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
        return self.get_response(url, stream=False).text

    def post(self, url: str, data: dict[str, str], referer: str | None = None) -> requests.Response:
        headers = {"X-Requested-With": "XMLHttpRequest"}
        if referer:
            headers["Referer"] = referer
        return self._request("POST", url, data=data, headers=headers, stream=False)

    def get_response(self, url: str, stream: bool) -> requests.Response:
        return self._request("GET", url, stream=stream)

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


def normalize_attachment_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if "file=" in value and "sebi_data/attachdocs" in value:
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        target = query.get("file", [""])[0]
        if target.startswith("http"):
            return target
        return absolute_url(target)
    if value.startswith("/../../web/?file="):
        target = value.split("file=", 1)[1]
        return absolute_url(target)
    if value.startswith("//"):
        return f"https:{value}"
    return absolute_url(value)


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
    parser = argparse.ArgumentParser(
        description="Scrape SEBI legal listings and download attached PDFs."
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Category to scrape. Can be repeated. Defaults to all legal categories.",
    )
    parser.add_argument("--output-dir", default="sebi_legal_downloads", help="Output directory.")
    parser.add_argument("--delay-seconds", type=float, default=0.75, help="Delay between requests.")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="Per-request timeout.")
    parser.add_argument("--retries", type=int, default=3, help="Retries per request.")
    parser.add_argument("--overwrite", action="store_true", help="Re-download files and overwrite metadata.")
    parser.add_argument("--max-items", type=int, default=None, help="Stop after this many listing items.")
    return parser.parse_args()


def resolve_categories(requested: list[str]) -> list[Category]:
    if not requested:
        return DEFAULT_CATEGORIES
    wanted = {name.casefold() for name in requested}
    mapping = {c.name.casefold(): c for c in DEFAULT_CATEGORIES}
    resolved = [c for c in DEFAULT_CATEGORIES if c.name.casefold() in wanted]
    missing = sorted(wanted - set(mapping))
    if missing:
        raise ValueError(f"Unknown SEBI categories: {', '.join(missing)}")
    return resolved


def main() -> None:
    args = parse_args()
    scraper = SEBILegalScraper(
        output_dir=Path(args.output_dir).resolve(),
        delay_seconds=args.delay_seconds,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
        overwrite=args.overwrite,
        max_items=args.max_items,
        categories=resolve_categories(args.category),
    )
    scraper.run()


if __name__ == "__main__":
    main()
