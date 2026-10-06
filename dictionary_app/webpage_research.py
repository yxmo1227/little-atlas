"""Import short, source-linked English excerpts from a user-chosen web page.

This path uses no AI service.  It reads only an explicit HTTPS article URL and
returns suggestions for the existing pen-selection UI; it never saves content.
"""

from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import re
import socket
import time
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .research import ResearchResult, Suggestion, USER_AGENT, _classify, _suggestions


MAX_HTML_BYTES = 1_000_000
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 10.0


class PageImportError(ValueError):
    """A page cannot safely provide reliable English excerpts."""


def _validate_url(raw: str) -> str:
    """Require a public HTTPS article URL, including on every redirect."""
    if not isinstance(raw, str) or not raw or len(raw) > 2048 or raw.strip() != raw:
        raise PageImportError("Paste a complete HTTPS article link.")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise PageImportError("The article link contains invalid characters.")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
        host = (parsed.hostname or "").rstrip(".").casefold()
    except ValueError as exc:
        raise PageImportError("The article link is invalid.") from exc
    if parsed.scheme.lower() != "https" or not host or not parsed.netloc:
        raise PageImportError("Paste an HTTPS article link.")
    if parsed.username is not None or parsed.password is not None:
        raise PageImportError("Article links cannot contain account details.")
    if port not in (None, 443):
        raise PageImportError("Only standard HTTPS article links are supported.")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".home.arpa")):
        raise PageImportError("Local network addresses cannot be imported.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or any(not label for label in host.split(".")):
            raise PageImportError("Local network addresses cannot be imported.")
    else:
        if not address.is_global:
            raise PageImportError("Local network addresses cannot be imported.")

    # A Google results/redirect page is not a cited article. The user needs to
    # open a result in Chrome and paste the destination page's link instead.
    labels = host.split(".")
    is_google = any(label == "google" and index < len(labels) - 1
                    for index, label in enumerate(labels))
    if is_google and parsed.path.rstrip("/").casefold() in {"/search", "/url"}:
        raise PageImportError("Open a Google result and paste the article's own link.")
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))


def _check_dns(host: str) -> None:
    """Refuse hostnames resolving to local/reserved addresses before each hop."""
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise PageImportError("Could not resolve the article website.") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global
                            for item in addresses):
        raise PageImportError("Local network addresses cannot be imported.")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def _open_request(request: Request, timeout: float):
    """Seam for mocked network tests; redirects are handled by _fetch_html."""
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _fetch_html(url: str) -> tuple[str, str]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    current = url
    for redirect_index in range(MAX_REDIRECTS + 1):
        current = _validate_url(current)
        _check_dns(urlsplit(current).hostname or "")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PageImportError("The article website took too long to respond.")
        request = Request(current, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
        })
        try:
            response = _open_request(request, remaining)
        except HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("Location")
                exc.close()
                if not location or redirect_index >= MAX_REDIRECTS:
                    raise PageImportError("The article redirected too many times.") from exc
                current = _validate_url(urljoin(current, location))
                continue
            raise PageImportError(f"The article website returned HTTP {exc.code}.") from exc
        except (OSError, TimeoutError) as exc:
            raise PageImportError("Could not open the article website.") from exc
        with response:
            final_url = _validate_url(response.geturl())
            if final_url != current:
                # A test double or alternate transport may redirect internally;
                # never treat that page as an approved source.
                raise PageImportError("The article redirected unexpectedly.")
            content_type = str(response.headers.get("Content-Type", "")).casefold()
            if not (content_type.startswith("text/html") or
                    content_type.startswith("application/xhtml+xml")):
                raise PageImportError("This link does not point to an HTML article.")
            length = response.headers.get("Content-Length")
            if length:
                try:
                    if int(length) > MAX_HTML_BYTES:
                        raise PageImportError("The article page is too large to import.")
                except ValueError as exc:
                    raise PageImportError("The article size is invalid.") from exc
            payload = response.read(MAX_HTML_BYTES + 1)
            if len(payload) > MAX_HTML_BYTES:
                raise PageImportError("The article page is too large to import.")
            charset_match = re.search(r"charset\s*=\s*([\w.-]+)", content_type)
            charset = charset_match.group(1) if charset_match else "utf-8"
            try:
                html = payload.decode(charset, errors="replace")
            except LookupError:
                html = payload.decode("utf-8", errors="replace")
            return html, current
    raise PageImportError("The article redirected too many times.")


_SKIP_TAGS = {"script", "style", "noscript", "template", "nav", "aside", "footer",
              "form", "button", "svg", "figcaption", "select"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
              "meta", "param", "source", "track", "wbr"}
