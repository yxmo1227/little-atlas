"""No-network tests for source-checked ChatGPT research."""

from __future__ import annotations

from io import BytesIO
import json
import unittest
from unittest.mock import patch

from dictionary_app import ai_research


SOURCE = "https://example.org/knowledge/saline"


def _completed(*, web: bool = True, source: str = SOURCE) -> dict:
    facts = [{"text": "Saline is a solution of sodium chloride in water.",
              "source_url": source},
             {"text": "Sterile saline has several clinical uses.",
              "source_url": source}]
    output = []
    if web:
        output.append({"type": "web_search_call", "status": "completed",
                       "action": {"type": "search", "sources": [{"url": SOURCE}]}})
    output.append({"type": "message", "content": [{
        "type": "output_text",
        "text": json.dumps({"title": "Saline", "category": "Human Body & Health",
                            "subcategory": "Body & Medicine", "facts": facts}),
        "annotations": [{"type": "url_citation", "url": SOURCE}],
    }]})
    return {"output": output}


class AIResearchTests(unittest.TestCase):
    def test_source_checked_result_and_no_auto_selection(self) -> None:
        with patch.object(ai_research, "_images", return_value=[]):
            result = ai_research._parse_completed(_completed(), "")
        self.assertEqual(result.title, "Saline")
        self.assertEqual(result.category, "Human Body & Health")
        self.assertEqual(len(result.suggestions), 2)
        self.assertEqual(result.suggestions[0].source_url, SOURCE)
        self.assertFalse(result.suggestions[0].selected)

    def test_rejects_forged_source_even_if_model_lists_it(self) -> None:
        with patch.object(ai_research, "_images", return_value=[]):
            with self.assertRaisesRegex(ai_research.AIResearchError, "verifiable web sources"):
                ai_research._parse_completed(
                    _completed(source="https://fake.example/claim"), "")

    def test_requires_actual_web_search_call(self) -> None:
        with self.assertRaisesRegex(ai_research.AIResearchError, "did not perform web search"):
            ai_research._parse_completed(_completed(web=False), "")

    def test_sse_needs_completed_terminal_event(self) -> None:
        delta = b'data: {"type":"response.output_text.delta","delta":"hello"}\n\n'
        with self.assertRaisesRegex(ai_research.AIResearchError, "without completion"):
            ai_research._read_sse(BytesIO(delta))
        terminal = (b'data: {"type":"response.completed","response":{"output":[]}}\n\n'
                    b'data: [DONE]\n\n')
        self.assertEqual(ai_research._read_sse(BytesIO(terminal)), {"output": []})

    def test_request_uses_web_search_and_privacy_fields(self) -> None:
        complete = {"type": "response.completed", "response": _completed()}
        stream = BytesIO(("data: " + json.dumps(complete) + "\n\n").encode("utf-8"))
        requests = []

        class FakeResponse:
            def __enter__(self):
                return stream

            def __exit__(self, *_args):
                pass

        def fake_open(request, **_kwargs):
            requests.append(request)
            return FakeResponse()

        with patch.object(ai_research, "urlopen", side_effect=fake_open):
            result = ai_research._responses_call("token-not-logged", "gpt-test", "盐水", "")
        self.assertEqual(result, _completed())
        body = json.loads(requests[0].data)
        self.assertIs(body["store"], False)
        self.assertIs(body["stream"], True)
        self.assertEqual(body["tools"], [{"type": "web_search"}])
        self.assertEqual(body["include"], ["web_search_call.action.sources"])
        self.assertNotIn("token-not-logged", json.dumps(body))

    def test_public_entry_reports_fallback_error(self) -> None:
        with (patch.object(ai_research, "_models", return_value=["gpt-test"]),
              patch.object(ai_research, "_responses_call", side_effect=ai_research.AIResearchError(
                  "This ChatGPT model or account cannot use web search."))):
            result = ai_research.research_topic_ai("test-token", "盐水")
        self.assertIn("cannot use web search", result.error)
        self.assertEqual(result.suggestions, [])


if __name__ == "__main__":
    unittest.main()
