"""Optional, source-linked research for a private personal dictionary.

Research only returns suggestions.  The caller decides which English facts and
Commons images to keep; this module never inserts an entry into the dictionary.
Wikipedia text and Commons media retain their source and license information.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "PersonalDictionary/0.1 (local desktop learning app; source-linked research)"
EN_API = "https://en.wikipedia.org/w/api.php"
ZH_API = "https://zh.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
MAX_RESPONSE_BYTES = 2_000_000
MAX_IMAGE_BYTES = 12_000_000


@dataclass(slots=True)
class Suggestion:
    title: str
    text: str
    source_url: str
    selected: bool = False


@dataclass(frozen=True, slots=True)
class ImageCandidate:
    title: str
    thumb_url: str
    image_url: str
    description_url: str
    attribution: str
    license: str
    license_url: str


@dataclass(slots=True)
class ResearchResult:
    title: str
    category: str
    subcategory: str
    source_url: str
    suggestions: list[Suggestion] = field(default_factory=list)
    images: list[ImageCandidate] = field(default_factory=list)
    error: str = ""


class ResearchError(Exception):
    """A remote lookup could not produce a trustworthy result."""


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_html(value: object, limit: int = 500, input_limit: int = 8000) -> str:
    if not isinstance(value, str):
        return ""
    parser = _PlainText()
    parser.feed(value[:input_limit])
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()[:limit]


def _get_json(endpoint: str, params: dict[str, str | int]) -> dict[str, Any]:
    url = endpoint + "?" + urlencode({"format": "json", "formatversion": 2, **params})
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=12) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 429:
            raise ResearchError("Wikipedia is receiving too many requests. Try again later.") from exc
        raise ResearchError("The research service is temporarily unavailable.") from exc
    except (OSError, TimeoutError) as exc:
        raise ResearchError("Could not reach Wikipedia or Wikimedia Commons.") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ResearchError("The research response was unexpectedly large.")
    try:
        data = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchError("The research service returned unreadable data.") from exc
    if not isinstance(data, dict) or "error" in data:
        raise ResearchError("The research service could not answer this request.")
    return data


def _search(endpoint: str, phrase: str) -> list[dict[str, Any]]:
    data = _get_json(endpoint, {
        "action": "query", "list": "search", "srsearch": phrase,
        "srnamespace": 0, "srlimit": 20,
    })
    results = data.get("query", {}).get("search", [])
    return [item for item in results if isinstance(item, dict) and item.get("title")]


def _normal(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def _title_similarity(title: str, phrase: str) -> float:
    title_key = _normal(title)
    phrase_key = _normal(phrase)
    if not title_key or not phrase_key:
        return 0.0
    if title_key == phrase_key:
        return 1.0
    if title_key in phrase_key:
        return 0.96
    if phrase_key in title_key:
        return 0.83
    size = len(title_key)
    if len(phrase_key) > size:
        return max(SequenceMatcher(None, title_key, phrase_key[start:start + size]).ratio()
                   for start in range(len(phrase_key) - size + 1))
    return SequenceMatcher(None, title_key, phrase_key).ratio()


def _search_phrases(raw: str) -> list[str]:
    """Try the likely subject clause, then the complete spoken/written note."""
    first = re.split(r"[,，。;；:：\n]", raw, maxsplit=1)[0].strip()
    first = re.sub(
        r"^(?:我(?:今天|最近)?(?:学了|学习了|了解了|知道了|听说了)?|"
        r"今天(?:学了|学习了|了解到)|关于|请介绍|给我讲讲|"
        r"I (?:learned|read|heard) about|Tell me about|What is)\s*",
        "", first, flags=re.IGNORECASE,
    ).strip()
    if re.search(r"[\u3400-\u9fff]", first):
        # Offline speech recognition usually supplies no punctuation. Treat a
        # following explanation as context, not as part of the named subject.
        first = re.split(r"就是|属于|指的是|是|关于", first, maxsplit=1)[0].strip()
        first = re.sub(r"^(?:一个叫|一位叫|一种叫|一个|一位|一种|一只|一条|一颗|一本|个|叫做|名叫)\s*",
                       "", first).strip()
    # The subject clause comes first: context such as "Greek god" can closely
    # resemble a broad article title and otherwise displace the actual name.
    phrases = [first, raw] if first else [raw]
    return list(dict.fromkeys(phrase[:160] for phrase in phrases if phrase.strip()))


def _find_title(raw: str, endpoint: str) -> str:
    for phrase in _search_phrases(raw):
        results = _search(endpoint, phrase)
        scored = [(_title_similarity(str(item["title"]), phrase), -index, str(item["title"]))
                  for index, item in enumerate(results)]
        if scored:
            score, _index, title = max(scored)
            if score >= 0.68:
                return title
    raise ResearchError("No close Wikipedia article was found. Try a more specific name.")


def _english_link(zh_title: str) -> str:
    data = _get_json(ZH_API, {
        "action": "query", "prop": "langlinks|pageprops", "titles": zh_title,
        "redirects": 1, "lllang": "en", "llprop": "url",
    })
    pages = data.get("query", {}).get("pages", [])
    if not pages or not isinstance(pages[0], dict):
        raise ResearchError("The Chinese article could not be opened.")
    page = pages[0]
    links = page.get("langlinks", [])
    for link in links:
        if link.get("lang") == "en" and link.get("title"):
            return str(link["title"])

    # Some articles expose an item but no language link in the page response.
    item = page.get("pageprops", {}).get("wikibase_item")
    if isinstance(item, str) and re.fullmatch(r"Q[1-9]\d*", item):
        entity_data = _get_json(WIKIDATA_API, {
            "action": "wbgetentities", "ids": item, "props": "sitelinks",
            "sitefilter": "enwiki",
        })
        title = (entity_data.get("entities", {}).get(item, {})
                 .get("sitelinks", {}).get("enwiki", {}).get("title"))
        if isinstance(title, str) and title:
            return title
    raise ResearchError("This topic has no linked English Wikipedia article.")


def _article(title: str) -> dict[str, Any]:
    params: dict[str, str | int] = {
        "action": "query", "prop": "extracts|categories|pageterms|pageprops|info",
        "titles": title, "redirects": 1, "explaintext": 1,
        "exsectionformat": "wiki",
        "cllimit": 100, "wbptterms": "description", "inprop": "url",
    }
    try:
        data = _get_json(EN_API, params)
    except ResearchError as exc:
        if str(exc) != "The research response was unexpectedly large.":
            raise
        # Very long articles still yield a bounded lead instead of losing the
        # whole research result to a response-size guard.
        data = _get_json(EN_API, {**params, "exintro": 1})
    pages = data.get("query", {}).get("pages", [])
    if not pages or not isinstance(pages[0], dict) or pages[0].get("missing"):
        raise ResearchError("The English article is unavailable.")
    page = pages[0]
    if "disambiguation" in page.get("pageprops", {}):
        raise ResearchError("This name has several meanings. Add a few words to specify the topic.")
    return page


def _classify(page: dict[str, Any]) -> tuple[str, str]:
    description = " ".join(page.get("terms", {}).get("description", []))
    categories = " ".join(item.get("title", "") for item in page.get("categories", []))
    text = (description + " " + categories + " " + str(page.get("extract", ""))[:220]).casefold()
    chapter_patterns: list[tuple[str, str, str]] = [
        ("Myths & Beliefs", r"mytholog|deit(?:y|ies)|goddess?|folklore|religion|legend|underworld|cosmogon", "Mythology & Belief"),
        ("Human Body & Health", r"anatom|physiolog|disease|medicine|medical|human body|organ|syndrome|health", "Body & Medicine"),
        ("Nature & Life", r"animal|plant|bird|mammal|reptile|insect|botan|zoolog|species|ecolog|fung|bacteri|biolog", "Living Things"),
        ("Earth & Space", r"astronom|planet|star|galax|spacecraft|geolog|volcano|mountain|ocean|earthquake|climat|geograph", "Earth & Universe"),
        ("Language & Literature", r"linguist|language|etymolog|grammar|literature|novel|poet|book|writing system", "Words & Works"),
        ("History & Society", r"histor|ancient civilization|archaeolog|politic|empire|war|dynast|societ|sociolog", "History & Society"),
        ("Science & Technology", r"physics|chemistr|mathematic|technology|computer|engineer|invention|scientific", "Science & Technology"),
        ("Arts & Culture", r"painting|sculptur|visual art|music|dance|film|architecture|theat|photograph", "Arts & Culture"),
        ("Everyday Life", r"food|cuisine|cooking|household|fashion|sport|hobby|craft", "Daily Life"),
        ("People & Places", r"births|deaths|biograph|person|city|town|country|region|people from", "People & Places"),
    ]
    for chapter, pattern, subcategory in chapter_patterns:
        if re.search(pattern, text):
            if chapter == "Myths & Beliefs":
                for culture in ("Greek", "Roman", "Norse", "Egyptian", "Hindu", "Chinese", "Japanese"):
                    if culture.casefold() in text:
                        return chapter, f"{culture} Mythology"
            if chapter == "Nature & Life":
                if re.search(r"animal|bird|mammal|reptile|insect|zoolog", text):
                    subcategory = "Animals"
                elif re.search(r"plant|botan|flora", text):
                    subcategory = "Plants"
            return chapter, subcategory
    return "Unsorted", "General"


def _suggestions(extract: str, source_url: str, exclude_text: str = "") -> list[Suggestion]:
    """Return bounded, source-worded facts from the lead and article sections.

    A QTextEdit HTML article may be passed as ``exclude_text``.  This removes
    previously selected sentences, even when they contain saved pen markup.
    The full extract is never copied into the local dictionary automatically.
    """
    saved = _normal(_plain_html(exclude_text, limit=120_000, input_limit=180_000))
    seen: set[str] = set()
    suggestions: list[Suggestion] = []
    section = "Overview"
    section_number = 0
    skipped_level = 0
    paragraphs: list[str] = []

    def add_paragraphs() -> None:
        nonlocal section_number
        if skipped_level:
            paragraphs.clear()
            return
        for paragraph in paragraphs:
            cleaned = re.sub(r"\s+", " ", paragraph).strip()
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"'(])", cleaned):
                sentence = sentence.strip()
                key = _normal(sentence)
                # Long lists and fragments are poor digestible choices; do not
                # trim them into claims that the source itself did not make.
                if not 35 <= len(sentence) <= 700 or key in seen or key in saved:
                    continue
                seen.add(key)
                section_number += 1
                suggestions.append(Suggestion(f"{section} · {section_number}", sentence, source_url))
                if len(suggestions) >= 15:
                    paragraphs.clear()
                    return
        paragraphs.clear()

    heading_pattern = re.compile(r"^(={2,6})\s*(.*?)\s*\1$")
    housekeeping = re.compile(
        r"^(?:notes?|references?|sources?|citations?|bibliography|further reading|"
        r"external links?|see also|footnotes?|works cited)$", re.IGNORECASE,
    )
    # Processing is bounded even for unusually large Wikipedia articles. The
    # HTTP layer separately caps the size of the received JSON response.
    bounded_extract = extract[:100_000]
    if len(extract) > len(bounded_extract):
        bounded_extract = bounded_extract.rsplit("\n", 1)[0]
    for line in bounded_extract.splitlines():
        if len(suggestions) >= 15:
            break
        match = heading_pattern.match(line.strip())
        if match:
            add_paragraphs()
            level = len(match.group(1))
            name = match.group(2).strip()
            if skipped_level and level > skipped_level:
                continue
            skipped_level = level if housekeeping.fullmatch(name) else 0
            section = name or "Overview"
            section_number = 0
        elif not line.strip():
            add_paragraphs()
        elif not skipped_level:
            paragraphs.append(line.strip())
    if len(suggestions) < 15:
        add_paragraphs()
    return suggestions


def _meta(metadata: dict[str, Any], name: str) -> str:
    value = metadata.get(name, {})
    return _plain_html(value.get("value", "") if isinstance(value, dict) else "")


def _free_license(metadata: dict[str, Any]) -> tuple[str, str] | None:
    short = _meta(metadata, "LicenseShortName")
    code = _meta(metadata, "License").casefold()
    is_free = (code == "pd" or code == "cc0" or code.startswith("cc-by")
               or code.startswith("gfdl") or short.casefold() in {"public domain", "cc0"})
    if not is_free or not short:
        return None
    raw_url = metadata.get("LicenseUrl", {})
    license_url = raw_url.get("value", "") if isinstance(raw_url, dict) else ""
    if not isinstance(license_url, str) or not license_url.startswith("https://"):
        license_url = "https://commons.wikimedia.org/wiki/Commons:Licensing"
    return short, license_url


def _image_search_query(title: str, category: str, subcategory: str) -> str:
    if category == "Myths & Beliefs" and subcategory.endswith("Mythology"):
        return f"{title} {subcategory.lower()}"
    return title


def _image_score(file_title: str, description: str, categories: str,
                 topic_title: str, chapter: str) -> int:
    filename = file_title.removeprefix("File:").casefold()
    topic = topic_title.casefold()
    surrounding = (description + " " + categories).casefold()
    tokens = [word for word in re.findall(r"[\w'-]+", topic) if len(word) > 2]
    if not tokens or not any(token in filename or token in surrounding[:500] for token in tokens):
        return -1
    score = 10 if topic in filename else 0
    score += 4 if topic in surrounding[:500] else 0
    score += sum(2 for token in tokens if token in filename)
    if chapter == "Myths & Beliefs":
        if any(term in filename for term in ("mount ", "volcano", "ship ", "antarctic", "aircraft")):
            return -1
        if "mytholog" in surrounding or "mytholog" in filename:
            score += 3
    return score


def _images(title: str, category: str, subcategory: str) -> list[ImageCandidate]:
    query = _image_search_query(title, category, subcategory)
    data = _get_json(COMMONS_API, {
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": 30, "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata", "iiurlwidth": 800,
    })
    pages = data.get("query", {}).get("pages", [])
    ranked: list[tuple[int, int, ImageCandidate]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        infos = page.get("imageinfo", [])
        if not infos or not isinstance(infos[0], dict):
            continue
        info = infos[0]
        if info.get("mime") not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        metadata = info.get("extmetadata", {})
        license_info = _free_license(metadata) if isinstance(metadata, dict) else None
        if license_info is None:
            continue
        image_url = info.get("thumburl") or info.get("url")
        page_url = info.get("descriptionurl")
        if not isinstance(image_url, str) or not isinstance(page_url, str):
            continue
        if urlparse(image_url).scheme != "https" or urlparse(page_url).scheme != "https":
            continue
        file_title = str(page.get("title", ""))
        description = _meta(metadata, "ImageDescription")
        categories = _meta(metadata, "Categories")
        score = _image_score(file_title, description, categories, title, category)
        if score < 0:
            continue
        image = ImageCandidate(
            title=file_title.removeprefix("File:").replace("_", " "),
            thumb_url=image_url,
            image_url=image_url,
            description_url=page_url,
            attribution=_meta(metadata, "Artist") or _meta(metadata, "Credit") or "See file page",
            license=license_info[0], license_url=license_info[1],
        )
        ranked.append((score, -int(page.get("index", 999)), image))
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:4]]


def research_topic(raw_input: str, *, exclude_text: str = "") -> ResearchResult:
    """Find English facts and freely licensed image choices for a user topic.

    Failures are returned in ``error`` so a network outage cannot remove or
    replace the user's own draft. No suggestion is selected automatically.
    """
    raw = re.sub(r"\s+", " ", raw_input).strip()
    if not raw:
        return ResearchResult("", "Unsorted", "General", "", error="Enter a topic first.")
    try:
        if re.search(r"[\u3400-\u9fff]", raw):
            title = _english_link(_find_title(raw, ZH_API))
        else:
            title = _find_title(raw, EN_API)
        page = _article(title)
        title = str(page.get("title", title))
        source_url = str(page.get("fullurl") or
                         "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"))
        category, subcategory = _classify(page)
        result = ResearchResult(title, category, subcategory, source_url,
                                _suggestions(str(page.get("extract", "")), source_url,
                                             exclude_text))
        if not result.suggestions:
            result.error = "No new English facts were found in this article."
        try:
            result.images = _images(title, category, subcategory)
        except (ResearchError, OSError, ValueError, TypeError):
            # Text suggestions remain useful when Commons is unavailable.
            pass
        return result
    except (ResearchError, OSError, ValueError, TypeError, KeyError) as exc:
        return ResearchResult(raw, "Unsorted", "General", "", error=str(exc))


def download_image(candidate: ImageCandidate, destination_dir: str | Path) -> Path:
    """Download one chosen Wikimedia image using a bounded, atomic file write."""
    parsed = urlparse(candidate.image_url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "upload.wikimedia.org", "thumb.wikimedia.org",
    }:
        raise ValueError("The image URL is not a Wikimedia upload URL.")
    extension = Path(candidate.title).suffix.casefold()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("The image format is not supported.")
    basename = re.sub(r"[^\w-]+", "-", Path(candidate.title).stem, flags=re.UNICODE)
    basename = basename.strip("-_")[:65] or "image"
    digest = sha256(candidate.description_url.encode("utf-8")).hexdigest()[:10]
    folder = Path(destination_dir)
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"{basename}-{digest}{extension}"
    request = Request(candidate.image_url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_IMAGE_BYTES:
                raise ValueError("The image is too large to save.")
            payload = response.read(MAX_IMAGE_BYTES + 1)
    except (OSError, TimeoutError) as exc:
        raise ResearchError("Could not download the selected image.") from exc
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("The image is too large to save.")
    signatures = {
        ".jpg": payload.startswith(b"\xff\xd8\xff"),
        ".jpeg": payload.startswith(b"\xff\xd8\xff"),
        ".png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        ".webp": payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
    }
    if not signatures[extension]:
        raise ValueError("The downloaded file is not the expected image format.")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".image-", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
