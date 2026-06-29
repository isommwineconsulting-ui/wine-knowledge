"""Crawl a web page (optionally its same-domain links) and find PDF links.

Polite by default: identifies itself via User-Agent, honours robots.txt, and
sleeps between requests.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from .config import get_settings


@dataclass(frozen=True)
class PdfLink:
    pdf_url: str
    source_page_url: str
    link_text: str


def _looks_like_pdf(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf")


def _same_domain(a: str, b: str) -> bool:
    return urlparse(a).netloc == urlparse(b).netloc


def parse_links(html: str, page_url: str) -> tuple[list[PdfLink], list[str]]:
    """Pure HTML parse: return (pdf_links, other_same-or-cross-domain hrefs).

    PDF links are returned as :class:`PdfLink`; non-PDF hrefs are returned as
    absolute, fragment-stripped URLs for the caller to filter/queue.
    """
    soup = BeautifulSoup(html, "html.parser")
    pdfs: list[PdfLink] = []
    others: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor["href"].strip())
        href, _ = urldefrag(href)
        if _looks_like_pdf(href):
            pdfs.append(
                PdfLink(
                    pdf_url=href,
                    source_page_url=page_url,
                    link_text=anchor.get_text(strip=True),
                )
            )
        else:
            others.append(href)
    return pdfs, others


class Scraper:
    """Finds PDF links starting from a seed URL."""

    def __init__(self, respect_robots: bool = True) -> None:
        self.settings = get_settings()
        self.respect_robots = respect_robots
        self._client = httpx.Client(
            headers={"User-Agent": self.settings.user_agent},
            follow_redirects=True,
            timeout=30.0,
        )
        self._robots: dict[str, RobotFileParser] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Scraper":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._robots.get(base)
        if rp is None:
            rp = RobotFileParser()
            rp.set_url(urljoin(base, "/robots.txt"))
            try:
                rp.read()
            except Exception:
                # If robots.txt cannot be read, default to allowing.
                rp = RobotFileParser()
                rp.parse([])
            self._robots[base] = rp
        try:
            return rp.can_fetch(self.settings.user_agent, url)
        except Exception:
            return True

    def _get_html(self, url: str) -> str | None:
        if not self._allowed(url):
            return None
        try:
            resp = self._client.get(url)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        if "text/html" not in resp.headers.get("content-type", ""):
            return None
        return resp.text

    def find_pdfs(self, seed_url: str, crawl_depth: int = 0) -> list[PdfLink]:
        """Return de-duplicated PDF links reachable from ``seed_url``.

        crawl_depth=0 scans only the seed page. Higher values follow
        same-domain HTML links up to that depth.
        """
        seen_pages: set[str] = set()
        found: dict[str, PdfLink] = {}
        # queue of (url, depth)
        queue: list[tuple[str, int]] = [(seed_url, 0)]

        while queue:
            url, depth = queue.pop(0)
            url, _ = urldefrag(url)
            if url in seen_pages:
                continue
            seen_pages.add(url)

            html = self._get_html(url)
            time.sleep(self.settings.request_delay_seconds)
            if html is None:
                continue

            pdfs, others = parse_links(html, url)
            for pdf in pdfs:
                found.setdefault(pdf.pdf_url, pdf)
            if depth < crawl_depth:
                for href in others:
                    if _same_domain(seed_url, href) and href not in seen_pages:
                        queue.append((href, depth + 1))

        return list(found.values())
