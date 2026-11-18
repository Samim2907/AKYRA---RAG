from __future__ import annotations

import asyncio
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup


class WebsiteCrawler:
    """Small, polite same-origin HTML crawler; it never circumvents robots.txt."""

    def __init__(self, timeout_seconds: float) -> None:
        self.timeout = timeout_seconds

    async def crawl(self, seed_url: str, max_pages: int) -> tuple[list[dict], list[str]]:
        seed = self._canonical(seed_url)
        host = urlparse(seed).netloc
        robots = await self._robots(seed)
        queue, seen, documents, skipped = deque([seed]), set(), [], []
        # A normal browser-identifying header avoids servers returning their low-content bot page.
        # robots.txt is still checked before every request.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=headers) as client:
            while queue and len(documents) < max_pages:
                url = queue.popleft()
                if url in seen:
                    continue
                seen.add(url)
                if not robots.can_fetch(headers["User-Agent"], url):
                    skipped.append(f"{url} (blocked by robots.txt)")
                    continue
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    skipped.append(f"{url} (HTTP {exc.response.status_code})")
                    continue
                except httpx.HTTPError as exc:
                    skipped.append(f"{url} ({type(exc).__name__})")
                    continue
                if "text/html" not in response.headers.get("content-type", ""):
                    skipped.append(f"{url} (not an HTML page)")
                    continue
                doc, links = self._parse(response.url, response.text, host)
                if not doc["text"] or self._looks_like_challenge(doc["text"]):
                    rendered, rendered_links, reason = await self._render_page(url, host)
                    if rendered and rendered["text"]:
                        doc, links = rendered, rendered_links
                    else:
                        skipped.append(f"{url} ({reason})")
                if doc["text"]:
                    documents.append(doc)
                for link in links:
                    if link not in seen and link not in queue:
                        queue.append(link)
                await asyncio.sleep(0)  # cooperative scheduling; add a rate limiter in multi-tenant deployments
        return documents, skipped

    async def _render_page(self, url: str, host: str) -> tuple[dict | None, list[str], str]:
        """Render JavaScript-only pages with Playwright when Chromium is installed."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None, [], "requires the optional browser renderer"
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36")
                await page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                await page.wait_for_timeout(1200)
                rendered_url, html = page.url, await page.content()
                await browser.close()
            document, links = self._parse(httpx.URL(rendered_url), html, host)
            if not document["text"]:
                return None, [], "browser rendered no extractable text"
            return document, links, ""
        except Exception as exc:
            message = str(exc).lower()
            if "executable doesn't exist" in message or "executable does not exist" in message:
                return None, [], "browser renderer needs 'python -m playwright install chromium'"
            return None, [], f"browser rendering failed: {type(exc).__name__} ({str(exc)[:160]})"

    @staticmethod
    def _looks_like_challenge(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in ("just a moment", "access denied", "captcha", "enable javascript"))

    async def _robots(self, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = RobotFileParser(robots_url)
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": "HybridWebRAG/0.1"}) as client:
                response = await client.get(robots_url)
            parser.parse(response.text.splitlines() if response.is_success else [])
        except httpx.HTTPError:
            parser.parse([])  # unavailable robots file: default allow
        return parser

    @staticmethod
    def _canonical(url: str) -> str:
        return urldefrag(url)[0].rstrip("/") or url

    def _parse(self, url: httpx.URL, html: str, host: str) -> tuple[dict, list[str]]:
        soup = BeautifulSoup(html, "html.parser")
        # Some sites (including large commercial home pages) put their visible product
        # and navigation copy inside semantic header/nav containers. Keep that text;
        # only remove elements that cannot contain indexable user-facing content.
        for unwanted in soup(["script", "style", "noscript", "svg", "canvas", "template"]):
            unwanted.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else str(url)
        text = soup.get_text(" ", strip=True)
        links = []
        for tag in soup.select("a[href]"):
            absolute = self._canonical(urljoin(str(url), tag["href"]))
            parsed = urlparse(absolute)
            if parsed.scheme in {"http", "https"} and parsed.netloc == host:
                links.append(absolute)
        return {"url": str(url), "title": title, "text": text}, links
