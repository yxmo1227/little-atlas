"""Focused research tests; remote services are represented by API-shaped data."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dictionary_app import research


def _licensed_image(title: str, index: int, *, mime: str = "image/png",
                    license_code: str = "cc-by-4.0", description: str = "Greek mythology") -> dict:
    return {
        "title": title, "index": index,
        "imageinfo": [{
            "mime": mime,
            "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/erebus.png",
            "url": "https://upload.wikimedia.org/wikipedia/commons/1/1a/erebus.png",
            "descriptionurl": "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
            "extmetadata": {
                "ImageDescription": {"value": description},
                "Categories": {"value": "Greek primordial deities"},
                "Artist": {"value": "<a href='https://example.test'>Example Artist</a>"},
                "LicenseShortName": {"value": "CC BY 4.0"},
                "License": {"value": license_code},
                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/4.0/"},
            },
        }],
    }


EREBUS_PAGE = {
    "title": "Erebus",
    "fullurl": "https://en.wikipedia.org/wiki/Erebus",
    "extract": (
        "In Greek mythology, Erebus is the personification of darkness. "
        "In Hesiod's Theogony, he is the offspring of Chaos. "
        "He is the father of Aether and Hemera by Nyx.\n"
        "The name is also used for the darkness of the underworld."
    ),
    "terms": {"description": ["primordial deity in Greek mythology"]},
    "categories": [
        {"title": "Category:Greek primordial deities"},
        {"title": "Category:Greek underworld"},
    ],
}

EREBUS_FULL_PAGE = {
    **EREBUS_PAGE,
    "extract": (
        "In Greek mythology, Erebus is the personification of darkness. "
        "In Hesiod's Theogony, he is the offspring of Chaos.\n\n"
        "== Etymology ==\n"
        "The ancient name is associated with darkness and gloom. "
        "The word also appears in accounts of the underworld.\n\n"
        "== Personification of darkness ==\n"
        "Erebus and Nyx are described as parents of Aether and Hemera. "
        "Other ancient genealogies offer different family relationships.\n\n"
        "== References ==\n"
        "This is a citation line that should not become a fact.\n\n"
        "=== Primary sources ===\n"
        "This is another citation line that should stay hidden."
    ),
}


class ResearchTests(unittest.TestCase):
    def test_unpunctuated_chinese_voice_note_extracts_named_subject(self) -> None:
        note = "我今天学了一个厄瑞波斯就是希腊神明"
        self.assertEqual(research._search_phrases(note)[0], "厄瑞波斯")
        self.assertEqual(research._search_phrases("厄瑞波斯，希腊神明")[0], "厄瑞波斯")
        self.assertEqual(research._search_phrases("Erebus, a Greek god")[0], "Erebus")

        searched: list[str] = []

        def api(endpoint: str, params: dict) -> dict:
            if endpoint == research.ZH_API and params.get("list") == "search":
                searched.append(params["srsearch"])
                return {"query": {"search": [
                    {"title": "希腊神话"}, {"title": "厄瑞玻斯"},
                ]}}
            if endpoint == research.ZH_API:
                return {"query": {"pages": [{"langlinks": [
                    {"lang": "en", "title": "Erebus"},
                ]}]}}
            if endpoint == research.EN_API:
                return {"query": {"pages": [EREBUS_PAGE]}}
            return {"query": {"pages": []}}

        with patch.object(research, "_get_json", side_effect=api):
            result = research.research_topic(note)
        self.assertEqual(searched, ["厄瑞波斯"])
        self.assertEqual(result.title, "Erebus")

    def test_follow_up_returns_new_section_facts_and_filters_saved_markup(self) -> None:
        def api(endpoint: str, params: dict) -> dict:
            if endpoint == research.EN_API and params.get("list") == "search":
                return {"query": {"search": [{"title": "Erebus"}]}}
            if endpoint == research.EN_API:
                self.assertEqual(params["exsectionformat"], "wiki")
                self.assertNotIn("exintro", params)
                return {"query": {"pages": [EREBUS_FULL_PAGE]}}
            return {"query": {"pages": []}}

        with patch.object(research, "_get_json", side_effect=api):
            first = research.research_topic("Erebus")
            saved_html = (
                "<html><body><p><span style='background-color:#fff09a'>"
                + first.suggestions[0].text + "</span></p>"
                "<p>" + first.suggestions[1].text + "</p></body></html>"
            )
            follow_up = research.research_topic("Erebus", exclude_text=saved_html)
        self.assertGreaterEqual(len(first.suggestions), 4)
        self.assertEqual(len(follow_up.suggestions), len(first.suggestions) - 2)
        self.assertNotIn(first.suggestions[0].text, [s.text for s in follow_up.suggestions])
        self.assertNotIn(first.suggestions[1].text, [s.text for s in follow_up.suggestions])
        self.assertTrue(any(s.title.startswith("Etymology") for s in follow_up.suggestions))
        self.assertTrue(any(s.title.startswith("Personification of darkness")
                            for s in follow_up.suggestions))
        self.assertFalse(any("citation line" in s.text for s in follow_up.suggestions))
        self.assertTrue(all(not s.selected and s.source_url == first.source_url
                            for s in follow_up.suggestions))

    def test_full_article_is_capped_and_oversized_response_falls_back_to_lead(self) -> None:
        many_sentences = "\n".join(
            f"This is sourced sentence number {index} about the topic."
            for index in range(30)
        )
        suggestions = research._suggestions(many_sentences, "https://en.wikipedia.org/wiki/Topic")
        self.assertEqual(len(suggestions), 15)
        self.assertEqual(suggestions[0].title, "Overview · 1")

        calls: list[dict] = []

        def api(_endpoint: str, params: dict) -> dict:
            calls.append(params)
            if len(calls) == 1:
                raise research.ResearchError("The research response was unexpectedly large.")
            return {"query": {"pages": [EREBUS_PAGE]}}

        with patch.object(research, "_get_json", side_effect=api):
            article = research._article("Erebus")
        self.assertEqual(article["title"], "Erebus")
        self.assertEqual(calls[1]["exintro"], 1)

    def test_chinese_near_translation_uses_english_article_and_relevant_free_image(self) -> None:
        def api(endpoint: str, params: dict) -> dict:
            if endpoint == research.ZH_API and params.get("list") == "search":
                return {"query": {"search": [
                    {"title": "佛波斯"}, {"title": "希腊神话"},
                    {"title": "厄瑞克透斯"},
                    {"title": "厄瑞玻斯"},
                ]}}
            if endpoint == research.ZH_API and params.get("prop") == "langlinks|pageprops":
                self.assertEqual(params["titles"], "厄瑞玻斯")
                return {"query": {"pages": [{"title": "厄瑞玻斯", "langlinks": [
                    {"lang": "en", "title": "Erebus"},
                ]}]}}
            if endpoint == research.EN_API and params.get("prop"):
                return {"query": {"pages": [EREBUS_PAGE]}}
            if endpoint == research.COMMONS_API:
                self.assertEqual(params["gsrsearch"], "Erebus greek mythology")
                return {"query": {"pages": [
                    _licensed_image("File:FT nyx+erebus.png", 2),
                    _licensed_image("File:Mount Erebus volcano.png", 1),
                    _licensed_image("File:Erebus mystery.png", 3, license_code="all-rights-reserved"),
                    _licensed_image("File:Erebus recording.ogg", 4, mime="audio/ogg"),
                ]}}
            self.fail(f"Unexpected API call: {endpoint} {params}")

        with patch.object(research, "_get_json", side_effect=api):
            result = research.research_topic("厄瑞波斯，希腊神明")
        self.assertEqual(result.title, "Erebus")
        self.assertEqual((result.category, result.subcategory),
                         ("Myths & Beliefs", "Greek Mythology"))
        self.assertEqual(len(result.suggestions), 4)
        self.assertTrue(all(not item.selected for item in result.suggestions))
        self.assertTrue(all(item.source_url == result.source_url for item in result.suggestions))
        self.assertEqual([item.title for item in result.images], ["FT nyx+erebus.png"])
        self.assertEqual(result.images[0].attribution, "Example Artist")
        self.assertEqual(result.error, "")

    def test_english_context_prefers_deity_over_volcano(self) -> None:
        def api(endpoint: str, params: dict) -> dict:
            if endpoint == research.EN_API and params.get("list") == "search":
                return {"query": {"search": [
                    {"title": "Mount Erebus"}, {"title": "Erebus"},
                ]}}
            if endpoint == research.EN_API and params.get("prop"):
                self.assertEqual(params["titles"], "Erebus")
                return {"query": {"pages": [EREBUS_PAGE]}}
            if endpoint == research.COMMONS_API:
                return {"query": {"pages": []}}
            self.fail(f"Unexpected API call: {endpoint} {params}")

        with patch.object(research, "_get_json", side_effect=api):
            result = research.research_topic("Erebus, a Greek god")
        self.assertEqual(result.title, "Erebus")
        self.assertEqual(result.suggestions[1].text,
                         "In Hesiod's Theogony, he is the offspring of Chaos.")

    def test_unavailable_service_preserves_input_without_facts(self) -> None:
        with patch.object(research, "_get_json", side_effect=research.ResearchError("Offline")):
            result = research.research_topic("猫")
        self.assertEqual(result.title, "猫")
        self.assertEqual(result.suggestions, [])
        self.assertEqual(result.images, [])
        self.assertEqual(result.error, "Offline")

    def test_commons_failure_keeps_english_suggestions(self) -> None:
        def api(endpoint: str, params: dict) -> dict:
            if params.get("list") == "search":
                return {"query": {"search": [{"title": "Erebus"}]}}
            if endpoint == research.EN_API:
                return {"query": {"pages": [EREBUS_PAGE]}}
            raise research.ResearchError("Commons unavailable")

        with patch.object(research, "_get_json", side_effect=api):
            result = research.research_topic("Erebus")
        self.assertEqual(len(result.suggestions), 4)
        self.assertEqual(result.images, [])
        self.assertEqual(result.error, "")

    def test_ambiguous_title_is_not_presented_as_a_fact(self) -> None:
        def api(endpoint: str, params: dict) -> dict:
            if params.get("list") == "search":
                return {"query": {"search": [{"title": "Mercury"}]}}
            return {"query": {"pages": [{"title": "Mercury", "pageprops": {
                "disambiguation": "",
            }}]}}

        with patch.object(research, "_get_json", side_effect=api):
            result = research.research_topic("Mercury")
        self.assertEqual(result.suggestions, [])
        self.assertIn("several meanings", result.error)


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = BytesIO(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        self.payload.close()

    def read(self, amount: int) -> bytes:
        return self.payload.read(amount)


class ImageDownloadTests(unittest.TestCase):
    def test_selected_image_is_saved_with_safe_name_and_bytes(self) -> None:
        image = research.ImageCandidate(
            title="Erebus: Nyx? tree.png",
            thumb_url="https://upload.wikimedia.org/wikipedia/commons/1/1a/erebus.png",
            image_url="https://upload.wikimedia.org/wikipedia/commons/1/1a/erebus.png",
            description_url="https://commons.wikimedia.org/wiki/File:Erebus.png",
            attribution="Artist", license="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
        )
        content = b"\x89PNG\r\n\x1a\n" + b"image data"
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(research, "urlopen", return_value=_FakeResponse(content)):
                saved = research.download_image(image, Path(temporary) / "images")
            self.assertEqual(saved.read_bytes(), content)
            self.assertEqual(saved.suffix, ".png")
            self.assertNotIn(":", saved.name)
            self.assertNotIn("?", saved.name)

    def test_image_download_rejects_other_hosts_and_mismatched_bytes(self) -> None:
        image = research.ImageCandidate(
            title="Erebus.png", thumb_url="", image_url="https://example.org/image.png",
            description_url="https://commons.wikimedia.org/wiki/File:Erebus.png",
            attribution="", license="CC BY 4.0", license_url="",
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                research.download_image(image, temporary)
            image = research.ImageCandidate(
                title=image.title, thumb_url=image.thumb_url,
                image_url="https://upload.wikimedia.org/wikipedia/commons/a/a1/image.png",
                description_url=image.description_url, attribution=image.attribution,
                license=image.license, license_url=image.license_url,
            )
            with patch.object(research, "urlopen", return_value=_FakeResponse(b"<html>no image</html>")):
                with self.assertRaises(ValueError):
                    research.download_image(image, temporary)
            self.assertEqual(list(Path(temporary).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
