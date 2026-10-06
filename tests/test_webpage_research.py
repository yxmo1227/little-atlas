"""Web-page import is source-faithful and never requires a ChatGPT token."""

from __future__ import annotations

from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from dictionary_app import webpage_research as pages


ARTICLE = b"""<!doctype html><html><head><title>Saline | Example</title>
<meta property="og:title" content="Saline: Uses and Composition"></head><body>
<nav><p>Sign in to discover every article on the website today.</p></nav>
<main><article><h1>Saline</h1>
<p>Saline is a mixture of sodium chloride and water, commonly used in medical care.</p>
<h2>Uses</h2><p>Clinicians may use saline to clean wounds and to replace fluids in some circumstances.</p>
<script><p>This fabricated sentence must never be imported from a script.</p></script>
</article></main><footer><p>Subscribe for the latest news and services from this site.</p></footer>
</body></html>"""


class _Response:
    def __init__(self, url: str, payload: bytes = ARTICLE,
                 content_type: str = "text/html; charset=utf-8",
                 content_length: str | None = None):
        self.url = url
        self.stream = BytesIO(payload)
        self.headers = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()

    def geturl(self) -> str:
        return self.url

    def read(self, size: int) -> bytes:
        return self.stream.read(size)


class WebpageResearchTests(unittest.TestCase):
    def test_wikipedia_style_root_classes_do_not_hide_article(self) -> None:
        url = "https://en.wikipedia.org/wiki/Erebus"
        html = b"""<!doctype html><html class="vector-feature-main-menu-enabled
            vector-feature-language-in-header-enabled"><head>
            <title>Erebus - Wikipedia</title></head><body>
            <header class="mw-body-header"><h1>Erebus</h1></header>
            <main><div class="mw-parser-output">
            <p>In Greek mythology, Erebus is the personification of darkness.</p>
            <p>In Hesiod's Theogony, he is the offspring of Chaos, and the father of Aether and Hemera.</p>
            </div></main></body></html>"""
        with patch.object(pages, "_check_dns"), patch.object(
            pages, "_open_request", return_value=_Response(url, html)
        ):
            result = pages.research_webpage(url)
        self.assertEqual(result.error, "")
        self.assertEqual(result.title, "Erebus")
        self.assertGreaterEqual(len(result.suggestions), 2)
        self.assertTrue(all(item.source_url == url for item in result.suggestions))

    def test_imports_article_sentences_with_real_source(self) -> None:
        url = "https://example.org/articles/saline"
        with patch.object(pages, "_check_dns"), patch.object(
            pages, "_open_request", return_value=_Response(url)
        ) as opener:
            result = pages.research_webpage(url)
        self.assertEqual(result.error, "")
        self.assertEqual(result.title, "Saline")
        self.assertEqual(result.source_url, url)
        self.assertEqual(len(result.suggestions), 2)
        self.assertTrue(all(item.source_url == url and not item.selected
                            for item in result.suggestions))
        self.assertIn("sodium chloride and water", result.suggestions[0].text)
        self.assertIn("clean wounds", result.suggestions[1].text)
        self.assertFalse(any("Subscribe" in item.text or "fabricated" in item.text
                             for item in result.suggestions))
        self.assertEqual(opener.call_count, 1)

    def test_rejects_unsafe_or_search_result_urls_before_network(self) -> None:
        unsafe = [
            "http://example.org/article", "file:///tmp/article.html",
            "https://localhost/article", "https://127.0.0.1/article",
            "https://192.168.1.1/article", "https://[::1]/article",
            "https://user:password@example.org/article",
            "https://example.org:8443/article", "https://intranet/article",
            "https://www.google.com/search?q=saline",
            "https://www.google.co.uk/url?sa=U&url=https://example.org/",
        ]
        with patch.object(pages, "_fetch_html") as fetch:
            for url in unsafe:
                with self.subTest(url=url):
                    self.assertTrue(pages.research_webpage(url).error)
        fetch.assert_not_called()

    def test_dns_private_address_is_rejected_before_fetch(self) -> None:
        with patch.object(pages.socket, "getaddrinfo", return_value=[
            (2, 1, 6, "", ("10.1.2.3", 443))
        ]), patch.object(pages, "_open_request") as opener:
            result = pages.research_webpage("https://example.org/article")
        self.assertIn("Local network", result.error)
        opener.assert_not_called()

    def test_rejects_oversized_and_non_html_responses(self) -> None:
        url = "https://example.org/article"
        for response in (
            _Response(url, content_length=str(pages.MAX_HTML_BYTES + 1)),
            _Response(url, payload=b"x" * (pages.MAX_HTML_BYTES + 1)),
            _Response(url, content_type="application/pdf"),
        ):
            with self.subTest(response=response.headers), patch.object(pages, "_check_dns"), \
                    patch.object(pages, "_open_request", return_value=response):
                self.assertTrue(pages.research_webpage(url).error)

    def test_rejects_redirect_to_local_address(self) -> None:
        url = "https://example.org/article"
        redirect = HTTPError(url, 302, "Moved", {"Location": "https://127.0.0.1/secret"}, None)
        with patch.object(pages, "_check_dns"), patch.object(
            pages, "_open_request", side_effect=redirect
        ) as opener:
            result = pages.research_webpage(url)
        self.assertIn("Local network", result.error)
        self.assertEqual(opener.call_count, 1)

    def test_safe_redirect_uses_destination_as_source(self) -> None:
        start = "https://example.org/article"
        destination = "https://example.org/articles/saline"
        redirect = HTTPError(start, 302, "Moved", {"Location": "/articles/saline"}, None)
        with patch.object(pages, "_check_dns"), patch.object(
            pages, "_open_request", side_effect=[redirect, _Response(destination)]
        ) as opener:
            result = pages.research_webpage(start)
        self.assertEqual(result.error, "")
        self.assertEqual(result.source_url, destination)
        self.assertTrue(all(item.source_url == destination for item in result.suggestions))
        self.assertEqual(opener.call_count, 2)

    def test_no_english_paragraphs_is_an_error(self) -> None:
        url = "https://example.org/article"
        html = "<html><title>Example article</title><article><p>这是一段完整的中文内容，没有英文资料可以供用户选择。</p></article></html>"
        with patch.object(pages, "_check_dns"), patch.object(
            pages, "_open_request", return_value=_Response(url, html.encode("utf-8"))
        ):
            result = pages.research_webpage(url)
        self.assertIn("no usable English", result.error)
        self.assertEqual(result.suggestions, [])


if __name__ == "__main__":
    unittest.main()
