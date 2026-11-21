import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.utils.validators import validate_url_security, SSRFValidationError, InvalidURLError

logger = logging.getLogger(__name__)


@dataclass
class ExtractedWebsiteData:
    """Clean structured data harvested from target website."""
    requested_url: str
    final_url: str
    status_code: int
    title: str = ""
    meta_description: str = ""
    meta_keywords: List[str] = field(default_factory=list)
    og_data: Dict[str, str] = field(default_factory=dict)
    headings: Dict[str, List[str]] = field(default_factory=dict)
    nav_links: List[str] = field(default_factory=list)
    clean_text: str = ""
    raw_text_length: int = 0


class WebsiteExtractorError(Exception):
    """Base exception for extraction failures."""
    pass


class WebsiteUnreachableError(WebsiteExtractorError):
    """Target website was unreachable, timed out, or returned a connection error."""
    pass


class WebsiteContentEmptyError(WebsiteExtractorError):
    """Target website returned empty or unparseable HTML."""
    pass


class WebsiteExtractor:
    """
    Robust asynchronous HTML fetcher and sanitizer.
    Includes redirect-level SSRF verification, DOM cleansing,
    meta intelligence gathering, and token-conscious text distillation.
    """

    def __init__(
        self,
        timeout: float = settings.REQUEST_TIMEOUT_SECONDS,
        max_redirects: int = settings.MAX_REDIRECTS,
        max_chars: int = settings.MAX_CONTENT_CHARS,
        user_agent: str = settings.USER_AGENT,
        block_private: bool = settings.BLOCK_PRIVATE_NETWORKS,
    ):
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.max_chars = max_chars
        self.user_agent = user_agent
        self.block_private = block_private

    async def fetch_and_extract(self, url: str) -> ExtractedWebsiteData:
        """
        Executes safe HTTP GET, validates redirects, cleans HTML,
        and extracts key semantic business signals.
        """
        validated_url, _ = validate_url_security(url, block_private=self.block_private)

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        }

        current_url = validated_url
        final_response: Optional[httpx.Response] = None
        redirect_count = 0

        async with httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(self.timeout, connect=5.0),
            follow_redirects=False,
            verify=False  # Allow sites with self-signed/expired certs while maintaining SSRF guard
        ) as client:
            while redirect_count <= self.max_redirects:
                try:
                    response = await client.get(current_url)
                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                    raise WebsiteUnreachableError(f"Connection to '{current_url}' timed out: {str(e)}")
                except (httpx.ConnectError, httpx.NetworkError) as e:
                    raise WebsiteUnreachableError(f"Network error connecting to '{current_url}': {str(e)}")
                except Exception as e:
                    raise WebsiteUnreachableError(f"Unexpected error requesting '{current_url}': {str(e)}")

                if response.is_redirect:
                    redirect_location = response.headers.get("Location")
                    if not redirect_location:
                        break
                    # Re-validate redirect target to strictly prevent SSRF via open redirects
                    redirect_url = str(response.url.join(redirect_location))
                    validated_redirect, _ = validate_url_security(
                        redirect_url, block_private=self.block_private
                    )
                    current_url = validated_redirect
                    redirect_count += 1
                    continue
                else:
                    final_response = response
                    break

        if not final_response:
            raise WebsiteUnreachableError(f"Too many redirects ({redirect_count}) for {url}")

        if final_response.status_code >= 400:
            raise WebsiteUnreachableError(
                f"Website responded with HTTP status code {final_response.status_code}"
            )

        html_content = final_response.text
        if not html_content or len(html_content.strip()) < 50:
            raise WebsiteContentEmptyError("Website returned empty or non-informative HTML.")

        return self._parse_html(
            requested_url=url,
            final_url=str(final_response.url),
            status_code=final_response.status_code,
            html=html_content
        )

    def _parse_html(
        self, requested_url: str, final_url: str, status_code: int, html: str
    ) -> ExtractedWebsiteData:
        """Parses HTML DOM, stripping scripts, styles, boilerplate, and gathering metadata."""
        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract Title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # 2. Extract Meta Description & Keywords
        meta_desc = ""
        meta_keywords: List[str] = []
        og_data: Dict[str, str] = {}

        for meta in soup.find_all("meta"):
            name = meta.get("name", "").lower()
            prop = meta.get("property", "").lower()
            content = meta.get("content", "").strip()
            if not content:
                continue

            if name == "description":
                meta_desc = content
            elif name == "keywords":
                meta_keywords = [k.strip() for k in content.split(",") if k.strip()]
            elif prop.startswith("og:"):
                og_key = prop[3:]
                og_data[og_key] = content
                if og_key == "title" and not title:
                    title = content
                elif og_key == "description" and not meta_desc:
                    meta_desc = content

        # 3. Extract Headings (h1, h2, h3)
        headings: Dict[str, List[str]] = {"h1": [], "h2": [], "h3": []}
        for tag in ["h1", "h2", "h3"]:
            for h in soup.find_all(tag):
                text = h.get_text(strip=True)
                if text and len(text) > 3 and text not in headings[tag]:
                    headings[tag].append(text[:150])

        # 4. Extract Navigation / Service links
        nav_links: List[str] = []
        for nav in soup.find_all(["nav", "header", "menu"]):
            for a in nav.find_all("a", href=True):
                anchor_text = a.get_text(strip=True)
                if anchor_text and 3 < len(anchor_text) < 40 and anchor_text not in nav_links:
                    nav_links.append(anchor_text)

        # 5. Clean DOM: Remove non-informative elements to optimize token usage
        for element in soup.find_all([
            "script", "style", "noscript", "svg", "iframe",
            "footer", "nav", "aside", "form"
        ]):
            element.decompose()

        # Target main content area if available
        main_container = soup.find(["main", "article", "div#content", "div#main", "section"])
        content_soup = main_container if main_container else soup

        # Extract text lines
        raw_text = content_soup.get_text(separator="\n")
        raw_length = len(raw_text)

        # Normalize whitespace
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        # Remove consecutive duplicate lines
        deduped_lines: List[str] = []
        for line in lines:
            if not deduped_lines or deduped_lines[-1] != line:
                deduped_lines.append(line)

        clean_body = "\n".join(deduped_lines)

        if not clean_body or len(clean_body.strip()) < 20:
            raise WebsiteContentEmptyError("Website returned empty or non-informative content.")

        # Truncate clean text to token budget without splitting words
        if len(clean_body) > self.max_chars:
            trimmed = clean_body[:self.max_chars]
            last_newline = trimmed.rfind("\n")
            if last_newline > self.max_chars * 0.8:
                clean_body = trimmed[:last_newline] + "\n...[truncated for token efficiency]"
            else:
                clean_body = trimmed + "...[truncated for token efficiency]"

        return ExtractedWebsiteData(
            requested_url=requested_url,
            final_url=final_url,
            status_code=status_code,
            title=title,
            meta_description=meta_desc,
            meta_keywords=meta_keywords[:10],
            og_data=og_data,
            headings=headings,
            nav_links=nav_links[:15],
            clean_text=clean_body,
            raw_text_length=raw_length,
        )