_BOILERPLATE = re.compile(
    r"(?:^|[-_\s])(?:nav|sidebar|cookie|advert|share|social|promo|related|breadcrumb|"
    r"toc|menu|subscribe|comment|footer|header|newsletter)(?:$|[-_\s])",
    re.IGNORECASE,
)


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []
        self.paragraphs: list[tuple[int, str, str, int]] = []
        self.title_text: list[str] = []
        self.og_title = ""
        self.h1 = ""
        self.heading = "Overview"
        self._capture: list[str] | None = None
        self._capture_tag = ""
        self._paragraph: list[str] | None = None
        self._paragraph_context = 0
        self._paragraph_heading = "Overview"
        self._link_chars = 0

    def _ignored(self) -> bool:
        return bool(self.stack and self.stack[-1][1])

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        attributes = dict(attrs)
        if tag == "meta" and (attributes.get("property") or "").casefold() == "og:title":
            self.og_title = attributes.get("content") or ""
        if tag == "br" and self._paragraph is not None:
            self._paragraph.append(" ")
        # Site-wide classes often contain words such as "header" and "menu"
        # (Wikipedia's <html> class has both). Treat those as layout clues only
        # on small containers, never as a reason to discard the whole document.
        boilerplate_container = tag in {"div", "section", "ul", "ol", "table"}
        ignored = (self._ignored() or tag in _SKIP_TAGS or
                   attributes.get("aria-hidden") == "true" or
                   (boilerplate_container and bool(_BOILERPLATE.search(
                       (attributes.get("class") or "") + " " +
                       (attributes.get("id") or "")))))
        if tag not in _VOID_TAGS:
            self.stack.append((tag, ignored))
        if ignored:
            return
        if tag in {"title", "h1", "h2", "h3"}:
            self._capture = []
            self._capture_tag = tag
        elif tag == "p":
            self._paragraph = []
            self._link_chars = 0
            self._paragraph_context = (2 if any(item[0] == "article" for item in self.stack)
                                       else 1 if any(item[0] == "main" for item in self.stack)
                                       else 0)
            self._paragraph_heading = self.heading

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._ignored():
            return
        if self._capture is not None:
            self._capture.append(data)
        if self._paragraph is not None:
            self._paragraph.append(data)
            if any(tag == "a" for tag, _ignored in self.stack):
                self._link_chars += len(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._capture is not None and tag == self._capture_tag:
            value = re.sub(r"\s+", " ", "".join(self._capture)).strip()
            if tag == "title":
                self.title_text.append(value)
            elif tag == "h1" and not self.h1:
                self.h1 = value
            elif tag in {"h2", "h3"} and value:
                self.heading = value[:100]
            self._capture = None
            self._capture_tag = ""
        if tag == "p" and self._paragraph is not None:
            value = re.sub(r"\s+", " ", "".join(self._paragraph)).strip()
            if value:
                self.paragraphs.append((self._paragraph_context, self._paragraph_heading,
                                        value, self._link_chars))
            self._paragraph = None
        if tag in _VOID_TAGS:
            return
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def _is_english_paragraph(text: str, link_chars: int) -> bool:
    if len(text) < 40 or len(text) > 3000 or link_chars > len(text) * 0.55:
        return False
    words = re.findall(r"[A-Za-z]{2,}", text)
    letters = [char for char in text if char.isalpha()]
    english_letters = sum(char.isascii() and char.isalpha() for char in text)
    return len(words) >= 7 and bool(letters) and english_letters / len(letters) >= 0.75


def _english_title(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    return bool(letters) and sum(char.isascii() and char.isalpha()
                                 for char in letters) / len(letters) >= 0.6


def research_webpage(url: str) -> ResearchResult:
    """Return article wording from a pasted URL for the three-pen selection UI."""
    try:
        source = _validate_url(url)
        html, source = _fetch_html(source)
        parser = _ArticleParser()
        parser.feed(html)
        parser.close()
        titles = [parser.h1, parser.og_title, *parser.title_text]
        title = next((re.sub(r"\s+", " ", item).strip()[:140]
                      for item in titles if item and _english_title(item)), "")
        if not title:
            raise PageImportError("Could not find an English article title on this page.")
        paragraphs = [item for item in parser.paragraphs
                      if _is_english_paragraph(item[2], item[3])]
        if not paragraphs:
            raise PageImportError("This page has no usable English article paragraphs.")
        best_context = max(item[0] for item in paragraphs)
        paragraphs = [item for item in paragraphs if item[0] == best_context][:40]
        extract_parts: list[str] = []
        previous_heading = "Overview"
        for _, heading, text, _ in paragraphs:
            if heading != previous_heading and heading.casefold() not in {
                "references", "external links", "see also", "further reading", "notes",
            }:
                extract_parts.append(f"== {heading} ==")
                previous_heading = heading
            extract_parts.append(text)
            extract_parts.append("")
        extract = "\n".join(extract_parts)[:30_000]
        suggestions: list[Suggestion] = _suggestions(extract, source)
        if not suggestions:
            raise PageImportError("This page has no usable English fact sentences.")
        category, subcategory = _classify({"title": title, "extract": extract})
        return ResearchResult(title, category, subcategory, source, suggestions)
    except (PageImportError, OSError, TimeoutError, UnicodeError, ValueError) as exc:
        return ResearchResult("", "Unsorted", "General", "", error=str(exc))
