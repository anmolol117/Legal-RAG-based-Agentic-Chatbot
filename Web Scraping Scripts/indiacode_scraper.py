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


BASE_URL = "https://www.indiacode.nic.in"
HOME_URL = f"{BASE_URL}/"
CENTRAL_COLLECTION_HANDLE = "123456789/1362"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class Collection:
    name: str
    handle: str

    @property
    def browse_url(self) -> str:
        return build_browse_url(self.handle, offset=0)

    @property
    def slug(self) -> str:
        return slugify(self.name)


def slugify(value: str, max_length: int = 120) -> str:
    value = re.sub(r"\s+", " ", value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    if not value:
        value = "item"
    return value[:max_length].rstrip("-")


def absolute_url(url: str) -> str:
    joined = urljoin(BASE_URL, url.strip())
    parsed = urlparse(joined)
    if not parsed.scheme or not parsed.netloc:
        return joined
    return urlunparse(("https", urlparse(BASE_URL).netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def build_browse_url(handle: str, offset: int, rpp: int = 100) -> str:
    encoded_handle = quote(handle, safe="/")
    params = {
        "type": "shorttitle",
        "sort_by": 3,
        "order": "ASC",
        "rpp": rpp,
        "etal": -1,
        "null": "",
        "offset": offset,
    }
    return f"{BASE_URL}/handle/{encoded_handle}/browse?{urlencode(params)}"


class IndiaCodeScraper:
    def __init__(
        self,
        output_dir: Path,
        delay_seconds: float = 1.0,
        timeout_seconds: int = 30,
        retries: int = 3,
        overwrite: bool = False,
        max_acts: int | None = None,
        max_collections: int | None = None,
        max_documents_per_act: int | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.overwrite = overwrite
        self.max_acts = max_acts
        self.max_collections = max_collections
        self.max_documents_per_act = max_documents_per_act
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.last_request_at = 0.0
        self.collection_rows: list[dict[str, str]] = []
        self.act_rows: list[dict[str, str]] = []
        self.document_rows: list[dict[str, str]] = []

    def run(self, scope: str, state_names: list[str] | None = None) -> None:
        collections = self.discover_collections(scope=scope, state_names=state_names or [])
        if self.max_collections is not None:
            collections = collections[: self.max_collections]

        self.output_dir.mkdir(parents=True, exist_ok=True)
        run_meta = {
            "started_at_epoch": int(time.time()),
            "scope": scope,
            "collections_requested": [c.name for c in collections],
            "delay_seconds": self.delay_seconds,
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "overwrite": self.overwrite,
            "max_acts": self.max_acts,
            "max_collections": self.max_collections,
        }
        (self.output_dir / "run_config.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")

        total_acts = 0
        for collection in collections:
            if self.max_acts is not None and total_acts >= self.max_acts:
                break
            processed_here = self.scrape_collection(collection, total_acts)
            total_acts += processed_here

        self.write_indexes()

    def discover_collections(self, scope: str, state_names: list[str]) -> list[Collection]:
        homepage = BeautifulSoup(self.get_text(HOME_URL), "html.parser")
        state_collections: dict[str, Collection] = {}
        handle_pattern = re.compile(r"/handle/(\d+/\d+)/?$")

        for anchor in homepage.select("a[href]"):
            href = anchor.get("href", "").strip()
            text = " ".join(anchor.get_text(" ", strip=True).split())
            match = handle_pattern.fullmatch(href)
            if not match or not text:
                continue
            state_collections[text] = Collection(name=text, handle=match.group(1))

        ordered_states = [state_collections[name] for name in sorted(state_collections)]
        central = Collection(name="Central Acts", handle=CENTRAL_COLLECTION_HANDLE)

        if scope == "central":
            collections = [central]
        elif scope == "all":
            collections = [central, *ordered_states]
        elif scope == "states":
            collections = ordered_states
        else:
            requested = {name.casefold() for name in state_names}
            collections = [c for c in ordered_states if c.name.casefold() in requested]
            missing = sorted(set(requested) - {c.name.casefold() for c in collections})
            if missing:
                raise ValueError(f"Unknown state collections: {', '.join(missing)}")

        self.collection_rows = [
            {"name": c.name, "handle": c.handle, "browse_url": c.browse_url, "slug": c.slug}
            for c in collections
        ]
        return collections

    def scrape_collection(self, collection: Collection, total_acts_so_far: int) -> int:
        collection_dir = self.output_dir / collection.slug
        collection_dir.mkdir(parents=True, exist_ok=True)

        acts_in_collection = 0
        offset = 0
        rpp = 100

        while True:
            if self.max_acts is not None and total_acts_so_far + acts_in_collection >= self.max_acts:
                break

            browse_url = build_browse_url(collection.handle, offset=offset, rpp=rpp)
            print(f"[browse] {collection.name} offset={offset}", flush=True)
            soup = BeautifulSoup(self.get_text(browse_url), "html.parser")
            act_links = self.extract_act_links(soup)
            if not act_links:
                break

            for act_url in act_links:
                if self.max_acts is not None and total_acts_so_far + acts_in_collection >= self.max_acts:
                    break
                self.scrape_act(collection, collection_dir, act_url)
                acts_in_collection += 1

            if not self.has_next_offset(soup, offset + rpp):
                break
            offset += rpp

        return acts_in_collection

    def extract_act_links(self, soup: BeautifulSoup) -> list[str]:
        links: list[str] = []
        seen: set[str] = set()
        for anchor in soup.select('a[href*="/handle/123456789/"]'):
            href = anchor.get("href", "")
            if "view_type=browse" not in href:
                continue
            if not href.startswith("/handle/123456789/"):
                continue
            url = absolute_url(href)
            if url in seen:
                continue
            seen.add(url)
            links.append(url)
        return links

    def has_next_offset(self, soup: BeautifulSoup, next_offset: int) -> bool:
        target = f"offset={next_offset}"
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            if target in href:
                return True
        return False

    def scrape_act(self, collection: Collection, collection_dir: Path, act_url: str) -> None:
        handle_id = act_url.rstrip("/").split("/")[-1].split("?")[0]
        act_dir = collection_dir / handle_id
        metadata_path = act_dir / "metadata.json"

        if metadata_path.exists() and not self.overwrite:
            print(f"[skip] {collection.name} handle={handle_id}", flush=True)
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.append_rows_from_metadata(existing, collection)
            return

        act_dir.mkdir(parents=True, exist_ok=True)
        print(f"[act] {collection.name} handle={handle_id}", flush=True)

        soup = BeautifulSoup(self.get_text(act_url), "html.parser")
        metadata = self.parse_act_page(soup, act_url, collection)

        downloads_dir = act_dir / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        docs_to_download = metadata["documents"]
        if self.max_documents_per_act is not None:
            docs_to_download = docs_to_download[: self.max_documents_per_act]

        for doc in docs_to_download:
            self.download_document(doc, downloads_dir)

        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        self.append_rows_from_metadata(metadata, collection)

    def parse_act_page(self, soup: BeautifulSoup, act_url: str, collection: Collection) -> dict:
        meta_map = self.read_meta_tags(soup)
        title = first_non_empty(
            meta_map.get("citation_title"),
            meta_map.get("dc.title"),
            soup.title.get_text(" ", strip=True) if soup.title else None,
        )
        handle_url = absolute_url(first_non_empty(meta_map.get("citation_abstract_html_url"), act_url))
        handle_id = handle_url.rstrip("/").split("/")[-1].split("?")[0]
        identifiers = meta_values(meta_map, "dc.identifier")
        act_identifier = next((value for value in identifiers if not value.startswith("http")), "")
        act_number = next((value for value in reversed(identifiers) if value.isdigit()), "")
        ministry = meta_first(meta_map, "dc.relation")

        documents: list[dict[str, str]] = []
        documents.extend(self.parse_main_act_documents(soup, meta_map))
        documents.extend(self.parse_subordinate_documents(soup))

        return {
            "collection_name": collection.name,
            "collection_handle": collection.handle,
            "act_handle": handle_id,
            "act_url": handle_url,
            "title": title,
            "year": first_non_empty(meta_first(meta_map, "dc.date"), meta_first(meta_map, "citation_date")),
            "act_identifier": act_identifier,
            "act_number": act_number,
            "ministry_or_department": ministry,
            "keywords": meta_map.get("citation_keywords"),
            "documents": documents,
        }

    def read_meta_tags(self, soup: BeautifulSoup) -> dict[str, list[str] | str]:
        meta_map: dict[str, list[str]] = {}
        for tag in soup.select("meta[name]"):
            name = tag.get("name", "").strip().lower()
            content = tag.get("content", "").strip()
            if not name or not content:
                continue
            meta_map.setdefault(name, []).append(content)

        normalized: dict[str, list[str] | str] = {}
        for key, values in meta_map.items():
            normalized[key] = values if len(values) > 1 else values[0]
        return normalized

    def parse_main_act_documents(self, soup: BeautifulSoup, meta_map: dict[str, list[str] | str]) -> list[dict[str, str]]:
        docs: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        citation_pdf_url = meta_map.get("citation_pdf_url")
        if isinstance(citation_pdf_url, str):
            docs.append(
                {
                    "section": "Act",
                    "document_label": "Main act PDF",
                    "language": "english",
                    "source_url": absolute_url(citation_pdf_url),
                    "source_kind": "bitstream",
                }
            )
            seen_urls.add(absolute_url(citation_pdf_url))

        for anchor in soup.select('a[href*="/bitstream/"]'):
            href = absolute_url(anchor.get("href", ""))
            if href in seen_urls:
                continue
            text = " ".join(anchor.get_text(" ", strip=True).split())
            docs.append(
                {
                    "section": "Act",
                    "document_label": text or "Act PDF",
                    "language": infer_language(text=text, href=href),
                    "source_url": href,
                    "source_kind": "bitstream",
                }
            )
            seen_urls.add(href)
        return docs

    def parse_subordinate_documents(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        documents: list[dict[str, str]] = []

        for modal_body in soup.select("div.modal-body"):
            section_label = modal_body.select_one("label.subordinate")
            table = modal_body.select_one("table")
            if not section_label or not table:
                continue

            section = " ".join(section_label.get_text(" ", strip=True).split())
            for row in table.select("tbody tr"):
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue

                year_or_date = cell_text(cells, 0)
                english_description = cell_text(cells, 1)
                hindi_description = cell_text(cells, 2)

                for link_cell_index, language in ((3, "english"), (4, "hindi")):
                    link_cell = cells[link_cell_index] if len(cells) > link_cell_index else None
                    if link_cell is None:
                        continue
                    link = link_cell.find("a", href=True)
                    if link is None:
                        continue
                    href = absolute_url(link["href"])
                    file_title = " ".join(link.get("title", "").split())
                    description = english_description if language == "english" else hindi_description
                    description = description or english_description or file_title or f"{section} document"
                    documents.append(
                        {
                            "section": section,
                            "document_label": description,
                            "language": language,
                            "year_or_date": year_or_date,
                            "source_url": href,
                            "source_kind": classify_uploaded_path(href),
                            "source_file_hint": file_title,
                        }
                    )

        return documents

    def download_document(self, doc: dict[str, str], downloads_dir: Path) -> None:
        section_dir = downloads_dir / slugify(doc["section"])
        section_dir.mkdir(parents=True, exist_ok=True)

        source_url = doc["source_url"]
        filename = self.build_filename(doc)
        destination = section_dir / filename
        doc["relative_path"] = str(destination.relative_to(downloads_dir.parent))

        if destination.exists() and not self.overwrite:
            return

        try:
            response = self.get_response(source_url, stream=True)
            with destination.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        fh.write(chunk)
        except requests.RequestException as exc:
            doc["download_error"] = str(exc)
            print(f"[download-error] {source_url} error={exc}", flush=True)

    def build_filename(self, doc: dict[str, str]) -> str:
        url = doc["source_url"]
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        hinted = query.get("file", [None])[0]
        raw_name = hinted or Path(parsed.path).name or slugify(doc["document_label"])
        raw_name = raw_name.replace("+", " ")
        suffix = Path(raw_name).suffix or ".pdf"
        stem = Path(raw_name).stem

        prefix_parts = [
            slugify(doc.get("year_or_date", ""), max_length=24),
            slugify(doc.get("language", ""), max_length=20),
            slugify(doc.get("document_label", ""), max_length=80),
        ]
        prefix = "-".join(part for part in prefix_parts if part)
        stem_slug = slugify(stem, max_length=60)
        if stem_slug and stem_slug not in prefix:
            prefix = "-".join(part for part in [prefix, stem_slug] if part)
        return f"{prefix[:180].rstrip('-')}{suffix.lower()}"

    def append_rows_from_metadata(self, metadata: dict, collection: Collection) -> None:
        self.act_rows.append(
            {
                "collection_name": collection.name,
                "collection_handle": collection.handle,
                "act_handle": metadata["act_handle"],
                "title": metadata.get("title", ""),
                "year": stringify(metadata.get("year")),
                "act_number": stringify(metadata.get("act_number")),
                "act_identifier": stringify(metadata.get("act_identifier")),
                "ministry_or_department": stringify(metadata.get("ministry_or_department")),
                "act_url": metadata.get("act_url", ""),
                "document_count": str(len(metadata.get("documents", []))),
            }
        )

        for doc in metadata.get("documents", []):
            self.document_rows.append(
                {
                    "collection_name": collection.name,
                    "collection_handle": collection.handle,
                    "act_handle": metadata["act_handle"],
                    "title": metadata.get("title", ""),
                    "section": doc.get("section", ""),
                    "language": doc.get("language", ""),
                    "document_label": doc.get("document_label", ""),
                    "year_or_date": doc.get("year_or_date", ""),
                    "source_kind": doc.get("source_kind", ""),
                    "source_url": doc.get("source_url", ""),
                    "relative_path": doc.get("relative_path", ""),
                    "download_error": doc.get("download_error", ""),
                }
            )

    def write_indexes(self) -> None:
        self.write_csv(
            self.output_dir / "collections.csv",
            ["name", "handle", "browse_url", "slug"],
            self.collection_rows,
        )
        self.write_csv(
            self.output_dir / "acts.csv",
            [
                "collection_name",
                "collection_handle",
                "act_handle",
                "title",
                "year",
                "act_number",
                "act_identifier",
                "ministry_or_department",
                "act_url",
                "document_count",
            ],
            dedupe_rows(self.act_rows, ("collection_handle", "act_handle")),
        )
        self.write_csv(
            self.output_dir / "documents.csv",
            [
                "collection_name",
                "collection_handle",
                "act_handle",
                "title",
                "section",
                "language",
                "document_label",
                "year_or_date",
                "source_kind",
                "source_url",
                "relative_path",
                "download_error",
            ],
            dedupe_rows(self.document_rows, ("source_url", "relative_path")),
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

    def respect_rate_limit(self) -> None:
        elapsed = time.time() - self.last_request_at
        remaining = self.delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)


def cell_text(cells: list[Tag], index: int) -> str:
    if index >= len(cells):
        return ""
    return " ".join(cells[index].get_text(" ", strip=True).split())


def classify_uploaded_path(url: str) -> str:
    lower_url = url.lower()
    kinds = [
        "rulesindividualfile",
        "hindirulesindividualfile",
        "regulationindividualfile",
        "hindiregulationsindividualfile",
        "notificationindividualfile",
        "orderindividualfile",
        "circularindividualfile",
        "ordinanceindividualfile",
        "statuteindividualfile",
        "schemesindividualfile",
    ]
    for kind in kinds:
        if kind in lower_url:
            return kind
    return "uploaded_file"


def infer_language(text: str, href: str) -> str:
    lower_text = text.casefold()
    lower_href = href.casefold()
    if any(token in lower_text for token in ["हिं", "hindi"]) or "hindi" in lower_href or "_hin" in lower_href:
        return "hindi"
    return "english"


def first_non_empty(*values: object) -> str:
    for value in values:
        if isinstance(value, list):
            for item in value:
                if item:
                    return str(item)
        elif value:
            return str(value)
    return ""


def meta_values(meta_map: dict[str, list[str] | str], key: str) -> list[str]:
    value = meta_map.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def meta_first(meta_map: dict[str, list[str] | str], key: str) -> str:
    values = meta_values(meta_map, key)
    return values[0] if values else ""


def stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    return str(value)


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
        description=(
            "Scrape India Code browse pages and download Acts plus linked subordinate legislation. "
            "Use politely; this can take a long time for the full site."
        )
    )
    parser.add_argument(
        "--scope",
        choices=["central", "all", "states", "selected-states"],
        default="central",
        help="Which collections to scrape.",
    )
    parser.add_argument(
        "--state",
        action="append",
        default=[],
        help="State or UT collection name. Use multiple times with --scope selected-states.",
    )
    parser.add_argument(
        "--output-dir",
        default="indiacode_downloads",
        help="Directory where files and indexes will be written.",
    )
    parser.add_argument("--delay-seconds", type=float, default=1.0, help="Delay between HTTP requests.")
    parser.add_argument("--timeout-seconds", type=int, default=30, help="Per-request timeout.")
    parser.add_argument("--retries", type=int, default=3, help="Retries per request.")
    parser.add_argument("--overwrite", action="store_true", help="Re-download files even if metadata exists.")
    parser.add_argument("--max-acts", type=int, default=None, help="Stop after this many Acts.")
    parser.add_argument(
        "--max-collections",
        type=int,
        default=None,
        help="Limit the number of collections processed.",
    )
    parser.add_argument(
        "--max-documents-per-act",
        type=int,
        default=None,
        help="Download only the first N documents per Act. Useful for smoke tests.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scraper = IndiaCodeScraper(
        output_dir=Path(args.output_dir).resolve(),
        delay_seconds=args.delay_seconds,
        timeout_seconds=args.timeout_seconds,
        retries=args.retries,
        overwrite=args.overwrite,
        max_acts=args.max_acts,
        max_collections=args.max_collections,
        max_documents_per_act=args.max_documents_per_act,
    )
    scraper.run(scope=args.scope, state_names=args.state)


if __name__ == "__main__":
    main()
