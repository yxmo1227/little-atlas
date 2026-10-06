"""Text facts that can be painted with a selection, yellow, or red pen.

The three pens deliberately have different meanings. Only the selection pen
changes what will be saved; the other pens annotate text if it is later saved.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit, QWidget


PEN_MODES = ("select", "yellow", "red")
YELLOW = "#fff09a"
RED = "#b12c35"
SELECTED = "#e5f2ec"
SELECTED_LINE = "#387765"


class PaintableFact(QTextEdit):
    """Read-only source text with persistent, drag-painted character ranges.

    ``paint_range`` and ``selected_segments`` use Python string offsets, so
    callers can use ``text.index(...)`` even for text containing emoji. Qt
    cursor offsets are converted internally from UTF-16 positions.
    """

    selection_changed = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pen = "select"
        self._ranges: dict[str, list[tuple[int, int]]] = {mode: [] for mode in PEN_MODES}
        self._history: list[dict[str, list[tuple[int, int]]]] = []
        self.setObjectName("paintableFact")
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setFrameShape(QTextEdit.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setStyleSheet(
            "QTextEdit#paintableFact { background: transparent; border: 0; "
            "padding: 0; color: #24302b; selection-background-color: #9cbfb0; }"
        )
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.setPlainText(text)

    @property
    def pen(self) -> str:
        return self._pen

    @property
    def selection_ranges(self) -> tuple[tuple[int, int], ...]:
        return tuple(self._ranges["select"])

    def set_pen(self, mode: str) -> None:
        """Choose the pen used by the next mouse drag."""
        if mode not in PEN_MODES:
            raise ValueError(f"Unknown pen mode: {mode}")
        self._pen = mode

    def setPlainText(self, text: str) -> None:  # noqa: N802 - Qt method name
        """Replace the fact, clearing ranges tied to the old text."""
        had_selection = bool(self._ranges["select"])
        super().setPlainText(text)
        self._ranges = {mode: [] for mode in PEN_MODES}
        self._history.clear()
        if had_selection:
            self.selection_changed.emit()

    def set_text(self, text: str) -> None:
        self.setPlainText(text)

    def paint_range(self, start: int, end: int, mode: str) -> None:
        """Paint exactly ``text[start:end]`` with the given pen.

        Adjacent or overlapping strokes with the same pen become one range.
        An annotation stroke never adds text to the dictionary selection.
        """
        if mode not in PEN_MODES:
            raise ValueError(f"Unknown pen mode: {mode}")
        length = len(self.toPlainText())
        if not (0 <= start <= end <= length):
            raise ValueError(f"Invalid text range: {start}:{end} for length {length}")
        if start == end:
            return
        before = list(self._ranges[mode])
        updated = _merge_ranges(before + [(start, end)])
        if updated == before:
            return
        self._history.append({pen: list(ranges) for pen, ranges in self._ranges.items()})
        self._ranges[mode] = updated
        self._refresh_formats()
        if mode == "select":
            self.selection_changed.emit()

    def undo_last_stroke(self) -> bool:
        """Remove the most recent effective pen stroke; return whether one existed."""
        if not self._history:
            return False
        old_selection = self._ranges["select"]
        self._ranges = self._history.pop()
        self._refresh_formats()
        if old_selection != self._ranges["select"]:
            self.selection_changed.emit()
        return True

    def selected_segments(self) -> list[tuple[str, str]]:
        """Return exact selected substrings and safe HTML for each span.

        Yellow and red annotations are included only where they intersect a
        selected span. Plain text is never included merely because it was
        painted yellow or red.
        """
        source = self.toPlainText()
        segments: list[tuple[str, str]] = []
        for start, end in self._ranges["select"]:
            boundaries = {start, end}
            for mode in ("yellow", "red"):
                for mark_start, mark_end in self._ranges[mode]:
                    if start < mark_start < end:
                        boundaries.add(mark_start)
                    if start < mark_end < end:
                        boundaries.add(mark_end)
            cuts = sorted(boundaries)
            html_parts: list[str] = []
            for left, right in zip(cuts, cuts[1:]):
                if left == right:
                    continue
                content = _escape_fragment(source[left:right])
                styles: list[str] = []
                if _contains(self._ranges["yellow"], left):
                    styles.append(f"background-color: {YELLOW}")
                if _contains(self._ranges["red"], left):
                    styles.extend((f"color: {RED}", "text-decoration: underline"))
                if styles:
                    content = f'<span style="{"; ".join(styles)}">{content}</span>'
                html_parts.append(content)
            segments.append((source[start:end], "".join(html_parts)))
        return segments

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt method name
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        start = _qt_to_python(self.toPlainText(), cursor.selectionStart())
        end = _qt_to_python(self.toPlainText(), cursor.selectionEnd())
        # Remove Qt's temporary blue highlight; persistent pen marks remain.
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.paint_range(start, end, self._pen)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt method name
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo_last_stroke()
            event.accept()
            return
        super().keyPressEvent(event)

    def _refresh_formats(self) -> None:
        text = self.toPlainText()
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.setCharFormat(QTextCharFormat())

        boundaries = {0, len(text)}
        for ranges in self._ranges.values():
            for start, end in ranges:
                boundaries.update((start, end))
        cuts = sorted(boundaries)
        for start, end in zip(cuts, cuts[1:]):
            if start == end:
                continue
            selected = _contains(self._ranges["select"], start)
            yellow = _contains(self._ranges["yellow"], start)
            red = _contains(self._ranges["red"], start)
            if not (selected or yellow or red):
                continue
            fmt = QTextCharFormat()
            if selected:
                fmt.setBackground(QColor(SELECTED))
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
                fmt.setUnderlineColor(QColor(SELECTED_LINE))
                fmt.setFontWeight(QFont.Weight.DemiBold)
            if yellow:
                fmt.setBackground(QColor(YELLOW))
            if red:
                fmt.setForeground(QColor(RED))
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
                fmt.setUnderlineColor(QColor(RED))
            cursor.setPosition(_python_to_qt(text, start))
            cursor.setPosition(_python_to_qt(text, end), QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(fmt)


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _contains(ranges: list[tuple[int, int]], offset: int) -> bool:
    return any(start <= offset < end for start, end in ranges)


def _escape_fragment(text: str) -> str:
    return escape(text).replace(" ", "&#160;").replace("\n", "<br>")


def _python_to_qt(text: str, offset: int) -> int:
    return len(text[:offset].encode("utf-16-le")) // 2


def _qt_to_python(text: str, offset: int) -> int:
    if offset <= 0:
        return 0
    utf16_units = 0
    for index, character in enumerate(text):
        utf16_units += 2 if ord(character) > 0xFFFF else 1
        if utf16_units >= offset:
            return index + 1
    return len(text)
