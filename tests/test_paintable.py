"""Pen selection must remain exact and separate from decorative annotation."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from dictionary_app.paintable import PaintableFact


class PaintableFactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_only_exact_selected_text_is_returned(self) -> None:
        fact = PaintableFact("Alpha beta gamma.")
        spy = QSignalSpy(fact.selection_changed)
        fact.paint_range(6, 10, "select")
        self.assertEqual(fact.selection_ranges, ((6, 10),))
        self.assertEqual(fact.selected_segments(), [("beta", "beta")])
        self.assertEqual(spy.count(), 1)

    def test_disjoint_strokes_survive_and_overlaps_merge(self) -> None:
        fact = PaintableFact("Alpha beta gamma delta")
        fact.paint_range(0, 5, "select")
        fact.paint_range(11, 16, "select")
        self.assertEqual([text for text, _ in fact.selected_segments()], ["Alpha", "gamma"])
        fact.paint_range(3, 12, "select")
        self.assertEqual(fact.selection_ranges, ((0, 16),))
        self.assertEqual(fact.selected_segments()[0][0], "Alpha beta gamma")

    def test_yellow_and_red_persist_only_inside_selected_spans(self) -> None:
        fact = PaintableFact("Alpha beta gamma.")
        fact.paint_range(0, 5, "select")
        fact.paint_range(11, 16, "select")
        fact.paint_range(2, 13, "yellow")
        fact.paint_range(12, 16, "red")
        segments = fact.selected_segments()
        self.assertEqual([text for text, _ in segments], ["Alpha", "gamma"])
        self.assertIn("Al<span style=\"background-color: #fff09a\">pha</span>", segments[0][1])
        self.assertIn("background-color: #fff09a", segments[1][1])
        self.assertIn("color: #b12c35", segments[1][1])
        self.assertNotIn("beta", "".join(html for _, html in segments))

    def test_annotation_alone_does_not_select_and_repainting_is_stable(self) -> None:
        fact = PaintableFact("A < B & C")
        fact.paint_range(0, 9, "yellow")
        self.assertEqual(fact.selected_segments(), [])
        fact.paint_range(0, 9, "select")
        fact.paint_range(0, 9, "yellow")
        fact.paint_range(2, 7, "red")
        self.assertEqual(fact.selection_ranges, ((0, 9),))
        plain, html = fact.selected_segments()[0]
        self.assertEqual(plain, "A < B & C")
        self.assertIn("&lt;", html)
        self.assertIn("&amp;", html)
        self.assertEqual(html.count("#b12c35"), 1)
        fact.set_text("New fact")
        self.assertEqual(fact.selected_segments(), [])

    def test_unicode_offsets_follow_python_string_indices(self) -> None:
        fact = PaintableFact("夜🌙 and stars")
        fact.paint_range(1, 2, "select")
        self.assertEqual(fact.selected_segments()[0][0], "🌙")
        self.assertEqual(fact.selection_ranges, ((1, 2),))

    def test_mouse_drag_uses_the_active_pen(self) -> None:
        fact = PaintableFact("Alpha beta gamma")
        fact.resize(480, 70)
        fact.show()
        self.app.processEvents()
        cursor = QTextCursor(fact.document())
        cursor.setPosition(6)
        start = fact.cursorRect(cursor).center()
        cursor.setPosition(10)
        end = fact.cursorRect(cursor).center()
        fact.set_pen("select")
        QTest.mousePress(fact.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(fact.viewport(), end)
        QTest.mouseRelease(fact.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(fact.selected_segments()[0][0], "beta")
        fact.close()

    def test_drag_from_first_character_keeps_first_character(self) -> None:
        fact = PaintableFact("Alpha beta")
        fact.resize(480, 70)
        fact.show()
        self.app.processEvents()
        cursor = QTextCursor(fact.document())
        cursor.setPosition(0)
        start = fact.cursorRect(cursor).center()
        cursor.setPosition(5)
        end = fact.cursorRect(cursor).center()
        QTest.mousePress(fact.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(fact.viewport(), end)
        QTest.mouseRelease(fact.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertEqual(fact.selected_segments()[0][0], "Alpha")
        fact.close()

    def test_undo_restores_selection_and_annotations_in_stroke_order(self) -> None:
        fact = PaintableFact("Alpha beta")
        spy = QSignalSpy(fact.selection_changed)
        fact.paint_range(0, 5, "select")
        fact.paint_range(1, 4, "yellow")
        fact.paint_range(2, 5, "red")
        self.assertIn("#fff09a", fact.selected_segments()[0][1])
        self.assertIn("#b12c35", fact.selected_segments()[0][1])
        self.assertTrue(fact.undo_last_stroke())
        self.assertNotIn("#b12c35", fact.selected_segments()[0][1])
        self.assertTrue(fact.undo_last_stroke())
        self.assertNotIn("#fff09a", fact.selected_segments()[0][1])
        self.assertTrue(fact.undo_last_stroke())
        self.assertEqual(fact.selected_segments(), [])
        self.assertFalse(fact.undo_last_stroke())
        self.assertEqual(spy.count(), 2)

    def test_ctrl_z_undoes_last_paint_stroke(self) -> None:
        fact = PaintableFact("Alpha beta")
        fact.paint_range(0, 5, "select")
        fact.show()
        fact.setFocus()
        QTest.keyClick(fact, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(fact.selected_segments(), [])
        fact.close()


if __name__ == "__main__":
    unittest.main()
