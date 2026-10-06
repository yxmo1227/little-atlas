"""A real Qt journey from unselected research to a saved, marked article."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from dictionary_app.app import MainWindow
from dictionary_app.research import ResearchResult, Suggestion
from dictionary_app.storage import DictionaryStore, Entry


class AppJourneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = DictionaryStore(Path(self.temp.name) / "private.sqlite3")
        with patch("dictionary_app.app.DictionaryStore", return_value=self.store):
            self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.temp.cleanup()

    def test_user_controls_english_facts_and_can_mark_saved_page(self) -> None:
        self.assertEqual(self.store.list_entries(), [])
        self.window.topic_input.setPlainText("厄瑞波斯，希腊神明")
        source = "https://en.wikipedia.org/wiki/Erebus"
        self.window._research_ready(ResearchResult(
            title="Erebus", category="Myths & Beliefs", subcategory="Greek Mythology",
            source_url=source,
            suggestions=[
                Suggestion("Overview", "Erebus is a primordial deity in Greek mythology.", source),
                Suggestion("Family", "He is associated with darkness.", source),
            ],
        ))
        self.assertEqual(self.store.list_entries(), [])
        self.assertEqual([fact.selection_ranges for fact, _ in self.window.fact_widgets], [(), ()])
        first = self.window.fact_widgets[0][0]
        start = first.toPlainText().index("primordial deity")
        first.paint_range(start, start + len("primordial deity"), "select")
        first.paint_range(start, start + len("primordial"), "yellow")
        self.window.fact_widgets[1][0].paint_range(0, 2, "red")
        self.window._accept_results()

        entries = self.store.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Erebus")
        self.assertEqual(entries[0].category, "Myths & Beliefs")
        self.assertEqual(entries[0].original_input, "厄瑞波斯，希腊神明")
        self.assertIn("厄瑞波斯", self.window.original_note.text())
        self.assertIn("primordial", entries[0].body_html)
        self.assertIn("deity", entries[0].body_html)
        self.assertIn("#fff09a", entries[0].body_html.lower())
        self.assertNotIn("Erebus is a", entries[0].body_html)
        self.assertNotIn("associated with darkness", entries[0].body_html)
        self.assertEqual(self.window.catalog.topLevelItemCount(), 1)

        cursor = self.window.article_editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Right,
                            QTextCursor.MoveMode.KeepAnchor, len("Erebus"))
        self.window.article_editor.setTextCursor(cursor)
        self.window._mark_text("yellow")
        self.assertIn("#fff09a", self.store.get_entry(entries[0].id).body_html.lower())

        self.window.target_entry_id = entries[0].id
        self.window._research_ready(ResearchResult(
            title="Erebus", category="Myths & Beliefs", subcategory="Greek Mythology",
            source_url=source,
            suggestions=[Suggestion("Family", "He is associated with darkness.", source)],
        ))
        second = self.window.fact_widgets[0][0]
        second.paint_range(0, len(second.toPlainText()), "select")
        self.window._accept_results()
        updated = self.store.get_entry(entries[0].id)
        article = QTextDocument()
        article.setHtml(updated.body_html)
        plain = article.toPlainText().replace("\u00a0", " ")
        self.assertIn("primordial deity", plain)
        self.assertIn("associated with darkness", plain)
        self.assertEqual(len(self.store.list_entries()), 1)

    def test_english_personal_observation_can_be_saved_without_suggestion(self) -> None:
        own_note = "I learned that octopuses have three hearts."
        self.window.topic_input.setPlainText(own_note)
        self.window._research_ready(ResearchResult(
            title="Octopus", category="Nature & Life", subcategory="Animals",
            source_url="https://en.wikipedia.org/wiki/Octopus",
            suggestions=[Suggestion("Overview", "Octopuses are molluscs.",
                                    "https://en.wikipedia.org/wiki/Octopus")],
        ))
        self.assertEqual(self.window.english_note_input.toPlainText(), "")
        self.window.english_note_input.setPlainText(own_note)
        self.window._accept_results()
        saved = self.store.list_entries()[0]
        self.assertIn(own_note, saved.body_html)
        self.assertNotIn("Octopuses are molluscs", saved.body_html)

    def test_signed_in_search_uses_sourced_ai_and_falls_back_when_unavailable(self) -> None:
        source = "https://example.org/saline"
        ai = ResearchResult("Saline", "Human Body & Health", "Medicine", source,
                            [Suggestion("Overview", "Saline contains salt and water.", source)])
        wiki = ResearchResult("Saline (medicine)", "Human Body & Health", "Medicine", source,
                              [Suggestion("Overview", "Saline is used in medicine.", source)])
        self.window.chatgpt = Mock()
        self.window.chatgpt.access_token.return_value = "test-token"

        def complete(action, on_result, _on_error=None):
            on_result(action())

        with patch.object(self.window, "_run_job", side_effect=complete), \
             patch("dictionary_app.app.research_topic_ai", return_value=ai) as search_ai, \
             patch("dictionary_app.app.research_topic", return_value=wiki) as search_wiki:
            self.window._start_lookup("生理盐水", "", prefer_ai=True)
            self.assertEqual(self.window.result.title, "Saline")
            self.assertEqual(search_ai.call_args.args[:2], ("test-token", "生理盐水"))
            search_wiki.assert_not_called()

        unavailable = ResearchResult("", "Unsorted", "General", "", error="Web search unavailable")
        with patch.object(self.window, "_run_job", side_effect=complete), \
             patch("dictionary_app.app.research_topic_ai", return_value=unavailable), \
             patch("dictionary_app.app.research_topic", return_value=wiki) as search_wiki:
            self.window._start_lookup("生理盐水", "", prefer_ai=True)
            self.assertEqual(self.window.result.title, "Saline (medicine)")
            self.assertIn("Wikimedia", self.window.status.text())
            search_wiki.assert_called_once()

    def test_home_is_compact_and_catalog_opens_only_on_demand(self) -> None:
        self.assertTrue(self.window.sidebar.isHidden())
        self.assertGreaterEqual(self.window.input_shell.width(), 720)
        self.assertGreaterEqual(self.window.topic_input.height(), 100)
        self.assertLessEqual(self.window.height(), 260)
        self.assertLessEqual(self.window.width(), 800)
        self.assertEqual(self.window.mic_button.text(), "")
        self.assertEqual(self.window.explore_button.text(), "")
        self.assertEqual(self.window.plus_button.text(), "")
        self.assertFalse(hasattr(self.window, "style_select"))
        self.assertFalse(hasattr(self.window, "menu_button"))
        self.window._toggle_menu()
        self.assertFalse(self.window.sidebar.isHidden())
        self.assertEqual(self.window.sidebar.layout().itemAt(0).layout().itemAt(0).widget().text(), "Contents")
        self.window._close_menu()
        self.assertTrue(self.window.sidebar.isHidden())

    def test_default_search_opens_google_and_uses_no_chatgpt_tokens(self) -> None:
        source = "https://en.wikipedia.org/wiki/Erebus"
        free = ResearchResult("Erebus", "Myths & Beliefs", "Greek Mythology", source,
                              [Suggestion("Overview", "Erebus is a Greek deity.", source)])
        self.window.topic_input.setPlainText("厄瑞波斯")

        def complete(action, on_result, _on_error=None):
            on_result(action())

        with patch.object(self.window, "_run_job", side_effect=complete), \
             patch("dictionary_app.app.QDesktopServices.openUrl", return_value=True) as browser, \
             patch("dictionary_app.app.research_topic", return_value=free) as public_search, \
             patch("dictionary_app.app.research_topic_ai") as paid_search:
            self.window._explore()
            self.assertEqual(self.window.result.title, "Erebus")
            self.assertGreaterEqual(self.window.height(), 650)
            self.assertIn("google.com/search", browser.call_args.args[0].toString())
            public_search.assert_called_once()
            paid_search.assert_not_called()

    def test_https_article_import_skips_google(self) -> None:
        url = "https://example.org/article"
        page = ResearchResult("Article", "Unsorted", "General", url,
                              [Suggestion("Paragraph", "An English article fact.", url)])
        self.window.topic_input.setPlainText(url)

        def complete(action, on_result, _on_error=None):
            on_result(action())

        with patch.object(self.window, "_run_job", side_effect=complete), \
             patch("dictionary_app.app.QDesktopServices.openUrl") as browser, \
             patch("dictionary_app.app.research_webpage", return_value=page) as import_page:
            self.window._explore()
            self.assertEqual(self.window.result.title, "Article")
            browser.assert_not_called()
            import_page.assert_called_once_with(url)

    def test_enter_searches_and_shift_enter_stays_in_the_composer(self) -> None:
        with patch.object(self.window, "_explore") as explore:
            self.window.topic_input.submitted.disconnect()
            self.window.topic_input.submitted.connect(explore)
            QTest.keyClick(self.window.topic_input, Qt.Key.Key_Return,
                           Qt.KeyboardModifier.ShiftModifier)
            self.assertIn("\n", self.window.topic_input.toPlainText())
            QTest.keyClick(self.window.topic_input, Qt.Key.Key_Return)
            explore.assert_called_once()

    def test_deleting_one_entry_keeps_an_image_used_by_another(self) -> None:
        first = self.store.upsert_entry(Entry(title="First", category="Unsorted", body_html="<p>First.</p>"))
        second = self.store.upsert_entry(Entry(title="Second", category="Unsorted", body_html="<p>Second.</p>"))
        image = self.store.images_dir / "shared.png"
        image.write_bytes(b"image bytes")
        self.store.add_image(first.id, image)
        self.store.add_image(second.id, image)
        self.window._open_entry(first.id)
        with patch("dictionary_app.app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.window._delete_entry()
        self.assertIsNone(self.store.get_entry(first.id))
        self.assertTrue(image.exists())
        self.assertEqual(len(self.store.list_images(second.id)), 1)


if __name__ == "__main__":
    unittest.main()
